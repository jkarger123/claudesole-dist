#!/usr/bin/env python3
"""cc-autonudge -- auto-reply a canned message to a Claude session EVERY TIME it stops (turn-end), so an agent
that keeps pausing to ask "want me to keep going?" just gets your push automatically and keeps working.

Same mechanism as cc-session-watchdog (the API-error nudger): it watches OPTED-IN tmux sessions and, when one is
IDLE at a turn-end, it `tmux send-keys` your message into the input box and presses Enter. Difference: it fires on
ANY idle turn-end (not just an error), with YOUR per-session message, and keeps doing it until you turn it off.
YOU are the only brake (per your choice: fire every turn-end, always nudge, run until disabled).

  cc-autonudge arm <session> [message...]   # arm a session (omit message -> the default "no shortcuts" push)
  cc-autonudge off <session>                # disarm (stop nudging it)
  cc-autonudge msg <session> <message...>   # change a session's message
  cc-autonudge list                         # armed sessions + nudge counts
  cc-autonudge run  [--dry]                 # ONE pass over armed sessions (for launchd StartInterval)
  cc-autonudge loop [--dry]                 # continuous (~8s); run under launchd KeepAlive or in tmux

SAFETY (mirrors the watchdog): opt-in only; nudges ONLY when the session is IDLE (no 'esc to interrupt' / spinner);
once per distinct turn-end (pane signature); a short cooldown so it can't double-fire. `--dry` logs without typing.
"""
import json, os, re, subprocess, sys, time, hashlib

TMUX = os.environ.get("CC_TMUX") or "/opt/homebrew/bin/tmux"
os.environ.setdefault("TMUX_TMPDIR", "/tmp")
STATE = os.path.expanduser("~/.cc-autonudge.json")
LOG = "/tmp/cc-autonudge.log"
COOLDOWN = 10   # min seconds between nudges to the same session (anti double-fire; turns shorter than this are rare)
_RALPHDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))), "data", "ralph")  # CC_HOME/data/ralph. realpath (NOT abspath) resolves the /opt/homebrew/bin symlink to the real file -- abspath left it at /opt/data/ralph
_COMPACT_LOCK_DIR = "/tmp/cf-compact-locks"   # server.py's graceful-auto-compact lock; state "running" == a compact is driving this session's input box right now
_LOOP_FRESH_SEC = 1800   # a "running" ralph loop whose status.json hasn't advanced in this long is treated as wedged/backgrounded (runner died mid-iteration, or it's just parked) -> stop suppressing nudges. Generous so a legit long iteration isn't cut short.

DEFAULT_MSG = ("Like always, I want the complete solution -- I do not want any shortcuts. We need to get this "
               "correct before we move on. If you really feel it is correct -- like truly as correct as we need it "
               "to be for this very important tool -- then continue to the next thing. Otherwise, continue and get "
               "this figured out. No shortcuts.")

def sh(a, t=10):
    try: return subprocess.run(a, capture_output=True, text=True, timeout=t)
    except Exception: return None

def load():
    try: return json.load(open(STATE))
    except Exception: return {}

def save(d):
    try:
        fd = os.open(STATE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.write(fd, json.dumps(d, indent=2).encode()); os.close(fd)
    except Exception: pass

def logline(m):
    try: open(LOG, "a").write(time.strftime("%F %T ") + m + "\n")
    except Exception: pass

def has_session(s):
    r = sh([TMUX, "has-session", "-t", s]); return bool(r) and r.returncode == 0

def pane(s):
    r = sh([TMUX, "capture-pane", "-t", s, "-p", "-S", "-40"]); return r.stdout if (r and r.returncode == 0) else ""

def is_busy(txt):
    # working = the classic 'esc to interrupt' flag, or an ACTIVE spinner with an elapsing timer ("…(32s")
    if "esc to interrupt" in txt.lower(): return True
    for ln in txt.splitlines()[-5:]:
        if re.search(r"…\s*\(\d+\s*s\b", ln): return True
    return False

def sig_of(txt):   # a signature of the idle screen, so we nudge ONCE per distinct turn-end
    ls = [l for l in txt.splitlines() if l.strip()][-14:]
    return hashlib.md5("\n".join(ls).encode()).hexdigest()

def do_nudge(s, msg, dry=False):
    if dry: return
    low = pane(s).lower()
    if "how is claude doing" in low or "rate this session" in low:   # rating modal eats keys -> dismiss first
        sh([TMUX, "send-keys", "-t", s, "0"]); time.sleep(0.6)
    sh([TMUX, "send-keys", "-t", s, "-l", msg]); time.sleep(0.4)     # type the message (-l = literal)
    sh([TMUX, "send-keys", "-t", s, "Enter"])                        # send it

# NEVER nudge into an active MENU / usage-billing prompt / compact window (a free-text msg + Enter there could
# disrupt a flow or pick a money-spending option). CRITICAL: only inspect the ACTIVE BOTTOM of the pane (the live
# prompt), NOT the scrollback -- else the agent merely MENTIONING "compaction"/"usage limit"/etc. in its message
# wrongly blocks a nudge (that bug missed a real nudge 2026-07-04). A menu lives at the very bottom; prose above it.
_TAIL_SKIP = (
    "do you want to proceed?",                              # tool-permission prompt
    "pay-as-you-go", "usage limit reached", "reached your usage limit", "out of credit", "insufficient credit",
    "buy more credits", "purchase credits",                # usage/billing prompt -- never auto-answer (money)
    "handoff_done", "before your context gets compacted",  # the auto-compact idle window (between handoff and /compact)
)
def skip_reason(txt):
    lines = [l for l in txt.splitlines() if l.strip()]
    if sum(1 for l in lines[-10:] if re.match(r"^\s*[❯>›)]?\s*\d+[.):]\s+\S", l)) >= 2:
        return "menu"                                       # 2+ numbered options at the bottom = a selection prompt
    tail = "\n".join(lines[-7:]).lower()                    # the live prompt area ONLY (not the message body)
    for k in _TAIL_SKIP:
        if k in tail: return k
    if "compact prep" in txt.lower(): return "compact-prep" # the exact injected auto-compact trigger (very specific)
    return None

def _session_cwd(session):
    try:
        r = sh([TMUX, "display-message", "-t", session, "-p", "#{pane_current_path}"])
        p = (r.stdout or "").strip() if r and r.returncode == 0 else ""
        return os.path.realpath(p) if p else ""   # realpath: /tmp vs /private/tmp, /Volumes symlinks, etc.
    except Exception:
        return ""

def _same_project(a, b):
    """True if the two paths are in the same project tree (equal, or one nested in the other)."""
    if not a or not b: return False
    if a == b: return True
    return (b + "/").startswith(a + "/") or (a + "/").startswith(b + "/")

def waiting_on_loop(session):
    """Don't nudge a session that is legitimately WAITING on an IN-FLIGHT Ralph loop. Suppression requires BOTH:
      1. the loop is genuinely in flight -- status.json state == "running" AND fresh (advanced within
         _LOOP_FRESH_SEC). A paused / stopped / halted / done / blocked / stalled loop, or a "running" one whose
         status went stale (runner died mid-iteration, or it's just parked), does NOT count -- the session isn't
         meaningfully waiting on it, so nudging resumes. (This was the bug fixed 2026-07-04: a PAUSED, unowned,
         hours-stale loop in the same project silently suppressed an armed chief's nudge forever.)
      2. a link to this session -- (a) loop.json notify_session == this session (set by cc-ralph / the dashboard),
         or (b) the loop's cwd is the SAME project as this session's cwd (for loops started without a launcher).
    Auto-resumes when the loop finishes/pauses/stalls or its ralph-<name> tmux exits."""
    try:
        if not os.path.isdir(_RALPHDIR): return None
        scwd = _session_cwd(session)
        for n in os.listdir(_RALPHDIR):
            d = os.path.join(_RALPHDIR, n)
            if n.startswith((".", "_")) or not os.path.isdir(d): continue
            r = sh([TMUX, "has-session", "-t", "ralph-" + n])   # ralph-<name> tmux alive?
            if not (r and r.returncode == 0): continue
            try: stj = json.load(open(os.path.join(d, "status.json")))
            except Exception: stj = {}
            st = (stj.get("state") or "").lower()
            if st and st != "running": continue                              # not in flight (paused/done/etc.) -> resume nudging
            upd = stj.get("updated") or stj.get("started") or 0              # "running" but STALE -> runner likely dead/parked -> resume
            try:
                if upd and (time.time() - float(upd)) > _LOOP_FRESH_SEC: continue
            except Exception: pass
            try: cfg = json.load(open(os.path.join(d, "loop.json")))
            except Exception: continue
            if (cfg.get("notify_session") or "") == session: return n            # (a) explicit link
            lc = cfg.get("cwd") or ""
            if lc and _same_project(scwd, os.path.realpath(lc)): return n         # (b) same-project link
    except Exception:
        pass
    return None

def compacting(session):
    """True if server.py's graceful auto-compact is DRIVING this session's input box right now (lock state
    'running'). Never nudge then: a nudge steals the box mid-'/compact' so the command is queued as text and the
    compact silently gives up (root cause of the 2026-07-04 auto-compact-didn't-fire on chief-mission-control)."""
    try:
        p = os.path.join(_COMPACT_LOCK_DIR, session + ".lock")
        if not os.path.isfile(p): return False
        return (json.load(open(p)).get("state") or "") == "running"
    except Exception:
        return False

def run_pass(dry=False):
    d = load(); changed = False; now = time.time()
    for s, cfg in list(d.items()):
        if not cfg.get("on"): continue
        if not has_session(s): continue
        if compacting(s): logline("skip %s (auto-compact in progress)" % s); continue  # let the compact own the box
        txt = pane(s)
        if not txt.strip() or is_busy(txt): continue          # gone / working -> leave it
        _sk = skip_reason(txt)
        if _sk: logline("skip %s (%s)" % (s, _sk)); continue  # compact / usage-billing / menu -> NEVER nudge
        _wl = waiting_on_loop(s)
        if _wl: logline("skip %s (waiting on ralph loop %s)" % (s, _wl)); continue  # it launched a loop -> let it wait
        if now - cfg.get("last", 0) < COOLDOWN: continue      # cooldown
        sg = sig_of(txt)
        if cfg.get("sig") == sg: continue                     # already nudged this exact idle
        do_nudge(s, cfg.get("msg") or DEFAULT_MSG, dry)
        cfg["sig"] = sg; cfg["last"] = now; cfg["count"] = cfg.get("count", 0) + 1; changed = True
        logline(("[dry] " if dry else "") + "nudged %s (#%d)" % (s, cfg["count"]))
    if changed and not dry: save(d)

def main():
    a = sys.argv[1:] or ["run"]; cmd = a[0]; dry = "--dry" in a
    rest = [x for x in a[1:] if x != "--dry"]
    if cmd == "arm":
        s = rest[0]; msg = " ".join(rest[1:]) or DEFAULT_MSG
        d = load(); d[s] = {"on": True, "msg": msg, "count": d.get(s, {}).get("count", 0)}; save(d)
        print("armed: " + s); print("  msg: " + msg[:80] + ("…" if len(msg) > 80 else ""))
    elif cmd in ("off", "disarm"):
        s = rest[0]; d = load()
        if s in d: d[s]["on"] = False; save(d)
        print("disarmed: " + s)
    elif cmd == "msg":
        s = rest[0]; msg = " ".join(rest[1:]); d = load()
        d.setdefault(s, {"on": True, "count": 0})["msg"] = msg; save(d); print("message updated for " + s)
    elif cmd == "list":
        d = load()
        if not d: print("(no sessions armed)"); return
        for s, c in d.items():
            print("%s  %-28s nudges=%-4d  %.55s" % ("ON " if c.get("on") else "off", s, c.get("count", 0), c.get("msg") or DEFAULT_MSG))
    elif cmd == "run":
        run_pass(dry)
    elif cmd == "loop":
        pidf = os.path.expanduser("~/.cc-autonudge.pid")   # single-instance guard (server lazy-start checks this)
        try:
            if os.path.isfile(pidf):
                op = int(open(pidf).read().strip() or "0")
                if op and op != os.getpid():
                    try: os.kill(op, 0); print("another cc-autonudge loop is running (pid %d) -- exiting" % op); return
                    except Exception: pass
        except Exception: pass
        try: open(pidf, "w").write(str(os.getpid()))
        except Exception: pass
        print("cc-autonudge loop -- every 8s%s (Ctrl-C to stop)" % (" [DRY]" if dry else ""))
        while True:
            try: run_pass(dry)
            except Exception as e: logline("err " + str(e)[:120])
            time.sleep(8)
    else:
        print(__doc__)

if __name__ == "__main__":
    main()
