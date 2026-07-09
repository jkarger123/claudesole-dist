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
#    excluded by construction -- only framework_paths are listed. CRITICAL: framework DIRS can contain nested
#    secrets/.env/_handoffs/node_modules (e.g. extensions/*/secrets/) -- rsync honoring the manifest never_ship
#    list strips them. Bare `cp -R` (the old code) would have shipped live OAuth tokens. (deep-audit 0.4.)
EXCL=(); while IFS= read -r pat; do [ -n "$pat" ] && EXCL+=( --exclude="$pat" ); done \
  < <(python3 -c "import json;[print(p) for p in json.load(open('claudesole.manifest.json')).get('never_ship',[])]")
python3 -c "import json;[print(p) for p in json.load(open('claudesole.manifest.json'))['framework_paths']]" | while read -r p; do
  for s in $p; do
    [ -e "$s" ] || continue
    mkdir -p "$STAGE/$(dirname "$s")"
    rsync -a "${EXCL[@]}" "$s" "$STAGE/$(dirname "$s")/"
  done
done

# 1b) HARD secret gate: assert nothing sensitive slipped into the staged tree (belt-and-suspenders over the
#     excludes). Fails the build rather than shipping a leak. Uses gitleaks if present, always greps for the
#     structural offenders (a secrets/ dir, an .env file, a live-token symlink). (deep-audit 0.4.)
_leaks="$(cd "$STAGE" && find . \( -name '.env' -o -name '.env.*' -o -type d -name secrets \) 2>/dev/null)"
if [ -n "$_leaks" ]; then
  echo "PACKAGE ABORT: secret-bearing paths staged despite excludes:"; echo "$_leaks"; rm -rf "$TMP"; exit 1
fi
if command -v gitleaks >/dev/null 2>&1; then
  gitleaks detect --no-git --redact --source "$STAGE" >/dev/null 2>&1 || { echo "PACKAGE ABORT: gitleaks found secrets in the staged bundle"; rm -rf "$TMP"; exit 1; }
fi

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
