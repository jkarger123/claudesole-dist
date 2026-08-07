# server.py — where things live

The section-by-section map of `command-center/server.py` (~30k lines). Line anchors are **approximate** —
they drift with every edit; use them to land in the right neighbourhood, then search. Split out of
`command-center/CLAUDE.md` so it is retrieved when needed rather than loaded on every turn.

## Major sections

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
- **Operator notes** (`op_note_*`, near `peers()`): a HUMAN↔human chat between node operators (e.g. an
  operator at Mission Control ↔ an operator at a node), SEPARATE from the chief mesh. Per-node `_opnotes.json` (`{threads:{peer:[{dir,text,ts,read}]},outq}`),
  own durable retry worker (`_opnote_worker`), rides the same X-Mesh-Token transport but delivers to
  **`/api/opnote-recv`** (in `AUTH_MESH_INGRESS`) → the peer's HUMAN, never the agent. APIs: `/api/opnotes[,-unread]`,
  `/api/opnote-send|-read|-recv`. Frontend = the **Notes** lens + the can't-miss `#opAlert` corner alert.
- **Drag-anything → session + Basket** (`SESSION_SEND_RESOLVERS`, `register_sendable`, `session_send[_batch]`):
  any portal item (Drive/email/calendar/deliverable/Granola/extension `entity`/`upload`) carries a `{kind,...}`
  descriptor (`ssAttr`) and drops onto a session → resolved to a real file + injected. The **Basket** is a
  client-side collection of those descriptors (sidebar, replaced the old machines widget) dropped into a session
  as a unit via `session_send_batch` (`/api/session-send-batch`); saved named "packs" persist server-side
  (`_baskets.json`, `/api/baskets*`); OS files added via `/api/basket-upload` (the `upload` sendable kind).
- **Tiered mesh trust + superadmin** (300–540): `MESH_TOKEN` (family badge), `MESH_ENFORCE` gate,
  `SUPERADMIN_TOKENS`, and Ed25519/HMAC **superadmin grants** (cryptographically-signed platform-owner
  directives any node will execute via `/api/superadmin-exec`). Keys: `.superadmin_ed25519` (MC-only, 0600),
  `superadmin.pub` (shipped, every node trusts it).
- **Google Workspace** (540–1175): server-side OAuth client (token file under the google-workspace extension
  secrets). Gmail (list/get/thread/send/draft/label/snooze/attachments), Calendar (events/create/update/rsvp/
  delete), Drive (list/get/content/thumb/modify/upload). `_g_api` + `_g_parallel`.
- **Auth + manifest** (1184–1222): `AUTH_TOKEN` (fail-secure: auto-minted if none configured; `auth_open:true` opts into open), cookie login, `AUTH_EXEMPT` /
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
  Auto + manual compact are deduped by a **cross-instance + restart-durable file lock**
  (`/tmp/cf-compact-locks/<session>.lock`; `_compact_lock_acquire`/`_compact_lock_mark`): co-located instances
  share the tmux server and the overseer is unscoped (sees every session), so without it the SAME session got
  compacted 2–4× (dup "COMPACT PREP"/"read handoff"). `O_EXCL`=one instance wins; on-disk=survives a restart.
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

## Notifications & recipients (added 2026-08)

- **`notify_send(text, to=, channel=)`** — the one entry point for reaching a HUMAN (phone), used by 20+
  call sites (security alerts, resource self-heal, incidents, Ralph completion, morning brief).
  Backed by a per-node recipient directory in `_recipients.json` (`STATE_DIR`).
  **With zero recipients configured it takes the legacy single-`TELEGRAM_CHAT_ID` path**, so existing
  deployments behave exactly as before until someone is added.
- **Channels**: `_telegram_send()` and `_twilio_send()` (stdlib, vault-first creds). SMS prefers
  `TWILIO_MESSAGING_SERVICE_SID` over a raw `TWILIO_FROM_NUMBER` — the messaging service is the correct
  sender for a registered US A2P 10DLC campaign.
- **SMS compliance is enforced in code, not docs**: `recip_add()` REFUSES a number without a `consent_by`
  record; enrolling one sends `SMS_ENROLL_CONFIRM` (built from `BRAND`, overridable via cc.config
  `sms_enroll_confirm`); `opted_out` is a hard gate on every send; Twilio error **21610** (recipient replied
  STOP) auto-mirrors into the directory via `recip_optout()` — carrier opt-out syncs with **no public
  webhook**, because the send failure itself is the signal.
- **`_recip_note_unlinked()`** hangs off the Telegram inbound poller: an unknown sender is recorded as
  "pending" so the operator can name them in one click (`recip_link_pending`). This exists because the
  server owns the ONLY permitted `getUpdates` consumer for the bot token — a second consumer 409s or steals
  a session reply, so we never poll for a chat id ourselves.
- Surfaces: **Recipients lens** (`loadRecipients()` in `PAGE`), `cc-reach` CLI, and
  `/api/recipients|recipient-add|-remove|-optout|-link`, `/api/notify-send`.
  Note `/api/notify` is claimed EARLIER in `do_POST` by the attention-event route — hence `/api/notify-send`.

## Sessions workspace panes

- `PANES` (ordered, persisted to `localStorage hpcc_panes`) is the source of truth; `renderWorkspace()`
  builds `.wkpane` elements separated by `.pane-split` dividers.
- **A pane holds a live terminal `<iframe>`, and moving an iframe node in the DOM RELOADS it** in every
  browser. So drag-to-reorder (`wkDragStart`) never reparents: it sets flexbox `order`, which is pure
  layout. **Therefore DOM order != visual order** — anything needing "which pane is where" must use
  `wkVisualNames()` / `wkPaneEl()`, not `previousElementSibling`. `wkAddPane`/`wkRemovePane` and the
  splitter-resize handler all depend on this.
