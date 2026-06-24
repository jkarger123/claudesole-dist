#!/usr/bin/env bash
# ClaudeFather bootstrap: prep the unzipped framework directory as CC_HOME. Idempotent, no destructive ops.
set -uo pipefail
CC_HOME="${CC_HOME:-$(cd "$(dirname "$0")" && pwd)}"
cd "$CC_HOME"
echo "== ClaudeFather bootstrap =="
echo "  CC_HOME: $CC_HOME"

# python3 + tmux are required
command -v python3 >/dev/null 2>&1 && echo "  python3: ok" || echo "  python3: MISSING (required)"
command -v tmux    >/dev/null 2>&1 && echo "  tmux: ok"    || echo "  tmux: MISSING (required for the dashboard)"

chmod +x ./*.sh 2>/dev/null || true
chmod +x command-center/*.sh agents/*/tools/*.sh agents/*/tools/*.py 2>/dev/null || true
mkdir -p data bin

# vendored scanners (best-effort; the backup secret-gate uses them)
if [ -x bin/gitleaks ]; then
  echo "  scanners: present"
elif [ -f agents/security/tools/install_scanners.sh ]; then
  bash agents/security/tools/install_scanners.sh >/dev/null 2>&1 \
    && echo "  scanners: installed" \
    || echo "  scanners: SKIP (no network?) -- install later via agents/security/tools/install_scanners.sh"
fi

echo
echo "Bootstrap done. Next:"
echo "  - Point Claude Code at AGENT_INSTALL.md (it does the rest), OR run:"
echo "      bash cc-init.sh <project_root> \"<name>\" \"<brand>\" \"<github|icloud|icloud+github>\""
echo "  - Then start the dashboard (see README_INSTALL.md) and open http://localhost:8799/"
