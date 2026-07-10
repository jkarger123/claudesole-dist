#!/bin/bash
# Generic ClaudeFather instance supervisor. Runs an instance as a session on the SHARED (brain) tmux
# server (so it inherits TCC context incl. external-SSD access, like the main CC), and stays foreground
# while it lives so launchd KeepAlive can restart it. Reusable for ANY nested instance.
# Usage (via launchd): cc-instance-supervise.sh <CC_CONFIG path> <tmux session name>
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export TMUX_TMPDIR=/tmp
# Resolve tmux portably (Homebrew Apple-Silicon path is just the fallback; Intel Macs use /usr/local, Linux
# uses /usr/bin -- a hardcoded /opt/homebrew path silently breaks the supervisor there). Matches server.py.
TMUX="$(command -v tmux || echo /opt/homebrew/bin/tmux)"
# Derive THIS bundle's command-center from the script's own location so a standalone/relocated bundle
# runs its OWN server.py (portable). Falls back to the canonical path if resolution fails.
CCDIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
[ -f "$CCDIR/server.py" ] || CCDIR="${CC_HOME:-$HOME/claudefather}/command-center"
CFG="${1:-${CC_HOME:-$HOME/claudefather}/instances/overseer/cc.config.json}"
SESS="${2:-cc-overseer}"
if ! "$TMUX" has-session -t "$SESS" 2>/dev/null; then
  _INST_HOME="$(cd "$CCDIR/.." 2>/dev/null && pwd)"   # CC_HOME = parent of this bundle's command-center
  CC_CONFIG="$CFG" python3 "$CCDIR/rollback_guard.py" "$_INST_HOME" 2>/dev/null || true  # #5: self-heal a won't-boot update before launch (no-op unless one is stuck)
  "$TMUX" new-session -d -s "$SESS" -c "$CCDIR" "CC_CONFIG=$CFG python3 server.py >>/tmp/$SESS.out.log 2>>/tmp/$SESS.err.log"
fi
while "$TMUX" has-session -t "$SESS" 2>/dev/null; do sleep 5; done
