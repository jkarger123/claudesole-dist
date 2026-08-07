#!/usr/bin/env python3
"""cc-session-watchdog -- keep Claude Code sessions moving through API OUTAGES.

The Claude Code main loop retries the API client-side, then GIVES UP and the turn ends with an error,
sitting idle until a human pokes it. This watchdog is that poke: it watches opted-in tmux sessions and,
when one is IDLE and STALLED ON AN API ERROR, it `tmux send-keys` a "continue" nudge -- repeatedly, with a
cooldown -- so the work resumes the moment the API outage clears. Stdlib only; one pass per invocation
(run it from launchd StartInterval, ~45s).

SAFETY (must not nudge a healthy session that merely MENTIONS an error, e.g. a chat discussing API errors):
  - opt-in: only sessions in the watchlist are ever touched.
  - the error must be a TRAILING ERROR *LINE* near the prompt (regex-anchored), not prose containing the words.
  - the session must be IDLE (no "esc to interrupt" -> not mid-retry/working).
  - the error must PERSIST across two consecutive checks (a transient that self-heals is left alone).
  - cooldown between nudges (default 150s) so we don't spam while the API is still down.

Usage:
  cc-session-watchdog.py run [--all] [--dry]   # one pass (default). --all watches every Claude session.
  cc-session-watchdog.py watch <session>...     # add sessions to the watchlist
  cc-session-watchdog.py unwatch <session>...
  cc-session-watchdog.py list                   # show watchlist + state
"""
import calendar, glob, json, os, re, subprocess, sys, time

TMUX = os.environ.get("CC_TMUX") or "/opt/homebrew/bin/tmux"
os.environ.setdefault("TMUX_TMPDIR", "/tmp")
STATE_FILE = os.path.expanduser("~/.cc-watchdog.json")
LOG = "/tmp/cc-watchdog.log"
COOLDOWN = 150            # seconds between nudges to the same session
NUDGE = "Please continue where you left off -- an API error interrupted you; resume the task."
# Out-of-process chief revival: each node server drops a launch descriptor here (see chief_open in server.py).
CHIEF_LAUNCH_DIR = "/tmp/cf-chief-launch"
CHIEF_REVIVE_COOLDOWN = 120   # seconds between revive attempts for the same chief (anti-thrash)
# Resume-on-revive: a chief's Claude Code transcript is ~/.claude/projects/<cwd-slug>/<session-id>.jsonl.
CLAUDE_PROJECTS = os.path.expanduser("~/.claude/projects")
RESUME_TOL = 300              # sec: first-record within 5min of tmux session start = confident match (matches server.py)

# A line is an ERROR line only if it is *predominantly* an API/transport error near the start of the line
# (optionally prefixed by Claude Code's box/glyph chars). This is what distinguishes a real stall from
# prose that merely contains the words "api error".
ERR_LINE = re.compile(
    r"^[\s>│|⎿╰╭✗✘×⚠!•⏺✻●◉◯·\-\*]*"   # allow Claude Code line glyphs (⏺ ✻ ⎿ etc.) as a prefix
    r"(api error|overloaded(_error)?|internal server error|service[ _]unavailable|"
    r"request timed out|request failed|connection (error|closed|reset)|econnreset|"
    r"stream (idle )?timeout|stream error|fetch failed|rate[ _]?limit(ed|_error)?|"
    r"server is temporarily limiting|temporarily limiting requests|"
    r"(5\d\d)\b|too many requests|upstream connect error)",
    re.I,
)

def sh(args, timeout=10):
    try: return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except Exception: return None

def tmux_sessions():
    r = sh([TMUX, "list-sessions", "-F", "#{session_name}"])
    return r.stdout.split() if r and r.returncode == 0 else []

def pane(s):
    r = sh([TMUX, "capture-pane", "-t", s, "-p"])
    return r.stdout if r and r.returncode == 0 else ""

def is_claude(txt):
    low = txt.lower()
    return ("esc to interrupt" in low) or ("? for shortcuts" in low) or ("/help for" in low) or ("✻" in txt) or ("context left" in low)

def is_busy(txt):
    # "esc to interrupt" is the classic working flag; also treat an ACTIVE spinner with an elapsing timer as
    # busy ("Actioning… (32s · thinking)") -- but NOT a past-tense "Worked for 39s" (that's a finished turn).
    if "esc to interrupt" in txt.lower(): return True
    for ln in txt.splitlines()[-5:]:
        if re.search(r"…\s*\(\d+\s*s\b", ln): return True
    return False

def has_feedback(txt):
    low = txt.lower()
    return "how is claude doing this session" in low or "0: dismiss" in low

def is_stalled_on_error(txt):
    """Idle AND an error line anywhere in the last ~15 non-empty lines (the error can be pushed ABOVE a
    feedback prompt / input box when a turn dies -- so a tiny tail window misses it)."""
    if is_busy(txt): return False
    lines = [ln for ln in txt.splitlines() if ln.strip()]
    return any(ERR_LINE.match(ln) for ln in lines[-15:])

_COMPACT_LOCK_DIR = "/tmp/cf-compact-locks"
def is_compacting(s):
    """True while a graceful auto-compact is driving this session's input box -- defer to it (same shared
    coordination signal auto-nudge + _mesh_deliver use), so an API error mid-compact doesn't fight the /compact."""
    try:
        p = os.path.join(_COMPACT_LOCK_DIR, s + ".lock")
        if not os.path.isfile(p): return False
        return (json.load(open(p)).get("state") or "") == "running"
    except Exception:
        return False

def load():
    try: return json.load(open(STATE_FILE))
    except Exception: return {"watch": [], "state": {}}

def save(d):
    try: json.dump(d, open(STATE_FILE, "w"), indent=2)
    except Exception: pass

def logline(msg):
    try:
        with open(LOG, "a") as f: f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except Exception: pass

def nudge(s):
    txt = pane(s)
    if has_feedback(txt):                                 # the "How is Claude doing?" overlay eats input -> dismiss it first
        sh([TMUX, "send-keys", "-t", s, "0"]); time.sleep(0.6)
    sh([TMUX, "send-keys", "-t", s, "-l", NUDGE]); time.sleep(0.4)
    sh([TMUX, "send-keys", "-t", s, "Enter"]); time.sleep(0.6)
    sh([TMUX, "send-keys", "-t", s, "Enter"])             # second Enter flushes a message left queued behind a rate-limit backoff

def _cwd_slug(cwd):
    # Claude Code keys a transcript dir by the cwd's REALPATH (e.g. /var/... -> /private/var/... on macOS),
    # so resolve symlinks before slugifying or the projects dir never matches.
    try: cwd = os.path.realpath(cwd)
    except Exception: pass
    return re.sub(r"[^A-Za-z0-9]", "-", cwd)

def _transcript_path(cwd, sid):
    return os.path.join(CLAUDE_PROJECTS, _cwd_slug(cwd), (sid or "") + ".jsonl")

def _tmux_session_created(sess):
    """UTC epoch when THIS tmux session was created (== when its `claude` launched). None if the session is gone."""
    r = sh([TMUX, "display-message", "-p", "-t", sess, "#{session_created}"])
    if r and r.returncode == 0:
        o = (r.stdout or "").strip()
        if o.isdigit(): return int(o)
    return None

def _jsonl_first_epoch(path):
    """UTC epoch of a transcript's FIRST record (timegm -> the 'Z' string is UTC; matches os/tmux epochs)."""
    try:
        with open(path, "rb") as f:
            for _ in range(60):
                ln = f.readline()
                if not ln: break
                try:
                    o = json.loads(ln); t = o.get("timestamp")
                    if t: return calendar.timegm(time.strptime(str(t)[:19], "%Y-%m-%dT%H:%M:%S"))
                except Exception: continue
    except Exception: pass
    return None

def _resolve_sid(cwd, created):
    """The session-id whose transcript was CREATED when this tmux session launched. A chief cwd (esp. the CC
    root) holds MANY .jsonl (every past Chief + every headless `claude -p` run), so 'newest mtime' is a coin
    flip and picks the WRONG one -- mirror server.py's PRIMARY match instead: the transcript whose FIRST-record
    timestamp best lines up with the tmux session's creation time (each tmux session writes ONE transcript from
    launch). Return None (-> caller COLD-launches) when there's no confident match: resuming a guessed wrong
    transcript is worse than a clean cold start."""
    if not created: return None
    d = os.path.join(CLAUDE_PROJECTS, _cwd_slug(cwd))
    if not os.path.isdir(d): return None
    best, bestd = None, None
    for j in glob.glob(os.path.join(d, "*.jsonl")):
        fe = _jsonl_first_epoch(j)
        if fe is None: continue
        dd = abs(fe - created)
        if bestd is None or dd < bestd: bestd, best = dd, j
    if best is not None and bestd is not None and bestd <= RESUME_TOL:
        return os.path.basename(best)[:-6]               # strip ".jsonl" -> the session-id
    return None

def _resume_cl(cl, sid):
    """Rewrite a chief COLD launch command into a RESUME of `sid`: inject `--resume <sid>` right after the
    `claude` token and DROP the trailing prompt arg (`"$(cat _chief_prompt.txt)"`) -- otherwise --resume would
    replay 'You are my Chief of Staff...' as a fresh user message on top of the restored history. Every other
    flag (--model/--append-system-prompt/--settings/--mcp-config/--dangerously-skip-permissions) + the env
    exports are preserved verbatim. Returns None if the command isn't shaped as expected (-> cold fallback)."""
    anchor = "claude --dangerously-skip-permissions"
    if anchor not in cl: return None
    new = cl.replace(anchor, "claude --resume %s --dangerously-skip-permissions" % sid, 1)
    new2 = re.sub(r'\s*"\$\(cat [^"]*\)"\s*$', "", new)  # strip the trailing "$(cat <promptfile>)" positional
    if new2 == new: return None                          # prompt arg not found where expected -> don't risk it
    return new2

def revive_chiefs(d, live, dry=False):
    """Recreate any chief whose tmux session is gone, from the launch descriptor its server left in
    CHIEF_LAUNCH_DIR. This runs in the launchd watchdog -- INDEPENDENT of any node server.py -- so a chief is
    revived even when its server is down/crash-looping (the server's own in-process watchdog dies with it).
    Cooldown-guarded so a chief that keeps dying can't be respawned in a tight loop.

    RESUME-ON-REVIVE: a cold revive brought the chief back with a blank 'you are my chief of staff' intro,
    destroying the operator's session + context on every unattended fleet restart. So while a chief is ALIVE we
    cache the session-id of its live transcript (resolved by session-start match, which is only accurate while
    the session exists); when it later dies we relaunch `claude --resume <sid>` to restore that exact history.
    Falls back to the original cold launch whenever we have no confident transcript (a never-seen chief, a
    missing transcript, or an unexpected command shape)."""
    cs = d.setdefault("chief_revive", {})
    tx = d.setdefault("chief_tx", {})                    # sess -> {sid, cwd, created, ts}: the resume target, cached while alive
    now = time.time(); acted = []
    for f in sorted(glob.glob(os.path.join(CHIEF_LAUNCH_DIR, "*.json"))):
        try: desc = json.load(open(f))
        except Exception: continue
        sess = desc.get("session"); cl = desc.get("cl"); cwd = desc.get("cwd") or os.path.expanduser("~")
        if not sess or not cl: continue

        if sess in live:
            # ALIVE: keep the resume target fresh. Re-resolve only when the cache is stale -- the tmux session was
            # recreated (session_created changed) or its transcript vanished -- so the O(N-transcripts) scan runs
            # ~once per session lifetime, not every 45s pass.
            created = _tmux_session_created(sess)
            rec = tx.get(sess) or {}
            fileok = rec.get("sid") and os.path.isfile(_transcript_path(cwd, rec.get("sid")))
            if not (fileok and rec.get("created") == created):
                nsid = _resolve_sid(cwd, created)
                if nsid:
                    tx[sess] = {"sid": nsid, "cwd": cwd, "created": created, "ts": now}
                elif fileok:
                    rec["created"] = created; rec["ts"] = now; tx[sess] = rec   # a resumed transcript's first record is old (won't re-match); keep the sid, sync created
                else:
                    tx.pop(sess, None)                   # no confident target -> revive will cold-launch
            continue

        # DEAD: revive.
        if now - cs.get(sess, 0) < CHIEF_REVIVE_COOLDOWN: continue  # cooldown
        rec = tx.get(sess) or {}; sid = rec.get("sid")
        launch, mode = cl, "cold"
        if sid and os.path.isfile(_transcript_path(cwd, sid)):
            rcl = _resume_cl(cl, sid)
            if rcl: launch, mode = rcl, "resume"
        tag = mode + (("=" + sid) if mode == "resume" else "")
        if dry: acted.append("WOULD-REVIVE %s [%s]" % (sess, tag)); continue
        r = sh([TMUX, "new-session", "-d", "-s", sess, "-c", cwd, launch]); cs[sess] = now
        ok = bool(r) and r.returncode == 0
        if ok and mode == "resume":
            tx[sess] = {"sid": sid, "cwd": cwd, "created": rec.get("created"), "ts": now}   # preserve target across the bounce
        acted.append("revived %s [%s]%s" % (sess, tag, "" if ok else " (FAILED)"))
        logline("out-of-process revive of chief %s [%s]%s" % (sess, tag, "" if ok else " FAILED"))
    for s in list(cs):                                             # forget chiefs whose descriptor is gone
        if not os.path.isfile(os.path.join(CHIEF_LAUNCH_DIR, s + ".json")): del cs[s]
    for s in list(tx):
        if not os.path.isfile(os.path.join(CHIEF_LAUNCH_DIR, s + ".json")): del tx[s]
    return acted

def cmd_run(watch_all=False, dry=False):
    d = load(); st = d.setdefault("state", {}); watch = set(d.get("watch", []))
    live = tmux_sessions()
    chief_acted = revive_chiefs(d, live, dry=dry)
    targets = [s for s in live if is_claude(pane(s))] if watch_all else [s for s in watch if s in live]
    now = time.time(); acted = []
    for s in targets:
        txt = pane(s)
        cur = st.get(s, {})
        stalled = is_stalled_on_error(txt)
        if stalled and is_compacting(s):        # a graceful auto-compact owns the box -> let it finish, don't nudge
            cur["err"] = True; st[s] = cur; continue
        if stalled:
            # require it was ALSO stalled last pass (persistence) + cooldown elapsed
            if cur.get("err") and (now - cur.get("nudge", 0) > COOLDOWN):
                if dry:
                    acted.append("WOULD-NUDGE " + s)
                else:
                    nudge(s); cur["nudge"] = now; cur["count"] = cur.get("count", 0) + 1
                    acted.append("nudged " + s + " (#%d)" % cur["count"])
            cur["err"] = True
        else:
            cur["err"] = False
        st[s] = cur
    for s in list(st):                          # prune sessions that vanished
        if s not in live: del st[s]
    if not dry: save(d)
    all_acted = chief_acted + acted
    if all_acted: logline("; ".join(all_acted))
    print("watchdog: targets=%d chiefs=%s %s" % (len(targets), (len(chief_acted) or "ok"),
          ("[dry] " if dry else "") + ("; ".join(all_acted) if all_acted else "nothing to do")))

def cmd_watch(names, add=True):
    d = load(); w = set(d.get("watch", []))
    (w.update(names) if add else w.difference_update(names)); d["watch"] = sorted(w); save(d)
    print(("watching" if add else "unwatched") + ": " + ", ".join(names)); print("watchlist:", d["watch"])

def cmd_list():
    d = load(); print("watchlist:", d.get("watch", [])); print("state:", json.dumps(d.get("state", {}), indent=2))

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "run":
        cmd_run(watch_all="--all" in a, dry="--dry" in a)
    elif a[0] == "watch":   cmd_watch(a[1:], add=True)
    elif a[0] == "unwatch": cmd_watch(a[1:], add=False)
    elif a[0] == "list":    cmd_list()
    else: print(__doc__)
