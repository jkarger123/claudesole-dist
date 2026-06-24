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

# A line is an ERROR line only if it is *predominantly* an API/transport error near the start of the line
# (optionally prefixed by Claude Code's box/glyph chars). This is what distinguishes a real stall from
# prose that merely contains the words "api error".
ERR_LINE = re.compile(
    r"^[\s>│|⎿╰╭✗✘×⚠!•\-\*]*"
    r"(api error|overloaded(_error)?|internal server error|service[ _]unavailable|"
    r"request timed out|request failed|connection (error|closed|reset)|econnreset|"
    r"stream (idle )?timeout|stream error|fetch failed|rate[_ ]?limit(_error)?|"
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
    return "esc to interrupt" in txt.lower()   # Claude shows this only while actively working/retrying

def is_stalled_on_error(txt):
    """Idle AND a trailing error line in the last few non-empty lines."""
    if is_busy(txt): return False
    lines = [ln for ln in txt.splitlines() if ln.strip()]
    tail = lines[-6:]                          # only the bottom of the pane (where a failed turn leaves the error)
    return any(ERR_LINE.match(ln) for ln in tail)

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
    sh([TMUX, "send-keys", "-t", s, "-l", NUDGE]); time.sleep(0.4)
    sh([TMUX, "send-keys", "-t", s, "Enter"])

def cmd_run(watch_all=False, dry=False):
    d = load(); st = d.setdefault("state", {}); watch = set(d.get("watch", []))
    live = tmux_sessions()
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
    if acted: logline("; ".join(acted))
    print("watchdog: targets=%d %s" % (len(targets), ("[dry] " if dry else "") + ("; ".join(acted) if acted else "nothing to nudge")))

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
