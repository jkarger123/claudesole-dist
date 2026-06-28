# Extensions — the ClaudeFather Marketplace catalog

The installable add-on system. Each subdir here is **one extension**: an external integration, an
agent-tool, a skill, a theme, or a lens. The catalog ships with the framework (propagates to every
deployment via `cc-update`); **install state + secrets are per-deployment** and gitignored.

Authoring standard: **`AUTHORING.md`** (READ FIRST before adding/editing any extension — it is law).

## What an extension IS (the contract)
A dir `extensions/<id>/` containing:
- **`extension.json`** — REQUIRED. The catalog card + the model-facing trigger. Keys: `id` (==dir name,
  `[a-z0-9-]`), `name`, `category`, `version`, `icon`, `summary`, `description`, `provides[]`,
  `requires[]`, `setup_doc`, `setup_agent`, **`default_category`** (which nav category this extension's lens
  lands in — Google/Workspace/Agency/Team/Integrations/System; surfaced via `_ext_lenses().category`; every
  extension declares one). `summary`/`description` are advertising the orchestrator reads at selection
  time — weak text = invisible capability.
  - **A lens needs a `lens:{id,label,icon}` object** to get a nav tab — that's what `_ext_lenses()` reads.
    `provides:["lens:x"]` is informational ONLY (it does NOT surface a tab). (This bit Granola: it declared
    `provides:["lens:calls"]` but no `lens` object, so the Calls tab never showed on any node until v0.99.4.)
- **`SETUP.md`** — REQUIRED. The script the guided setup agent runs. Fixed section order (What/Why/How/
  Prerequisites/Setup steps/Verify/Usage/Best practices) — see AUTHORING.md.
- Category-specific payload (below).

## Categories — how `install` wires each (server.py, `_ext_apply_payload` + `_ext_wire_mcp`)
- **`integration`** (MCP / external service): ships `mcp.json` (template with `<PLACEHOLDERS>`). Install
  merges its `mcpServers` into the deployment `.mcp.json`; the setup agent fills credentials + writes
  secrets to the gitignored env. (Path A claude.ai connectors need no `mcp.json` — wired at setup.)
- **`agent-tool`**: ships `payload/` (an `agents/<id>/` charter + `tools/run.py`). Install copies it to
  `AGENTS_DIR/<id>/`, adds it to `.gitignore`, surfaces it in the Agents lens.
- **`skill`**: ships `payload/` (a `SKILL.md`). Install copies it to `~/.claude/skills/<id>/`, surfaces
  in the Skills lens.
- **`theme`**: ships `theme.css` scoped to `[data-theme=<id>]`. Install records it; select via
  `cc.config` `theme:`. Cosmetic only — no data, no secrets.
- **`agency`/`lens:*`** (e.g. granola): provides a dashboard lens; configured via `cc.config.json`, not
  MCP. (Not in AUTHORING's four — a real category used by the agency shape.)

Uninstall is **reversible**: MCP entries removed, skill/agent payloads moved to `_archive/` (never
deleted), accounts/keys never touched.

## Where things live (server.py ≈ lines 2567–2806)
- **Catalog**: `extensions/` (this dir) → `EXT_DIR`. FRAMEWORK; propagates via `cc-update`. Do not put
  per-deployment state here.
- **Install state**: `<state>/_extensions.json` (`{"installed": [...]}`) → `EXT_STATE`. PER-DEPLOYMENT,
  gitignored. (`command-center/_extensions.json` is this node's.)
- **MCP wiring target**: `<deploy>/.mcp.json` → `MCP_JSON`. Gitignored.
- **Secrets**: `<deploy>/.env.claudefather` (`KEY=VALUE`) → `DEPLOY_ENV`; or a per-extension `secrets/`
  dir (google-workspace) that ships its own `.gitignore`. NEVER committed, never echoed in full.
- **API/UI**: `/api/extensions` (list), `/api/extension-{install,uninstall,setup}`; Marketplace lens
  (`loadMarketplace`, server.py ~11249). Setup = a tmux `claude` agent in the ext dir briefed by SETUP.md.

## Hard rules / gotchas
- **ASCII only.** Secrets ONLY in the gitignored deployment env / `secrets/` — never in
  `extension.json`/`SETUP.md`/git; never echo a full token. Default read-only / least-privilege.
- **Core change, not local:** new/edited extensions are a PLATFORM change. On a node, route via a CCR
  (Propose Change) — build once at Mission Control, ship via dist + `cc-update`. Don't author locally on
  a tenant node.
- `id` MUST equal the dir name. Install loops scan dirs; `_`/`.` prefixes are skipped.
- Integrations may intentionally **not** auto-wire on install (figma: endpoint unconfirmed → setup
  verifies + wires). Path A connectors carry no `mcp.json`.
- `telegram-notify/notify.py` is a self-contained payload any loop/cron/agent can call directly; the
  server's `notify_send()` is the in-process path (Telegram is the only channel today).

## Extending it
1. `mkdir extensions/<id>`, write `extension.json` + `SETUP.md` per AUTHORING.md.
2. Add the category payload: `mcp.json` (integration) / `payload/` (skill, agent-tool) / `theme.css`
   (theme).
3. It auto-appears in the Marketplace (catalog is a dir scan). Test Install → Set up → Verify.
4. On a node, ship it as a CCR — don't commit it into a tenant deployment.

## Catalog index (one line each)
**Integrations (MCP):**
- `github` — repos, issues/PRs, CI status (GitHub official MCP; remote OAuth or local PAT).
- `atlassian-jira-confluence` — Jira issues + Confluence pages (Atlassian Cloud).
- `aws` — query AWS resources + docs, read-first.
- `brave-search` — live privacy-respecting web search (Brave index).
- `cloudflare` — Workers, DNS, KV/R2, analytics.
- `figma` — read Figma files/components/frames for design-to-code (endpoint unconfirmed; wired at setup).
- `filesystem` — scoped, read-controlled file ops over a chosen dir.
- `google-workspace` — Gmail + Calendar + Drive + a Google power-agent; draft-first email; Path B
  self-hosted MCP default for headless; ships `secrets/` + a Google agent payload.
- `linear` — read/manage Linear issues, projects, cycles.
- `notion` — read/write Notion pages + databases.
- `pagerduty` — incidents + on-call; ack/resolve with approval.
- `playwright-browser` — drive a real browser (navigate/click/fill/screenshot).
- `postgres-supabase` — read-only-by-default SQL against Postgres/Supabase.
- `sentry` — production errors + issues.
- `slack` — post to + read from Slack channels.
- `stripe` — customers, subscriptions, invoices, refunds (read-first).
- `telegram-notify` — two-way Telegram: push notifications + chat to agents (also `notify.py` payload).

**Agent-tools:**
- `incident-commander` — capstone agent: triages Sentry + PagerDuty + logs into one ranked posture
  (degrades to logs-only).

**Skills:**
- `web-research` — guided deep-research workflow (fan-out search, verify sources, cited synthesis).

**Themes:**
- `theme-claudefather-dark` — dark, high-contrast ClaudeFather palette (cosmetic; no data/secrets).

**Lens (agency):**
- `granola` — Granola call transcripts → REVIEWED proposals updating client CLAUDE.md, tasks, reminders
  (Calls lens; configured via `cc.config.json`).
