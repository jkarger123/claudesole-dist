#!/usr/bin/env bash
# ClaudeFather bootstrap: prep the unzipped framework directory as CC_HOME. Idempotent, no destructive ops.
set -uo pipefail
CC_HOME="${CC_HOME:-$(cd "$(dirname "$0")" && pwd)}"
cd "$CC_HOME"
echo "== ClaudeFather bootstrap =="
echo "  CC_HOME: $CC_HOME"

# python3 + tmux + Claude Code are the three requirements
command -v python3 >/dev/null 2>&1 && echo "  python3: ok" || echo "  python3: MISSING (required)"
command -v tmux    >/dev/null 2>&1 && echo "  tmux: ok"    || echo "  tmux: MISSING (required for the dashboard)"
# CONNECT CLAUDE (deep-audit P0-2): every chief/agent/Ralph loop runs the `claude` CLI. Without it (or without
# auth) the dashboard boots green but every agent FAILS on first launch -- so make it a first-class prereq here.
if command -v claude >/dev/null 2>&1; then
  echo "  claude (Claude Code): ok"
  # is it authenticated? (a login, an API key, or an OAuth token) -- heuristic only; don't call the API here (cost/hang on a fresh box)
  if [ -n "${ANTHROPIC_API_KEY:-}" ] || [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] || [ -f "$HOME/.claude.json" ]; then
    echo "  claude auth: looks configured -- verify ONCE before launching:  claude -p 'reply OK'"
  else
    echo "  claude auth: NOT DETECTED -- run 'claude login' (or export ANTHROPIC_API_KEY) BEFORE you start, or every agent fails. Verify with:  claude -p 'reply OK'"
  fi
else
  echo "  claude (Claude Code): MISSING (REQUIRED) -- install it first (https://claude.com/claude-code), then 'claude login'. Every agent runs the 'claude' CLI; without it the dashboard boots but agents fail on launch."
fi

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

# cryptography (Fernet + Ed25519) -- REQUIRED for the credential VAULT (every secret store/lease uses Fernet) and
# for verifying the owner's superadmin grants. The CC boots without it, but the vault is DISABLED (secret saves
# silently fail) until it is present. Install for the SAME python3 the CC runs under. NB the PEP-668 trap: recent
# Homebrew/Debian pythons are "externally managed", so `pip install --user` EXITS NONZERO without installing
# anything -- we VERIFY by real import after each attempt and fall back to --break-system-packages, then fail LOUD.
if python3 -c "import cryptography" >/dev/null 2>&1; then
  echo "  cryptography: ok"
else
  python3 -m pip install --user --quiet cryptography >/dev/null 2>&1 || true
  if ! python3 -c "import cryptography" >/dev/null 2>&1; then
    # PEP-668 externally-managed environment: --user no-op'd. Retry allowing it (safe for a leaf dep like this).
    python3 -m pip install --user --break-system-packages --quiet cryptography >/dev/null 2>&1 || true
  fi
  if python3 -c "import cryptography" >/dev/null 2>&1; then
    echo "  cryptography: installed (credential vault + Ed25519 superadmin enabled)"
  else
    echo "  cryptography: **NOT INSTALLED** -- the credential VAULT will be DISABLED (secret saves fail) and owner"
    echo "               superadmin grants can't be verified. Fix, then restart the CC:"
    echo "                 python3 -m pip install --user --break-system-packages cryptography"
    echo "               (or create a venv the CC runs under). Verify: python3 -c 'import cryptography'"
  fi
fi

echo
echo "Bootstrap done. Next:"
echo "  - Point Claude Code at AGENT_INSTALL.md (it does the rest), OR run:"
echo "      bash cc-init.sh <project_root> \"<name>\" \"<brand>\" \"<github|icloud|icloud+github>\""
echo "  - Then start the dashboard (see README_INSTALL.md) and open http://localhost:8799/"
