# Protecting the codebase (anti-clone / anti-jailbreak) — strategy + honest limits

The threat James named: a customer tells an AI agent to **copy the whole tree, strip the protection blocks, and
run a jailbroken, unprotected, un-licensed copy.** This doc is how we make that not worth doing. Read it with
the hardening backbone (`docs/HARDENING.md`) — that stops in-place tampering; this stops *cloning the code out*.

## The unavoidable truth (state it to every stakeholder)
The customer owns the hardware and has root, and our product is **plaintext Python**. **You cannot make
on-prem code uncrackable** — every shipped binary (Adobe, JetBrains, games) eventually gets cracked. The goal
is therefore NOT "impossible," it's: **(1) raise the effort from "ask an agent" to "expert reverse-engineering,"
(2) make a stripped copy NON-FUNCTIONAL without a secret only we hold, (3) make cloning DETECTABLE + traceable,
(4) back it with legal + the ongoing-value moat.** Layered, those defeat the realistic threat.

## The layers, ranked by leverage

### 1. License activation bound to hardware + signed by us + expiring  ★ strongest software lever, buildable now
The key idea: a protection that is just a *removable block* is worthless. A protection that **gates real
functionality on a secret the customer never receives** survives stripping. On first run the appliance computes
a **hardware fingerprint** (Mac `IOPlatformUUID` / serial via `ioreg`), sends it to OUR activation endpoint, and
gets back an **Ed25519-signed license** bound to *that machine* + an expiry. The runtime verifies the license
with `superadmin.pub` (already shipped) on boot and periodically:
- Copy the tree to a second Mac → different fingerprint → license invalid → refuses.
- Strip the license check → you also lose updates/self-heal/managed features, and any capability we choose to
  gate (or content we deliver *encrypted under a key released only on valid activation*) stays dead.
- Reuses what we built: Ed25519 signing (us-only private key), the vault/lease pattern, the dist channel.
Enforcement should ship **soft first** (detect + doctor warn + report) so we never brick our own fleet, then
flip to **hard refuse** per sold box via a config flag. This is the single highest-value build and it's ours
to do — recommended Phase-3 first item.

### 2. Ship obfuscated / compiled code, not plaintext  ★ raises the bar from trivial to expert
"Tell an agent to remove the block" only works on readable source. Options:
- **PyArmor** (recommended, purpose-built): encrypts bytecode, binds to machine, supports expiry; the runtime
  decrypts in memory. ~$70–150/yr. Stops casual + agent-driven stripping cold; an expert can still attack it.
- **Cython → native `.so`**: compile `server.py` + key modules to a C extension (no readable source). Free, but
  heavy to set up for an 18k-line stdlib file and it slows OUR iteration.
- **Bytecode-only `.pyc`**: weak (decompilable) — not worth it.
Critical principle: **keep authoring in plaintext; obfuscate only the SHIPPED APPLIANCE ARTIFACT in a build/
packaging step.** Our fleet runs plaintext (full velocity); the dist build for appliances is the protected one.
This needs a tool decision (PyArmor license + a packaging pipeline) — see "Decision needed" below.

### 3. OS read-only core + non-admin runtime  ✓ already built (Phase 2)
`cf-appliance-install.sh` makes core read-only to the runtime user, so the *agent* can't edit OR copy-with-intent
in place. It does NOT stop a *root* user copying the tree elsewhere — that's what layers 1+2 cover.

### 4. Light license heartbeat / duplicate-fingerprint detection  ★ makes cloning detectable
Even in "standalone," a periodic signed check-in (license refresh) lets us **detect the same license/fingerprint
running on two boxes**, or a box that went dark, and **revoke** — the next activation/refresh then fails. This is
license validation, NOT governance phone-home (privacy-clean: just a fingerprint + license nonce). Pairs with the
standalone topology.

### 5. Per-customer watermarking + legal  ★ deterrent + traceability
Embed a per-customer marker (in the signed license, in logs/build) so a leaked copy is traceable to who leaked
it. Back it with a EULA forbidding reverse-engineering/redistribution and per-seat licensing. For most on-prem
SaaS the real moat is **a cracked copy gets no updates, no managed features, no support, and is legally exposed**.

## Recommended program (in order)
1. **(Phase 3a) License activation** — hardware-bound, Ed25519-signed, expiring; soft-enforce → hard-enforce per
   box. Buildable now with our existing crypto. Biggest leverage.
2. **(Phase 3b) Appliance build pipeline that obfuscates** the shipped artifact (PyArmor) — authoring stays
   plaintext. Needs the tool decision.
3. **(continuous) Heartbeat + duplicate-fingerprint revocation; watermark; EULA.**

## Decision needed from James
- **Obfuscation tool:** PyArmor (paid, easiest, machine-bind + expiry built in) vs Cython (free, heavier, slower
  iteration) vs ship plaintext for now and rely on license + OS layers. Recommendation: **PyArmor for the
  appliance build**, plaintext for our own fleet.
- **License hard-enforce timing:** ship the license layer soft (detect/warn) immediately; flip hard-refuse on
  for the first sold Mac mini once we've confirmed it won't disrupt our fleet.

## Status (what's built)
- **License activation — SHIPPED (v0.87.0), soft-enforce.** Hardware fingerprint (`_hw_fingerprint`, macOS
  IOPlatformUUID), Ed25519-signed licenses bound to fingerprint+expiry+customer (`license_issue`, authoring/MC
  only), node-side verify+gate (`license_status`/`_licensed`). APIs: `GET /api/license`, `POST /api/license-issue`
  (MC mints for a box's fingerprint), `POST /api/license-install` (node stores it). Soft by default (health
  `licensed` field + doctor warn); set `cc.config license_enforce=true` on a SOLD box to hard-refuse service
  (the `_auth_gate` shows a "license required" page with the machine fingerprint to send the vendor). Tested:
  installs+validates on the issuing machine; rejects wrong-machine / tampered / expired.
  - **To license a sold box:** on the box `GET /api/license` -> copy its `fingerprint`; on MC
    `POST /api/license-issue {fingerprint, customer, days}`; paste the returned license to the box
    `POST /api/license-install`; set `license_enforce=true` in its cc.config.
- **Obfuscation — SCAFFOLD (v0.87.0), needs the tool.** `cf-build-appliance.sh` stages the authoring tree and
  obfuscates the Python via **PyArmor** (preferred) or **Cython** (`--cython` fallback), keeping authoring
  plaintext. It will NOT ship plaintext silently (stops if the tool is absent). **Blocked on a purchase:** buy a
  PyArmor license (~$70-150/yr), `pip install --user pyarmor`, `pyarmor reg <license>`, then the pipeline
  produces a real obfuscated artifact (which then gets `core_sign`ed over the obfuscated files + published as the
  appliance dist). Until then appliances ship plaintext-but-licensed (license is the active protection).

## What NOT to do (false comfort)
- Don't rely on a removable `if not licensed: exit` in plaintext — that's exactly the "strip the block" attack.
  The check must gate something unreconstructable (a signed token tied to hardware, or content decrypted with our
  key), not just a flag.
- Don't claim "uncrackable." Claim "licensed, hardware-bound, updated, supported" — and make the un-licensed path
  genuinely worse (no updates, revocable, traceable, illegal).
