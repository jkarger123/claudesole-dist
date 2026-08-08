#!/usr/bin/env bash
# ClaudeFather bootstrap: prep the unzipped framework directory as CC_HOME. Idempotent, no destructive ops.
#
# This script does the ACTIONS (chmod, dirs, install cryptography + scanners); `cf-preflight` does the
# CHECKING and is the gate. Dependencies are DECLARED in claudefather.deps.json -- add new ones there, not
# as another ad-hoc `command -v` here, or they end up unchecked on the interpreters that actually matter.
set -uo pipefail
CC_HOME="${CC_HOME:-$(cd "$(dirname "$0")" && pwd)}"
cd "$CC_HOME"
echo "== ClaudeFather bootstrap =="
echo "  CC_HOME: $CC_HOME"

# python3 is needed by everything below (including the preflight checker itself).
if ! command -v python3 >/dev/null 2>&1; then
  echo "  python3: MISSING (required) -- install it first:  xcode-select --install   (or: brew install python3)"
  exit 1
fi

chmod +x ./*.sh cf-preflight 2>/dev/null || true
chmod +x command-center/*.sh agents/*/tools/*.sh agents/*/tools/*.py 2>/dev/null || true
mkdir -p data bin

# vendored scanners (best-effort; the backup secret-gate uses them). NOTE: gitleaks is VENDORED into bin/,
# not a system dependency -- do not "fix" a missing gitleaks by installing it system-wide.
if [ -x bin/gitleaks ]; then
  echo "  scanners: present"
elif [ -f agents/security/tools/install_scanners.sh ]; then
  bash agents/security/tools/install_scanners.sh >/dev/null 2>&1 \
    && echo "  scanners: installed" \
    || echo "  scanners: SKIP (no network?) -- install later via agents/security/tools/install_scanners.sh"
fi

# cryptography (Fernet + Ed25519) -- the ONE third-party python dependency, and it is load-bearing for four
# systems: the credential vault, Ed25519 superadmin grants, the signed-update gate, and the appliance healer.
# Install it for the SAME python3 the CC runs under. NB the PEP-668 trap: recent Homebrew/Debian pythons are
# "externally managed", so `pip install --user` EXITS NONZERO without installing anything -- we VERIFY by real
# import after each attempt and fall back to --break-system-packages. cf-preflight then re-checks it for EVERY
# interpreter that needs it (the server, and on an appliance also cfrun and root), which is the failure this
# script alone cannot see.
if python3 -c "import cryptography" >/dev/null 2>&1; then
  echo "  cryptography: ok"
else
  python3 -m pip install --user --quiet cryptography >/dev/null 2>&1 || true
  if ! python3 -c "import cryptography" >/dev/null 2>&1; then
    python3 -m pip install --user --break-system-packages --quiet cryptography >/dev/null 2>&1 || true
  fi
  if python3 -c "import cryptography" >/dev/null 2>&1; then
    echo "  cryptography: installed (credential vault + Ed25519 superadmin enabled)"
  else
    echo "  cryptography: **NOT INSTALLED** -- the credential VAULT will be DISABLED (secret saves fail) and"
    echo "               signed updates cannot be verified. Fix, then re-run:"
    echo "                 python3 -m pip install --user --break-system-packages cryptography"
  fi
fi

# ---- the gate: every declared dependency, on every interpreter that needs it ----
echo
PREFLIGHT_RC=0
if [ -f cf-preflight ]; then
  bash cf-preflight "$@" || PREFLIGHT_RC=$?
else
  echo "  WARN: cf-preflight not found in this bundle -- dependencies were NOT verified."
fi

echo
if [ "$PREFLIGHT_RC" -ne 0 ]; then
  echo "Bootstrap INCOMPLETE -- resolve the preflight problems above, then re-run:  bash install.sh"
  echo "(Re-run with --appliance if this box is being built as a hardened customer appliance.)"
  exit "$PREFLIGHT_RC"
fi

echo "Bootstrap done. Next:"
echo "  - Point Claude Code at AGENT_INSTALL.md (it does the rest), OR run:"
echo "      bash cc-init.sh <project_root> \"<name>\" \"<brand>\" \"<github|icloud|icloud+github>\""
echo "  - Then start the dashboard (see README_INSTALL.md) and open http://localhost:8799/"
