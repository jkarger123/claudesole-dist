# Command Center — the engine

<!-- CC:CHILDREN auto-managed by the Command Center; do not hand-edit -->
**Sub-tools in this folder** (you can launch into any of these; file a learning to the one it belongs to):
- `Usage/` -- This is everything about the usage tracking tool
<!-- /CC:CHILDREN -->

The ClaudeFather platform's web control plane: a single **stdlib-Python HTTP server** (`server.py`,
~12.8k lines) with an **embedded vanilla-JS frontend** (the `PAGE` string). No build step, no deps
beyond the stdlib (one optional: `cryptography` for Ed25519 superadmin; falls back to HMAC). It serves
the dashboard, runs tmux sessions in a browser terminal, drives agents/Ralph loops, talks to the rest
of the fleet (mesh), and integrates Google Workspace + Tasks + deliverables.

- Serves `0.0.0.0:8799` (override `HPCC_PORT` env or `cc.config.json:port`); reachable on the tailnet.
- **Self-locating + portable:** `BASE`=this dir, `CC_HOME`=parent (the install root). All project-specific
  settings come from `cc.config.json` (resolved via `$CC_CONFIG`, else `$CC_HOME/cc.config.json`) — never
  hardcode. Nestable: each instance points at its OWN config, so child instances run the same `server.py`.
- After editing `server.py` or a lens, the running dashboard does NOT update until its supervised tmux
  session is recreated. **Use the `claudesole-restart` skill** (don't just `kill` the process).

## How it runs (supervisors)
- `cc-supervise.sh` — runs the CC inside tmux session **`hpcc`** on the SHARED brain tmux server (so it
  inherits TCC context with external-SSD access; launchd's own context gets EPERM on `/Volumes/...`).
  launchd `KeepAlive` restarts it. This is the production path.
- `cc-instance-supervise.sh <CC_CONFIG> <sess>` — generic supervisor for any nested instance (overseer, etc).
- `launcher.command` — double-click/GUI launcher (kills port 8799, nohups `server.py`, opens browser).
- `cc-launch.sh <studio|t490|t480> <name> [dir]` — creates a persistent tmux session; remote targets wrap
  `ssh -t` into the Windows box (Windows has no tmux; the Studio tmux is the persistence layer).
- `bridge-supervise.sh` / `crons-supervise.sh` — text2tune product runtime supervisors (not the CC itself).

## server.py — major sections (line anchors approximate)
- **Config/boot** (1–160): imports, `cc.config.json` load, `PROJECT`/`BRAND`/`PRODUCT`/`THEME`/`STORAGE_MODE`/
  `ROLE`/`PRESET`/`PORT`/`SCOPE_SESSIONS`, state-file path constants. `render_page()` injects preset lenses.
  Boot tail (`__main__`, ~12727): chmod 0600 secret files, credential-change watch, then a daemon thread for
  heavy housekeeping (treemap, framework blocks, deliverables migration) so the HTTP server serves immediately.
- **Claude account wallet** (78–124): per-node remote-login token files + usage.
- **State persistence** (163–169): `load()`/`save()` over the `_*.json` files in `STATE_DIR` (defaults to this
  dir); `slug()`, `projpath()`.
- **iCloud materialization** (175–227): force-download evictable iCloud files before reading.
- **Mesh comms** (227–300, 1223–1400): inter-chief messaging — persistent inbox (`_mesh_inbox.json`),
  durable outbound queue with retry/backoff, the mesh worker, send/recv/reply. Pairs with `mesh_stop_hook.py`.
- **Tiered mesh trust + superadmin** (300–540): `MESH_TOKEN` (family badge), `MESH_ENFORCE` gate,
  `SUPERADMIN_TOKENS`, and Ed25519/HMAC **superadmin grants** (cryptographically-signed platform-owner
  directives any node will execute via `/api/superadmin-exec`). Keys: `.superadmin_ed25519` (MC-only, 0600),
  `superadmin.pub` (shipped, every node trusts it).
- **Google Workspace** (540–1175): server-side OAuth client (token file under the google-workspace extension
  secrets). Gmail (list/get/thread/send/draft/label/snooze/attachments), Calendar (events/create/update/rsvp/
  delete), Drive (list/get/content/thumb/modify/upload). `_g_api` + `_g_parallel`.
- **Auth + manifest** (1184–1222): `AUTH_TOKEN` (off by default = open), cookie login, `AUTH_EXEMPT` /
  `AUTH_MESH_INGRESS` path allowlists, PWA web manifest.
- **Shell/ssh/tmux + fleet** (1402–1440): `sh()`, `ssh_to()`, `machine_status()`, `all_status()`.
- **Sessions** (1440–1548): tmux session listing, scoping to `PROJECT` (`SCOPE_SESSIONS`), protected names,
  titles, cwd/location labels.
- **Token usage** (1549–1822): scans `~/.claude/projects` transcripts for per-session remaining-context +
  metered cost; `usage_payload()` / `token_usage_payload()` (subscription-vs-API leverage).
- **Pipeline live-view** (1822–1908): reads the project's `.pipeline/` (`PIPELINE_DIR`) manifests/heartbeats.
- **Deliverables/storage** (1909–2153): GitHub backup hub + **tiered deliverables**. `STORAGE_MODE` /
  `DELIV_LOCAL_ROOT` (SSD/local store, overrides iCloud) / iCloud age-off to SSD. Scoped browser file explorer.
- **Claude account switching** (2264–2364): snapshot/swap the GLOBAL macOS-Keychain login + `~/.claude.json`.
- **Launch + Chief + agents** (2365–2566): `launch()` (the session creator), the persistent **Chief of Staff**
  session, peer roster + `chief_broadcast`, the **Admin shell** (operator-typed sudo), `agent_open()`.
- **Extensions** (2567–2808): installable add-ons (Marketplace lens) — per-deploy secrets (`.env.claudefather`),
  notify channel, MCP wiring, theme CSS, install/uninstall/setup.
- **Agents / Skills / Teams** (2809–3420): scoped agent-tools (`agents/<slug>`), REAL Claude Code skills
  (`.claude/skills/*/SKILL.md`), Teams (multi-agent rosters that launch coordinated sessions), `ROSTER.md` gen.
- **Description-audit** (3421–3636): the anti-rot routine — static + live audit of agent/skill descriptions
  (the orchestrator only sees descriptions at selection time; weak ones make a capability invisible).
- **Overseer/portfolio** (3637–3722): roll up child ClaudeFathers (scrape their `/api/chief` + `/api/security`).
- **Compaction** (3723–3864): write-handoff → `/compact` → re-read (preserve agent memory across compaction).
- **History/resume** (3865–3942): past conversations across the fleet (`scan_projects.py`) + resume/fork.
- **Ralph loops** (3943–4105): file-driven parallel agent loops; state in `data/ralph/<name>/` (run by
  `ralph_runner.py` inside `ralph-<name>` tmux). See `RALPH_LOOPS.md`.
- **Managed CLAUDE.md blocks + module system** (4106–4593): the Docs/Modules lenses — write/remove
  `<!-- CC:BEGIN id=.. -->` regions across the project tree, whole-tree module map (`CC:TREEMAP`),
  framework-default governance blocks (`seed_framework_blocks`).
- **Agency integration** (4594–4694): interpret the tree as Clients/Partners/Pipeline/Tools (vs Product Modules).
- **Email folders / VoiceMatch / Tasks / Ideas** (4695–6078): client-mail folders + auto-assign,
  the **VoiceMatch** smart-reply engine (voice profile, 360-context bundle, staged replies), **Tasks**
  (programmatic FREE extraction + AI scan + Morning Command Center daily loop), Ideas capture/promote.
- **CCR / drift / settings** (6079–6280): Core Change Request queue (up to Mission Control), framework drift
  report, UI settings (tier/type).
- **Browser terminal** (6281–6332): stdlib **WebSocket ↔ PTY** attached to tmux; `set_winsize`.
- **`class H`** (6333–12648): the request handler. `do_GET` (~6475: routes, `/ws` terminal, `/wsvnc`,
  `/static/`, `/` → `render_page`), `do_POST` (~6652: all `/api/*` mutations), auth gate, `serve_static`.
  The giant **`PAGE`** frontend string lives inside this region (starts ~7149).
- **Autoapprove** (12649–12722): keep agents off the permission-prompt wall (`_autoapprove_loop`).

## Frontend (the `PAGE` string, ~7149+)
Single-page vanilla JS. `LENS` selects the active view; `render()` (~8205) dispatches to per-lens loaders.
Lenses include: pillars, modules, files, gmail/calendar/drive, ralph, pipeline, jobs, machines, desktop,
usage, backup, security, agents, marketplace, agency, calls, comms, skills, teams, audit, portfolio,
sessions, history, tree, tasks, ideas, ccr, propose, accounts, settings, chief, docs, doctor. Which lenses
appear is driven by the **preset** (`../presets/<PRESET>.json` → `project.json` / `overseer.json`).
Brand assets in `static/brand/`; terminal via `static/xterm.js`; remote desktop via `static/novnc/`.

## Helper files (this dir)
- `granola.py` — Granola call transcripts → reviewed proposals (client CLAUDE.md note + tasks/reminders).
  `server.py` calls `granola.init(ctx)` once; `gr_*` behind `/api/granola*`. Nothing applies until approved.
- `ralph_runner.py` — the Ralph loop driver (one loop/invocation, runs in `ralph-<name>` tmux).
- `scan_projects.py` — fast scan of `~/.claude/projects` → past-conversation JSON (runs on macOS + Windows).
- `cc-session-watchdog.py` — nudges opted-in tmux sessions stalled on API outages (launchd ~45s; opt-in only).
- `mesh_stop_hook.py` — Claude Code Stop hook: forwards a chief's EXACT reply to the peer that messaged it
  (deterministic, no scrape). No-op on operator turns. Wired via the chief launch `--settings` + `MESH_CC`.
- `git-backup.sh` / `git-backup-secretscan.py` — backup engine + pre-backup secret/oversize gate (aborts
  staging if a real secret or >95MB file would be committed; public Supabase anon key is intentionally allowed).
- `cc-task "<title>"` — propose a to-do; lands as a SUGGESTION in the Tasks lens (resolves port/token from config).
- `agents/<slug>/` — scoped agent-tool dirs (`config.json`, `reports/`); also `_agent-backup/`.
- `_*.json` — per-node state (machines, components, routines, ralph, jobs, ideas, tasks, ccr, resumes,
  managed blocks, mesh inbox/settings, kc/cred backups). `STATE_DIR` defaults to this dir.

## Hard rules / gotchas
- **Stdlib only.** Don't add pip deps to `server.py`. `cryptography` is the sole optional import (guarded).
- **Tasks extraction must not flood the list.** The FREE programmatic sweep (`_extract_tasks_from_text`,
  `tasks_sweep_programmatic`) scans sent/received mail for commitments/requests. THREE invariants keep it sane
  (regressions here = a junk-task flood, esp. on bulk-outreach inboxes): (1) contraction patterns REQUIRE an
  apostrophe — never optional (`i'?ll`/`we'?ll` also match "ill"/"well", so greetings like "Hope you're well!"
  became "(you committed)" tasks); (2) greetings/pleasantries/sign-offs are dropped via `_is_task_boiler`
  (extend its list, don't loosen it); (3) `task_add` dedups on the `fp` fingerprint in ANY status, so a
  dismissed/done suggestion never resurrects on the daily morning re-scan (keeps the loop idempotent). Titles
  are HTML-unescaped + tag-stripped in `task_add`. Per-node data: `_tasks.json` (gitignored state).
- **Restart after edits:** changes don't take effect until the `hpcc` tmux session is recreated —
  use the `claudesole-restart` skill.
- **Portability boundary:** anything project/tenant-specific goes in `cc.config.json`, not the code.
  Never reintroduce hardcoded paths/ports/brand. `INSTANCE_ID` + `PORT` + brand all derive from config.
- **Secret files are chmod 0600 on boot** (`cc.config.json`, `peers.json`, mesh hook settings). Don't make
  them world-readable. Never change `auth_token`/`mesh_token` without confirming the exact value first
  (lockout risk; a credential-change watch logs any change to `~/.cc-credential-changes.log`).
- **Auth is OFF by default** (open) so existing deployments keep working; `doctor()` warns while off.
  Mesh enforcement (`MESH_ENFORCE`) is likewise carried-but-not-rejected until explicitly turned on.
- **Run on the brain tmux server, not bare launchd** — the SSD (`/Volumes/Samsung990PRO`) needs that TCC
  context; bare launchd EPERMs and silently breaks the Docs/doctor/deliverables lenses.
- **Write growing artifacts to the SSD**, never the near-full internal disk (deliverables → `DELIV_LOCAL_ROOT`).
- **Boot must not block on I/O:** heavy housekeeping runs in a daemon thread; keep it that way (a slow iCloud
  node once "came up" but never reached `serve_forever`).
- Sessions are tmux ON THE STUDIO (even "open on T490/T480" = a Studio tmux wrapping `ssh -t`). Agents have
  no TTY → no sudo; use the Admin shell pre-type protocol (`docs/SESSIONS_AND_SUDO.md`).

## How to extend it
- **New API + lens:** add a backend fn → register a `do_GET`/`do_POST` route in `class H` → add a `loadX()`
  in `PAGE` and a `LENS=="x"` branch in `render()` → list the lens in the relevant `presets/*.json`. Restart.
- **New agent-tool:** `agent_create()` / drop `agents/<slug>/` (config + CLAUDE.md + reports). Give it a
  strong description (the orchestrator selects on the description — run the description-audit).
- **New skill:** `.claude/skills/<name>/SKILL.md` (frontmatter `name`+`description`); surfaced via Skills lens.
- **New extension:** Marketplace install/uninstall; per-deploy secrets in `.env.claudefather` (gitignored).
- **Mesh/superadmin changes:** respect `AUTH_MESH_INGRESS` and the token tiers; never weaken the gate silently.

<!-- CC:NOTES (preserve this region verbatim across regenerations) -->
<!-- /CC:NOTES -->
