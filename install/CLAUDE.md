# install/ -- Installer & lifecycle (ClaudeFather)

This module is the **install + lifecycle surface** of ClaudeFather: how a node is born, configured,
updated, recovered, packaged, and shipped to other deployments. The `install/` dir holds the
packaged entry point; the lifecycle SCRIPTS themselves live at the framework ROOT (`$CC_HOME/`).

ClaudeFather (formerly "Claudesole") = a portable, brand/project-agnostic AI control center: a
stdlib-Python dashboard (`command-center/server.py`) + scoped agent-tools, tmux-supervised,
config-driven via `cc.config.json`. THE hard line everything here enforces:

> **FRAMEWORK is generic and ships unchanged. CONFIG/STATE/SECRETS are per-deployment and never propagate.**
> The framework could go fully public without leaking a credential.

## Files (this dir)
- `install.sh` -- bootstrap: prep an unzipped framework dir as `CC_HOME`. Idempotent, non-destructive:
  chmods scripts, makes `data/ bin/`, installs secret scanners (best-effort) + `cryptography`
  (Ed25519, for superadmin grant verification), prints next steps. NOTE: a SECOND copy lives at the
  package root and is what `make-install-package.sh` ships (see below).
- `AGENT_INSTALL.md` -- the **complete playbook a Claude Code agent follows** to install a node.
  Covers NEW project (4A) vs MIGRATE an existing one (4B, safety-first read-only-original rules),
  storage modes, start+verify, optional overseer registration, hard rules. This is the source of truth
  for the install flow.
- `README_INSTALL.md` -- short human-facing intro: the easy way ("point Claude Code at AGENT_INSTALL.md")
  and the manual way (the raw command sequence).

## Lifecycle scripts (at `$CC_HOME/` root, NOT in this dir)
- `cc-init.sh <project_root> [name] [brand] [storage]` -- "drop a project in". Writes/merges
  `cc.config.json`, makes `agents/ bin/ data/ deliverables/`, installs scanners + pre-commit secret gate
  (git repos), seeds a starter project `CLAUDE.md`, runs first security scan. Re-run with no args to
  refresh from the existing config. `storage` = `github | icloud | icloud+github`.
- `cc-update.sh <git-url|local-dir> [--dry-run]` -- pull FRAMEWORK updates into THIS deployment from an
  upstream. The heart of the fleet: copies `framework_paths`, NEVER touches `preserve_paths`, excludes
  nested `secrets/`/`.env*`/`*.local` from dir rsyncs, and splices each MD file's `CC:NOTES` region back
  in. Self-locates `CC_HOME` (robust to any deployment path / remote superadmin trigger). Ends by
  chmod-600'ing secret-bearing preserve files (closes the pre-restart 644 window).
- `cc-spawn.sh <id> <project_root> [preset=project|overseer] [port]` -- create a NESTED child node under
  `instances/<id>/` (own config/state/port/role, SHARED framework code), auto-picks a free port (8800+),
  registers it in the parent's `_instances.json`.
- `cc-promote.sh <module_dir|rel> [port]` -- graduate a CLAUDE.md MODULE into its own nested ClaudeFather
  (calls `cc-spawn.sh`, then starts it in tmux). The module stays in the project tree AND gets a scoped
  instance in the Portfolio.
- `cc-recover.sh` -- BREAK-GLASS. Reads live `cc.config.json`s (owner-only 0600) directly and prints every
  node on the machine: login PIN (`auth_token`), port, role, tailnet URLs (`peers.json`). Works when the
  web UI is down. First check: is Tailscale ON (dashboards are tailnet-only).
- `make-install-package.sh` -- build `dist/claudefather-install.zip`: stages every `framework_path`
  (preserve paths excluded by construction), adds the install guides + `install.sh` + a `VERSION` file at
  the package root, zips it. Deliver the zip; recipient unzips and points Claude Code at
  `claudefather/AGENT_INSTALL.md`.
- `brain.sh` -- not an installer: opens/attaches the always-on operator Claude session
  (tmux `<node>-brain`, `claude --dangerously-skip-permissions`). Kept here for orientation.

## The framework / preserve model (`claudesole.manifest.json`)
The manifest is the SINGLE source of truth for what propagates. Both `cc-update.sh` and
`make-install-package.sh` read it.
- `framework_paths[]` -- generic code/docs that SHIP + propagate to every deployment on update
  (server.py, agents/*/tools, cc-*.sh, install/, docs, presets, extensions, the manifest itself,
  `superadmin.pub`, ...).
- `preserve_paths[]` -- per-deployment config/data/secrets/state/learnings, NEVER overwritten
  (`cc.config.json`, `data/`, `bin/`, all `command-center/_*.json` state, `.env.claudefather`, `.mcp.json`,
  `agents/*/config.json`+`reports`+`baselines`+`rotation_ledger.json`, `peers.json`).
- `preserve_regions.markers` -- inside an UPDATED framework doc, the deployment's content between
  `<!-- CC:NOTES append-only` and `<!-- /CC:NOTES -->` is spliced back so local learnings survive a bump.
  GOTCHA: this splice is **MD-only** -- code files (e.g. `server.py`) contain those marker strings in
  their source, so `cc-update.sh` copies code VERBATIM (splicing code would silently revert it).
- `update_model` -- THIS deployment (the authoring/Mission Control node) is the dev/master copy; features are added HERE, then
  flow outward via `cc-update.sh`.

## How a node lifecycle works
1. **Configure/refresh:** `cc-init.sh` writes `cc.config.json` (the portability boundary: project_root,
   brand, port, enabled agents, storage_mode, chief_brief). server.py reads everything from it.
2. **Start (supervised):** `CC_CONFIG=$CC_HOME/cc.config.json TMUX_TMPDIR=/tmp tmux new-session -d -s
   <name> "cd $CC_HOME && python3 command-center/server.py"`. Always-on = launchd (macOS) / systemd.
   Verify with `curl -s -o /dev/null -w "%{http_code}" http://localhost:<port>/` -> expect `200`.
3. **Update:** `cc-update.sh <upstream>`; restart the tmux session to load.
4. **Nest:** `cc-spawn.sh` / `cc-promote.sh` create child instances under `instances/`.
5. **Recover:** `cc-recover.sh` when locked out.

## Dev -> dist mirror flow (how other nodes get updates)
The core framework repo (`github.com/<you>/claudesole-core`) is PRIVATE, so nodes without GitHub
creds (e.g. a node running under a different user's account) can't clone it. Distribution goes through a PUBLIC mirror,
`github.com/<you>/claudesole-dist`, holding framework_paths only (its `.gitignore` blocks
`secrets/`, `*.env`, keys, oauth json). Local checkout: `/Users/Shared/claudefather-dist/claudefather`.
Ship flow for a new version:
1. Edit + bump `version` in `claudesole.manifest.json` (here in the core).
2. Local nodes share this `server.py` -> just restart their tmux sessions.
3. Sync the local dist checkout: `bash /Users/Shared/claudefather-dist/claudefather/cc-update.sh <CC_HOME>`
4. Commit/push core AND push the mirror (`cd /Users/Shared/claudefather-dist/claudefather && git add -A && git commit && git push`).
5. Update a remote node: have its operator run `cc-update.sh <mirror-url>` then restart via its OWN
   supervisor (launchd) -- NEVER remote `restart:true`. (Zip-based alternative: `make-install-package.sh`.)

## Hard rules / gotchas
- **ASCII only** in every file the installer writes.
- **Never hardcode this deployment's paths into framework files** -- per-project values go in `cc.config.json`.
- **Secrets ONLY in gitignored files**; never commit/echo a full secret. `cc-update.sh`'s rsync `--exclude`
  for `secrets/`/`.env*` exists precisely because rsync ignores `.gitignore` -- without it one tenant's
  secret would replicate to every node.
- **CC:NOTES splice is MD-only** -- adding a code file's marker-style splice would revert it ("version
  bumped, code stale"). Keep code in the verbatim branch.
- **During a MIGRATION never modify the live original** -- read-only until you're on a copy (AGENT_INSTALL.md 4B).
- **Two copies of `install.sh`** exist: `install/install.sh` (dev source) and `$CC_HOME/install.sh`
  (root, what gets zipped). They are NOT identical (the root copy was the one shipped); keep them in sync
  when editing the bootstrap.
- **Don't blind-`git add -A`** in the core tree (it is very dirty); the dist mirror tree is the safe one to bulk-commit.
- **`update_upstream` is NOT in the superadmin set_config allowlist** -- a remote node's `cc_update`
  upstream must be passed explicitly each time (or set locally in its cc.config).

## Extend this area
- New shippable file -> add its path to `framework_paths` in the manifest (so update + package pick it up).
- New per-deployment state file -> add to `preserve_paths` (so an update never clobbers it).
- New install step -> edit `AGENT_INSTALL.md` (the agent playbook) and, if scripted, the relevant
  `cc-*.sh`; mirror non-secret changes into `install.sh`.
- New lifecycle script -> root `$CC_HOME/`, honor `CC_HOME`/`CC_CONFIG`, read the manifest for any
  framework/preserve decisions, and list it in `framework_paths`.
- Bump `version` in the manifest on every ship; record it in `docs/CHANGELOG.md`.
- Deeper refs: `docs/PACKAGING.md` (the split + rationale), `docs/CHANGELOG.md`, `docs/SUPERADMIN.md`,
  `docs/STORAGE_ARCHITECTURE.md`, `extensions/AUTHORING.md`.

<!-- CC:NOTES append-only -- per-deployment install/lifecycle learnings go here; survives cc-update -->
<!-- /CC:NOTES -->
