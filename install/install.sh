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

# cryptography (Ed25519) -- needed to verify the platform owner's superadmin grants (superadmin.pub). The CC
# still boots without it, but the node is NOT under the owner's superadmin until it's present. Install for
# the SAME python3 the CC runs under.
if python3 -c "import cryptography" >/dev/null 2>&1; then
  echo "  cryptography: ok"
else
  python3 -m pip install --user --quiet cryptography >/dev/null 2>&1 \
    && echo "  cryptography: installed (Ed25519 superadmin verification enabled)" \
    || echo "  cryptography: SKIP (no network / pip?) -- run 'python3 -m pip install --user cryptography' so this node honors owner superadmin grants"
fi

echo
echo "Bootstrap done. Next:"
echo "  - Point Claude Code at AGENT_INSTALL.md (it does the rest), OR run:"
echo "      bash cc-init.sh <project_root> \"<name>\" \"<brand>\" \"<github|icloud|icloud+github>\""
echo "  - Then start the dashboard (see README_INSTALL.md) and open http://localhost:8799/"
