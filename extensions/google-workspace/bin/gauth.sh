#!/usr/bin/env bash
# gauth.sh -- one-command headless Google auth for the workspace-mcp (Path B) extension.
# Mints a refresh token for a single account, handling the remote-host reverse-tunnel case.
#
# Usage:
#   bin/gauth.sh                       # local: browser is on THIS host
#   bin/gauth.sh --remote <ssh-host>   # remote: open consent URL on <ssh-host>'s browser
#                                      #         (reverse-tunnels the callback to it; needs working
#                                      #          OUTBOUND ssh from here to <ssh-host>)
#
# Env (or edit the defaults): ACCOUNT, SECRETS_DIR, PORT, PERMS
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ACCOUNT="${ACCOUNT:?set ACCOUNT=the-account@gmail.com}"
PORT="${PORT:-8765}"
REMOTE_HOST=""
[ "${1:-}" = "--remote" ] && REMOTE_HOST="${2:?--remote needs an ssh host}"

LOG="$(mktemp -t gauth.XXXXXX)"
DRIVER_PID=""; TUNNEL_PID=""
cleanup() { [ -n "$DRIVER_PID" ] && kill "$DRIVER_PID" 2>/dev/null || true
            [ -n "$TUNNEL_PID" ] && kill "$TUNNEL_PID" 2>/dev/null || true; }
trap cleanup EXIT

echo "[gauth] starting unbuffered token minter on localhost:$PORT ..."
PYTHONUNBUFFERED=1 ACCOUNT="$ACCOUNT" PORT="$PORT" \
  nohup uv run --with workspace-mcp python -u "$HERE/mint_token.py" >"$LOG" 2>&1 &
DRIVER_PID=$!

# wait for the callback server to bind + the consent URL to appear
for _ in $(seq 1 30); do sleep 1; grep -q "AUTH_URL>>>" "$LOG" && break; done
URL="$(grep -m1 "AUTH_URL>>>" "$LOG" | sed 's/^AUTH_URL>>> //')"
[ -z "$URL" ] && { echo "[gauth] ERROR: no consent URL (check $LOG)"; cat "$LOG"; exit 1; }

if [ -n "$REMOTE_HOST" ]; then
  echo "[gauth] opening reverse tunnel  $REMOTE_HOST:localhost:$PORT  ->  here:$PORT ..."
  nohup ssh -N -R "$PORT:localhost:$PORT" -o ExitOnForwardFailure=yes \
        -o ServerAliveInterval=30 "$REMOTE_HOST" >/dev/null 2>&1 &
  TUNNEL_PID=$!
  sleep 3
  echo "[gauth] On $REMOTE_HOST, open this URL in a browser and approve (sign in AS $ACCOUNT):"
else
  echo "[gauth] Open this URL in a browser on THIS host and approve (sign in AS $ACCOUNT):"
fi
echo; echo "  $URL"; echo
echo "[gauth] waiting for you to complete consent ..."

# block until the driver stores the token (or dies)
wait "$DRIVER_PID"; DRIVER_PID=""
if grep -q "STORED: True" "$LOG"; then
  echo "[gauth] OK -- token minted + stored. Refresh token present:"
  grep -E "REFRESH_TOKEN_PRESENT|GRANTED_SCOPES" "$LOG"
  echo "[gauth] Now verify:  ACCOUNT=$ACCOUNT uv run --with workspace-mcp python -u $HERE/verify.py"
else
  echo "[gauth] FAILED -- see log:"; cat "$LOG"; exit 1
fi
