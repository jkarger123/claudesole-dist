# ClaudeFather Platform — Master Architecture

> Enterprise architecture reference for the ClaudeFather autonomous-operations platform.
> Repo root: `<CC_HOME>` (the control plane; the canonical *project* tree lives on the SSD at `<project root>`).
> Authority: this node is **Mission Control** — the ClaudeFather platform authority. Framework changes are built here and shipped to the fleet.

---

## 1. What ClaudeFather Is

ClaudeFather is a **self-hostable control plane for running autonomous Claude operations as a governed fleet**. A single deployment ("a ClaudeFather") wraps one project: it gives a human operator a web dashboard over live Claude Code sessions, scoped agent-tools, scheduled loops, third-party integrations, and a persistent "Chief of Staff" Claude session — all on the operator's own hardware, with secrets that never leave the box.

Multiple ClaudeFathers federate under a **ClaudeGrandfather** (Mission Control / an "org" node) into an asymmetric-authority mesh: **governance flows DOWN** (the owner can force any node via cryptographically signed grants) and **observability + change requests roll UP** (a node can only *propose* core changes; it never acts on a peer's say-so). The same framework code runs at every altitude — only `cc.config.json` (role, project, secrets, paths) differs.

**Design tenets that recur everywhere:**
- **One codebase, many tenants.** The framework (`server.py`, `agents/`, `presets/`, `bin/`, manifest) is generic and ships unchanged; per-deployment config/data/secrets/state are the only things that vary. Nesting is real: child instances live under `instances/` and reuse the same code via `$CC_CONFIG` + per-instance `state_dir`.
- **Zero build step.** The whole frontend is an embedded vanilla-JS single page inside the server; the server is stdlib Python with one optional guarded `cryptography` import.
- **Read-only / least-privilege / human-gated by default.** Agents propose; humans approve. Scanned content is treated as untrusted data, never instructions. Irreversible actions escalate to a human.
- **Single source of truth, no drift.** Mission Control owns the framework; nodes that hand-edit framework files are detected (fingerprint drift) and must instead file a Core Change Request (CCR).
- **Secrets never committed, never echoed, never shipped.** `.env.claudefather`, `secrets/`, tokens, and per-deployment state are gitignored and excluded from updates; secret files are chmod-600 hardened.

**Mental model — three concentric rings:**
1. **The engine** — one HTTP server process per node (`command-center/server.py`) that *is* the dashboard, the API, the mesh participant, and the supervisor of Claude sessions.
2. **The deployment** — that engine pointed at one project via `cc.config.json`, with its own state, deliverables, agents, extensions, and Chief of Staff.
3. **The fleet** — many deployments federated over Tailscale under Mission Control, with signed governance down and observability/CCRs up.

---

## 2. The Core Engine — `command-center/server.py`

The Command Center is the platform's web control plane: a single **~28.5k-line stdlib-Python HTTP server** (as of 2026-07-09; the embedded `PAGE` frontend alone is ~9.6k lines, ~286 `/api` endpoints) with an **embedded vanilla-JS single-page frontend** (the `PAGE` string inside request-handler class `H`). No build step, no external deps except the optional guarded `cryptography` import used for Ed25519 superadmin.

> **Platform self-assessment (2026-07-09):** a full 5-agent deep audit of ClaudeFather — architecture, fleet/governance, packaging, the OmniAgent benchmark, and the product differentiator — plus the definitive platform profile and the ranked roadmap live in `conceptsandideas/OmniAgent/deliverables/deep-audit-20260709/` (`CLAUDEFATHER_PROFILE.md` + `THE_PATH_FORWARD.md`).

- **Bind / portability.** Serves the dashboard on `0.0.0.0:8799` (override via `HPCC_PORT`/config). Self-locating and portable: `BASE` = this dir, `CC_HOME` = parent, all tenant settings come from `cc.config.json` via `$CC_CONFIG`, so nested instances reuse the same code with different config + `state_dir`.
- **Supervision.** Runs inside the `hpcc` tmux session on the shared **brain tmux server** (`cc-supervise.sh` + a launchd `KeepAlive`) so it inherits TCC context for SSD access. **Edits to `server.py` do NOT take effect until that session is recreated** — use the `claudesole-restart` skill after any server/frontend edit.
- **Non-blocking boot.** Config/boot runs a **daemon-thread housekeeping tail** so the server never blocks `serve_forever` on slow I/O (e.g. iCloud faulting, deliverables re-routing).

**Major sections inside `server.py` (the whole platform lives here):**
- Config / boot; `ROLE` / `PRESET` / `SCOPE_SESSIONS` resolution (~L41–51).
- Claude **account wallet** (`_claude_wallet.json`, 0600 token files).
- JSON state persistence (the `_*.json` registries).
- **Mesh comms** + tiered trust + Ed25519/HMAC **superadmin** grants (~L234–1390, ~L321–535).
- Full **Google Workspace** client (Gmail/Calendar/Drive over stdlib `urllib`, ~L540).
- Cookie **auth** (off by default), tiered `_authed()`.
- Fleet / tmux **sessions**, token-usage transcript scanning, **pipeline** live-view.
- Tiered **deliverables / storage** (SSD vs iCloud, doctor at ~L4265).
- **Chief of Staff** + **Admin shell** + **agent-tools** discovery + run.
- **Extensions / Marketplace** wiring (~L2567–2806).
- **Agents / skills / teams** + description anti-rot audit.
- **Overseer / portfolio** rollup, compaction, history/resume, **Ralph loops**.
- Managed `CLAUDE.md` blocks + module map, **agency integration**, email folders + VoiceMatch smart-reply + Tasks/Ideas.
- **CCR / drift / settings**, a stdlib **WebSocket↔PTY browser terminal**, and request-handler class `H` (`do_GET`/`do_POST` route maps, `/ws`, `/wsvnc`, `/static`, `PAGE`).

**Frontend model.** The single page dispatches by **LENS**. Which lenses appear is driven by `presets/<PRESET>.json` (filtered in `applyPreset()`, ~L12195); several lenses self-toggle on capability flags (`window.CC.agency/pipeline/google/accountWallet`, org-only `portfolio`, always-on `tasks`).

**Engine helpers (same dir):** `granola.py` (Calls engine), `ralph_runner.py` (loop runner), `scan_projects.py`, `cc-session-watchdog.py`, `mesh_stop_hook.py` (the mesh reply mechanism), `git-backup.sh` + `git-backup-secretscan.py`, `cc-task`, and the `cc-supervise.sh` / `cc-launch.sh` shell scripts.

---

## 3. Installer & Lifecycle

The packaged **entry point** lives in `install/` (`install.sh` bootstrap, `AGENT_INSTALL.md` agent playbook, `README_INSTALL.md` human intro). The **lifecycle scripts** live at the framework root (`$CC_HOME`):

- `cc-init.sh` — scaffold a node and write its `cc.config.json`.
- `cc-update.sh` — overlay framework paths from upstream; **never touches `preserve_paths`**; splices `CC:NOTES` regions in Markdown (code copies verbatim); chmod-600 secures secrets on the tail.
- `cc-spawn.sh` / `cc-promote.sh` — create / promote nested child instances under `instances/`.
- `cc-recover.sh` — break-glass dump of PIN / port / URL.
- `make-install-package.sh` — build the dist zip.
- `brain.sh` — operator session on the shared brain tmux server.

**`claudesole.manifest.json` is the single source of truth** for what is generic vs per-deployment:
- **FRAMEWORK paths** — ship + propagate via `cc-update` (server.py, agents charters/tools, presets, bin, manifest).
- **PRESERVE paths** — config / data / secrets / state, **never overwritten** by an update.
- **`CC:NOTES`** preserve-region markers — local notes inside otherwise-framework Markdown survive updates.

**Update flow:** dev → fleet via `cc-update` against either the **private core repo** or, for credential-less nodes, the **public `claudesole-dist` mirror** (local checkout at `/Users/Shared/claudefather-dist/claudefather`). Key gotchas: ASCII-only; `CC:NOTES` splice is MD-only; two `install.sh` copies exist; never modify a migration's live original; never bulk `git add` the dirty core tree.

---

## 4. The Extension Model + Marketplace

`extensions/` is the **Marketplace catalog**: each subdir is one installable extension. An extension is a directory with:
- a required **`extension.json`** (catalog card + model-facing trigger: `id/name/category/version/icon/summary/description/provides/requires/setup_doc/setup_agent`), and
- a required **`SETUP.md`** (the script a guided tmux **setup-agent** runs; fixed section order per `AUTHORING.md`).

**Five category mechanics, all wired in `server.py` (~L2567–2806):**
- **integration** — ships an `mcp.json` template whose `mcpServers` are merged into the deployment's gitignored `.mcp.json` on install; the setup agent fills secrets.
- **agent-tool** — ships `payload/` copied to `AGENTS_DIR/<id>/`.
- **skill** — ships `payload/` copied to `~/.claude/skills/<id>/`.
- **theme** — ships `theme.css` scoped to `[data-theme=<id>]`, selected via `cc.config`.
- **agency / lens** — adds a dashboard lens configured via `cc.config.json` (e.g. granola's Calls lens).

**Catalog vs state vs secrets.** The catalog (`EXT_DIR`) is FRAMEWORK and propagates via `cc-update`. Install **state** is per-deployment in `<state>/_extensions.json` (`EXT_STATE`, gitignored). Secrets live in `<deploy>/.env.claudefather` or a per-ext `secrets/` dir (google-workspace). API: `/api/extensions` + `/api/extension-{install,uninstall,setup}`, surfaced in the **Marketplace** lens. Uninstall is reversible (MCP removed, payloads archived; accounts/keys never touched).

**Hard rules:** ASCII only; secrets never committed/echoed; read-only / least-privilege default; and on a **tenant node, new/edited extensions must be routed as a CCR** (built once at Mission Control, shipped via dist) — never authored locally.

**Catalog (current):**
- **Integrations:** github, atlassian-jira-confluence, aws, brave-search, cloudflare, figma, filesystem, google-workspace, linear, notion, pagerduty, playwright-browser, postgres-supabase, sentry, slack, stripe, telegram-notify.
- **Agent-tool:** incident-commander (triages Sentry + PagerDuty + logs into one ranked posture; degrades to logs-only).
- **Skill:** web-research (guided deep-research workflow; payload copied into `~/.claude/skills`).
- **Theme:** theme-claudefather-dark.
- **Agency/Calls lens:** granola.

**Notable behaviors:** `figma` intentionally does NOT auto-wire `mcp.json` (endpoint unconfirmed; wired at setup); `telegram-notify` ships `notify.py` as a standalone payload callable by loops/cron; `google-workspace` defaults to a self-hosted **Path B** MCP for headless use and is **draft-first** for email.

---

## 5. Scoped Agents (`agents/`)

`agents/` is the ClaudeFather's **agent-tool roster**: each subdir is one scoped, human-facing capability with its own `CLAUDE.md` charter, optional `tools/` (a read-only `run.py` check-suite plus any gated executors), per-deployment `config.json`, and `reports/`.

**Discovery + UI (zero per-agent frontend code).** The Command Center auto-discovers any `agents/<slug>/` that has a `CLAUDE.md` (`agents_list` in `server.py`) and renders it in the **Agents** lens. `agent_open` launches a tmux session (`agt-<slug>`, cwd = the agent dir) briefed to read its own charter; `agent_run` executes `tools/run.py` with `CC_AGENT_STATE` (reads this instance's config, writes this instance's reports); `agent_report` reads `reports/latest.json` for the RAG rollup. Tools write a **common report schema** `{slug,title,overall,summary,counts,items[],ts}`; rollup precedence `err > warn > ok > unknown`.

**Framework vs per-deployment.** Charters + tools are shared framework (shipped via repo / `cc-update`); `config.json` + `reports/` are per-deployment and gitignored, so nodes never collide. `agent_delete` archives to `agents/_archive/` (never `rm`).

**The nine agents:**
- **backup** — additive-only git backups (engine = `command-center/git-backup.sh` + a 4h launchd job; never destructive/force-push).
- **cost** — read-only spend posture vs thresholds; never calls a paid/billing API.
- **deploy** — ship-readiness health checks (read-only) + a `--yes`-gated `deploy.py` executor; never fires autonomously.
- **google** — Gmail/Calendar/Drive via MCP, read/draft-first; never sends; needs Path B MCP for headless.
- **ideas** — capture verbatim → refine → promote (logic in `server.py` `idea_add/idea_promote`).
- **incidents** — read-only open-incident posture from configured logs; never remediates.
- **routines** — scheduled-job heartbeat; **currently a stub** (registry exists, runner not yet wired).
- **security** — posture auditor with its own richer `checks[]/sev/dim` schema + `rotation_ledger.json` + `ROTATION_CHECKLIST.md`; proposes irreversible fixes for human approval only.
- **usage** — token + cost analytics from Claude Code transcripts (aggregation in `server.py`; Usage lens). Cost figures are estimates.

**Core principles across all agents:** read-only by default; state changes proposed for human approval; scanned content treated as untrusted data; never read secret contents; ASCII-only with large output to the SSD; delete-means-archive.

---

## 6. Presets & Roles — ClaudeFather vs ClaudeGrandfather

`presets/` holds the **role-tier lens/agent bundles**. Two JSON files express the two deployment tiers:

- **`project.json` — ClaudeFather (`role: "project"`)** — the full ~24-lens single-project operator surface (lands on **Sessions**).
- **`overseer.json` — ClaudeGrandfather (`role: "org"`)** — a leaner portfolio/overseer surface aggregating child ClaudeFathers (lands on **Portfolio**). Mission Control is the canonical overseer.

**Selection flow (in `server.py`):** `ROLE` comes from the instance's `cc.config.json`; `PRESET` defaults to `ROLE` but is overridable; `render_page()` loads `presets/<PRESET>.json` and injects `.lenses` as `window.CC.lenses`; the frontend `applyPreset()` (~L12195) hides any nav button whose `data-l` isn't in the list, then lands on `lenses[0]`. `SCOPE_SESSIONS` also derives from role (projects see only their own sessions; an org can see the whole box).

**Lenses that escape the preset list (capability-gated):** `agency`/`calls` (via `CC.agency`), `pipeline` (via `CC.pipeline`), `gmail`/`calendar`/`drive` (via `CC.google`), `accounts` (via `CC.accountWallet`), `tasks` (always on), `portfolio` (org-only).

Both preset JSONs are **framework files** (in `FW_FINGERPRINT_FILES`) — change them at Mission Control and ship via dist/`cc-update`, never edit on a node.

---

## 7. Mesh, Superadmin & Multi-Node

The multi-node layer turns independent per-project Command Centers into a **governed fleet** with an **asymmetric-authority model**: governance/commands flow DOWN (signed superadmin grants); requests flow UP (CCRs the owner approves). Four cooperating subsystems, all in `server.py` over plain HTTP across Tailscale, plus a fixed 3-level nested-oversight model in docs.

**Peer roster (`peers.json` + `peers()`).** Shared instance list `{id,url}`; example fleet: node-a (8443), mission-control (default 443), node-b (10000), node-c (8850) — all on one Tailscale host (`your-host.tailXXXXX.ts.net`). `peers()` unions the shared file with a local `_instances.json`, deduped by URL; `INSTANCE_ID` lets broadcasts skip the node's own chief; served at `/api/peers`.

**The mesh (chief-to-chief, ~L234–1390 + `mesh_stop_hook.py`).** Each node runs a persistent **Chief of Staff** Claude session in tmux (`chief_open`, launched `--dangerously-skip-permissions` with a Stop-hook settings file + `MESH_CC` env). Any chief reaches any/all peers via `chief_broadcast` / `mesh_send` (POST `{text, targets:[...]}` to `/api/chief-broadcast`; empty targets = all). Delivery is an **enterprise durable queue**, not a blocking curl: `mesh_enqueue` writes a pending out-record; a single background `_mesh_worker` drains it (`kind='msg'` → peer `/api/chief-say`, `kind='reply'` → `/api/mesh-recv`) with retry/backoff (`MESH_MAX_ATTEMPTS=6`) and status receipts (pending → delivered → replied | failed) shown in the **Comms** lens. `_mesh_deliver` injects inbound messages as a clean separate turn only when the chief is idle.

The key mechanism is **`mesh_stop_hook.py`**: Claude Code runs it when a chief finishes a turn; it parses the transcript for any unforwarded `[message from X]` user turn, extracts the chief's exact reply, and POSTs it to `/api/mesh-reply` → the peer's `/api/mesh-recv` — deterministic, instant, no screen-scraping, idempotent per message uuid. Operator turns never match `[message from]` (operator replies never leak to peers); replies arrive tagged `[reply from X]` and are NOT re-forwarded (exactly one round-trip). **"No silent drops":** an unanswered reply-expecting message past `MESH_REPLY_SLA` (default 600s) goes overdue with one auto re-ping and a dashboard/nav badge.

**Trust frame & tiered auth.** Every inbound peer message is stamped with **`PEER_FRAME`** — an explicit notice that it is from an untrusted external peer chief, not the operator, so the chief refuses secrets/destructive/outward actions on a peer's say-so. Auth is tiered: **`MESH_TOKEN`** is the family badge (every node under one grandfather shares it); **`SUPERADMIN_TOKENS`** are master keys trusted on top (the owner reaches any node in any family). **`MESH_ENFORCE`** gates rejection (default off = permissive rollout; flip true fleet-wide only once every node carries a badge). `_authed()` accepts operator cookie/Bearer/`X-CC-Token` OR a valid `X-Mesh-Token`. `AUTH_MESH_INGRESS` lists endpoints reachable by peer traffic without operator auth: `chief-say`, `mesh-recv`, `mesh-reply`, `ccr-submit`, `fw-fingerprint`, `superadmin-exec`.

**Superadmin (Ed25519 signed grants, ~L321–535, `docs/SUPERADMIN.md`).** The legitimate DOWN channel. Default since v0.10.0 is **public-key**: MC holds an Ed25519 private key (`.superadmin_ed25519`, 0600, gitignored, never shipped); the matching public key ships in the framework as **`superadmin.pub`** so every install verifies the owner's grants out of the box. A compromised install holds only the public key — it can verify, never forge. A grant `{v,node,action,params,issued,exp,nonce,alg}` is canonicalized + signed; `_sa_verify` enforces node-binding (== `INSTANCE_ID`), freshness (`exp`, `SA_SKEW=300s`), and single-use (nonce replay cache). A fallback derived-key **HMAC** path exists (`node_key=HMAC(master,"sa-v1:"+id)`); `alg` is inside the signed payload so it can't be downgraded. Flow: MC `/api/superadmin-send` (mint + POST) → node `/api/superadmin-exec` (the signature *is* the auth, so it crosses families). `superadmin_exec` runs only **allowlisted** actions, never arbitrary shell: `ping`, `accept_skip_permissions`, `set_config` (one allowlisted key; secrets excluded), `set_claude_setting` (synchronous), `instruct` (delivers an owner-authorized directive marked SUPERADMIN, NOT the peer frame), `cc_update`, `restart` (`os.execv` via `_self_restart`), `relink_deliverables`, `ageoff_deliverables`. MC-side mint endpoints require both the private/master key and operator auth.

**CCR — Core Change Requests (~L6079–6178).** Mission Control owns all framework/core build-out; nodes do NOT self-edit framework files. A node `ccr_propose`s (server-side POST to MC's `/api/ccr-submit`, local echo in `CCR_SENT`); MC queues it with lifecycle new → triaged → approved → building → shipped | rejected (kinds: module/extension/framework/fix), reviewed in the **Change Requests** lens, built once at MC, shipped via dist + `cc-update`. The mesh is the notify channel.

**Anti-drift backbone (~L6180–6243).** Each node fingerprints its core files (`FW_FINGERPRINT_FILES`: server.py, granola.py, mesh_stop_hook.py, ralph_runner.py, cc-update.sh, manifest, presets) via sha256 at `/api/fw-fingerprint`; MC's `drift_report` labels each peer current / behind / drifted (locally edited — a CCR violation) / ahead / unreachable / no-dist, making self-edits LOUD.

**Nested oversight (`docs/NESTED_OVERSIGHT.md`).** A fixed 3-level hierarchy **ORG** (Mission Control, role=org) → **PROJECT** (a ClaudeFather, role=project) → **MODULE** (a `CLAUDE.md` folder). Same framework at every altitude; role in config picks behavior; bounded recursion (default depth 3, cap ~5); leaf agents can't spawn. Topology is **PULL over Tailscale**: the org hub scrapes each spoke's read-only `/api/*` on a schedule, caching last-good payload + timestamp (never blocking a page load). Status states UP/DEGRADED/DOWN/UNKNOWN/STALE with staleness first-class. `portfolio()` is the partial implementation (rolls up each child's `/api/chief` + `/api/security` into a RAG; a dead child shows DOWN, never blocks). Non-negotiables: staleness never green; break-glass so org governance can't lock the owner out; spokes are independent failure domains.

---

## 8. Storage & Data

**Physical standard (`docs/STORAGE_ARCHITECTURE.md`).** Each node gets its OWN dedicated APFS SSD, and that node's macOS user HOME lives on it, so everything the node produces (project tree AND, for iCloud nodes, the iCloud container) sits on the SSD, not the small internal boot drive — because macOS can only sync the iCloud container inside the home on whatever volume the home is on. Requirements: SSD is APFS, mounted at login (desktop, not laptop), ownership ENFORCED; fresh installs set `NFSHomeDirectory` to `/Volumes/<ssd>/<user>` at user-create. Includes a backup-first relocation runbook (`rsync -aE`, chown, `dscl . -change NFSHomeDirectory`, reboot, verify) from a separate admin account.

**Enforcement (`/api/doctor`, ~L4265–4302).** Compares the home's volume device to the root volume via `st_dev`; emits warn-severity issues pointing at `STORAGE_ARCHITECTURE.md` when iCloud's home or the project lives on the internal drive.

**Storage modes (~L41–45).** `cc.config "storage_mode"` (default `"github"`): `github` = local + git push; `icloud` = local under the iCloud-synced folder; `icloud+github` = both. `_icloud_status()` verifies the project actually lives under `ICLOUD_ROOT` and counts `*.icloud` pending placeholders.

**The SSD data symlink.** Repo root has `data -> <SSD>/claudefather-data` (and `_source_docs -> .../caches/_source_docs`). Bulk/volatile runtime data lives on the SSD off the repo: `ralph/` (one dir per Ralph loop), `team-runs/`, `audit-runs/`, `research/`, `scratch/`, `caches/`, `downloads/`, `archive/`, `_module_archive/`, `deliverables/`, `backup.log`. `.gitignore` excludes `data/`, `_source_docs/`, `instances/`, `instances/*/state/`.

**Deliverables — the smart-files store (`docs/SMART_FILES.md`, ~L1936–2152).** Convention: anything an agent makes FOR the user goes in `<module>/deliverables/`. The Projects-lens drill-in shows a per-module Files card; a top-level **Files** lens aggregates every agent-output file across modules, newest first, tagged by module + storage tier. Two actions per file: Open (Finder reveal on host) and Download (PROJECT-scoped via `projpath`, secret-blocked via `_path_has_secret`). **Routing precedence:** (1) explicit `cc.config deliverables_root` (SSD/local store) overrides iCloud; (2) legacy iCloud tiered mode (hot in the iCloud container, cold aged off >90d to the SSD archive); (3) self-contained default `CC_HOME/deliverables`. This node uses option 1 (`.../deliverables/<node>`). The SSD-local store exists because headless full-disk boxes evict iCloud files and can't fault them back; local bytes always download. `_icloud_state()` uses `st_blocks==0` to detect evicted stubs; reads materialize on demand (bounded threaded read) so the server never hangs; boot housekeeping runs in a daemon thread.

**Per-node state files (`_*.json`).** `STATE_DIR` = `cc.config "state_dir"` or `BASE` (the command-center dir). Each instance keeps its own registries so portfolios never collide: `_machines.json`, `_components.json`, `_routines.json`, `_ralph_loops.json`, `_jobs.json`, `_ideas.json`, `_ccr.json`/`_ccr_sent.json`, `_resumes.json`, `_managed_blocks.json`, `_instances.json`, `_mesh_inbox.json`, `_session_titles.json`, `_extensions.json`, `_kc_backup.json`, `_backup_state.json`, `_cred_fingerprint.json`, `_mesh_hook_settings.json`, `_claude_wallet.json` (0600), plus per-instance `ACTIVE_TOKEN_FILE` (0600). The main node instance writes `_*.json` directly into `command-center/`; child instances set `state_dir` explicitly (`instances/<node>/state`, `instances/overseer/state`). **`cc.config.json` is the portability boundary** (`project_name/project_root/storage_mode/deliverables_root/state_dir/role`).

---

## 9. Where Everything Lives (map)

| Concern | Path |
|---|---|
| **Engine (server + frontend)** | `command-center/server.py` |
| Engine helpers | `command-center/{granola.py, ralph_runner.py, scan_projects.py, cc-session-watchdog.py, mesh_stop_hook.py, git-backup*.sh/py, cc-task}` |
| Engine CLAUDE.md | `command-center/CLAUDE.md` |
| **Installer entry** | `install/{install.sh, AGENT_INSTALL.md, README_INSTALL.md}` |
| **Lifecycle scripts** | `$CC_HOME/{cc-init.sh, cc-update.sh, cc-spawn.sh, cc-promote.sh, cc-recover.sh, make-install-package.sh, brain.sh}` |
| Ship manifest (FW vs PRESERVE) | `claudesole.manifest.json` |
| **Extensions catalog** | `extensions/<id>/` (each has `extension.json` + `SETUP.md`); authoring guide `extensions/AUTHORING.md` |
| Extension install state | `<state>/_extensions.json` |
| **Scoped agents** | `agents/<slug>/` (charter `CLAUDE.md`, `tools/run.py`, `config.json`, `reports/`); overview `agents/CLAUDE.md` |
| **Presets / roles** | `presets/project.json` (ClaudeFather), `presets/overseer.json` (ClaudeGrandfather) |
| **Mesh / fleet** | `peers.json`, `command-center/mesh_stop_hook.py`, `server.py` |
| **Superadmin keys** | `superadmin.pub` (shipped), `.superadmin_ed25519` (MC-only, 0600, gitignored) |
| Config (portability boundary) | `cc.config.json` (+ `$CC_CONFIG` for nested instances) |
| Nested instances | `instances/<id>/{cc.config.json, state/}` |
| **SSD data** | `data/ -> <SSD>/claudefather-data` |
| Deliverables (this node) | `<SSD>/claudefather-data/deliverables/<node>` |
| **Docs** | `docs/{SUPERADMIN.md, NESTED_OVERSIGHT.md, STORAGE_ARCHITECTURE.md, SMART_FILES.md, PACKAGING.md, MEMORY_SKILLS_AGENTS.md, SESSIONS_AND_SUDO.md, AGENCY_INTEGRATION.md, CHANGELOG.md}` |

**Key operational rules to remember:** restart via `claudesole-restart` after any `server.py`/frontend edit; never hand-edit framework files on a tenant node (file a CCR); never commit/echo secrets; default all output to the SSD; dashboard PIN is 3673 (confirm before any auth change).
