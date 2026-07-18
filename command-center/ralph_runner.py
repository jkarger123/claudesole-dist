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

def _notify_cfg():
    try: return json.load(open(os.environ.get("CC_CONFIG") or os.path.join(CC_HOME, "cc.config.json")))
    except Exception: return {}

def _notify(payload):
    """POST to the local server so it pings the session that STARTED this loop (loop.json notify_session, or the
    project chief as a fallback). Works even when the loop was NOT launched via /api/ralph-launch: if CC_NOTIFY
    isn't in the env, DERIVE the local URL from the node config (port), so a directly-run loop still notifies."""
    c = _notify_cfg()
    url = os.environ.get("CC_NOTIFY") or ("http://127.0.0.1:%s" % (c.get("port") or 8799))
    if not url: return False
    tok = c.get("auth_token") or ""
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

# ---- cross-vendor advisor: external GPT review at loop-completion (opt-in) ----------------------------
# When a loop COMPLETES (all boxes checked), an independent external GPT (Codex on the ChatGPT subscription,
# a DIFFERENT AI vendor) reviews the finished work against the loop's goal + checklist. In review_and_steer
# mode a "revise"/"block" verdict can send the loop back for another bounded pass (guidance prepended to
# prompt.txt + a re-open item added to progress.md). Opt-in per loop via a loop.json `advisor` block; ABSENT
# = feature off (zero behaviour change). ALWAYS fail-open: any advisor trouble -> finalize the loop, never
# block completion. The engine is command-center/cc-advise (run with --stream so the review is VISIBLE in
# this loop's tmux tab). Full system: docs/CROSS_VENDOR_ADVISOR.md. Provenance: conceptsandideas/OmniAgent/.
ADVISOR = CFG.get("advisor") if isinstance(CFG.get("advisor"), dict) else None
_ADV_ENGINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cc-advise")
_ADV_BUDGET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_advise_budget.json")  # shared w/ the interactive advisor
ADV_BEGIN, ADV_END = "<!-- CC:ADVISOR BEGIN -->", "<!-- CC:ADVISOR END -->"

def _advisor_state():
    try: return json.loads(read(lp("advisor.json"), "{}")) or {}
    except Exception: return {}

def _advisor_gate():
    """On loop completion, get an external cross-vendor review of the finished work. Returns True if the loop
    should CONTINUE (review_and_steer re-opened it for another pass), False to finalize as done. Fail-open:
    ANY trouble -> False (never block loop completion)."""
    cfg = ADVISOR
    if not cfg or cfg.get("enabled") is False:   # no advisor block, or explicitly disabled -> normal completion
        return False
    if DRY or not os.path.isfile(_ADV_ENGINE):
        return False
    st = _advisor_state()
    rounds = int(st.get("rounds", 0))
    cap = int((cfg.get("budget") or {}).get("max_rounds", cfg.get("max_rounds", 2)))
    mode = cfg.get("mode", "review_and_steer")
    verify = bool(cfg.get("verify", False))
    goal, progress, notes = read(lp("prompt.txt")), read(lp("progress.md")), read(lp("notes.md"))[-6000:]
    payload = (
        "=== RALPH LOOP FINISHED -- REVIEW THE COMPLETED WORK ===\n"
        "A Claude agent ran an autonomous loop to completion (all checklist items checked). OPEN the files under\n"
        "the repo root and review the finished work against the loop's goal + checklist -- skeptically.\n\n"
        "Repo root you may read: %s\n\n"
        "=== LOOP GOAL / ITERATION PROMPT ===\n%s\n\n"
        "=== COMPLETED CHECKLIST (progress.md) ===\n%s\n\n"
        "=== SHARED NOTES (notes.md, tail) ===\n%s\n" % (CWD, goal, progress, notes)
    )
    pf, rf = lp("_advisor_payload.txt"), lp("_advisor_result.json")
    try: open(pf, "w", encoding="utf-8").write(payload)
    except Exception: return False
    try: os.remove(rf)
    except Exception: pass
    log(""); log("  ============================================================")
    log("  =  EXTERNAL THIRD-PARTY REVIEW (cross-vendor GPT)  round %d/%d" % (rounds + 1, cap))
    log("  ============================================================")
    cmd = ["python3", _ADV_ENGINE, "--payload", pf, "--repo", CWD, "--stream",
           "--result-file", rf, "--mode", mode, "--budget-file", _ADV_BUDGET]
    if verify: cmd.append("--verify")
    mcpd = (cfg.get("budget") or {}).get("max_calls_per_day")
    if mcpd: cmd += ["--max-calls-per-day", str(mcpd)]
    try:
        subprocess.run(cmd, cwd=CWD, timeout=int(cfg.get("timeout_sec", 360)))   # inherits stdout -> visible in the loop tab
    except Exception as e:
        log("  advisor call failed (%s) -- finalizing (fail-open)." % str(e)[:100]); return False
    try: v = json.loads(read(rf, "{}")) or {}
    except Exception: v = {}
    verdict = v.get("verdict")
    blocking = v.get("blocking") or []
    guidance = (v.get("next_task_guidance") or "").strip()
    # audit trail (viewable in the Ralph lens)
    try:
        with open(lp("advisor.md"), "a", encoding="utf-8") as f:
            f.write("\n## Round %d -- %s -- verdict: %s\n" % (rounds + 1, time.strftime("%Y-%m-%d %H:%M"), verdict))
            for b in blocking:
                f.write("- BLOCKING: %s  (%s)\n" % (b.get("issue", ""), b.get("location", "")))
            if guidance: f.write("\nGuidance for the next pass:\n%s\n" % guidance)
    except Exception: pass
    st["rounds"] = rounds + 1; st["last_verdict"] = verdict
    try: open(lp("advisor.json"), "w").write(json.dumps(st))
    except Exception: pass
    # surface to the operator/starting session (reuses the notify path)
    _notify({"kind": "advisor_review", "verdict": verdict, "round": rounds + 1,
             "blocking": len(blocking), "guidance": guidance[:400]})
    if verdict in (None, "skipped", "ship"):
        log("  external review verdict: %s -- loop stays complete." % (verdict or "no result")); return False
    if mode != "review_and_steer":
        log("  external review verdict: %s (review-only) -- loop stays complete." % verdict); return False
    if rounds + 1 >= cap:
        log("  external review verdict: %s, but advisor round cap (%d) reached -- finalizing." % (verdict, cap)); return False
    # STEER: prepend the labeled guidance to prompt.txt + re-open the loop with a task to address it
    block = (ADV_BEGIN + "\n\U0001f535 EXTERNAL GPT ADVISOR (independent cross-vendor review of the just-finished "
             "work -- weigh it, you hold the pen). Verdict: %s. Address the blocking items below, update the "
             "deliverable, then re-check the boxes.\n%s\n" % (verdict, guidance or "(see advisor.md for details)")
             + ADV_END)
    try:
        cur = read(lp("prompt.txt"))
        cur = re.sub(re.escape(ADV_BEGIN) + r".*?" + re.escape(ADV_END), "", cur, flags=re.S).lstrip()
        open(lp("prompt.txt"), "w", encoding="utf-8").write(block + "\n\n" + cur)
    except Exception: pass
    try:
        with open(lp("progress.md"), "a", encoding="utf-8") as f:
            f.write("\n- [ ] Address external reviewer round %d (%s): %s\n"
                    % (rounds + 1, verdict, (guidance or "see advisor.md")[:120]))
    except Exception: pass
    log("  external review verdict: %s -- RE-OPENED the loop for another pass (round %d/%d)." % (verdict, rounds + 1, cap))
    return True

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

def _sleep_interruptible(secs):
    """Sleep up to `secs`, but bail early the moment a halt/pause is requested -- so a backoff never blocks a stop."""
    end = time.time() + secs
    while time.time() < end:
        if control_state() != "run": return
        time.sleep(min(3, max(0.1, end - time.time())))

def _reap_live():
    """Tear down the ralph-<name>-live viewer tab when the runner exits, so a DEAD loop doesn't LOOK alive (the
    lingering -live pane misled diagnosis for hours). (CCR ccr-1784357840269 D4)"""
    try:
        import shutil as _sh
        if not os.environ.get("TMUX"): return
        tmux = _sh.which("tmux") or "/opt/homebrew/bin/tmux"
        subprocess.run([tmux, "kill-session", "-t", "=ralph-%s-live" % NAME], capture_output=True, timeout=8)
    except Exception: pass

# ---- one iteration -----------------------------------------------------------
def _pane_summary(raw):
    """The runner's OWN pane stays clean -- just the end-of-iteration blurb (as it was before the live tab existed).
    All the per-step activity (tool calls, mid-iteration text) lives in the `ralph-<name>-live` tab now."""
    try: e = json.loads(raw)
    except Exception: return ""                        # non-JSON stderr -> keep the runner pane clean (it's in the live tab)
    if e.get("type") == "result":                      # the "little blurb when the iteration finished"
        txt = (e.get("result") or "").strip().replace("\n", " ")
        stats = "%s turns, %.1fs" % (e.get("num_turns"), (e.get("duration_ms") or 0) / 1000.0)
        return ("%s  (%s)" % (txt[:220], stats)) if txt else ("iteration %s (%s)" % (e.get("subtype", "done"), stats))
    return ""                                          # everything else -> the live tab only

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

    # stream-json -> we can render the iteration LIVE in the `ralph-<name>-live` tab (ralph_live.py follows live.jsonl)
    cmd = ["claude", "--dangerously-skip-permissions", "--max-turns", str(MAX_TURNS), "--verbose", "--output-format", "stream-json", "-p"]
    if MODEL: cmd[1:1] = ["--model", MODEL]
    _ps = os.environ.get("CC_POLICY_SETTINGS")           # per-action policy engine PreToolUse hook (graft G1)
    if _ps and os.path.isfile(_ps): cmd[1:1] = ["--settings", _ps]
    env = dict(os.environ); env["PATH"] = env.get("PATH", "") + ":" + os.path.join(HOME, ".local/bin") + ":/opt/homebrew/bin"
    _lf = None                               # ONE handle for the whole iteration: truncate (reset the live tab) + keep open to stream into
    try:
        _lf = open(lp("live.jsonl"), "w", encoding="utf-8")
        _lf.write(json.dumps({"type": "cc_iter", "iter": n, "ts": time.time()}) + "\n"); _lf.flush()
    except Exception: _lf = None
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
    last_result = {}; limit_hit = False
    for line in proc.stdout:
        raw = line.rstrip("\n")
        if not raw: continue
        if _lf:                                   # feed the live tab (ralph_live.py renders this stream)
            try: _lf.write(raw + "\n"); _lf.flush()
            except Exception: pass
        _low = raw.lower()                         # transient usage/rate-limit signal anywhere in the stream (D3)
        if ("session limit" in _low or "usage limit" in _low or "rate_limit" in _low or "rate limit" in _low
                or "resets " in _low or "overloaded_error" in _low):
            limit_hit = True
        try:
            _ev = json.loads(raw)
            if isinstance(_ev, dict) and _ev.get("type") == "result": last_result = _ev
        except Exception: pass
        s = _pane_summary(raw)                     # keep the runner pane a COMPACT control+activity view
        if s: log("  " + s)
    try:
        if _lf: _lf.close()
    except Exception: pass
    proc.wait(); INTERRUPTED["proc"] = None
    # bank the spend/turns even when the iteration fails -- never report zero cost for real work done (D2)
    _cost = last_result.get("total_cost_usd"); _turns = last_result.get("num_turns")
    if _cost is not None or _turns is not None:
        try: set_status(last_cost=_cost, last_turns=_turns, last_iter_end=time.time())
        except Exception: pass
    if stop["why"] == "timeout":
        log("  ITERATION TIMED OUT (%ds) -- killed." % TIMEOUT); return "timeout"
    if stop["why"] == "halt":  return "halt"
    if stop["why"] == "pause": log("  iteration interrupted (pause requested)."); return "pause"
    _sub = str(last_result.get("subtype") or "")
    if limit_hit:                                  # transient -> caller backs off + retries; NEVER terminal (D3)
        log("  usage/rate limit detected this iteration."); return "limit"
    if last_result.get("is_error") and _sub != "error_max_turns":
        log("  iteration error: %s" % (_sub or "error")); return "error"
    return "ok"

# ---- the live-view sibling tab ----------------------------------------------
def _ensure_live_tab():
    """Spawn the `ralph-<name>-live` tab the moment the runner starts, so BOTH windows appear together no matter
    HOW the loop was launched (API, cc-ralph, or an agent starting the runner directly). Idempotent + best-effort;
    only when we're inside tmux (a normal ralph launch), never during a bare direct-run test."""
    if not os.environ.get("TMUX"): return
    try:
        import shutil as _sh
        tmux = _sh.which("tmux") or "/opt/homebrew/bin/tmux"
        live = "ralph-%s-live" % NAME
        if subprocess.run([tmux, "has-session", "-t", live], capture_output=True).returncode == 0: return
        here = os.path.dirname(os.path.abspath(__file__))
        subprocess.run([tmux, "new-session", "-d", "-s", live, "-c", here,
                        "CC_HOME=%s python3 %s %s" % (CC_HOME, os.path.join(here, "ralph_live.py"), NAME)],
                       capture_output=True, timeout=10)
    except Exception: pass

# ---- main loop ---------------------------------------------------------------
def main():
    _ensure_live_tab()                          # bring up the live-iteration tab immediately, alongside the runner
    log("")
    log("  ========================================================")
    log("  =  RALPH LOOP -- %s" % NAME)
    log("  =  cwd=%s  max_iters=%s  timeout=%ds" % (CWD, MAX_ITERS or "inf", TIMEOUT))
    log("  ========================================================")
    # clear stale control markers from a PRIOR run so a fresh launch ALWAYS starts clean. A leftover `halt`
    # (from a previous halt/kill) otherwise makes main() exit instantly below -> a halted loop was UNRECOVERABLE
    # by any launch path that doesn't itself clear it (cc-ralph / direct / agent starts). (CCR ccr-1784357840269 D1)
    for _ctl in ("pause", "halt"):
        try: os.remove(lp(_ctl))
        except Exception: pass
    set_status(state="running", started=time.time())
    n = START; t0 = time.time(); stall = 0; err_streak = 0
    while True:
        if os.path.exists(lp("halt")):
            log("  HALT requested -- stopping."); set_status(state="halted"); break
        wait_if_paused()
        if is_complete():   # UNCONDITIONAL (was gated on n>START): a relaunched DONE loop must exit instantly, not
                            # burn a full iteration + verifier first. Safe: is_complete() requires total>0 AND
                            # unchecked==0 (+ capstone), so a fresh loop with real items never false-completes here.
            if _advisor_gate():   # opt-in external cross-vendor review sent the loop back for another pass
                set_status(state="running", current="external review -> another pass"); n += 1; continue
            log(""); log("  ===== %s COMPLETE -- all items checked =====" % NAME); set_status(state="done")
            _notify_starter(); break   # ping the agent/session that started this loop (via the server)
        if MAX_ITERS and n > (START + MAX_ITERS - 1):
            log("  max iterations reached."); set_status(state="stopped"); break
        before = parse_progress()["checked"]
        res = run_iteration(n)
        if res == "halt":
            log("  HALT during iteration -- stopping."); set_status(state="halted"); break
        if res == "limit":                          # transient usage/rate limit -> back off + RETRY same iteration (D3)
            wait_s = int(CFG.get("limit_backoff_s", 900))
            log("  usage limit -- backing off %ds then retrying (the window is otherwise burned banking nothing)." % wait_s)
            set_status(state="throttled", current="usage limit -- waiting to retry"); _sleep_interruptible(wait_s); continue
        if res == "error":                          # real mid-iteration error -> record, brief backoff, retry (bounded) (D2)
            err_streak += 1
            if err_streak >= int(CFG.get("error_limit", 6)):
                log("  %d consecutive errors -- pausing for attention." % err_streak)
                set_status(state="paused", current="repeated iteration errors"); open(lp("pause"), "w").close(); continue
            log("  iteration errored (streak %d) -- brief backoff, retry." % err_streak)
            set_status(state="running", current="iteration errored -- retrying"); _sleep_interruptible(min(60 * err_streak, 300)); continue
        err_streak = 0
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
    _reap_live()   # runner is exiting -> tear down the live viewer so the loop doesn't keep LOOKING alive (D4)

if __name__ == "__main__":
    main()
