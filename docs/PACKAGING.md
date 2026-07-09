# ClaudeFather -- packaging the control center as a portable product

**Product name: ClaudeFather** (Claude + console) -- the console you run a whole project/company from with
Claude Code. Per-deployment it can be re-branded (e.g. this deployment's `brand` could be "Acme Tuning"), but the
framework/product is **ClaudeFather**. The `cc` prefix (`cc.config.json`, `cc-init.sh`) reads as the
ClaudeFather CLI.

Goal: drop ClaudeFather onto ANY project/company and have it operate, with all bases covered and no
per-project rebuild. The discipline that makes that possible is one hard line:

> **FRAMEWORK is generic and ships unchanged. CONFIG is per-project.**
> The framework repo could go open-source without leaking a single credential.

## The split

FRAMEWORK (generic -- the product):
- `command-center/server.py` -- the dashboard + lenses + session launcher + terminal.
- `agents/<slug>/` -- the agent-tools (security, backup, usage, ideas, routines). Each is a directory
  with a `CLAUDE.md` charter + `tools/`; the dashboard AUTO-DISCOVERS them (`/api/agents`) and shows a
  "Talk to <slug> agent" button. **Add a dir -> get a tab+agent. Zero dashboard code per capability.**
- `bin/` -- vendored scanners (gitleaks/trufflehog/osv-scanner), installed by
  `agents/security/tools/install_scanners.sh` (detects OS/arch; no sudo).
- `command-center/ralph_runner.py` -- the autonomous-loop engine.
- `cc-init.sh` -- the "drop a project in" scaffolder.

CONFIG (per-project -- changes per deployment):
- `cc.config.json` -- project_name, project_root, brand, enabled agents, chief_brief. THE portability
  boundary. `server.py` reads `project_root` from here (falls back to a default if absent).
- The project tree itself (e.g. `<project root>`) + its CLAUDE.md hierarchy.
- Secrets (`.env`, deploy keys, Cloudflare/Anthropic) -- never in the framework.
- Fleet registries (`command-center/_machines.json`, `_components.json`) -- this deployment's machines.

## `cc init` -- onboarding a new project
```
bash <CC_HOME>/cc-init.sh <project_root> [project_name] [brand]
```
It: writes/merges `cc.config.json` -> ensures `agents/ bin/ data/` -> installs scanners (if missing) ->
creates a starter `CLAUDE.md` in the project if none -> installs the pre-commit secret gate (git repos)
-> runs the first security scan. Then restart the dashboard (cc-init prints the exact command, with the tmux
binary resolved via `command -v tmux` and the session name read from cc.config `"session"`). The control
center now targets that project.
(Verified 2026-06-20 end-to-end on a throwaway project: config + starter CLAUDE.md + gate all produced.)

## Updating deployments (`cc update`) -- features flow from master to all installs
`claudesole.manifest.json` classifies every path as **framework_paths** (ship + propagate) or
**preserve_paths** (per-deployment config/data/secrets/learnings -- never overwritten). This deployment
(the dev/master node) is where features are added.
```
bash <CC_HOME>/cc-update.sh <git-url|local-dir> [--dry-run]
```
It overlays the upstream's framework_paths onto the local deployment, NEVER touches preserve_paths, and
splices back each file's `CC:NOTES` region (so a tool's accumulated learnings survive a framework bump).
Bump `version` in the manifest when you ship; deployments see local-vs-upstream version on update.
Verified 2026-06-20: framework files update, while `cc.config.json` + `data/` + CC:NOTES are preserved.

Distribution (next): publish the framework_paths to a `claudesole-core` git repo so installs
`cc-update.sh <core-repo-url>`. For now `cc-update.sh` also accepts a local dir (e.g. a shared mount).

## Done (2026-06-20)
- `server.py` reads `project_root` + `project_name` + `brand` from `cc.config.json` (the core lever).
- Agent-tools auto-discovered; new one = new dir, no code.
- Portable scanner + gate installers; `cc-init.sh` scaffolder; this doc.

## Remaining for FULL portability (backlog)
1. **Frontend still has hardcoded project paths** -- `PROJ()` and the "New session" default cwd in the
   page (~`server.py` PAGE) return `<project root>`. Inject `PROJECT`/`PROJECT_NAME` into
   the page as a JS global and use it.
2. **Brand/title** -- the HTML `<title>` + the page header should use `BRAND` from config (server already
   reads it; just template it into the PAGE). The brand is currently a hardcoded literal string.
3. **Fleet is deployment-specific** -- `SERVICES` (bridge/crons/brain) + `_machines.json` + `_components.json`
   are this deployment's. Move them into config (or a per-project `fleet.json`).
4. **Framework home** -- everything assumes `<CC_HOME>`. For a clean product, make the framework
   relocatable (read `CC_HOME` env; most scripts already honor it).
5. **Distribution** -- bundle the framework as a versioned unit (a Claude Code plugin/marketplace, or a
   git template repo) so `cc init` can pull + wire it on a fresh machine.
6. **Per-tool ownership** -- migrate each agent-tool's LOGIC (e.g. backup's scripts, usage's aggregation
   currently in server.py) under its own `agents/<slug>/tools/` so the tool is fully self-contained.

When 1-4 are done, the framework + `cc init` are project-agnostic; 5-6 make it cleanly shippable.

## Reproducibility landmines -- "download -> works" (deep-audit 2026-07-09, finding 03)
A living tracker of every place a fresh install on a clean Mac would fail or need hand-holding. Source: the
5-agent deep audit (`conceptsandideas/OmniAgent/deliverables/deep-audit-20260709/03_...`). Keep this current as
each is closed -- it is the checklist that makes "download -> BYO tokens -> works" real.

| # | Landmine | Status |
|---|---|---|
| P0-1 | A rebuilt install zip would ship LIVE OAuth secrets (bare `cp -R` of `extensions/*/secrets/`) | ✅ manifest `never_ship` + all 3 copiers use it + a build secret gate (Phase 0.4) |
| P0-3 | Framework files referenced by shipped code MISSING from the manifest (`ralph_live.py`, `cc-lifeline`) | ✅ added + a manifest-completeness preship gate (Phase 0.5) |
| P1-4 | Shipped CLIs hardcode the dev install path (`$HOME/<the-authoring-dir>`) as a config fallback (breaks any other install) | ✅ removed from every `cc-*` CLI + `cc-spawn`/`cc-promote` self-locate (2026-07-09) |
| P1-7 | `desktop/` ships ~1.4 GB `node_modules`/`release` | ✅ `never_ship` excludes `node_modules`/`release` (Phase 0.4) |
| P2-10 | Tenant work-state (`_handoffs/`, dev-SSD `deliverables` symlink) rides along in `extensions/` | ✅ `never_ship` excludes them (Phase 0.4) |
| P0-2 | **No "Connect Claude" step** anywhere -- fresh install boots green, every agent then fails | ✅ install.sh prereq check + AGENT_INSTALL step 0 + a Doctor check (`_claude_connected`: red if the CLI is missing, warn if no auth) (2026-07-09) |
| P1-5 | The documented supervisor doesn't ship; the one that ships hardcodes `/opt/homebrew/bin/tmux` (Intel/Linux break) | ✅ shipping supervisor (`cc-instance-supervise.sh`) now resolves tmux via `command -v tmux`; AGENT_INSTALL points at it (the dev-only `cc-supervise.sh` reference was removed); + shipped launchd (`.plist`) & systemd (`.service`) templates in `install/templates/` (2026-07-09) |
| P1-6 | Printed restart instructions reference the dev tmux session `hpcc` | ✅ every printed restart command (`cc-init`, `cc-update`, `cc-spawn`) derives the session name from cc.config `"session"` (default `claudefather`) + resolves tmux portably (2026-07-09) |
| P1-8 | Auto-update silently points at a personal GitHub + an unrotatable signing key | ✅ (1) `cc-update.sh` now VERIFIES the upstream's `core.sig` against THIS box's trust root + file hashes BEFORE overlaying (`verify_update.py`), policy `update_verify` (warn default / enforce / off) + `--allow-unsigned` (never bypasses tampering); (2) managed-vs-standalone made explicit (`update_channel:"standalone"` disables auto-pull) + Doctor surfaces the built-in-mirror auto-pull so it's not silent; (3) key rotation IS supported -- trust = primary `superadmin.pub` + break-glass `recovery.pub` (either verifies). Full model: `docs/UPDATES.md` (2026-07-09) |
| P1-9 | Auth is open-by-default at the server layer on first boot | ✅ fail-secure: a fresh install with NO token auto-mints a random one (persisted to cc.config + `STATE_DIR/_auth_token.txt` + printed to stderr); open requires an explicit `auth_open:true` opt-out (Doctor still warns). env `CC_AUTH_TOKEN` / cc.config `auth_token` still win; an install that already has a token is unchanged (2026-07-09) |
| P2-11 | `platform_map.json` hardcodes absolute `/Users/<user>/…` paths + is unmanaged | ✅ the file now stores paths RELATIVE to CC_HOME (residue-clean); `/api/platform-map` absolutizes them against THIS install's CC_HOME at serve time; added to the manifest (ships + managed) + dropped from preship's `_KNOWN_UNSHIPPED` (2026-07-09) |
| P2-12 | 47 tenant-residue hits still ratchet-tolerated (incl. the dev PIN `3673` fallback) | ✅ ratcheted **47 → 0** and re-baselined to 0 (`.residue_baseline.json`) -- clean-core is now ENFORCED: any framework file that gains a tenant marker FAILS the ship. Comment/example/test-fixture mentions were genericized; the functional defaults are now config-driven -- service session labels come from cc.config `services` via `_service_labels()` (no hardcoded service names), the cwd-shortening regex is generic (last-two-segments, works on any install), the product-bridge chip label is generic (2026-07-09) |
| P2-13 | macOS-isms vs the claimed Linux support (iCloud, `/opt/homebrew`, `launchctl`) | ✅ claim scoped honestly ("Platform support" section below + a precise AGENT_INSTALL prereq): server BOOTS + RUNS on Linux via the shipped systemd template (P1-5), tmux resolves via `command -v tmux`, and every macOS-only binary (`security`/keychain, `launchctl`, `pmset`, iCloud) is invoked ONLY on-demand through guarded `sh()` handlers -- confirmed nothing macOS-specific runs at boot, so Linux degrades gracefully instead of crashing (2026-07-09) |
| P2-14 | `pip install cryptography` can no-op on PEP-668 Homebrew Python -> vault refuses to store, silently | ✅ install.sh now VERIFIES by real import after each pip attempt + falls back to `--break-system-packages` + fails LOUD (was a soft "SKIP (no network?)" that misattributed the PEP-668 no-op); Doctor gained a RED `vault` error when the vault can't encrypt (names the PEP-668 trap) instead of the failure being silent (2026-07-09) |

Closed: **14 / 14 -- every reproducibility/clean-core landmine is closed.** (P0-1/2/3, P1-4/5/6/7/8/9, P2-10/11/12/13/14.) Framework residue is 0 and the clean-core gate is baselined at 0, so the core stays tenant-neutral by construction.

## Platform support -- macOS-first, Linux via systemd (deep-audit P2-13)
ClaudeFather is **developed and run on macOS**; the control server itself is portable stdlib Python and **boots
+ runs on Linux** too. Be honest about the split so a Linux operator isn't surprised:

- **Cross-platform (works on Linux):** the dashboard/API server, sessions/terminal (tmux resolved via
  `command -v tmux`), agents, Ralph loops, mesh/superadmin, the credential vault, deliverables, Google Workspace,
  the CCR pipeline. Supervise with the shipped **systemd** template (`install/templates/claudefather.service.template`).
- **macOS-only (degrades gracefully on Linux -- never crashes boot):** these call macOS binaries ONLY on-demand
  through guarded `sh()` handlers, so on Linux the feature is simply unavailable/empty, not fatal:
  - **Claude account switching** -- reads/writes the macOS **Keychain** (`security`) + `~/.claude.json`.
  - **iCloud storage modes** (`icloud`, `icloud+github`) -- `~/Library/Mobile Documents/...`; on Linux use
    `github`.
  - **launchd supervision** (`launchctl`, `*.plist`) -- on Linux use the systemd unit instead.
  - **Power/thermal vitals** (`pmset`, `macmon`) -- macOS sensors; the vitals lens just omits them on Linux.
  - The **tmux "brain server" for TCC/Full-Disk-Access** is a macOS-only workaround (Linux has no TCC), so on
    Linux you can run `server.py` directly (the systemd template's default ExecStart does exactly this).

Bottom line: run on Linux with `storage_mode: github` + the systemd unit; the account-switch / iCloud / power
lenses are the only things that no-op. A future full-Linux edition would add a keychain-equivalent + drop the
TCC workaround entirely.

## Fresh-install validation -- "download -> works" proven end-to-end (2026-07-09)
Built a framework-ONLY tree (manifest `framework_paths` minus `never_ship`, no secrets/state) with a bare fresh
`cc.config.json` (no tenant values), booted it on a throwaway port, verified, then tore it down. Results:
- **Tenant-neutral:** the only framework files carrying a tenant marker were `preship.py` + `residue_lint.py`
  (the linters, which name markers by design -- SKIP-listed). No real leak. The one marker hit in the served
  page was `window.CC.project` = the tenant's OWN configured project path (runtime data), not framework code.
- **Fail-secure auth (P1-9):** no `auth_token` configured -> the install MINTED + persisted one and required it
  (`/api/doctor` = 401 without, 200 with). Not wide open.
- **Update transparency (P1-8):** Doctor fired the "this node auto-installs framework code from the built-in
  public mirror" warning -- the auto-pull is not silent.
- **Neutral chief:** `/api/chief` -> `services: []`, `pillars: null` (no tenant fleet/pillars leaked).
- Expected non-issues on the throwaway: an `integrity DRIFTED` flag (the test copied edited files against a
  stale `core.sig` without re-signing -- a real ship re-signs) and soft license/storage warnings.

Conclusion: a downloaded framework + a bare config boots clean, secure-by-default, and tenant-neutral -- the
"download -> BYO tokens -> works" bar is met. (Repro: copy `framework_paths` minus `never_ship`, write a minimal
`cc.config.json`, `CC_CONFIG=... python3 command-center/server.py`.)
