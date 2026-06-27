# Super-creator recovery — you can ALWAYS get back in

The hardening makes the fleet tamper-resistant. The flip side: **your authority is rooted in one Ed25519 private
key** (`.superadmin_ed25519`). It signs everything — superadmin grants, the core integrity manifest, licenses,
entitlements. Lose it with no backup and you can never update, re-license, or govern the fleet again. This doc
is the guarantee that **that can never happen to you** — multiple INDEPENDENT ways back in, no single point of
failure. (Accepts a little extra trust surface — a second key — on purpose, exactly as you asked.)

## The three independent recovery paths
You only need ONE of these to survive. Having all three = it cannot happen.

1. **Encrypted key bundle (multi-location).** `cf-key-backup.sh` packages the primary key + recovery key +
   vault key into an AES-256 bundle (your passphrase). Copy it to several places (1Password, a USB key, another
   Mac, cloud). Restore onto any new Mac with `cf-key-restore.sh`.
2. **Paper backup (offline, survives everything digital).** The same script prints the private keys as text
   (+ QR if `qrencode` is installed). Print it, put it in a safe / deposit box. Disk failure, ransomware, theft,
   cloud lockout — paper is immune. This is the "this can never happen to me" layer.
3. **Recovery / break-glass key (trusted by every node, kept offline).** A SECOND owner keypair: `recovery.pub`
   ships with the framework so **every node trusts it alongside the primary**; the recovery PRIVATE key lives
   OFFLINE (paper/USB), never on a box. If the primary is lost OR compromised, restore the recovery key and you
   can immediately sign — it verifies everywhere — then rotate in a fresh primary. No node is ever locked out.

## One-time setup (do this now, on Mission Control)
```
# 1) the recovery keypair already exists (recovery.pub ships; .recovery_ed25519 is here, gitignored):
ls .recovery_ed25519 recovery.pub
# 2) make durable backups of ALL crown jewels (prompts for a strong passphrase):
bash cf-key-backup.sh ~/cf-key-backup
#    -> writes ~/cf-key-backup/claudefather-keys.cfkeys.enc  AND  ~/cf-key-backup/PAPER-BACKUP.txt
# 3) COPY the .enc bundle to >=3 places; PRINT the PAPER-BACKUP and store it in a safe.
# 4) once the RECOVERY key is safely backed up, take it OFFLINE -- delete it from the box:
rm .recovery_ed25519
#    (the PRIMARY key stays on MC -- it's what signs day to day. The recovery key is cold storage.)
# 5) verify a backup actually restores (do this -- an untested backup isn't a backup):
bash cf-key-restore.sh --verify ~/cf-key-backup/claudefather-keys.cfkeys.enc
```

## Recovery runbooks
### A. MC disk died / new Mac (you still have the primary key backup)
1. Stand up a fresh ClaudeFather authoring checkout on the new Mac.
2. `bash cf-key-restore.sh <bundle.cfkeys.enc> <cc_home>` (or hand-type the paper backup into the named files).
3. Restart the CC. It signs/verifies with the restored keys immediately. You're back — full authority.

### B. Break-glass — the primary key is LOST or COMPROMISED (you only have the recovery key)
1. Restore the recovery private key: `cp .recovery_ed25519 .superadmin_ed25519` on the (new) MC — the fleet
   already trusts `recovery.pub`, so grants/licenses/integrity you sign now verify everywhere.
2. Rotate a FRESH primary so you're back to a normal two-key posture:
   - delete the old `superadmin.pub`, run `superadmin_keygen` (new primary), and ship the new `superadmin.pub`
     via the normal flow (`core_sign` + dist push + converge). Nodes pick up the new primary and keep trusting
     recovery.
   - then generate a NEW recovery key (`recovery_keygen`), back it up, take it offline. (If the OLD key was
     compromised, this fully rotates both.)

### C. You're locked out of an APPLIANCE (a customer box, or your own)
Appliances **degrade gracefully, never brick on their own**: the license default is soft, and integrity
self-heals to the last signed core, so a box keeps working even if it can't reach you. With the recovery key you
can sign a fresh license/grant for any box. (A hard-`license_enforce` box that truly expired needs a new license
installed — `POST /api/license-install` — which you can always mint with either the primary or recovery key.)

## Why this is safe AND recoverable
- Two trusted keys is a slightly larger surface, but both are OURS, the recovery one is COLD (offline), and it
  converts "lost the key = lost the fleet forever" into "restore from any of three backups." The trade is
  deliberate and correct for a system you must never be locked out of.
- Backups are encrypted (passphrase you hold) or paper (physically secured). The bundle alone is useless without
  the passphrase; the paper alone requires physical access.

## Hard rules
- `recovery.pub` SHIPS (public, every node trusts it). The recovery + primary PRIVATE keys NEVER ship / commit
  (gitignored). Move the recovery private key OFFLINE after backup.
- Test a restore before you rely on it. An untested backup is not a backup.
- Keep the paper backup and at least one encrypted bundle in physically separate locations.
