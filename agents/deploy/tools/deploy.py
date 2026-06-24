#!/usr/bin/env python3
"""Deploy agent -- GATED executor. Runs a target's deploy_cmd ONLY with --yes. Never auto-fires.
ASCII-only."""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)


def load_config():
    try:
        return json.load(open(os.path.join(os.environ.get("CC_AGENT_STATE") or AGENT, "config.json")))
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description="Run a configured deploy target (gated by --yes).")
    ap.add_argument("--target", required=True, help="target name from config.json")
    ap.add_argument("--yes", action="store_true", help="actually run it (without this, prints the plan only)")
    args = ap.parse_args()

    cfg = load_config()
    if not cfg or not cfg.get("targets"):
        print("ERROR: no config.json / no targets. Copy config.example.json first.")
        sys.exit(2)
    t = next((x for x in cfg["targets"] if x.get("name") == args.target), None)
    if not t:
        print("ERROR: no target named %r. Have: %s" %
              (args.target, ", ".join(x.get("name", "?") for x in cfg["targets"])))
        sys.exit(2)
    cmd = t.get("deploy_cmd")
    cwd = t.get("cwd") or os.getcwd()
    if not cmd:
        print("ERROR: target %r has no deploy_cmd." % args.target)
        sys.exit(2)

    print("Target : %s" % args.target)
    print("Cwd    : %s" % cwd)
    print("Command: %s" % cmd)
    if not args.yes:
        print("\n[DRY RUN] add --yes to actually deploy. Nothing was run.")
        return
    print("\n[RUNNING] (human-approved via --yes)\n")
    rc = subprocess.call(cmd, shell=True, cwd=cwd)
    print("\nexit code: %d" % rc)
    sys.exit(rc)


if __name__ == "__main__":
    main()
