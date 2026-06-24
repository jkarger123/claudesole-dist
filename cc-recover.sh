#!/usr/bin/env bash
# cc-recover.sh — BREAK-GLASS access recovery.
# Run this in ANY terminal as the owner when you can't get into a ClaudeFather web console. It prints every
# node on this machine: its login PIN (auth_token), port, and tailnet URL — so you can always get back in.
# Reads the live configs directly (owner-only 0600 files), so it works even when the web UI is down.
set -uo pipefail
CC_HOME="$(cd "$(dirname "$0")" && pwd)"
echo "================ ClaudeFather access recovery — $(date) ================"
echo "Can't reach a console? Check these IN ORDER:"
echo "  1) Is Tailscale ON on the device you're using?  (dashboards are tailnet-only — #1 cause of 'looks broken')"
echo "  2) Use a PIN below at the /login screen for that node's URL."
echo "  3) Still stuck? the server may be down — check: launchctl list | grep claudesole   (KeepAlive respawns it)"
echo
echo "---- nodes on this machine ($CC_HOME) ----"
shopt -s nullglob
for cfg in "$CC_HOME/cc.config.json" "$CC_HOME"/instances/*/cc.config.json; do
  [ -f "$cfg" ] || continue
  python3 - "$cfg" <<'PY'
import json, sys
try: c = json.load(open(sys.argv[1]))
except Exception as e: print("  (could not read %s: %s)" % (sys.argv[1], e)); raise SystemExit
brand = c.get("brand") or c.get("project_name") or "?"
pin   = c.get("auth_token") or "(open — no PIN set)"
mesh  = c.get("mesh_token")
print("• %-18s  port %-5s  PIN: %s" % (brand, c.get("port", "?"), pin))
print("    role=%s  wallet=%s  mesh_token=%s" % (
    c.get("role", "project"), bool(c.get("account_wallet")),
    (mesh[:10] + "…") if mesh else "(none)"))
print("    config: %s" % sys.argv[1])
PY
done
echo
if [ -f "$CC_HOME/peers.json" ]; then
  echo "---- tailnet URLs (peers.json) ----"
  python3 -c "import json
try:
    for p in json.load(open('$CC_HOME/peers.json')): print('  %-16s %s' % (p.get('id','?'), p.get('url','?')))
except Exception as e: print('  (peers.json unreadable: %s)' % e)" 2>/dev/null
fi
echo
echo "---- recent credential changes (if any were detected at boot) ----"
if [ -f "$HOME/.cc-credential-changes.log" ]; then tail -5 "$HOME/.cc-credential-changes.log"; else echo "  (none logged — good)"; fi
echo "======================================================================"
