#!/usr/bin/env bash
# cc update -- pull FRAMEWORK updates into THIS ClaudeFather deployment from an upstream.
# Per claudesole.manifest.json: copies framework_paths, NEVER touches preserve_paths (config/data/secrets)
# and NEVER propagates secrets nested inside a framework dir (rsync --exclude secrets/ etc., below),
# and splices back each file's CC:NOTES region so per-deployment learnings survive the update.
# Usage: cc-update.sh <git-url|local-dir> [--dry-run]
set -uo pipefail
CC_HOME="${CC_HOME:-$(cd "$(dirname "$0")" && pwd)}"   # self-locate: the script lives at CC_HOME root (robust to any deployment path / remote superadmin cc_update), not a hardcoded $HOME default
MAN="$CC_HOME/claudesole.manifest.json"
SRC=""; DRY=""; ALLOW_UNSIGNED=""; ROLLBACK=""
for _a in "$@"; do
  case "$_a" in
    --dry-run) DRY=1 ;;
    --allow-unsigned) ALLOW_UNSIGNED=1 ;;   # proceed past an UNSIGNED upstream (never past active tampering)
    --rollback) ROLLBACK=1 ;;               # restore the pre-update framework snapshot (deep-audit #5)
    *) [ -z "$SRC" ] && SRC="$_a" ;;
  esac
done
[ -f "$MAN" ] || { echo "no manifest at $MAN"; exit 1; }

# Resolve this install's STATE dir (honors CC_CONFIG + cc.config state_dir, exactly like server.py) -- home of the
# rollback snapshot + the pending-update marker (deep-audit #5: node-side post-ship rollback).
STATE="$(python3 - "$CC_HOME" <<'PY' 2>/dev/null || echo "$CC_HOME/command-center"
import json, os, sys
home = sys.argv[1]
cfg = os.environ.get("CC_CONFIG") or os.path.join(home, "cc.config.json")
d = os.path.join(home, "command-center")
try: d = os.path.expanduser((json.load(open(cfg)) or {}).get("state_dir") or d)
except Exception: pass
print(d)
PY
)"
ROLLBACK_DIR="$STATE/_rollback"; SNAP="$ROLLBACK_DIR/rollback.tar.gz"; PENDING="$STATE/_update_pending.json"

# --rollback: restore the snapshot taken before the last update, then print the restart command. Self-heal path
# for a node that came up broken on a new version (invoked by the supervisor guard, an operator, or MC).
if [ -n "$ROLLBACK" ]; then
  [ -f "$SNAP" ] || { echo "no rollback snapshot at $SNAP -- nothing to restore"; exit 1; }
  echo "rolling back framework from $SNAP ..."
  tar -xzf "$SNAP" -C "$CC_HOME" || { echo "rollback extract FAILED"; exit 1; }
  [ -f "$CC_HOME/VERSION" ] && python3 -c "import json;print(json.load(open('$MAN')).get('version',''))" > "$CC_HOME/VERSION"
  python3 -c "import json,os;p='$PENDING';os.path.exists(p) and os.remove(p)" 2>/dev/null || true
  echo "  restored framework to $(python3 -c "import json;print(json.load(open('$MAN')).get('version'))")"
  _CFG="${CC_CONFIG:-$CC_HOME/cc.config.json}"
  SESS="$(python3 -c "import json,sys;print((json.load(open(sys.argv[1])).get('session') or 'claudefather'))" "$_CFG" 2>/dev/null || echo claudefather)"
  TMUXBIN="$(command -v tmux || echo /opt/homebrew/bin/tmux)"
  echo "Done. Restart to load the rollback: TMUX_TMPDIR=/tmp $TMUXBIN kill-session -t $SESS"
  exit 0
fi

[ -z "$SRC" ] && { echo "usage: cc-update.sh <git-url|local-dir> [--dry-run] [--allow-unsigned] | --rollback"; exit 1; }

TMP=""
if [ -d "$SRC" ]; then UP="$SRC"
else TMP=$(mktemp -d); echo "cloning $SRC ..."; git clone --depth 1 -q "$SRC" "$TMP" || { echo "clone failed"; exit 1; }; UP="$TMP"; fi
[ -f "$UP/claudesole.manifest.json" ] || { echo "upstream is not a ClaudeFather framework (no manifest)"; [ -n "$TMP" ] && rm -rf "$TMP"; exit 1; }

echo "local    version: $(python3 -c "import json;print(json.load(open('$MAN')).get('version'))")"
echo "upstream version: $(python3 -c "import json;print(json.load(open('$UP/claudesole.manifest.json')).get('version'))")"
[ -n "$DRY" ] && echo "(dry run -- nothing written)"

# SUPPLY-CHAIN GATE (deep-audit P1-8): before overlaying ANY framework code, verify the upstream is signed by
# THIS box's existing trust root (superadmin.pub/recovery.pub) and that the files match the signed hashes -- so
# a wrong/malicious upstream (or a swapped-in server.py / trust root) is caught BEFORE it lands + runs. Policy
# from cc.config `update_verify`: "warn" (default -- verify + LOUD warn, still apply, matches the MESH_ENFORCE/
# POLICY_ENFORCE staged-rollout convention), "enforce" (BLOCK on failure), "off" (skip). `--allow-unsigned` lets
# one run proceed past an UNSIGNED upstream (exit 2) but NEVER past active tampering (exit 1). Dry-runs skip.
VP="$CC_HOME/command-center/verify_update.py"
if [ -z "$DRY" ] && [ -f "$VP" ]; then
  VMODE="$(python3 -c "import json,os;cfg=os.environ.get('CC_CONFIG') or '$CC_HOME/cc.config.json';print((json.load(open(cfg)).get('update_verify') or 'warn').lower())" 2>/dev/null || echo warn)"
  if [ "$VMODE" != "off" ]; then
    python3 "$VP" "$UP" "$CC_HOME"; VRC=$?
    if [ "$VRC" -eq 0 ]; then
      :   # VERIFIED -- proceed
    elif [ "$VRC" -eq 2 ] && [ -n "$ALLOW_UNSIGNED" ]; then
      echo "  update-verify: proceeding past an UNSIGNED upstream (--allow-unsigned)."
    elif [ "$VMODE" = "enforce" ]; then
      echo "  update-verify: BLOCKED (update_verify=enforce) -- refusing to apply an unverified framework update."
      [ -n "$TMP" ] && rm -rf "$TMP"; exit 3
    else
      echo "  update-verify: WARNING -- applying an unverified update anyway (update_verify=warn). Set update_verify:enforce to block, or investigate the upstream."
    fi
  fi
fi

# Build the rsync --exclude set from the UPSTREAM manifest's never_ship list (single source of truth, ships with
# the framework so it stays in sync across cc-update / make-install-package / cc-newinstance). Fall back to the
# historical hardcoded set if an older upstream lacks never_ship. (deep-audit 2026-07-09 finding 0.4.)
EXCL=(); while IFS= read -r pat; do [ -n "$pat" ] && EXCL+=( --exclude="$pat" ); done \
  < <(python3 -c "import json;[print(p) for p in json.load(open('$UP/claudesole.manifest.json')).get('never_ship',[])]" 2>/dev/null)
[ ${#EXCL[@]} -eq 0 ] && EXCL=( --exclude='secrets/' --exclude='secrets' --exclude='*.local' --exclude='.env' --exclude='.env.*' )

# SNAPSHOT BEFORE OVERLAY (deep-audit #5): tar the CURRENT (about-to-be-replaced) framework into the rollback dir
# and drop a pending-update marker, so a node that comes up BROKEN on the new version can be restored to exactly
# the code it was running. Cheap (code is small), reversible, and skipped on a dry run. Never fatal -- a snapshot
# failure warns but still applies the update (we don't block a legit update because the snapshot couldn't be taken).
# Only for a REAL install (has cc.config.json) -- a bare dist mirror has no running node to protect, and writing
# the snapshot/marker there would pollute the dist repo's `git add -A`. Skipped on dry runs.
if [ -z "$DRY" ] && [ -f "$CC_HOME/cc.config.json" ]; then
  mkdir -p "$ROLLBACK_DIR" 2>/dev/null
  if python3 - "$CC_HOME" "$MAN" "$UP/claudesole.manifest.json" "$SNAP" "$PENDING" <<'PY'
import glob, json, os, sys, tarfile, time
home, man, upman, snap, pending = sys.argv[1:6]
from_v = (json.load(open(man)) or {}).get("version", "")
to_v = (json.load(open(upman)) or {}).get("version", "")
fps = (json.load(open(man)) or {}).get("framework_paths", [])
never = (json.load(open(man)) or {}).get("never_ship", []) or ["secrets/", "secrets", ".env", ".env.*", "*.local"]
def excluded(rel):
    base = os.path.basename(rel.rstrip("/"))
    import fnmatch
    return any(fnmatch.fnmatch(base, p.rstrip("/")) or ("/" + p.rstrip("/") + "/") in ("/" + rel + "/") for p in never)
# collect the CURRENT (about-to-be-replaced) framework files that exist, glob-expanded, minus never_ship
members = []
for p in fps:
    for ab in glob.glob(os.path.join(home, p)):
        rel = os.path.relpath(ab, home)
        if excluded(rel): continue
        members.append(rel)
try:
    with tarfile.open(snap, "w:gz") as t:
        for rel in sorted(set(members)):
            t.add(os.path.join(home, rel), arcname=rel,
                  filter=lambda ti: None if excluded(ti.name) else ti)
    open(pending, "w").write(json.dumps({"from": from_v, "to": to_v, "snapshot": snap,
        "ts": int(time.time()), "attempts": 0, "confirmed": False}))
    print("  snapshot saved (rollback point v%s) -> %s" % (from_v, snap))
except Exception as e:
    print("  (warning: could not take a rollback snapshot: %s -- applying the update anyway)" % str(e)[:100])
    sys.exit(1)
PY
  then :; else :; fi
fi

python3 -c "import json;[print(p) for p in json.load(open('$UP/claudesole.manifest.json'))['framework_paths']]" | while read -r p; do
  for s in $UP/$p; do
    [ -e "$s" ] || continue
    rel="${s#$UP/}"; dst="$CC_HOME/$rel"
    if [ -d "$s" ]; then
      [ -n "$DRY" ] && { echo "  dir  $rel/"; continue; }
      # NEVER propagate per-deployment secrets that may live inside a framework dir (e.g.
      # extensions/*/secrets/ -- OAuth client JSON + refresh tokens). rsync ignores .gitignore, so without
      # these excludes one tenant's secret would replicate to every node on update. (CCR: rsync-secrets-exclude.)
      mkdir -p "$dst"; rsync -a "${EXCL[@]}" "$s/" "$dst/"; echo "  updated dir  $rel/"
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

# Keep the VERSION stamp truthful. Bundles/mirrors carry a VERSION file (written at build time) but updates
# only refreshed the manifest, so VERSION drifted (the public dist advertised 0.12.5 while shipping 0.99.x).
# The manifest is the single source of truth -- restamp from it whenever a VERSION file exists here.
if [ -z "$DRY" ] && [ -f "$CC_HOME/VERSION" ]; then
  python3 -c "import json;print(json.load(open('$MAN')).get('version',''))" > "$CC_HOME/VERSION"
  echo "  stamped VERSION $(cat "$CC_HOME/VERSION")"
fi

# Derive THIS install's session name from its own config (default `claudefather`) + resolve tmux portably, so
# the printed restart command is correct on ANY install -- not the dev box's `hpcc` / Homebrew path (P1-5/P1-6).
if [ -z "$DRY" ]; then
  _CFG="${CC_CONFIG:-$CC_HOME/cc.config.json}"
  SESS="$(python3 -c "import json,sys;print((json.load(open(sys.argv[1])).get('session') or 'claudefather'))" "$_CFG" 2>/dev/null || echo claudefather)"
  TMUXBIN="$(command -v tmux || echo /opt/homebrew/bin/tmux)"
  echo "Done. Restart to load updates: TMUX_TMPDIR=/tmp $TMUXBIN kill-session -t $SESS"
fi
