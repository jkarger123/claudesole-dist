#!/usr/bin/env bash
# ============================================================================================================
# cf-key-restore.sh -- reinstate the SUPER-CREATOR keys from a cf-key-backup bundle onto a (new) Mission
# Control box, re-establishing full authority. Use after a disk failure / new machine / break-glass.
#
# Usage:
#   bash cf-key-restore.sh --verify <bundle.cfkeys.enc>     # decrypt + list contents WITHOUT installing
#   bash cf-key-restore.sh <bundle.cfkeys.enc> [cc_home]    # decrypt + install keys into cc_home (default ~/hptuners-control)
#
# You'll be prompted for the encryption passphrase. After a restore, restart the CC; it signs/verifies with the
# restored keys immediately. If you're restoring the RECOVERY key as the new primary (break-glass), copy
# .recovery_ed25519 -> .superadmin_ed25519, then rotate in a fresh primary (see docs/RECOVERY.md).
# ============================================================================================================
set -uo pipefail
say(){ printf "\n\033[1m== %s\033[0m\n" "$*"; }
die(){ printf "\033[31mERROR: %s\033[0m\n" "$*" >&2; exit 1; }
command -v openssl >/dev/null 2>&1 || die "openssl required"

VERIFY=0; if [ "${1:-}" = "--verify" ]; then VERIFY=1; shift; fi
ENC="${1:-}"; CC_HOME="${2:-$HOME/hptuners-control}"
[ -f "$ENC" ] || die "bundle not found: $ENC"

STAGE="$(mktemp -d)"; trap 'rm -rf "$STAGE"' EXIT
say "decrypt bundle"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -in "$ENC" -out "$STAGE/bundle.tar.gz" || die "decryption failed (wrong passphrase?)"
tar -xzf "$STAGE/bundle.tar.gz" -C "$STAGE" || die "extract failed"
echo "  contents:"; ls -1a "$STAGE" | grep -vE '^\.\.?$|bundle\.tar\.gz' | sed 's/^/    /'   # -a so the PRIVATE keys (dotfiles) show, not just the .pub files
[ -f "$STAGE/MANIFEST.txt" ] && { echo "  manifest:"; sed 's/^/    /' "$STAGE/MANIFEST.txt"; }

if [ "$VERIFY" = "1" ]; then
  say "verify-only -- nothing installed"
  # sanity: can openssl read the primary key?
  [ -f "$STAGE/.superadmin_ed25519" ] && openssl pkey -in "$STAGE/.superadmin_ed25519" -noout 2>/dev/null \
    && echo "  primary key parses OK" || echo "  WARN primary key missing/unreadable"
  exit 0
fi

[ -d "$CC_HOME" ] || die "cc_home not found: $CC_HOME"
say "install keys into $CC_HOME"
for f in .superadmin_ed25519 .recovery_ed25519 .vault_key superadmin.pub recovery.pub; do
  if [ -f "$STAGE/$f" ]; then
    cp "$STAGE/$f" "$CC_HOME/$f"
    case "$f" in .*ed25519|.vault_key) chmod 600 "$CC_HOME/$f";; *) chmod 644 "$CC_HOME/$f";; esac
    echo "  restored $f"
  fi
done
echo
echo "DONE. Restart the CC (claudesole-restart) -- it will sign/verify with the restored keys."
echo "If this was a BREAK-GLASS restore of only the recovery key: cp $CC_HOME/.recovery_ed25519 $CC_HOME/.superadmin_ed25519,"
echo "then rotate a fresh primary + re-ship superadmin.pub (docs/RECOVERY.md)."
