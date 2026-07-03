#!/usr/bin/env bash
# Build a portable ClaudeFather install package: a zip of the FRAMEWORK (per claudesole.manifest.json
# framework_paths) + the agent playbook + bootstrap. Point a Claude Code instance at the unzipped
# AGENT_INSTALL.md and it installs a new project or migrates an existing one. Output: dist/claudefather-install.zip
set -uo pipefail
CC_HOME="${CC_HOME:-$(cd "$(dirname "$0")" 2>/dev/null && pwd)}"
cd "$CC_HOME"
[ -f claudesole.manifest.json ] || { echo "no manifest at $CC_HOME"; exit 1; }

OUT="$CC_HOME/dist"; mkdir -p "$OUT"
TMP="$(mktemp -d)"; STAGE="$TMP/claudefather"; mkdir -p "$STAGE"

# 1) copy every framework_path (globs expand; dirs copied recursively). preserve_paths (state/secrets) are
#    excluded by construction -- only framework_paths are listed.
python3 -c "import json;[print(p) for p in json.load(open('claudesole.manifest.json'))['framework_paths']]" | while read -r p; do
  for s in $p; do
    [ -e "$s" ] || continue
    mkdir -p "$STAGE/$(dirname "$s")"
    cp -R "$s" "$STAGE/$(dirname "$s")/"
  done
done

# 2) the install guides + bootstrap at the package ROOT (what README points Claude Code at)
cp install/AGENT_INSTALL.md install/README_INSTALL.md "$STAGE/"
cp install/install.sh "$STAGE/install.sh"; chmod +x "$STAGE/install.sh"
python3 -c "import json;print(json.load(open('claudesole.manifest.json'))['version'])" > "$STAGE/VERSION"

# 3) zip it
ZIP="$OUT/claudefather-install.zip"; rm -f "$ZIP"
( cd "$TMP" && zip -rqX "$ZIP" claudefather )
rm -rf "$TMP"

echo "built: $ZIP"
echo "  version: $(cat "$STAGE/VERSION" 2>/dev/null || sed -n '1p' VERSION 2>/dev/null)"
du -h "$ZIP" | cut -f1 | xargs echo "  size:"
echo "  files: $(unzip -l "$ZIP" | tail -1 | awk '{print $2}')"
echo "Deliver this zip; the recipient unzips it and points Claude Code at claudefather/AGENT_INSTALL.md."
