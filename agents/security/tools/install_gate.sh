#!/usr/bin/env bash
# Install the control-center secret pre-commit gate into a target repo. Portable; no sudo.
# Usage: install_gate.sh [repo_path]   (defaults to project_root from cc.config.json)
# Pre-commit only (scans STAGED changes). We intentionally do NOT add a pre-push history scan:
# a repo with un-rotated historical secrets would have every push blocked. Scrub history first.
set -uo pipefail
CC_HOME="${CC_HOME:-$(cd "$(dirname "$0")/../../.." 2>/dev/null && pwd)}"
REPO="${1:-}"
if [ -z "$REPO" ] && [ -f "$CC_HOME/cc.config.json" ]; then
  REPO=$(python3 -c "import json;print(json.load(open('$CC_HOME/cc.config.json')).get('project_root',''))" 2>/dev/null)
fi
[ -d "$REPO/.git" ] || { echo "not a git repo: ${REPO:-<none>}"; exit 1; }
HOOK="$REPO/.git/hooks/pre-commit"
mkdir -p "$REPO/.git/hooks"
[ -f "$HOOK" ] && [ ! -f "$HOOK.cc-bak" ] && cp "$HOOK" "$HOOK.cc-bak" && echo "backed up existing pre-commit -> $HOOK.cc-bak"
cat > "$HOOK" <<'EOF'
#!/usr/bin/env bash
# CC secret gate (installed by the control center Security agent-tool). Blocks commits with secrets.
GL="${CC_HOME:-$HOME/claudefather}/bin/gitleaks"; command -v "$GL" >/dev/null 2>&1 || GL=gitleaks
command -v "$GL" >/dev/null 2>&1 || { echo "[cc-gate] gitleaks not installed; skipping (install via the Security tab)"; exit 0; }
if ! "$GL" git --staged --pre-commit --no-banner --redact; then
  echo "[cc-gate] secret detected in staged changes -- commit blocked. Remove it (and rotate the key)."
  exit 1
fi
EOF
chmod +x "$HOOK"
echo "installed pre-commit secret gate -> $HOOK"
