#!/usr/bin/env python3
"""Ralph loop runner -- Mac-native, reusable, one loop per invocation.

Drives a self-terminating, resumable agent loop. Designed to run INSIDE a tmux session named
`ralph-<name>` on the brain server, so the Command Center's browser terminal shows it live and you can
Ctrl-C / type to interrupt. The runner is dumb: all loop state lives in markdown files that the agent
AND you can edit between iterations -- the loop picks up your edits on its next pass.

Usage:  ralph_runner.py <loop-name> [--dry-run] [--start N]

Loop dir (created by /api/ralph-create or by hand):
  <CC_HOME>/data/ralph/<name>/
    loop.json     config {cwd, max_iters, timeout_sec, model, max_turns, capstone}
    prompt.txt    iteration prompt; "$ITER" is replaced with the iteration number
    rules.md      hard rules (referenced by the prompt)
    progress.md   checkbox TODO list = the loop's durable memory ("- [ ]" / "- [x]")
    notes.md      free-form shared scratchpad (you <-> agent)
    status.json   written by the runner: {state, iteration, current, progress, updated}
    run.log       append-only combined log (what the terminal shows)
    halt / pause  control files (presence-based) the dashboard buttons drop
"""
import json, os, re, signal, subprocess, sys, threading, time

HOME = os.path.expanduser("~")
CC_HOME = os.environ.get("CC_HOME") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # this bundle's root (portable; = <CC_HOME> on the authoring node)
ap = [a for a in sys.argv[1:]]
DRY = "--dry-run" in ap
START = 1
if "--start" in ap:
    try: START = int(ap[ap.index("--start") + 1])
    except Exception: START = 1
POS = [a for a in ap if not a.startswith("--") and a != str(START)]
NAME = POS[0] if POS else None
if not NAME:
    print("usage: ralph_runner.py <loop-name> [--dry-run] [--start N]"); sys.exit(2)

LOOPDIR = os.path.join(CC_HOME, "data", "ralph", NAME)
def lp(*p): return os.path.join(LOOPDIR, *p)
if not os.path.isdir(LOOPDIR):
    print("FATAL: no such loop dir: " + LOOPDIR); sys.exit(1)

CFG = {}
try: CFG = json.loads(open(lp("loop.json")).read())
except Exception: CFG = {}
DRY       = DRY or bool(CFG.get("dry"))             # loop.json can force dry mode (for wiring tests)
CWD       = CFG.get("cwd") or LOOPDIR
MAX_ITERS = int(CFG.get("max_iters", 0))            # 0 = until complete/halt
TIMEOUT   = int(CFG.get("timeout_sec", 2700))       # per-iteration wall clock
STALL_LIMIT = int(CFG.get("stall_limit", 12))       # circuit-breaker: auto-halt after N iters that check 0 new boxes (0 = off)
MAX_TURNS = int(CFG.get("max_turns", 200))
MODEL     = CFG.get("model", "")                    # "" = inherit session default
CAPSTONE  = CFG.get("capstone", "")                 # optional file whose existence also gates completion

# ---- small file helpers ------------------------------------------------------
def read(path, default=""):
    try:
        with open(path, encoding="utf-8", errors="replace") as f: return f.read()
    except Exception: return default

def log(line=""):
    line = str(line).rstrip("\n")
    print(line, flush=True)
    try:
        with open(lp("run.log"), "a", encoding="utf-8") as f: f.write(line + "\n")
    except Exception: pass

def parse_progress():
    txt = read(lp("progress.md"))
    checked   = len(re.findall(r"- \[[xX]\]", txt))
    unchecked = len(re.findall(r"- \[ \]", txt))
    phase, nxt, cphase = "", "", ""
    for ln in txt.splitlines():
        m = re.match(r"#{1,6}\s+(.*)", ln)
        if m: cphase = m.group(1).strip()
        if re.match(r"\s*- \[ \]", ln):
            phase = cphase
            nxt = re.sub(r"\s*- \[ \]\s*", "", ln).strip()[:140]
            break
    return {"checked": checked, "unchecked": unchecked, "total": checked + unchecked, "phase": phase, "next": nxt}

def set_status(**kw):
    st = {}
    try: st = json.loads(read(lp("status.json"), "{}")) or {}
    except Exception: st = {}
    st.update(kw)
    st["progress"] = parse_progress()
    st["pid"] = os.getpid()
    st["updated"] = time.time()
    try:
        with open(lp("status.json"), "w") as f: json.dump(st, f)
    except Exception: pass

def is_complete():
    p = parse_progress()
    done = p["total"] > 0 and p["unchecked"] == 0
    if CAPSTONE:
        done = done and os.path.exists(CAPSTONE)
    return done

NOTIFY_ITERS = CFG.get("notify_iters", True) is not False   # ping the launching session after each iteration too

def _notify(payload):
    """POST to the server (CC_NOTIFY) so it pings the session that STARTED this loop (loop.json notify_session).
    Best-effort + authenticated. `payload` gets {name} added; kind='iteration'|'complete' picks the message."""
    url = os.environ.get("CC_NOTIFY")
    if not url: return False
    tok = ""
    try:
        _cp = os.environ.get("CC_CONFIG") or os.path.join(CC_HOME, "cc.config.json")
        tok = json.load(open(_cp)).get("auth_token") or ""
    except Exception: pass
    try:
        import urllib.request
        body = dict(payload); body["name"] = NAME
        req = urllib.request.Request(url.rstrip("/") + "/api/ralph-notify",
                                     data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "Cookie": "cc_auth=%s" % tok})
        urllib.request.urlopen(req, timeout=12).read()
        return True
    except Exception as e:
        log("  (notify failed: %s)" % str(e)[:100]); return False

def _notify_starter():
    """On COMPLETION, tell the starting session the loop finished (server delivers when that session is idle)."""
    if _notify({"kind": "complete"}): log("  notified the starting session that this loop finished.")

def _notify_iteration(n, checked_this, prog):
    """After EACH iteration, send a progress ping to the starting session (unless loop.json notify_iters:false)."""
    if not NOTIFY_ITERS: return
    if _notify({"kind": "iteration", "iter": n, "checked_this": checked_this,
                "done": prog.get("checked", 0), "total": prog.get("total", 0), "next": prog.get("next", "")}):
        log("  pinged the starting session (iteration %d progress)." % n)

# ---- control: halt (stop) / pause (wait) -------------------------------------
PAUSED = threading.Event()
def control_state():
    if os.path.exists(lp("halt")): return "halt"
    if os.path.exists(lp("pause")): return "pause"
    return "run"

def wait_if_paused():
    announced = False
    while control_state() == "pause":
        if not announced:
            log("  [paused] -- waiting (delete the pause file or click Resume).")
            set_status(state="paused"); announced = True
        time.sleep(2)
    if announced:
        log("  [resumed]"); set_status(state="running")

# Ctrl-C in the attached terminal: stop the current iteration + pause (second Ctrl-C exits)
INTERRUPTED = {"n": 0, "proc": None}
def on_sigint(sig, frame):
    INTERRUPTED["n"] += 1
    p = INTERRUPTED.get("proc")
    if p and p.poll() is None:
        log("\n  [Ctrl-C] stopping this iteration...")
        try: p.terminate()
        except Exception: pass
    if INTERRUPTED["n"] >= 2:
        log("  [Ctrl-C x2] exiting runner."); set_status(state="stopped"); os._exit(130)
    # pause after an interrupt so you can inspect/edit before it continues
    try: open(lp("pause"), "w").close()
    except Exception: pass
signal.signal(signal.SIGINT, on_sigint)

# ---- one iteration -----------------------------------------------------------
def run_iteration(n):
    prompt = read(lp("prompt.txt")).replace("$ITER", str(n))
    if not prompt.strip():
        log("  FATAL: prompt.txt is empty"); set_status(state="blocked", current="empty prompt"); return "blocked"
    # Pin the agent to THIS loop's control files by ABSOLUTE path. The agent runs with cwd=CWD (the project),
    # so a bare "progress.md" in the prompt makes it create/edit one at the project root -- which the runner
    # never reads (it counts lp("progress.md")), so every iteration shows 0 boxes checked and the
    # circuit-breaker false-halts. Appending the absolute paths makes the target unambiguous for any loop.
    prompt += ("\n\n[LOOP FILES -- use these EXACT absolute paths; NEVER a progress.md/rules.md/notes.md at "
               "the project root or anywhere else]\n- checklist you MUST update (flip '- [ ]' to '- [x]' in "
               "THIS file): %s\n- rules: %s\n- scratchpad: %s\n" % (lp("progress.md"), lp("rules.md"), lp("notes.md")))
    log("")
    log("  --------------------------------------------------------")
    log("  %s  iteration %d  %s" % (NAME, n, time.strftime("%Y-%m-%d %H:%M:%S")))
    log("  --------------------------------------------------------")
    set_status(state="running", iteration=n, current="iteration %d" % n, started=time.time())
    if DRY:
        log("  [DRY RUN] would invoke claude (cwd=%s, max_turns=%d). Prompt head:" % (CWD, MAX_TURNS))
        log("    " + prompt.strip().splitlines()[0][:100])
        for _ in range(int(CFG.get("dry_sleep", 3))):          # simulate work so the live UI is watchable
            if control_state() != "run": return "pause"
            time.sleep(1)
        return "ok"

    cmd = ["claude", "--dangerously-skip-permissions", "--max-turns", str(MAX_TURNS), "-p"]
    if MODEL: cmd[1:1] = ["--model", MODEL]
    env = dict(os.environ); env["PATH"] = env.get("PATH", "") + ":" + os.path.join(HOME, ".local/bin") + ":/opt/homebrew/bin"
    try:
        proc = subprocess.Popen(cmd, cwd=CWD, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
    except Exception as e:
        log("  ERROR launching claude: %s" % e); set_status(state="blocked", current=str(e)); return "blocked"
    INTERRUPTED["proc"] = proc
    try:
        proc.stdin.write(prompt); proc.stdin.close()
    except Exception: pass

    # watcher: enforce per-iteration timeout + kill on halt/pause-request mid-iteration
    deadline = time.time() + TIMEOUT
    stop = {"why": ""}
    def watch():
        while proc.poll() is None:
            if time.time() > deadline: stop["why"] = "timeout"; proc.terminate(); return
            cs = control_state()
            if cs == "halt": stop["why"] = "halt"; proc.terminate(); return
            if cs == "pause": stop["why"] = "pause"; proc.terminate(); return
            time.sleep(2)
    t = threading.Thread(target=watch, daemon=True); t.start()
    for line in proc.stdout:
        log("  " + line.rstrip("\n"))
    proc.wait(); INTERRUPTED["proc"] = None
    if stop["why"] == "timeout":
        log("  ITERATION TIMED OUT (%ds) -- killed." % TIMEOUT); return "timeout"
    if stop["why"] == "halt":  return "halt"
    if stop["why"] == "pause": log("  iteration interrupted (pause requested)."); return "pause"
    return "ok"

# ---- main loop ---------------------------------------------------------------
def main():
    log("")
    log("  ========================================================")
    log("  =  RALPH LOOP -- %s" % NAME)
    log("  =  cwd=%s  max_iters=%s  timeout=%ds" % (CWD, MAX_ITERS or "inf", TIMEOUT))
    log("  ========================================================")
    # clear any stale pause from a previous run; honor an explicit halt
    try:
        if os.path.exists(lp("pause")): os.remove(lp("pause"))
    except Exception: pass
    set_status(state="running", started=time.time())
    n = START; t0 = time.time(); stall = 0
    while True:
        if os.path.exists(lp("halt")):
            log("  HALT requested -- stopping."); set_status(state="halted"); break
        wait_if_paused()
        if is_complete():   # UNCONDITIONAL (was gated on n>START): a relaunched DONE loop must exit instantly, not
                            # burn a full iteration + verifier first. Safe: is_complete() requires total>0 AND
                            # unchecked==0 (+ capstone), so a fresh loop with real items never false-completes here.
            log(""); log("  ===== %s COMPLETE -- all items checked =====" % NAME); set_status(state="done")
            _notify_starter(); break   # ping the agent/session that started this loop (via the server)
        if MAX_ITERS and n > (START + MAX_ITERS - 1):
            log("  max iterations reached."); set_status(state="stopped"); break
        before = parse_progress()["checked"]
        res = run_iteration(n)
        if res == "halt":
            log("  HALT during iteration -- stopping."); set_status(state="halted"); break
        if res == "blocked":
            log("  BLOCKED -- pausing for attention."); open(lp("pause"), "w").close(); continue
        # optional verifier (can un-check items)
        if os.path.exists(lp("verify.py")) and not DRY:
            log("  running verifier...");
            try:
                vp = subprocess.run(["python3", lp("verify.py")], cwd=CWD, capture_output=True, text=True, timeout=300)
                for ln in (vp.stdout or "").splitlines(): log("    " + ln)
                log("    verifier: %s" % ("all good" if vp.returncode == 0 else "unchecked something -> fix next iter"))
            except Exception as e: log("    verifier error: %s" % e)
        prog_now = parse_progress()
        after = prog_now["checked"]
        log("  items checked this iteration: %d (total %d)" % (after - before, after))
        _notify_iteration(n, after - before, prog_now)   # progress ping to the session that started the loop
        # circuit-breaker: a loop that checks 0 new boxes for many iterations is non-converging (spinning,
        # or a verifier that fails every pass). Auto-halt + escalate so it can't burn tokens forever.
        if (after - before) > 0:
            stall = 0
        else:
            stall += 1
            if STALL_LIMIT and stall >= STALL_LIMIT:
                msg = ("STALLED -- %d consecutive iterations checked 0 new boxes (non-converging loop or a "
                       "verifier failing every pass). Auto-halted by the circuit-breaker. Review progress.md, "
                       "notes.md, and verify.py before resuming." % stall)
                log("  " + msg); set_status(state="stalled", current=msg)
                try:
                    with open(lp("notes.md"), "a") as f:
                        f.write("\n## AUTO-HALT circuit-breaker %s\n- %s\n" % (time.strftime("%Y-%m-%d %H:%M"), msg))
                except Exception: pass
                break
        set_status(state="running", iteration=n, current="between iterations")
        n += 1
        if DRY and not CFG.get("dry_loop") and n > START + 1:
            log("  [DRY RUN] stop after 1."); set_status(state="done"); break
        time.sleep(3)
    log("")
    log("  total: %.2f hr / %d iterations" % ((time.time() - t0) / 3600.0, n - START))

if __name__ == "__main__":
    main()
