# ClaudeFather — Hardening / Turnkey Appliance Architecture

How ClaudeFather becomes a **tamper-resistant product** a customer runs on their own hardware (a Mac mini)
but cannot modify the core or our extensions — while we (the authoring tier) retain full creator control.

## The honest threat model (read this first)
The customer owns the hardware and has root. **No software-only scheme is unbreakable against an owner of
the machine** — that's the DRM reality. So "they can't modify the core" is delivered as **defense in depth**,
where each layer raises the bar and the realistic threats (a customer's *agent* running with skip-permissions,
a curious admin, accidental edits, an attacker who gets a shell as the runtime user) are actually stopped:

| Layer | Stops | Mechanism |
|---|---|---|
| **OS (the real teeth)** | the agent + runtime user writing core | dedicated non-admin runtime user; core owned by admin/root, read-only to it; `--dangerously-skip-permissions` is then harmless (FS denies the write) |
| **Platform tier-lock** | core-mutating operations via the product | `edition: appliance` refuses authoring endpoints (keygen, grant minting, unsigned-ext install, framework writes) |
| **Integrity + self-heal** | tampered/drifted core surviving | boot+periodic hash check vs a **signed** manifest; mismatch → restore from signed dist + report up |
| **Sandbox** | customer code touching core/secrets | customer tools live in writable `custom/`, run in the restricted server-function runtime |
| **Managed attest (opt-in)** | a sophisticated owner re-rooting trust | enrolled boxes report to our MC over the signed channel; we hold the real private key |

The one limit to state plainly: a determined owner with root could swap the on-box `superadmin.pub` and re-sign a
tampered manifest (the root of trust is a file on their box). That defeats *standalone* integrity but not the
OS layer (still read-only to the runtime user) and not *managed* attestation (we hold the private key; they
can't forge a valid report to us). This is true of all on-prem software; we are honest about it.

## Why Claude Code permissions are NOT the boundary
The platform runs Claude Code agents with `--dangerously-skip-permissions` (agents have no TTY and can't answer
permission prompts — non-negotiable for autonomous operation). Therefore **the enforcement boundary is the OS
user, not Claude Code.** Run the runtime as a non-admin user that does not own core files; the agent then simply
cannot write them. All protection layers assume skip-permissions is on.

## Authority tiers (the "two-court" + super-creator)
Three layers of authority:
1. **Super-creator / authoring (US)** — `edition: authoring`. Modifies core, authors + signs extensions, mints
   superadmin grants + entitlements, signs the integrity manifest, pushes the dist. Holds the Ed25519 **private**
   key (`.superadmin_ed25519`, never ships). This is Mission Control / the authoring checkout.
2. **Customer overseer (THEM)** — `edition: appliance`, `role: org`. The top authority the customer interacts
   with: runs their fleet, configures, uses every product feature, builds in the sandbox. **Cannot** modify
   core/our extensions, mint grants, or become a super-creator (no private key on the box; locked endpoints).
3. **Customer nodes** — `role: project` under their overseer.

Every install defaults to the two-court shape: **an overseer + at least one node.** The "Godfather
infrastructure" the customer cannot change = the core we author + sign; our control = the signing key + the
signed update channel, not a live connection.

## Topology: standalone by default, opt-in managed
- **Standalone (default):** self-contained box; pulls **signed** framework updates from the public dist and
  verifies with `superadmin.pub`; no phone-home. We govern via *what we sign*.
- **Managed (opt-in):** the overseer enrolls as a tenant under our Mission Control for remote support/governance
  over the existing signed superadmin channel (how our own AFP/shopos fleet already runs).

## Edition resolution
`EDITION = cc.config.edition` else auto: a **source node** (`_is_update_source()`) → `authoring`; otherwise →
`appliance`. So our authoring checkout is authoring; a shipped/tenant box is a locked appliance by default.
`_authoring()` is the single gate; authoring-only endpoints refuse when false.

## Integrity manifest (signed) + self-heal
- **Sign (authoring, at ship time):** `core_sign()` hashes every FRAMEWORK file (manifest `framework_paths`,
  excluding the signature file itself), builds `{v, version, files:{rel:sha256}, generated}`, signs the canonical
  JSON with the Ed25519 private key, writes `core.sig.json` into the framework (ships via dist).
- **Verify (appliance, boot + periodic):** `core_verify()` loads `core.sig.json`, verifies its signature with
  `superadmin.pub` (a bad/again-signed manifest is rejected), recomputes hashes, and on any mismatch/missing
  file: **self-heals** by restoring that file from the local signed dist mirror (re-`cc_update` if the mirror
  itself is dirty), logs to `_core_integrity.log`, and reports drift up. Chosen behavior: **self-heal + report
  up** (edits to core silently revert; safe-mode only if self-heal can't obtain a clean copy).

## Sandbox arena (customer customization)
Chosen scope: **sandbox + local extension authoring.** A writable `custom/` tree (PRESERVE, never in the
integrity manifest) holds the customer's own tools/agents; they may also author **local** extensions (their own
ids) that install on their box. They can **never** modify our shipped `extensions/` or core. Customer code runs
in the existing sandboxed server-function runtime (restricted env, resource + timeout limits, no core secrets) —
the `third_party` tier (tighter sandbox + explicit operator approval) governs anything not dist-signed.

## OS hardening (the turnkey installer — Phase 2, lands with the Mac mini)
`cf-appliance-install.sh` will: create a dedicated non-admin runtime user (e.g. `cfrun`); install core owned by
an admin user, mode read-only (`r-x`) to `cfrun`; make only `state/`, `custom/`, `deliverables/`, and config
writable; set up the launchd supervisor running as `cfrun`; and run the first `core_verify`. Optional `+immutable`
profile adds `chflags` on core (unlock → update → relock around `cc-update`).

## Phased roadmap
- **Phase 1 (software backbone — THIS):** `edition` flag + `_authoring()` gate; signed integrity manifest
  (`core_sign`) + verify/self-heal loop (`core_verify`); lock authoring-only endpoints (keygen, grant/entitlement
  minting) on an appliance; `GET /api/core-integrity` + doctor surfacing.
- **Phase 2 (turnkey OS install):** `cf-appliance-install.sh` (dedicated user + read-only core), the Mac mini
  bring-up runbook, appliance edition defaults baked into the install package.
- **Phase 3 (sandbox + signing):** the `custom/` arena + third-party sandbox tier; extension signing so an
  appliance installs only signed/official extensions (local customer extensions stay sandboxed); managed-enroll
  opt-in flow.

## Hard rules
- Never ship the private key; only `superadmin.pub` + `core.sig.json` ship. Sign on the authoring box only.
- The integrity check must verify the manifest **signature** before trusting its hashes (no unsigned manifest).
- Self-heal restores from a **signed** source (the dist), never from an unverified local copy.
- Locking an appliance must NOT break normal tenant operation (sessions, official-extension install, vault
  lease, CCR-up) — only authoring/core-mutation is refused.
