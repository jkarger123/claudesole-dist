# Granola Calls — meeting-notes ingestion (agency tenants)

Turn **Granola** call transcripts into **REVIEWED** updates to the agency tree: a dated note in the matched
client's `CLAUDE.md`, plus action-item tasks and follow-up reminders. The defining invariant is a
**propose → approve → apply** spine: ingest + LLM extraction are read-only and produce **PROPOSALS** only;
**nothing** touches a client file or creates a task/reminder until the operator approves it in the **Calls lens**.

Agency deployments only (the lens shows when `Clients/` + `Tools/` are present, or `cc.config integration=agency`).

## How it works (5 stages)
1. **INGEST** (read-only) — pull recent meetings + transcripts from Granola. Two sources:
   - **API** (default if `api_key` set): `GET public-api.granola.ai/v1/notes` + `/notes/{id}?include=transcript`, `Authorization: Bearer grn_...`. Cloud — works from any box.
   - **cache** (no key): `~/Library/Application Support/Granola/cache-v3.json`. Local only — viable **only if the deployment box is the same Mac that records the calls**. The cache is double-JSON-encoded (a JSON file whose top value is a JSON string) — see `_load_cache`.
2. **MATCH** — each meeting → a client folder via `match_client`: explicit `client_map` (attendee domains/aliases in title+emails) wins, then fuzzy de-slugged folder-name in title. Searches `Clients/<x>` and `Partners/<p>/clients/<x>`. Unmatched → operator picks a client at approve time.
3. **EXTRACT** — `_claude_extract` runs a **headless `claude -p`** (Max subscription, **no metered key**) with `EXTRACT_PROMPT`, returns strict JSON: `summary, notes, tasks, reminders, decisions`. Extraction only — never writes. Tests inject a fake via `ctx["extractor"]`.
4. **REVIEW** — every call is stored as a PENDING proposal in `_granola.json`. Shown in the Calls lens; operator Approves / picks client / Skips.
5. **APPLY** (`gr_apply`, on approve) — (a) appends a dated entry to the client's `CLAUDE.md` inside a managed `CC:CALLS` region; (b) creates tasks + reminders in the configured destination(s).

## Key files / where things live
- `command-center/granola.py` — the **engine** (stdlib only). All logic lives here; `server.py` injects context and exposes endpoints.
- `extensions/granola/extension.json` — manifest: `provides: lens:calls`, requires a Granola API key OR the desktop app, `setup_agent: true`.
- `extensions/granola/SETUP.md` — setup-agent walkthrough (config, sources, destinations, privacy).
- `command-center/server.py`:
  - `granola.init({...})` (~L4619) — injects `CC, PROJECT, STATE_DIR, agency_dirs, agency_subfolders`.
  - Endpoints: `/api/granola` (proposals), `/api/granola-sync` (POST, runs `gr_sync` in a **background thread** — extraction is slow), `/api/granola-apply`, `/api/granola-skip`.
  - **Calls lens** UI (`LENS=="calls"`, `callsSync/callsApply/callsSkip`).
- **State (per-deployment):** `<STATE_DIR>/_granola.json` — `{proposals, seen, last_sync}`. `seen` is capped at last 500 meeting ids; proposals carry `status: pending|applied|skipped`.
- `<STATE_DIR>/_granola_google_outbox.jsonl` — pending Google requests (see destinations).

## The CC:CALLS managed region
`_append_call_note` writes a dated `### <date> — <title>` block (summary, `- ` notes, `- DECISION:` lines) into the client's `CLAUDE.md`, fenced by:
```
<!-- CC:CALLS log (Granola; newest first) -->  …entries…  <!-- /CC:CALLS -->
```
(constants `granola.CALLS_B` / `granola.CALLS_E`). If the region exists, new entries are **prepended inside it** (newest first); otherwise a `## Call log` + region is appended. **This region is machine-managed — do not hand-edit inside the markers.** It is read elsewhere (the flex/smart-reply context bundler and the task-suggestion scan in `server.py` parse this region read-only as prior-call context).

## Destinations (`cc.config granola.destinations`, any combination)
- `cc` (default) — per-client `TODO.md` checkbox list in the client folder (`_dest_cc`). No external accounts; shows in the client's Files panel + Calls lens.
- `slack` — per-call action digest to an incoming webhook (`granola.slack_webhook`, `_dest_slack`).
- `google` — Calendar/Tasks. Does **not** call Google directly; the Google MCP is at the session layer, so `_dest_google` appends to `_granola_google_outbox.jsonl` for the chief to fulfill via MCP.
- `apple` — native Reminders via `osascript` (runs on this Mac, `_dest_apple`).

## Config (`cc.config.json` → `granola`)
`source` (api|cache), `api_key`, `cache_path`, `client_map` ({slug: [domains/aliases]}), `destinations`, `slack_webhook`, `apply_mode` (review|hybrid|auto — only `review` is fully wired today). Minimum: `api_key` (or `source:"cache"`); `client_map` is optional (title matching works without it). Note: `server.py` has a one-time importer that syncs `client_map` into per-folder domains/keywords so email matching stays consistent.

## Hard rules / gotchas
- **Review-first is the safety model.** Apply is the only write path; ingest + extract never write. Don't add an auto-apply path without an explicit operator-gated mode.
- **No metered key.** Extraction uses the headless `claude -p` (Max sub). Don't route it through the metered API key.
- **Cache source needs the calls to be recorded on this same box.** Otherwise there is no cache → API only. Don't assume cache works on a headless Studio.
- **`gr_apply` requires a resolved client.** Unmatched proposals must have `client` set (manual pick) or apply errors out — by design.
- **`/api/granola-sync` is async** (background thread); the POST returns immediately and proposals appear as extraction finishes. Don't block on it.
- This is the **template for the propose→approve→apply spine** that `server.py`'s flex `_actions.json` queue generalizes fleet-wide — keep that pattern intact if you refactor.

## How to extend
- **New destination:** add a `_dest_<name>(client, cpath, tasks, reminders, p)` in `granola.py` and register it in the dispatch dict inside `gr_apply`; then add `<name>` to `destinations` config. Adapters must be auditable and side-effect-only (no writes outside the operator's chosen surface).
- **Different extraction shape:** edit `EXTRACT_PROMPT` and the proposal/`_append_call_note` consumers together; keep output strict JSON.
- **Different source:** add a branch in `list_meetings` / `get_transcript` / `_source`.
- After any `server.py` change, restart the supervised Command Center (see the `claudesole-restart` skill) — the dashboard won't pick it up otherwise.
