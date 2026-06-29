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
import json, os, re, subprocess, sys, time

TMUX = os.environ.get("CC_TMUX") or "/opt/homebrew/bin/tmux"
os.environ.setdefault("TMUX_TMPDIR", "/tmp")
STATE_FILE = os.path.expanduser("~/.cc-watchdog.json")
LOG = "/tmp/cc-watchdog.log"
COOLDOWN = 150            # seconds between nudges to the same session
NUDGE = "Please continue where you left off -- an API error interrupted you; resume the task."
# Out-of-process chief revival: each node server drops a launch descriptor here (see chief_open in server.py).
CHIEF_LAUNCH_DIR = "/tmp/cf-chief-launch"
CHIEF_REVIVE_COOLDOWN = 120   # seconds between revive attempts for the same chief (anti-thrash)

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

def revive_chiefs(d, live, dry=False):
    """Recreate any chief whose tmux session is gone, from the launch descriptor its server left in
    CHIEF_LAUNCH_DIR. This runs in the launchd watchdog -- INDEPENDENT of any node server.py -- so a chief is
    revived even when its server is down/crash-looping (the server's own in-process watchdog dies with it).
    Cooldown-guarded so a chief that keeps dying can't be respawned in a tight loop."""
    import glob
    cs = d.setdefault("chief_revive", {}); now = time.time(); acted = []
    for f in sorted(glob.glob(os.path.join(CHIEF_LAUNCH_DIR, "*.json"))):
        try: desc = json.load(open(f))
        except Exception: continue
        sess = desc.get("session"); cl = desc.get("cl"); cwd = desc.get("cwd") or os.path.expanduser("~")
        if not sess or not cl or sess in live: continue            # missing data or already alive
        if now - cs.get(sess, 0) < CHIEF_REVIVE_COOLDOWN: continue  # cooldown
        if dry: acted.append("WOULD-REVIVE " + sess); continue
        r = sh([TMUX, "new-session", "-d", "-s", sess, "-c", cwd, cl]); cs[sess] = now
        ok = bool(r) and r.returncode == 0
        acted.append("revived " + sess + ("" if ok else " (FAILED)"))
        logline("out-of-process revive of chief %s%s" % (sess, "" if ok else " FAILED"))
    for s in list(cs):                                             # forget chiefs whose descriptor is gone
        if not os.path.isfile(os.path.join(CHIEF_LAUNCH_DIR, s + ".json")): del cs[s]
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
