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
-> runs the first security scan. Then restart the dashboard:
`TMUX_TMPDIR=/tmp /opt/homebrew/bin/tmux kill-session -t hpcc`. The control center now targets that project.
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
