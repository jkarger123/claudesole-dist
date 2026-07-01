#!/usr/bin/env bash
# enable-services.sh -- ONE-COMMAND activation for Google services (sheets/docs/forms, etc.) on an
# ALREADY-installed google-workspace extension whose token predates those scopes. It does BOTH steps in a
# single run: (1) idempotently adds the services to the LIVE deployment .mcp.json, and (2) re-mints the token
# so Google consents the new scopes. You just: run it -> open the ONE printed consent URL -> click Allow ->
# restart the node. (Fresh installs don't need this -- SETUP.md already mints with these services.)
#
# Usage (stage into the Admin shell; the operator hits enter, then approves in a browser):
#   ACCOUNT=you@gmail.com bin/enable-services.sh                       # browser is on THIS host
#   ACCOUNT=you@gmail.com bin/enable-services.sh --remote <ssh-host>   # browser is on a remote host (reverse tunnel)
# Env: ACCOUNT (required); SERVICES (default "sheets:full docs:full forms:full"); CC_HOME (auto); PORT (default 8765).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ACCOUNT="${ACCOUNT:?set ACCOUNT=the-account@gmail.com}"
SERVICES="${SERVICES:-sheets:full docs:full forms:full}"
CC_HOME="${CC_HOME:-$(cd "$HERE/../../.." && pwd)}"
MCP="$CC_HOME/.mcp.json"
[ -f "$MCP" ] || { echo "[enable] ERROR: no live .mcp.json at $MCP -- install + set up the extension first."; exit 1; }

# 1) idempotently add SERVICES to the google server's --permissions in the LIVE .mcp.json, and print back the
#    FULL permission set so the re-mint requests exactly what the server will run with.
FULL_PERMS="$(SERVICES="$SERVICES" MCP="$MCP" python3 - <<'PY'
import json, os, sys
mcp = os.environ["MCP"]; svcs = os.environ["SERVICES"].split()
d = json.load(open(mcp))
srv = (d.get("mcpServers") or {}).get("google")
if not srv: sys.stderr.write("[enable] no 'google' server in .mcp.json\n"); sys.exit(3)
args = srv.get("args", [])
if "--permissions" in args:
    i = args.index("--permissions"); j = i + 1
    while j < len(args) and (":" in args[j]) and not args[j].startswith("--"): j += 1
    perms = args[i + 1:j]
    have = {p.split(":")[0] for p in perms}
    perms = perms + [s for s in svcs if s.split(":")[0] not in have]   # add only missing services (idempotent)
    args = args[:i + 1] + perms + args[j:]
else:
    perms = list(svcs); args = args + ["--permissions"] + perms
srv["args"] = args
tmp = mcp + ".tmp"; json.dump(d, open(tmp, "w"), indent=2); os.chmod(tmp, 0o600); os.replace(tmp, mcp)
print(" ".join(perms))
PY
)"
echo "[enable] live .mcp.json google scopes -> $FULL_PERMS"

# 2) re-mint with the FULL perms (reuses gauth.sh: prints the consent URL, handles the --remote reverse tunnel,
#    stores the refresh token). mint_token.py reads PERMS from the environment.
echo "[enable] re-minting the token so Google consents the new scopes ..."
ACCOUNT="$ACCOUNT" PERMS="$FULL_PERMS" "$HERE/gauth.sh" "$@"

echo
echo "[enable] DONE. Now RESTART this node so the MCP reloads with the new tools:"
echo "         local node   : TMUX_TMPDIR=/tmp /opt/homebrew/bin/tmux kill-session -t <hpcc|cc-overseer|cc-carsearch>"
echo "         appliance/AFP: ask Mission Control to superadmin 'restart' this node"
echo "[enable] Verify:  ACCOUNT=$ACCOUNT uv run --with workspace-mcp python -u $HERE/verify.py"
