#!/usr/bin/env bash
# cc update -- pull FRAMEWORK updates into THIS ClaudeFather deployment from an upstream.
# Per claudesole.manifest.json: copies framework_paths, NEVER touches preserve_paths (config/data/secrets)
# and NEVER propagates secrets nested inside a framework dir (rsync --exclude secrets/ etc., below),
# and splices back each file's CC:NOTES region so per-deployment learnings survive the update.
# Usage: cc-update.sh <git-url|local-dir> [--dry-run]
set -uo pipefail
CC_HOME="${CC_HOME:-$(cd "$(dirname "$0")" && pwd)}"   # self-locate: the script lives at CC_HOME root (robust to any deployment path / remote superadmin cc_update), not a hardcoded $HOME default
MAN="$CC_HOME/claudesole.manifest.json"
SRC="${1:-}"; DRY=""; [ "${2:-}" = "--dry-run" ] && DRY=1
[ -z "$SRC" ] && { echo "usage: cc-update.sh <git-url|local-dir> [--dry-run]"; exit 1; }
[ -f "$MAN" ] || { echo "no manifest at $MAN"; exit 1; }

TMP=""
if [ -d "$SRC" ]; then UP="$SRC"
else TMP=$(mktemp -d); echo "cloning $SRC ..."; git clone --depth 1 -q "$SRC" "$TMP" || { echo "clone failed"; exit 1; }; UP="$TMP"; fi
[ -f "$UP/claudesole.manifest.json" ] || { echo "upstream is not a ClaudeFather framework (no manifest)"; [ -n "$TMP" ] && rm -rf "$TMP"; exit 1; }

echo "local    version: $(python3 -c "import json;print(json.load(open('$MAN')).get('version'))")"
echo "upstream version: $(python3 -c "import json;print(json.load(open('$UP/claudesole.manifest.json')).get('version'))")"
[ -n "$DRY" ] && echo "(dry run -- nothing written)"

python3 -c "import json;[print(p) for p in json.load(open('$UP/claudesole.manifest.json'))['framework_paths']]" | while read -r p; do
  for s in $UP/$p; do
    [ -e "$s" ] || continue
    rel="${s#$UP/}"; dst="$CC_HOME/$rel"
    if [ -d "$s" ]; then
      [ -n "$DRY" ] && { echo "  dir  $rel/"; continue; }
      # NEVER propagate per-deployment secrets that may live inside a framework dir (e.g.
      # extensions/*/secrets/ -- OAuth client JSON + refresh tokens). rsync ignores .gitignore, so without
      # these excludes one tenant's secret would replicate to every node on update. (CCR: rsync-secrets-exclude.)
      mkdir -p "$dst"; rsync -a --exclude='secrets/' --exclude='secrets' --exclude='*.local' --exclude='.env' --exclude='.env.*' "$s/" "$dst/"; echo "  updated dir  $rel/"
    else
      [ -n "$DRY" ] && { echo "  file $rel"; continue; }
      mkdir -p "$(dirname "$dst")"
      # CC:NOTES preservation is ONLY for markdown docs (CLAUDE.md etc.) -- a code file like server.py
      # contains the literal "<!-- CC:NOTES -->" marker strings IN ITS CODE, and splicing on those reverts
      # the file to the old copy while the version still bumps ("version bumped, code stale"). Code = verbatim.
      case "$rel" in
        *.md)
          if [ -f "$dst" ] && grep -q "CC:NOTES" "$dst" 2>/dev/null; then
            python3 - "$s" "$dst" <<'PY'
import sys,re
up=open(sys.argv[1]).read(); cur=open(sys.argv[2]).read()
m=re.search(r'<!-- CC:NOTES.*?<!-- /CC:NOTES -->', cur, re.S)
out=re.sub(r'<!-- CC:NOTES.*?<!-- /CC:NOTES -->', lambda _:m.group(0), up, flags=re.S) if m else up
open(sys.argv[2],'w').write(out)
PY
            echo "  updated file $rel (kept CC:NOTES)"
          else
            cp -p "$s" "$dst"; echo "  updated file $rel"
          fi ;;
        *)
          cp -p "$s" "$dst"; echo "  updated file $rel" ;;
      esac
    fi
  done
done

[ -n "$TMP" ] && rm -rf "$TMP"
echo

# Lock secret-bearing PRESERVE files to owner-only (0600) right after the update -- mirrors server.py's
# boot self-heal, but closes the window BEFORE the next CC restart (the only gap that remained: an update
# could land while perms were still 644 until the operator restarted). Resolves paths exactly as server.py
# does (honors CC_CONFIG env + cc.config state_dir/peers_file overrides). (CCR: secret-file-perms.)
if [ -z "$DRY" ]; then
  python3 - "$CC_HOME" <<'PY'
import json, os, sys
home = sys.argv[1]
cfg_path = os.environ.get("CC_CONFIG") or os.path.join(home, "cc.config.json")
cc = {}
try: cc = json.load(open(cfg_path))
except Exception: pass
state = os.path.expanduser(cc.get("state_dir") or os.path.join(home, "command-center"))
for p in (cfg_path,
          os.path.expanduser(cc.get("peers_file") or os.path.join(home, "peers.json")),
          os.path.join(state, "_mesh_hook_settings.json")):
    try:
        if os.path.isfile(p): os.chmod(p, 0o600); print("  secured 0600 " + p)
    except Exception as e: print("  (could not chmod %s: %s)" % (p, e))
PY
fi

[ -z "$DRY" ] && echo "Done. Restart to load updates: TMUX_TMPDIR=/tmp /opt/homebrew/bin/tmux kill-session -t hpcc"
