# Granola Calls -- setup walkthrough

Brief for the setup agent. ASCII only. Agency tenants only (the Calls lens shows when the deployment is an
agency: Clients/ + Tools/ present, or cc.config integration=agency).

## What it does
Turns your Granola call transcripts into a REVIEW QUEUE of proposed updates: for each call it matches a
client, then drafts a dated note for that client's CLAUDE.md plus action-item tasks and follow-up reminders.
Nothing is written until you approve it in the **Calls** lens.

## How it works
1. INGEST (read-only) -- pulls recent meetings + transcripts from Granola, either:
   - **Official API** (recommended): `GET https://public-api.granola.ai/v1/notes` + `/notes/{id}?include=transcript`,
     auth `Authorization: Bearer grn_...`. Create the key in the Granola desktop app: Settings -> Connectors
     -> API keys (Business plan). **IMPORTANT PREREQUISITE:** the Granola workspace must have **end-to-end
     encryption turned OFF**. With E2E on, Granola will not expose notes to the public API (you'll see an
     encryption-related message when creating/using the key, and the API returns 401/403). Turn E2E off in
     the Granola workspace settings (or use a workspace/plan that permits API access) BEFORE creating the key.
   - **Local cache** (no key): `~/Library/Application Support/Granola/cache-v3.json`. Fully local, no key --
     BUT this only works if THIS deployment's box is the SAME Mac where the calls are recorded (Granola
     desktop installed + signed in here). On most agency setups the always-on ClaudeFather box (e.g. a Mac
     Studio) is NOT the laptop where calls are taken, so there is no cache on it -> use the **official API**
     (cloud; works from any box). Rule of thumb: deployment box == call-taking machine? cache is viable.
     Otherwise, API only.
2. MATCH -- each call -> a client folder (Clients/<x> or Partners/<p>/clients/<x>) by attendee email/domain
   (via `client_map`) or by the meeting title. Unmatched calls show a client picker.
3. EXTRACT -- a headless `claude -p` (your Max subscription, no metered key) pulls summary, notes, tasks,
   reminders, decisions as strict JSON. Extraction only -- it never writes.
4. REVIEW -- every call lands in the Calls lens as a PROPOSAL. You Approve / pick-client / Skip.
5. APPLY (on approve) -- appends a dated entry to the client's CLAUDE.md (managed `CC:CALLS` region) and
   creates the tasks + reminders in your configured destination(s).

## Configure (cc.config.json -> "granola")
```json
"granola": {
  "source": "api",                                  // "api" (if api_key set) | "cache"
  "api_key": "grn_xxx",                              // from Granola Settings -> Connectors -> API keys
  "cache_path": "~/Library/Application Support/Granola/cache-v3.json",   // used when source=cache
  "client_map": {                                    // client folder -> attendee domains / title aliases
    "acme": ["acme.com", "Acme Corp"],
    "the-childrens-place": ["childrensplace.com", "TCP"]
  },
  "destinations": ["cc"],                            // any of: cc, google, apple, slack
  "slack_webhook": "https://hooks.slack.com/...",    // only if "slack" in destinations
  "apply_mode": "review"                             // review (default; everything queued for approval)
}
```
Minimum to start: `api_key` (or `source:"cache"`). `client_map` is optional (title-matching works without it).

## Destinations
- **cc** (default, built-in): a per-client `TODO.md` checklist in the client folder -- shows in that client's
  Files panel and the Calls lens. No external accounts.
- **google**: Calendar events (reminders) + Tasks (action items). The Google MCP tools are connected at the
  session layer; this writes a `_granola_google_outbox.jsonl` the chief fulfills via Google MCP (wire live
  once you confirm the target calendar/list).
- **apple**: native Reminders on this Mac via `osascript` (runs locally).
- **slack**: a per-call action digest to an incoming webhook (`slack_webhook`).
You can set more than one.

## Use it
Open the **Calls** lens -> **Sync Granola calls** (transcribes + extracts in the background; proposals appear
as they finish) -> for each call, confirm the client and **Approve & apply**, or **Skip**. Approved calls show
under "Recently handled"; the dated note is now in that client's CLAUDE.md and the tasks/reminders are created.

## Privacy / safety
- Ingest is READ-ONLY from Granola. Extraction is LLM; it can mis-summarize, which is exactly why apply is
  review-first -- nothing touches a client file until you approve it.
- Everything runs on THIS deployment's box against THIS deployment's client tree. No client data leaves it
  except (a) to your own LLM for extraction and (b) to any destination you explicitly enable.

## Troubleshooting
- **"encryption" message / Sync error 401 or 403:** your Granola WORKSPACE has end-to-end encryption enabled,
  which blocks the public API from reading notes (or the plan doesn't allow API keys). Fix: Granola workspace
  settings -> turn E2E encryption OFF, confirm a Business plan, recreate the `grn_` key, paste it into
  `granola.api_key`, then Sync. This is a Granola account condition, not a ClaudeFather bug.
- **Calls lens says "needs setup":** no usable source yet. The lens shows the exact next step (add the API
  key, or -- on a call-taking Mac -- install Granola for the local cache).
- **"no Granola API key set":** `source` is "api" but `api_key` is empty in `cc.config.json`. Add the key.

## Files
- Engine: `command-center/granola.py`  | Lens + endpoints: in `command-center/server.py` (Calls lens,
  `/api/granola*`).  | State (per-deployment): `<state>/_granola.json` (proposals + seen-meeting ids).
