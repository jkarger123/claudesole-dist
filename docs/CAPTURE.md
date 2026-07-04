# ClaudeFather — CAPTURE (turning the world into context)

> Companion to **docs/VISION.md**. The browser/desktop and integrations are a **capture surface** that feeds
> the context layer; a review-first agent turns captures into durable, cited knowledge. Build everything as
> the same loop, just with different intake.

## The one loop (everything is this)

> **Capture** anything (a web page, a clip, a screenshot, a meeting transcript, a Slack thread) → it lands in
> a per-subject **inbox** as a provenance-stamped event → an **agent triages** it (cluster, dedup, summarize,
> extract tasks/decisions/contacts) → it **proposes** durable updates → **you approve** → applied, **with
> receipts back to the source.**

Nothing is applied without a human nod (the granola/CCR invariant). Every applied insight links to its
source. Web/Slack/web content is `external`/`contact` trust — **data, never instructions** — so the
capability plane can never act on a poisoned page.

This loop **reuses machinery we already have**, which is why it's tractable:
- **granola.py** = the canonical propose→approve→apply spine (`_claude_extract`, managed `CC:` regions).
- **context.py** = the event store + graph + router (`ingest_event`, `assemble`, `subjects`).
- **Routines** = scheduled "end of day" runs. **Tasks** = extracted to-dos. **Deliverables/** = filed
  screenshots/files (show in the Files lens). **Managed CLAUDE.md blocks** = the `CC:CLIPS`/`CC:CALLS`
  regions. **drag-anything-into-a-session** = hand a capture to an agent right now. **Focus engine** =
  auto-suggests the subject. **VoiceMatch** = draft in the user's voice.

## Capture types

### 1. Universal "Save to ClaudeFather" (⭐ button / hotkey)  — desktop browser
One click on any page → subject pre-filled from the **current focus** → confirm + optional note + a *kind*
(reference / lead / competitor / inspiration / read-later). Saves url + readable text + a thumbnail
screenshot + provenance into that subject's **clip tray** (pending; not yet applied). `POST /api/clip`.

### 2. The triage agent — "process my clips" (end-of-day or on demand)
Per subject: cluster the day's clips, dedup, summarize, extract entities/tasks/decisions/links, and
**propose**: a dated digest into the client's `CLAUDE.md` `CC:CLIPS` region, tasks/reminders, and screenshots
filed to `deliverables/`. Reviewed in the **Capture lens** (approve / edit / skip), like the Calls lens.
`POST /api/clips/process` (propose) → `POST /api/clips/apply` (apply, cited). A Routine can run the propose
step nightly (review-first; never auto-applies).

### 3. Screenshots & text clips → a project/client  — desktop browser
Full-page (or region) screenshot + highlighted-text excerpt with its source url → saved to the subject's
`deliverables/` + ingested as context. Quick annotation per clip.

### 4. Zoom / Meet / Teams recordings + transcripts
Granola, extended. Three intakes → one pipeline: (a) Zoom cloud-recording API → fetch the VTT transcript;
(b) the desktop app captures a meeting tab live; (c) drop a recording/`.vtt`. The agent updates the client's
`CC:CALLS` + tasks exactly like granola. (`command-center/zoom.py`.)

### 5. Slack
- **Read** via the Slack API (like Gmail): client-relevant channels/DMs ingested as `slack` events
  (`contact` trust) → appear in briefs + the X-ray.
- **Capture**: "save this thread to <client>".
- **Smart**: the agent surfaces "X asked about Y in Slack — relates to <project>" via the graph.
  (`command-center/slack.py` + `extensions/slack/`.)

## The intelligence layer

### AI co-reading / page intelligence (over-the-shoulder)  — desktop browser
Because we know your calendar, clients, emails and tools, a subtle sidebar flags what you'd miss on a page:
"this competitor just shipped what a client asked about," "this article cites a contact of yours," "ties to
your 2pm." `POST /api/context/page-intel {url,title,text}` → `{related:[…], flags:[…]}` (read-only). This is
the clearest "a chat box can't do this" moment.

### More, designed-in (build as demand warrants)
- **Auto-reclassify** a misfiled clip to the right client on triage (entity match).
- **Per-subject tab sets** ("open my Acme tabs") — browser homing.
- **Read-it-later → morning digest** (ranked by relevance to active projects).
- **Pre-meeting auto-pull** — 20 min before a calendar event, assemble everything about that client this week.
- **Clip → draft** an email/message about it in the user's voice (VoiceMatch).
- **Topic/competitor watch** — subscribe a client to a topic; flag changes seen in browsing + the web.
- **Voice/quick capture**, **PDF/doc capture**.
- **Receipts & one-click delete** for captures (the X-ray extends to capture: see what was captured + where
  it went; delete any of it). The portal is the consented surface — *that's* the privacy story.

## Cross-cutting invariants
- **Review-first.** Captures propose; you approve. Nothing edits a CLAUDE.md or sends anything without a nod.
- **Provenance + trust on everything.** Every applied insight cites its source; untrusted intake stays data.
- **Local + owned.** All capture goes only to the user's own ClaudeFather; no telemetry. Default capture OFF;
  explicit Save is always user-initiated.
- **Additive.** None of this changes the existing web app; the desktop app and integrations are opt-in.

## Architecture map
- `command-center/server.py` — the spine: `/api/clip`, `/api/clips`, `/api/clips/{process,apply,skip}`,
  `/api/context/page-intel`; the Capture lens; `_clips.json` store; the triage agent (granola-pattern); the
  `CC:CLIPS` managed region.
- `command-center/context.py` — events + graph + router (intake target + page-intel source).
- `command-center/zoom.py`, `command-center/slack.py` + `extensions/slack/` — extra intake into the loop.
- `desktop/` — the Electron browser: Save button, screenshot/selection, the co-reading sidebar, the bridge.
- Routines — the nightly "process clips" propose step.

## Build order
1. **The spine** (clip tray + Save + triage agent + Capture lens) — powers everything.
2. **Desktop capture UX** (Save, screenshots, co-reading sidebar).
3. **Slack read** + **Zoom transcript** intake (into the same pipeline).
4. The intelligence extras (pre-meeting pull, watches, digests) as demand warrants.
