# ClaudeFather updates -- trust model (managed vs standalone, signature-gated)

How framework code reaches an install, and how it is made safe. Addresses deep-audit P1-8 (a fresh install
used to auto-pull framework code from a hardcoded personal GitHub with no signature check).

## The two postures -- pick one per install

- **Managed** (fleet node -- the default). The install auto-converges from an upstream: it probes the upstream
  version every `auto_update_check_min` minutes and, when behind and outside business hours, runs `cc-update.sh`
  to overlay the new framework, then restarts. Set `update_source` to the upstream you trust (a git URL on any
  host, or a local/shared-mount dir). If unset it falls back to the built-in **ClaudeFather public mirror**
  (`OFFICIAL_DIST_GIT`) -- Doctor surfaces this so it is never silent.
- **Standalone** (self-operated, not part of anyone's fleet). Set `cc.config "update_channel": "standalone"`
  (or `auto_update: false`). The install never auto-pulls a third party's code; you update deliberately when you
  choose (`cc-update.sh <your-upstream>`).

A **source/authoring** node (`update_role: source`, or the dist mirror, or the private-core git remote) never
self-updates -- it is where framework code is authored.

## The signature gate -- verify BEFORE applying

`cc-update.sh` will not overlay framework code until the upstream is verified against **this box's existing
trust root** (`superadmin.pub`, plus the optional break-glass `recovery.pub`) -- never the incoming copy. The
gate (`command-center/verify_update.py`) checks two things:
1. the upstream's `core.sig.json` is signed by a currently-trusted owner key (Ed25519); and
2. every framework file the update will install hash-matches that signed manifest -- so a swapped `server.py`,
   or a swapped-in new trust root, is caught before it lands and runs.

**Policy -- `cc.config "update_verify"`:**
- `"warn"` (default): verify, log a LOUD warning on failure, but still apply. Matches the staged-rollout
  convention of the other enforcement gates (`MESH_ENFORCE`, `POLICY_ENFORCE`) -- turn it on fleet-wide first,
  watch, then harden. Zero risk of halting convergence on a transient signing hiccup.
- `"enforce"`: BLOCK the update on any verification failure. The recommended hardened setting once you have
  confirmed the fleet verifies cleanly. **This is the target for a packaged product.**
- `"off"`: skip verification (not recommended).

**Verdicts + overrides:**
- **VERIFIED** -> applies.
- **UNVERIFIED** (upstream ships no `core.sig.json`, or this box has no trust root, or `cryptography` is
  missing): a self-authored upstream can proceed with `cc-update.sh <src> --allow-unsigned`; `enforce` blocks
  it otherwise.
- **FAILED** (a signature is present but invalid, or a signed file's hash mismatches = tampering / an
  un-re-signed build): **never** bypassable by `--allow-unsigned`; `enforce` always blocks it.

Signing is produced at ship time by `core_sign()` (authoring only) -> `core.sig.json`, shipped with the
framework. The 15-minute `core_verify` self-heal is the *runtime* companion: it restores any drifted file from
the signed dist. The update gate is the *pre-install* companion: it refuses to install an unverified build in
the first place.

## Key rotation / recovery

The trust root is the owner's Ed25519 key. Every install trusts **two** public keys if present: the primary
`superadmin.pub` and a break-glass `recovery.pub` (`_trusted_pubkeys()` -- any one verifying suffices). This is
the rotation/recovery path: the owner can re-establish authority by restoring either key without locking the
fleet out. Rotating the primary is a deliberate ceremony (`superadmin_keygen()` refuses to clobber an existing
private key) -- sign the transition so nodes carrying the old trust root still verify during the cutover.

## Quick reference (cc.config keys)

| key | default | meaning |
|-----|---------|---------|
| `update_channel` | (managed) | `"standalone"` disables all auto-update |
| `auto_update` | `true` | master on/off for auto-convergence (managed nodes) |
| `update_source` | built-in public mirror | the upstream to pull from (git URL any host, or a dir) |
| `update_verify` | `"warn"` | `"warn"` \| `"enforce"` \| `"off"` -- the signature gate policy |
| `update_role` | (auto) | `"source"` = authoring node, never self-updates |
| `auto_update_check_min` | `30` | minutes between update probes |
