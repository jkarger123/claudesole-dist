# Command Center — the engine

<!-- LATEST-HANDOFF -->
**>> Resume here:** read `_handoffs/20260807-1556__command-center.md` first -- it is the latest handoff.
<!-- /LATEST-HANDOFF -->

> **▶ TOUCHING USAGE / ACCOUNT TELEMETRY? READ `docs/USAGE_TELEMETRY.md` FIRST.** `_scan_tok`,
> `_acct_active_at`, `_acct_feature_since`, `_acct_model_view` and `account_windows_store` sit on a hot path that
> runs over ~470k events on **every** dashboard poll — it once pinned a node at 146/193 threads with CPU at 100%.
> It is now held together by four deliberate guards (walk TTL, binary-search attribution, a feature memo, and a
> single-flight lock) plus two easy-to-break invariants (atomic index swap; `_feat_copy` must deep-copy
> `by_ver`). The doc has the measurements, the accuracy proofs, and how to diagnose a recurrence. **Never "fix"
> a slowdown here by deleting transcripts — that breaks the numbers (it once cut monthly usage 85k → 42k).**

> **▶ THE DISCIPLINE SYSTEM: `docs/ENGINEERING_AUTOPILOT.md`** — how we control the context payload (Menu/Scout/
> Vault) AND auto-enforce engineer-grade habits (folder structure, filing, warm-transfer routing, record-keeping,
> self-curating notes, housekeeping). Read it before touching context briefs, the housekeeping loop, the
> warm-transfer/drift sweep, or session lifecycle — it's the model you're plugging into.

> **▶ CROSS-VENDOR ADVISOR ("Third-party review"): `docs/CROSS_VENDOR_ADVISOR.md`.** The external-GPT
> second-opinion system — engine `cc-advise` (fail-open, budget-guarded, `--stream`), interactive button in
> every session (+`/term`), and the Ralph loop-finish review+steer gate (`ralph_runner.py` `_advisor_gate`).
> Read it before touching `cc-advise`, the `/api/advise*` routes, the advisor panel, or the Ralph advisor hook.
> Provenance (the "cheatsheet" it was built from) = the OmniAgent/Omnigent analysis in `conceptsandideas/OmniAgent/`.

> **▶ UI WORK? READ `docs/DESIGN_SYSTEM.md` FIRST.** The dashboard has ONE design language — build every lens/
> feature from the shared primitives (`cc-head`/`cc-list`/`cc-item`/`cc-grid`/`cc-tile`/`cc-panel`/`cc-in`,
> `mini`/`btn`(+`danger`), `badge bdg-*`, `confirmM`/`promptM`/`alertM`, `toast`/`busyOn`). NEVER hand-roll a
> native `confirm/prompt/alert`, an off-palette/GitHub-hex color, an inline-colored badge, or a decorative
> header/button emoji. ENFORCED: `command-center/ui_lint.py` runs in the preship gate, so violations FAIL the
> ship. Run `python3 command-center/ui_lint.py` (green = ships). New primitive? Add it to the shared CSS +
> DESIGN_SYSTEM.md so the next feature reuses it — don't inline a one-off.

> **▶ COLORS / THEMES? READ `docs/THEMING.md`.** The dashboard is **multi-theme** (Dark/Light/High-Contrast/
> Slate/Midnight/Paper) built on a semantic design-token vocabulary (`--bg/--card/--ink/--accent/--ok/…`). A theme
> is a `[data-theme=<id>]` block; `:root` is the default Dark palette (**byte-identical to before — never change it**)
> + the fallback. Per-operator choice (localStorage `cc_theme`) + node default (`cc.config theme`) + Auto (OS).
> Terminals theme too (`themeToXterm` in `TERM_PAGE`/`RALPH_PAGE`): **dark console on light themes** (Claude Code
> colors for a dark bg). NEVER hardcode a hex outside the theme blocks — it breaks every non-Dark theme. Adding a
> theme, the cascade, terminal + brand theming, code touch-points: all in `docs/THEMING.md`. Shipped v0.99.206.

<!-- CC:NOTES (preserve this region verbatim across regenerations) -->
<!-- /CC:NOTES -->

<!-- CC:CHILDREN auto-managed by the Command Center; do not hand-edit -->
**Sub-tools in this folder** (you can launch into any of these; file a learning to the one it belongs to):
- `ServerHeath/` -- >> Resume here: read _handoffs/20260704-1405__ServerHeath.md first -- it is the latest handoff.
- `Usage/` -- >> Resume here: read _handoffs/20260806-1811__Usage.md first -- it is the latest handoff.
- `autonudge/` -- My job: when a Claude session keeps stopping to ask "want me to keep going?", auto-send a canned push (e.g.
- `front-door/` -- >> Resume here: read _handoffs/20260720-0541__front-door.md first -- it is the latest handoff.
- `mobile/` -- >> Resume here: read _handoffs/20260725-1522__mobile.md first -- it is the latest handoff.
- `native-app/` -- A thin bare-Swift + WKWebView iPhone app that wraps the live ClaudeFather dashboard and adds the four native powers a web page can't have on iOS (background aud
- `update/` -- This folder is the home + documentation of how a ClaudeFather node gets new framework code, reliably,
- `vault/` -- This folder is the documentation home for ClaudeFather's credential system: the per-install vault, the
- `voice/` -- >> Resume here: read _handoffs/20260731-1756__voice.md first -- it is the latest handoff.
<!-- /CC:CHILDREN -->

The ClaudeFather platform's web control plane: a single **stdlib-Python HTTP server** (`server.py`,
~28.5k lines as of 2026-07-09; the embedded `PAGE` frontend alone is ~9.6k) with an **embedded vanilla-JS frontend** (the `PAGE` string). No build step, no deps
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
- `cc-launch.sh <local|remote-a|remote-b> <name> [dir]` — creates a persistent tmux session; remote targets wrap
  `ssh -t` into a remote box (e.g. a Windows box with no tmux; the local tmux is the persistence layer).
- `bridge-supervise.sh` / `crons-supervise.sh` — product runtime supervisors (not the CC itself).

## server.py — where things live
The section-by-section map of `server.py` (line anchors, every major subsystem) lives in
**`docs/SERVER_MAP.md`** — read it when you need to find where something is. It is kept out of this
always-loaded file on purpose: it is reference material, not orientation.

## Frontend (the `PAGE` string, ~7149+)
Single-page vanilla JS. `LENS` selects the active view; `render()` (~8205) dispatches to per-lens loaders.
Lenses include: pillars, modules, files, gmail/calendar/drive, ralph, pipeline, jobs, machines, desktop,
usage, backup, security, agents, marketplace, agency, calls, comms, **notes**, skills, teams, audit, portfolio,
sessions, history, tree, tasks, ideas, ccr, propose, accounts, settings, chief, docs, doctor. Which lenses
appear is driven by the **preset** (`../presets/<PRESET>.json` → `project.json` / `overseer.json`).
Brand assets in `static/brand/`; terminal via `static/xterm.js`; remote desktop via `static/novnc/`.
- **Nav categories** (`navDefaultTree`/`NAV_CAT`/`NAV_PINNED`, `paintNavNotif`): the sidebar ships GROUPED into
  default COLLAPSED categories (Google/Workspace/Agency/Team/Integrations/System) with daily-drivers pinned on
  top; a collapsed category whose hidden members have unread badges GLOWS + shows the summed count. Built on the
  pre-existing grouping engine (tree in `localStorage ccnav:<project>`; drag/rename/+category/flatten/reset).
  Built-in lens→category in `NAV_CAT`; extension lenses carry `extension.json default_category` (via
  `_ext_lenses().category`). `navFlatten()` opts out to the most-used list; `navAuto()` re-seeds the defaults.
- **Sessions workspace + Basket** live in `PAGE` too: the split-pane workspace (drag a session up to split) and
  the sidebar **Basket** (`#basketwrap`, `renderBasket`/`basketSendTo`) that drops a whole collection into a session.

## Helper files (this dir)
- `granola.py` — Granola call transcripts → reviewed proposals (client CLAUDE.md note + tasks/reminders).
  `server.py` calls `granola.init(ctx)` once (passing the `secret` resolver); `gr_*` behind `/api/granola*`.
  Nothing applies until approved. The API key resolves VAULT-FIRST (`_api_key()` → `_deploy_env("GRANOLA_API_KEY")`,
  falling back to `cc.config granola.api_key`) — so a key added via the Vault/secure-field just works.
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
- **Sessions panes hold live terminal iframes.** Moving an iframe node in the DOM RELOADS it (every
  browser), so pane drag-reorder uses flexbox `order` and never reparents. Consequence: **DOM order is
  not visual order** — use `wkVisualNames()`/`wkPaneEl()`, never `previousElementSibling`, when you need
  to know which pane sits where (`docs/SERVER_MAP.md`).
- **Restart after edits:** changes don't take effect until the `hpcc` tmux session is recreated —
  use the `claudesole-restart` skill.
- **Portability boundary:** anything project/tenant-specific goes in `cc.config.json`, not the code.
  Never reintroduce hardcoded paths/ports/brand. `INSTANCE_ID` + `PORT` + brand all derive from config.
- **Secret files are chmod 0600 on boot** (`cc.config.json`, `peers.json`, mesh hook settings). Don't make
  them world-readable. Never change `auth_token`/`mesh_token` without confirming the exact value first
  (lockout risk; a credential-change watch logs any change to `~/.cc-credential-changes.log`).
- **Auth is FAIL-SECURE by default** (deep-audit P1-9): a fresh install with no configured token auto-mints one
  (persisted to cc.config, dropped in `STATE_DIR/_auth_token.txt`, printed to stderr). Run open ONLY with an
  explicit `auth_open:true` (Doctor warns). env `CC_AUTH_TOKEN` / cc.config `auth_token` still win.
  Mesh enforcement (`MESH_ENFORCE`) is likewise carried-but-not-rejected until explicitly turned on.
- **Run on the brain tmux server, not bare launchd** — the SSD (`<SSD>`) needs that TCC
  context; bare launchd EPERMs and silently breaks the Docs/doctor/deliverables lenses.
- **Write growing artifacts to the SSD**, never the near-full internal disk (deliverables → `DELIV_LOCAL_ROOT`).
- **Boot must not block on I/O:** heavy housekeeping runs in a daemon thread; keep it that way (a slow iCloud
  node once "came up" but never reached `serve_forever`).
- Sessions are tmux ON THE LOCAL HOST (even "open on a remote box" = a local tmux wrapping `ssh -t`). Agents have
  no TTY → no sudo; use the Admin shell pre-type protocol (`docs/SESSIONS_AND_SUDO.md`).

## How to extend it
- **New API + lens:** add a backend fn → register a `do_GET`/`do_POST` route in `class H` → add a `loadX()`
  in `PAGE` and a `LENS=="x"` branch in `render()` → list the lens in the relevant `presets/*.json`. Restart.
  Give the new lens a `NAV_CAT` entry (else it defaults to "Workspace"); a built-in always-on lens outside the
  preset list must be force-shown in `applyPreset()` (see the `tasks`/`notes` lines). For a per-lens unread
  badge, add a `<span id="xBadge">` inside its nav button — `paintNavNotif` aggregates it into the category glow.
- **New agent-tool:** `agent_create()` / drop `agents/<slug>/` (config + CLAUDE.md + reports). Give it a
  strong description (the orchestrator selects on the description — run the description-audit).
- **New skill:** `.claude/skills/<name>/SKILL.md` (frontmatter `name`+`description`); surfaced via Skills lens.
- **New extension:** Marketplace install/uninstall; per-deploy secrets in `.env.claudefather` (gitignored).
- **Mesh/superadmin changes:** respect `AUTH_MESH_INGRESS` and the token tiers; never weaken the gate silently.

