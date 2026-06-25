# ClaudeFather — Product Principles (read before building ANYTHING)

**ClaudeFather is a product, not a private rig.** Everything we build here is designing an **enterprise
solution we may package, sell, or give away**. The north star:

> A person downloads an **executable / installer**, runs it, provides **their own tokens** (their Anthropic
> key, their Google OAuth, Slack, etc.), and **it just works** — their own self-hosted ClaudeFather.

That goal is a HARD CONSTRAINT on how every feature is built. We are not allowed to accumulate one-off
hacks that are impossible to extract later.

## The rules (apply to every change)
1. **Framework-level, never one-off.** A feature must work for *any* deployment, not just this one. If it
   only makes sense for hptuners/AFP, it's wrong. Ask: "would this help a tenant who is neither me nor any
   specific user?" If no, redesign it generic.
2. **Config-driven, zero hardcoding.** Project name, paths, ports, brand, accounts, tokens, side labels,
   visibility — all from `cc.config.json` / env, never baked into code. The portability boundary is
   `cc.config.json`; code stays generic. (We already enforce this — keep it.)
3. **BYO secrets, never bundled.** No key, token, or credential is ever committed or shipped. The installer
   collects them at setup into per-deployment, gitignored, 0600 files (`.env.claudefather`, extension
   `secrets/`). A fresh install starts with NO secrets and prompts for them.
4. **Cleanly extractable / packageable.** Generic code lives in `framework_paths` (ships to every node);
   per-deployment state/secrets live in `preserve_paths` (never overwritten). New features add to the
   framework, splice their per-deploy settings via config, and ride `make-install-package.sh` / `cc-update`
   out to every node. If a feature can't be expressed as "framework + config," it's not done.
5. **Multi-tenant aware.** Assume multiple users/nodes/accounts who may not trust each other. Default to the
   single-owner full-visibility experience, but provide isolation toggles (see fleet usage visibility:
   `fleet_view` / `fleet_share`). New cross-node features get the same treatment.
6. **Stdlib-only engine.** `command-center/server.py` adds no pip deps (one guarded optional: `cryptography`).
   Keeps the executable buildable + dependency-light.
7. **Ship fleet-wide, verify.** Bump the manifest version + CHANGELOG, validate (ast.parse + node-check the
   served JS), restart, and propagate via dist + `cc-update`. Test before declaring done.
8. **Document where it lives.** Every module keeps a CLAUDE.md; the Projects tree (`platform_map.json`) and
   `docs/ARCHITECTURE.md` stay current so the whole thing remains comprehensible to a new operator (or buyer).

## The packaging path (already partly built — keep it whole)
- `claudesole.manifest.json` — FRAMEWORK (ship) vs PRESERVE (per-deploy) split. The contract that makes a
  build extractable.
- `cc-init.sh` (scaffold a deployment), `cc-newinstance.sh` (a new self-contained instance), `cc-update.sh`
  (overlay framework, keep secrets/state), `make-install-package.sh` (build the install zip), `install/`
  (the install playbook). The "download → install → BYO tokens → works" flow runs through these.
- The eventual **executable**: wraps install.sh + the framework + a first-run setup wizard that collects the
  user's tokens into the gitignored secret files, then launches. Build toward this; don't regress it.

**Bottom line:** if a change isn't generic, config-driven, secret-clean, and shippable as framework, it's a
liability we'll have to rip out before we can sell this. Build it right the first time.
