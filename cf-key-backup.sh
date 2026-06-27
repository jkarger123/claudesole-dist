#!/usr/bin/env bash
# ============================================================================================================
# cf-key-backup.sh -- back up the SUPER-CREATOR crown jewels so you can ALWAYS re-establish control, even if
# this Mac dies/is stolen/ransomwared. These keys ARE your authority: lose them with no backup and you can
# never update, re-license, or govern the fleet again. So we make MULTIPLE INDEPENDENT copies.
#
# Backs up: .superadmin_ed25519 (PRIMARY signing key), .recovery_ed25519 (break-glass key, if still on the box),
# .vault_key, superadmin.pub + recovery.pub, and a manifest. Produces:
#   1) an ENCRYPTED bundle (AES-256, your passphrase) -> copy to several places (1Password/USB/another Mac/cloud),
#   2) a PAPER backup (the private keys as text + QR if `qrencode` is installed) -> print + store in a safe.
# Paper survives disk failure, ransomware, and theft -- it is the "this can NEVER happen to me" layer.
#
# Usage:  bash cf-key-backup.sh [out_dir]        (default out_dir: ./cf-key-backup-<date-from-arg-or-manual>)
#   Set CF_HOME to the install root if not the default. You'll be prompted for an encryption passphrase.
# ============================================================================================================
set -uo pipefail
CC_HOME="${CC_HOME:-$HOME/hptuners-control}"
OUT="${1:-$CC_HOME/cf-key-backup}"
say(){ printf "\n\033[1m== %s\033[0m\n" "$*"; }
die(){ printf "\033[31mERROR: %s\033[0m\n" "$*" >&2; exit 1; }
command -v openssl >/dev/null 2>&1 || die "openssl required"
mkdir -p "$OUT" || die "cannot create $OUT"
chmod 700 "$OUT"

PRIMARY="$CC_HOME/.superadmin_ed25519"
RECOVERY="$CC_HOME/.recovery_ed25519"
VAULT="$CC_HOME/.vault_key"
[ -f "$PRIMARY" ] || die "no primary key at $PRIMARY -- run on the authoring/MC box"

say "1/3 stage crown jewels"
STAGE="$(mktemp -d)"; trap 'rm -rf "$STAGE"' EXIT
copied=()
for f in "$PRIMARY" "$RECOVERY" "$VAULT" "$CC_HOME/superadmin.pub" "$CC_HOME/recovery.pub"; do
  [ -f "$f" ] && { cp "$f" "$STAGE/$(basename "$f")"; copied+=("$(basename "$f")"); }
done
{ echo "ClaudeFather key backup"; echo "host: $(hostname)"; echo "cc_home: $CC_HOME"; echo "files: ${copied[*]}"; echo "primary_fpr: $(openssl pkey -in "$PRIMARY" -pubout 2>/dev/null | openssl dgst -sha256 | awk '{print $2}')"; } > "$STAGE/MANIFEST.txt"
echo "  staged: ${copied[*]}"

say "2/3 encrypted bundle (choose a STRONG passphrase -- you'll need it to restore)"
TAR="$OUT/claudefather-keys.cfkeys"; ENC="$TAR.enc"
tar -czf "$TAR" -C "$STAGE" . || die "tar failed"
openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 -in "$TAR" -out "$ENC" || die "encryption failed (passphrase mismatch?)"
rm -f "$TAR"; chmod 600 "$ENC"
echo "  wrote $ENC  (AES-256, pbkdf2). COPY THIS to >=3 places: 1Password, a USB key, another Mac, cloud."

say "3/3 PAPER backup (print this, store in a safe)"
PAPER="$OUT/PAPER-BACKUP.txt"
{
  echo "================ CLAUDEFATHER SUPER-CREATOR -- PAPER KEY BACKUP ================"
  echo "Generated on $(hostname). KEEP SECRET. Anyone with these keys controls the fleet."
  echo "Restore: cf-key-restore.sh (paste these back as the named files in the install root)."
  echo
  for k in "$PRIMARY" "$RECOVERY"; do
    [ -f "$k" ] || continue
    echo "----- BEGIN $(basename "$k") (base64 of the PEM) -----"
    base64 "$k"
    echo "----- END $(basename "$k") -----"; echo
  done
  echo "primary_fpr: $(openssl pkey -in "$PRIMARY" -pubout 2>/dev/null | openssl dgst -sha256 | awk '{print $2}')"
} > "$PAPER"
chmod 600 "$PAPER"
if command -v qrencode >/dev/null 2>&1; then
  base64 "$PRIMARY" | qrencode -o "$OUT/primary-key-qr.png" 2>/dev/null && echo "  QR: $OUT/primary-key-qr.png"
  [ -f "$RECOVERY" ] && base64 "$RECOVERY" | qrencode -o "$OUT/recovery-key-qr.png" 2>/dev/null && echo "  QR: $OUT/recovery-key-qr.png"
else
  echo "  (install qrencode for scannable QR backups: brew install qrencode)"
fi
echo "  wrote $PAPER -- PRINT it and put it in a safe/deposit box."

echo
echo "DONE. Now: (a) copy $ENC to several locations, (b) print $PAPER, (c) once the RECOVERY key is safely"
echo "backed up, you may DELETE $RECOVERY from this box (it should live OFFLINE). See docs/RECOVERY.md."
echo "Verify any backup with: cf-key-restore.sh --verify <bundle.enc>"
