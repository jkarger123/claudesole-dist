#!/usr/bin/env python3
"""Campaign runner -- a GPT-DIRECTED autonomous campaign over a chain of Ralph loops.

The cycle (full-auto, with an operator INTERCEPT window before each loop launches):
  1. DIRECT   -- an external GPT (Codex on the ChatGPT subscription, a DIFFERENT vendor) reads the campaign's
                 north-star goal + the just-finished loop's output + history, and decides the next loop
                 (a goal + checklist) or declares the campaign DONE.  [visible, via cc-advise --mode direct_next]
  2. INTERCEPT-- the proposed next loop is surfaced with a countdown. The operator MAY edit / launch-now /
                 pause / halt; if nobody interacts before the deadline, it proceeds automatically.
  3. BUILD+RUN-- a Claude agent executes that loop to completion (a real Ralph loop, its own live tab).
  4. repeat until the director says DONE, the round cap is hit, or the operator halts.

Designed to run INSIDE a tmux session `campaign-<name>` on the brain server, so the Command Center shows it
live and you can Ctrl-C / halt. Reuses the Ralph runner (the executor) and cc-advise (the director). Full
system: docs/CROSS_VENDOR_ADVISOR.md. Fail-SAFE (unlike the per-review advisor, which is fail-open): if the
director can't decide, the campaign PAUSES for the operator rather than barrelling on.

Campaign dir: <CC_HOME>/data/campaigns/<name>/
  campaign.json  {name, goal, cwd, state, round, max_rounds, intercept_secs, model, max_turns, history[]}
  pending.json   the directive currently in its intercept window {round, directive{goal,checklist,rationale}, deadline, status}
  director.md    append-only log of every director decision
  run.log        combined log (what the tab shows)
  halt / pause   control files the dashboard buttons drop
Loops it launches live at <CC_HOME>/data/ralph/_camp-<name>-r<N>/ (hidden from the Ralph lens by the '_' prefix;
watchable from the Campaigns lens).
"""
import json, os, re, signal, subprocess, sys, threading, time

HOME = os.path.expanduser("~")
CC_HOME = os.environ.get("CC_HOME") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
CC_ADVISE = os.path.join(HERE, "cc-advise")
RALPH_RUNNER = os.path.join(HERE, "ralph_runner.py")
ADV_BUDGET = os.path.join(HERE, "_advise_budget.json")

POS = [a for a in sys.argv[1:] if not a.startswith("--")]
NAME = POS[0] if POS else None
if not NAME:
    print("usage: campaign_runner.py <campaign-name>"); sys.exit(2)

CDIR = os.path.join(CC_HOME, "data", "campaigns", NAME)
def cp(*p): return os.path.join(CDIR, *p)
if not os.path.isdir(CDIR):
    print("FATAL: no such campaign dir: " + CDIR); sys.exit(1)

def read(path, default=""):
    try:
        with open(path, encoding="utf-8", errors="replace") as f: return f.read()
    except Exception: return default

def log(line=""):
    line = str(line).rstrip("\n"); print(line, flush=True)
    try:
        with open(cp("run.log"), "a", encoding="utf-8") as f: f.write(line + "\n")
    except Exception: pass

def load_cfg():
    try: return json.loads(read(cp("campaign.json"), "{}")) or {}
    except Exception: return {}

def save_cfg(c):
    try:
        with open(cp("campaign.json"), "w") as f: json.dump(c, f, indent=2)
    except Exception: pass

def set_state(state, **extra):
    c = load_cfg(); c["state"] = state; c["updated"] = time.time()
    c.update(extra); save_cfg(c)

def control_state():
    if os.path.exists(cp("halt")): return "halt"
    if os.path.exists(cp("pause")): return "pause"
    return "run"

def wait_if_paused():
    announced = False
    while control_state() == "pause":
        if not announced: log("  [paused] -- waiting (Resume in the Campaigns lens)."); set_state("paused"); announced = True
        time.sleep(2)
    if announced: log("  [resumed]"); set_state("running")

# ---- notify the operator (reuses the local server) --------------------------------------------------
def _cfg_node():
    try: return json.load(open(os.environ.get("CC_CONFIG") or os.path.join(CC_HOME, "cc.config.json")))
    except Exception: return {}

def _notify(payload):
    c = _cfg_node(); url = os.environ.get("CC_NOTIFY") or ("http://127.0.0.1:%s" % (c.get("port") or 8799))
    try:
        import urllib.request
        body = dict(payload); body["name"] = NAME
        req = urllib.request.Request(url.rstrip("/") + "/api/campaign-notify", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "Cookie": "cc_auth=%s" % (c.get("auth_token") or "")})
        urllib.request.urlopen(req, timeout=12).read(); return True
    except Exception as e:
        log("  (notify failed: %s)" % str(e)[:100]); return False

# ---- the DIRECTOR step (external GPT decides the next loop) ------------------------------------------
def run_director(cfg, prior_loopdir):
    """Ask the external GPT director for the next loop (or DONE). Visible via cc-advise --stream. Returns the
    parsed director dict, or {} on failure. Fail-SAFE: an empty/failed result pauses the campaign upstream."""
    goal = cfg.get("goal", ""); cwd = cfg.get("cwd") or CC_HOME
    hist = cfg.get("history", [])
    hist_txt = "\n".join("Round %d: %s -> %s" % (h.get("round"), h.get("goal", ""), h.get("status", "ran"))
                         for h in hist[-8:]) or "(none yet -- this is the first loop)"
    if prior_loopdir and os.path.isdir(prior_loopdir):
        prog = read(os.path.join(prior_loopdir, "progress.md"))
        notes = read(os.path.join(prior_loopdir, "notes.md"))[-6000:]
        prior = ("=== JUST-FINISHED LOOP -- CHECKLIST ===\n%s\n\n=== ITS NOTES (tail) ===\n%s\n" % (prog, notes))
    else:
        prior = "(no finished loop yet -- plan the FIRST loop from the north-star goal.)"
    brief = read(cp("brief.md"))   # rich seeded context (current state, targets, rails) -- travels every round
    brief_sec = ("=== CAMPAIGN BRIEF / SEEDED CONTEXT (authoritative -- honor it) ===\n%s\n\n" % brief) if brief.strip() else ""
    payload = (
        "=== AUTONOMOUS CAMPAIGN -- DECIDE THE NEXT LOOP ===\n"
        "You are directing a chain of Claude agent loops toward a north-star goal. OPEN the repo to see the\n"
        "actual current state, then decide the next loop (or declare the campaign done).\n\n"
        "Repo root you may read: %s\n\n"
        "=== NORTH-STAR GOAL ===\n%s\n\n"
        "%s"
        "=== PRIOR LOOPS ===\n%s\n\n%s\n" % (cwd, goal, brief_sec, hist_txt, prior)
    )
    pf, rf = cp("_director_payload.txt"), cp("_director_result.json")
    try: open(pf, "w", encoding="utf-8").write(payload)
    except Exception: return {}
    cmd = ["python3", CC_ADVISE, "--payload", pf, "--repo", cwd, "--stream", "--result-file", rf,
           "--mode", "direct_next", "--budget-file", ADV_BUDGET]
    mcpd = cfg.get("max_calls_per_day")
    if mcpd: cmd += ["--max-calls-per-day", str(mcpd)]
    # RETRY: unattended all-night runs must self-heal transient director glitches instead of pausing on the
    # first empty result. Try up to 3 times before giving up (the supervisor catches a persistent failure).
    for attempt in range(3):
        try: os.remove(rf)
        except Exception: pass
        try:
            subprocess.run(cmd, cwd=cwd, timeout=int(cfg.get("director_timeout", 360)))
        except Exception as e:
            log("  director call failed (attempt %d): %s" % (attempt + 1, str(e)[:120]))
        try:
            d = json.loads(read(rf, "{}")) or {}
        except Exception:
            d = {}
        if d.get("status"):
            return d
        if attempt < 2:
            log("  director returned no decision (attempt %d/3) -- retrying in 20s..." % (attempt + 1)); time.sleep(20)
    return {}

# ---- the INTERCEPT window (operator can edit/launch-now/pause/halt before a loop launches) ------------
def intercept(cfg, rnd, directive):
    """Surface the proposed next loop with a countdown. Returns the FINAL directive to run, or None on halt.
    Operator interactions go through pending.json (status: awaiting|go|paused) + the halt/pause control files."""
    secs = int(cfg.get("intercept_secs", 120))
    deadline = time.time() + secs
    pend = {"round": rnd, "directive": directive, "deadline": deadline, "status": "awaiting", "secs": secs}
    try: open(cp("pending.json"), "w").write(json.dumps(pend))
    except Exception: pass
    _notify({"kind": "intercept", "round": rnd, "goal": directive.get("goal", ""),
             "checklist": directive.get("checklist", []), "secs": secs})
    log("  INTERCEPT WINDOW (%ds): next loop = %r. Edit / Launch-now / Pause / Halt in the Campaigns lens, or "
        "it auto-launches." % (secs, directive.get("goal", "")))
    while time.time() < deadline:
        cs = control_state()
        if cs == "halt": return None
        if cs == "pause": wait_if_paused(); deadline = time.time() + secs; continue   # pause extends the window
        try: cur = json.loads(read(cp("pending.json"), "{}")) or {}
        except Exception: cur = {}
        if cur.get("status") == "go":                 # operator hit Launch now (possibly after editing)
            return cur.get("directive") or directive
        time.sleep(1.5)
    try:                                              # deadline reached -> proceed with whatever is current (edits honored)
        cur = json.loads(read(cp("pending.json"), "{}")) or {}
        return cur.get("directive") or directive
    except Exception:
        return directive

# ---- BUILD + RUN a Ralph loop from a directive ------------------------------------------------------
import shutil as _shutil
TMUX = _shutil.which("tmux") or "/opt/homebrew/bin/tmux"
CUR = {"sess": None, "loopdir": None}

def _loop_state(ld):
    try: return (json.loads(read(os.path.join(ld, "status.json"), "{}")) or {}).get("state", "")
    except Exception: return ""

def build_and_run(cfg, rnd, directive):
    """Create a Ralph loop from the directive and run it to completion (a Claude agent executes it). The loop
    launches as its OWN tmux session `ralph-<ln>` -- so it shows the FAMILIAR two tabs (the runner + its live
    iteration tab) in the taskbar, exactly like a normal Ralph loop -- while the campaign tab stays a clean
    director/orchestration view. We poll the loop's status.json for completion, honoring a campaign halt."""
    ln = "_camp-%s-r%d" % (NAME, rnd)
    ld = os.path.join(CC_HOME, "data", "ralph", ln)
    os.makedirs(ld, exist_ok=True)
    cwd = cfg.get("cwd") or CC_HOME
    checklist = directive.get("checklist") or [directive.get("goal", "do the work")]
    loopcfg = {"name": ln, "goal": directive.get("goal", ""), "cwd": cwd,
               "max_iters": int(cfg.get("loop_max_iters", 0) or 0),
               "timeout_sec": int(cfg.get("loop_timeout_sec", 2700) or 2700),
               "max_turns": int(cfg.get("max_turns", 200) or 200), "model": cfg.get("model", ""),
               "notify_iters": False}   # the campaign is the notifier, not each sub-loop
    open(os.path.join(ld, "loop.json"), "w").write(json.dumps(loopcfg, indent=2))
    open(os.path.join(ld, "prompt.txt"), "w").write(
        "You are the '%s' loop (campaign '%s', round %d), iteration $ITER. GOAL: %s\n\n"
        "Read progress.md, pick the FIRST unchecked item, DO it (write real code/files under the working "
        "directory), then flip its box to '- [x]' with a one-line summary. One deliverable per iteration.\n"
        % (ln, NAME, rnd, directive.get("goal", "")))
    open(os.path.join(ld, "rules.md"), "w").write(
        "# %s -- hard rules\n- Build real, working deliverables. ASCII only. Stop on a hard blocker.\n"
        "- Rationale for this loop: %s\n" % (ln, directive.get("rationale", "")))
    prog = "# %s -- progress\n\n## Round %d\n" % (ln, rnd) + "".join("- [ ] %s\n" % it for it in checklist)
    open(os.path.join(ld, "progress.md"), "w").write(prog)
    open(os.path.join(ld, "notes.md"), "w").write("")
    for ctl in ("halt", "pause"):
        try: os.remove(os.path.join(ld, ctl))
        except Exception: pass
    log("  BUILD+RUN loop %s (%d items) as tmux session ralph-%s -- open it to watch (its own runner + live tabs)."
        % (ln, len(checklist), ln))
    set_state("running", current="round %d: running loop %s" % (rnd, ln))
    sess = "ralph-" + ln
    cfgpath = os.environ.get("CC_CONFIG") or os.path.join(CC_HOME, "cc.config.json")
    subprocess.run([TMUX, "kill-session", "-t", sess], capture_output=True)
    subprocess.run([TMUX, "new-session", "-d", "-s", sess, "-c", HERE,
                    "CC_HOME=%s CC_CONFIG=%s python3 %s %s" % (CC_HOME, cfgpath, RALPH_RUNNER, ln)],
                   capture_output=True)
    CUR["loopdir"] = ld; CUR["sess"] = sess
    time.sleep(6)   # let the runner boot + write status.json (avoid a false 'gone' before it starts)
    done_states = ("done", "halted", "stopped", "stalled", "blocked", "aborted")
    while True:
        if os.path.exists(cp("halt")):
            try: open(os.path.join(ld, "halt"), "w").close()
            except Exception: pass
            subprocess.run([TMUX, "kill-session", "-t", sess], capture_output=True); break
        st = _loop_state(ld)
        alive = subprocess.run([TMUX, "has-session", "-t", sess], capture_output=True).returncode == 0
        if st in done_states or not alive:
            break
        time.sleep(5)
    subprocess.run([TMUX, "kill-session", "-t", sess + "-live"], capture_output=True)   # reap the live tab
    CUR["sess"] = None
    return ld

# Ctrl-C in the attached tab: halt the campaign (and the running loop)
def on_sigint(sig, frame):
    log("\n  [Ctrl-C] halting the campaign.");
    try: open(cp("halt"), "w").close()
    except Exception: pass
    s = CUR.get("sess")
    if s:
        try: subprocess.run([TMUX, "kill-session", "-t", s], capture_output=True)
        except Exception: pass
signal.signal(signal.SIGINT, on_sigint)

# ---- main ------------------------------------------------------------------------------------------
def main():
    cfg = load_cfg()
    max_rounds = int(cfg.get("max_rounds", 10) or 10)
    log(""); log("  ========================================================")
    log("  =  GPT-DIRECTED CAMPAIGN -- %s" % NAME)
    log("  =  north-star: %s" % (cfg.get("goal", "")[:80]))
    log("  =  max_rounds=%d  intercept=%ds  cwd=%s" % (max_rounds, int(cfg.get("intercept_secs", 120)), cfg.get("cwd", "")))
    log("  ========================================================")
    try:
        if os.path.exists(cp("pause")): os.remove(cp("pause"))
    except Exception: pass
    set_state("running", started=time.time())
    prior_loopdir = None
    rnd = int(cfg.get("round", 0)) + 1
    while True:
        if control_state() == "halt":
            log("  HALT -- stopping campaign."); set_state("halted"); break
        wait_if_paused()
        if rnd > max_rounds:
            log("  round cap (%d) reached -- stopping." % max_rounds)
            set_state("capped"); _notify({"kind": "ended", "reason": "round cap (%d) reached" % max_rounds}); break
        # 1. DIRECT
        cfg = load_cfg()
        log(""); log("  ===== ROUND %d/%d -- DIRECTOR (external GPT) planning the next loop =====" % (rnd, max_rounds))
        set_state("running", round=rnd, current="round %d: director planning" % rnd)
        d = run_director(cfg, prior_loopdir)
        if not d or not d.get("status"):
            log("  director returned nothing -- PAUSING for the operator (fail-safe).")
            open(cp("pause"), "w").close(); set_state("paused", current="director failed -- needs attention")
            _notify({"kind": "attention", "reason": "the director could not decide the next loop"}); wait_if_paused(); continue
        try:
            with open(cp("director.md"), "a") as f:
                f.write("\n## Round %d -- %s -- status: %s\n%s\n" % (rnd, time.strftime("%Y-%m-%d %H:%M"),
                        d.get("status"), d.get("assessment", "")))
        except Exception: pass
        if d.get("status") == "done":
            log("  DIRECTOR: campaign DONE -- %s" % (d.get("done_reason") or "goal met"))
            set_state("done", current=d.get("done_reason", "goal met"))
            _notify({"kind": "done", "reason": d.get("done_reason", "the director judged the north-star goal met")}); break
        directive = d.get("next_loop") or {}
        if not directive.get("goal"):
            log("  director gave no next-loop goal -- pausing (fail-safe)."); open(cp("pause"), "w").close(); wait_if_paused(); continue
        # 2. INTERCEPT
        final = intercept(cfg, rnd, directive)
        try: os.remove(cp("pending.json"))
        except Exception: pass
        if final is None:
            log("  HALT during intercept -- stopping."); set_state("halted"); break
        # 3. BUILD + RUN
        ld = build_and_run(cfg, rnd, final)
        prior_loopdir = ld
        # record history
        cfg = load_cfg()
        cfg.setdefault("history", []).append({"round": rnd, "goal": final.get("goal", ""),
                                              "loop": os.path.basename(ld), "status": "ran", "ts": time.time()})
        cfg["round"] = rnd; save_cfg(cfg)
        _notify({"kind": "loop_done", "round": rnd, "goal": final.get("goal", "")})
        if control_state() == "halt":
            log("  HALT after loop -- stopping."); set_state("halted"); break
        rnd += 1
        time.sleep(2)
    log(""); log("  campaign %s ended (state=%s, %d round(s))." % (NAME, load_cfg().get("state"), rnd - 1))

if __name__ == "__main__":
    main()
