#!/usr/bin/env python3
"""incident-commander readiness report (common agent-report schema). The real triage is INTERACTIVE -- see
CLAUDE.md: talk to the agent and it ranks Sentry issues + PagerDuty incidents/on-call + local logs. This
run.py just reports which incident sources are wired so the Agents lens shows a clean posture. Read-only;
never acts. ASCII only."""
import json, os, time, glob

def _installed():
    out = set()
    # self-locate CC_HOME: when installed this is <CC_HOME>/agents/incident-commander/tools/run.py (portable)
    cch = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    paths = [os.path.join(cch, "command-center", "_extensions.json")]
    paths += glob.glob(os.path.join(cch, "instances", "*", "state", "_extensions.json"))
    for p in paths:
        try: out |= set(json.load(open(p)).get("installed", []))
        except Exception: pass
    return out

def main():
    inst = _installed()
    deps = [("sentry", "production errors / issues"), ("pagerduty", "incidents + on-call")]
    items = [{"name": k, "status": ("active" if k in inst else "not installed"), "detail": v} for k, v in deps]
    active = [k for k, _ in deps if k in inst]
    overall = "ok" if active else "warn"
    note = ("Talk to this agent for a ranked incident posture (Sentry + PagerDuty + local logs)."
            if active else
            "Logs-only: install the sentry and/or pagerduty extensions for full incident coverage, then talk to me.")
    rep = {"slug": "incident-commander", "title": "Incident Commander", "overall": overall,
           "counts": {"sources_active": len(active), "sources_possible": len(deps)},
           "items": items, "note": note, "ts": int(time.time())}
    out_dir = os.environ.get("CC_AGENT_STATE") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rdir = os.path.join(out_dir, "reports")
    try:
        os.makedirs(rdir, exist_ok=True)
        json.dump(rep, open(os.path.join(rdir, "latest.json"), "w"), indent=2)
    except Exception:
        pass
    print(json.dumps(rep, indent=2))

if __name__ == "__main__":
    main()
