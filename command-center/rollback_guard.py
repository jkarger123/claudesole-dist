#!/usr/bin/env python3
# Post-ship rollback guard (deep-audit #5). Run by the supervisor BEFORE it (re)launches server.py. If a framework
# update is pending-confirmation and has failed to come up healthy across several launches, restore the pre-update
# snapshot (cc-update.sh --rollback) so a node that won't boot on a bad ship self-heals instead of crash-looping.
#
# Contract: no-op (exit 0) when there's no pending update -> zero overhead on a normal launch. Every error is
# swallowed -> the guard can NEVER block a launch. On a HEALTHY update, server.py clears the marker shortly after
# boot (_update_confirm), so subsequent launches find no marker. The marker only survives when boot keeps failing.
#
# Usage: rollback_guard.py <CC_HOME>   (honors CC_CONFIG env for state_dir resolution, like server.py/cc-update.sh)
import json, os, subprocess, sys, time

THRESHOLD = 3   # failed launches (server never confirmed) before we roll back

def main():
    home = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CC_HOME") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = os.environ.get("CC_CONFIG") or os.path.join(home, "cc.config.json")
    state = os.path.join(home, "command-center")
    try: state = os.path.expanduser((json.load(open(cfg)) or {}).get("state_dir") or state)
    except Exception: pass
    pending = os.path.join(state, "_update_pending.json")
    if not os.path.isfile(pending):
        return 0
    try:
        p = json.load(open(pending))
    except Exception:
        return 0
    if p.get("confirmed"):
        try: os.remove(pending)
        except Exception: pass
        return 0
    attempts = int(p.get("attempts") or 0) + 1
    p["attempts"] = attempts
    if attempts < THRESHOLD:
        try: json.dump(p, open(pending, "w"))            # record the try; give the server another chance to boot healthy
        except Exception: pass
        return 0
    # too many failed launches -> the new version isn't coming up. Roll back to the snapshot.
    script = os.path.join(home, "cc-update.sh")
    if not os.path.isfile(script):
        return 0
    log = os.path.join(state, "_autoupdate.log")
    def _log(m):
        try:
            with open(log, "a") as f: f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + "rollback_guard " + m + "\n")
        except Exception: pass
    _log("update to v%s failed to come up healthy after %d launches -> ROLLING BACK to v%s" % (p.get("to"), attempts, p.get("from")))
    try:
        env = dict(os.environ, CC_HOME=home, CC_CONFIG=cfg)
        r = subprocess.run(["bash", script, "--rollback"], capture_output=True, text=True, timeout=120, env=env)
        _log("rollback %s%s" % ("OK" if r.returncode == 0 else "FAILED", "" if r.returncode == 0 else (": " + (r.stderr or r.stdout)[-160:])))
    except Exception as e:
        _log("rollback error: " + str(e)[:160])
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception:
        sys.exit(0)   # never block the launch
