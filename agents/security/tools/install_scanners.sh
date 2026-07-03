#!/usr/bin/env bash
# Portable scanner installer for the control-center Security agent-tool.
# Downloads gitleaks, trufflehog, osv-scanner for THIS host's OS/arch into the framework bin dir.
# No sudo. Re-runnable. Works on any machine the framework is dropped onto (macOS/Linux, arm64/amd64).
set -uo pipefail
BIN="${CC_BIN:-$(cd "$(dirname "$0")/../../.." 2>/dev/null && pwd)/bin}"
mkdir -p "$BIN"
OS=$(uname -s | tr '[:upper:]' '[:lower:]')               # darwin | linux
case "$(uname -m)" in arm64|aarch64) A=arm64;; x86_64|amd64) A=amd64;; *) A=$(uname -m);; esac
echo "installing scanners -> $BIN  (os=$OS arch=$A)"

asset_url(){ # repo, match-substring -> first matching download URL (excludes sigs/checksums/sboms)
  curl -fsSL "https://api.github.com/repos/$1/releases/latest" \
    | grep -o '"browser_download_url": *"[^"]*"' | sed 's/.*": *"//;s/"$//' \
    | grep -i "$2" | grep -iv 'sha256\|\.sig\|\.pem\|sbom\|\.txt\|\.json' | head -1
}
get_tar(){ # name repo match inner
  local n="$1" url; url=$(asset_url "$2" "$3") || true
  [ -z "${url:-}" ] && { echo "  $n: SKIP (no $3 asset)"; return 1; }
  echo "  $n: $url"
  curl -fsSL "$url" -o "/tmp/$n.tgz" && tar -xzf "/tmp/$n.tgz" -C /tmp "$4" && mv "/tmp/$4" "$BIN/$n" && chmod +x "$BIN/$n" && rm -f "/tmp/$n.tgz"
}
get_raw(){ # name repo match
  local n="$1" url; url=$(asset_url "$2" "$3") || true
  [ -z "${url:-}" ] && { echo "  $n: SKIP (no $3 asset)"; return 1; }
  echo "  $n: $url"
  curl -fsSL "$url" -o "$BIN/$n" && chmod +x "$BIN/$n"
}

get_tar gitleaks   gitleaks/gitleaks            "${OS}_${A}.tar.gz" gitleaks   || true
get_tar trufflehog trufflesecurity/trufflehog   "${OS}_${A}.tar.gz" trufflehog || true
get_raw osv-scanner google/osv-scanner          "${OS}_${A}"                   || true

echo "versions:"
for t in gitleaks trufflehog osv-scanner; do
  if [ -x "$BIN/$t" ]; then echo "  $t: $("$BIN/$t" --version 2>&1 | head -1)"; else echo "  $t: NOT installed"; fi
done
