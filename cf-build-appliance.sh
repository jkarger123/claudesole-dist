#!/usr/bin/env bash
# ============================================================================================================
# cf-build-appliance.sh -- produce a PROTECTED appliance artifact from the plaintext authoring tree.
#
# Principle (docs/IP_PROTECTION.md): we author in PLAINTEXT (full velocity); only the SHIPPED appliance build
# is obfuscated, so "tell an agent to remove the block" doesn't work on readable source. This script stages the
# framework, obfuscates the Python with PyArmor (preferred) or Cython (fallback), and leaves the result ready to
# be signed (core_sign over the OBFUSCATED tree) + published as the appliance dist.
#
# Usage:  bash cf-build-appliance.sh <authoring_tree> <out_dir> [--cython]
#   PyArmor (recommended): pip install --user pyarmor  AND a purchased license registered (pyarmor reg <file>).
#   --cython: free fallback -- compiles the big modules to .so (heavier; verify the build runs).
#
# IMPORTANT this is a SCAFFOLD: the obfuscation step requires the tool to be installed/licensed. Without it the
# script stops with a clear message rather than shipping plaintext silently. After a successful build:
#   1) run the server from <out_dir> once to smoke-test it still boots,
#   2) core_sign over <out_dir> (so core.sig.json hashes the OBFUSCATED files),
#   3) publish <out_dir> as the appliance dist the healer pulls.
# ============================================================================================================
set -uo pipefail
SRC="${1:-}"; OUT="${2:-}"; MODE="pyarmor"; [ "${3:-}" = "--cython" ] && MODE="cython"
say(){ printf "\n\033[1m== %s\033[0m\n" "$*"; }
die(){ printf "\033[31mERROR: %s\033[0m\n" "$*" >&2; exit 1; }
[ -n "$SRC" ] && [ -n "$OUT" ] || die "usage: cf-build-appliance.sh <authoring_tree> <out_dir> [--cython]"
[ -f "$SRC/command-center/server.py" ] || die "no command-center/server.py under $SRC (not an authoring tree)"

say "1/4 stage framework -> $OUT"
rm -rf "$OUT"; mkdir -p "$OUT"
rsync -a --exclude '.git' --exclude 'instances' --exclude 'data' --exclude 'deliverables' \
  --exclude '.env.claudefather' --exclude '.mcp.json' --exclude '.vault*' --exclude '.superadmin_ed25519' \
  --exclude '_*.json' --exclude '*.log' "$SRC"/ "$OUT"/ || die "stage rsync failed"

say "2/4 obfuscate Python ($MODE)"
# The modules worth protecting (the product logic). Non-.py framework (presets/extensions json, static) ships as-is.
PYFILES=(command-center/server.py command-center/granola.py command-center/context.py command-center/focus.py \
         command-center/clips.py command-center/ralph_runner.py command-center/scan_projects.py)
if [ "$MODE" = "pyarmor" ]; then
  command -v pyarmor >/dev/null 2>&1 || die "pyarmor not installed. Buy a license + 'pip install --user pyarmor' (see docs/IP_PROTECTION.md), or re-run with --cython."
  if ! pyarmor reg >/dev/null 2>&1; then echo "  WARN: pyarmor appears UNREGISTERED (trial mode has limits). Register your purchased license: pyarmor reg <license.zip>"; fi
  for f in "${PYFILES[@]}"; do
    [ -f "$OUT/$f" ] || continue
    d="$(dirname "$OUT/$f")"
    # pyarmor gen writes an obfuscated copy + a pyarmor_runtime; bind to platform/expiry as policy dictates.
    pyarmor gen --output "$d.__obf" "$OUT/$f" >/dev/null 2>&1 || die "pyarmor failed on $f"
    cp -f "$d.__obf/$(basename "$f")" "$OUT/$f" && cp -rf "$d.__obf"/pyarmor_runtime* "$d"/ 2>/dev/null || true
    rm -rf "$d.__obf"
    echo "  obfuscated $f"
  done
elif [ "$MODE" = "cython" ]; then
  command -v cythonize >/dev/null 2>&1 || die "cython not installed: pip install --user cython (and Xcode CLT for the C compiler)."
  for f in "${PYFILES[@]}"; do
    [ -f "$OUT/$f" ] || continue
    ( cd "$(dirname "$OUT/$f")" && cythonize -i -3 "$(basename "$f")" >/dev/null 2>&1 ) \
      && rm -f "$OUT/$f" && echo "  compiled $f -> .so" \
      || echo "  WARN: cython failed on $f (dynamic code? keep plaintext or use PyArmor)"
  done
fi

say "3/4 smoke check"
echo "  -> manually: CC_HOME=$OUT python3 $OUT/command-center/server.py  (confirm it boots + serves)"

say "4/4 next: sign + publish"
cat <<NEXT
  The build is obfuscated but NOT yet signed. To finish the appliance dist:
   1) boot it once and confirm /api/health responds.
   2) sign the OBFUSCATED tree:  CC_HOME=$OUT  (authoring node) -> POST /api/core-sign  (hashes the obf files).
   3) publish $OUT as the appliance dist the healer pulls (separate from the plaintext authoring dist).
  See docs/IP_PROTECTION.md (license + obfuscation) and docs/HARDENING.md (integrity/self-heal).
NEXT
echo "DONE (scaffold). Obfuscation tool required -- this never ships plaintext silently."
