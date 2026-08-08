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
# PORT GUARD. If something ELSE already holds this instance's port, spawning another server is pointless: it
# binds, fails with "Address already in use", exits, the session ends, and this supervisor loops again --
# every ~10s, forever, invisibly. A real one ran 2532 times in 7 hours while the node looked perfectly healthy
# (an ORPHANED server, detached from its tmux session by an in-place execv restart, was serving the port fine).
# Nothing surfaced it because a supervisor restarting is normal and the service really was up. So: detect the
# squatter, say so LOUDLY in the log, and back off instead of spinning. If the holder is a healthy server for
# this same instance, there is nothing to fix -- leave it serving.
_PORT="$(python3 -c "import json,os,sys;print(json.load(open(sys.argv[1])).get('port') or '')" "$CFG" 2>/dev/null)"
if [ -n "$_PORT" ] && ! "$TMUX" has-session -t "$SESS" 2>/dev/null; then
  _HOLD="$(lsof -nP -iTCP:"$_PORT" -sTCP:LISTEN -t 2>/dev/null | head -1)"
  if [ -n "$_HOLD" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') [supervise] port $_PORT already held by pid $_HOLD and no '$SESS' session exists." >> "/tmp/$SESS.err.log"
    echo "  That process is almost certainly an ORPHANED instance of this same node (an execv restart keeps the pid but loses the tmux session)." >> "/tmp/$SESS.err.log"
    echo "  Launching another server here would only crash on bind. Backing off 60s. To adopt cleanly: kill $_HOLD and let this supervisor respawn." >> "/tmp/$SESS.err.log"
    sleep 60
    exit 0
  fi
fi
if ! "$TMUX" has-session -t "$SESS" 2>/dev/null; then
  _INST_HOME="$(cd "$CCDIR/.." 2>/dev/null && pwd)"   # CC_HOME = parent of this bundle's command-center
  CC_CONFIG="$CFG" python3 "$CCDIR/rollback_guard.py" "$_INST_HOME" 2>/dev/null || true  # #5: self-heal a won't-boot update before launch (no-op unless one is stuck)
  "$TMUX" new-session -d -s "$SESS" -c "$CCDIR" "CC_CONFIG=$CFG python3 server.py >>/tmp/$SESS.out.log 2>>/tmp/$SESS.err.log"
fi
while "$TMUX" has-session -t "$SESS" 2>/dev/null; do sleep 5; done
