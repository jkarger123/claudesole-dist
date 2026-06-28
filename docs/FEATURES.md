# ClaudeFather — Feature Guide (what it can do & how)

Every powerful feature also has an in-app **"How this works"** explainer: it auto-shows once when you first
open a lens (dismissible, "Don't show again"), and the **?** button in the top bar reopens it anytime. This
file is the written companion. (Per-version detail: `docs/CHANGELOG.md`.)

## Email (Gmail) — a full client, built in
- Keyboard-first triage: `j/k` move · `↵` open · `e` archive · `s` star · `#` trash · `r` reply · `c` compose · `z` undo. Saved lanes, threaded reader, operator-chip search.
- **✨ Smart reply** — drafts a reply *in your voice* using everything we know about the sender (past emails, calls, calendar, Drive files, pipeline status), staged as a Gmail **draft**. It **never sends** — you review and click Send. (`/api/flex/context`, `/api/flex/stage-reply`.)
- **🔎 Sender history** — a one-glance dossier fused across channels.
- Attachments preview/download inline; **💾 Save to…** drops a file straight into a client/project folder.
- **Auto-refresh**: new mail appears on its own (the list refreshes every ~45s without yanking it while you read — a "↑ N new" pill appears if you're mid-thread); the tab badge shows unread count (30s).
- Read/unread is Gmail's real state both ways (listing never marks read; opening does).

## WYSIWYG composer
Rich text + shortcuts, paste that keeps formatting **and** images, inline images embedded (cid) so they render on the recipient end, drag-drop file attachments, signature, draft autosave. Sends correct MIME (`multipart/mixed › related › alternative`) — verified by live round-trip.

## Calendar
Day/week/month/agenda; drag to create, resize, move; natural-language quick-add ("lunch with Sam thu 1pm"); click to edit/RSVP/delete (with undo); gold "now" line.

## Drive
Folders + breadcrumbs, search, grid/list, **Spacebar Quick Look** (full-screen preview), multi-select batch actions, open/download.

## Email ↔ client/project linking (CRM-grade)
Link a folder (agency client *or* project module) to emails/domains. Per-folder **correspondence view** (a live read-safe Gmail query). Reader **"Linked to"** chip + suggestions. **Save-attachment-to-folder** (path-safe, into the folder's `deliverables/`). `/api/mail/*`.

## Sessions taskbar (desktop)
A Windows-style dock of every live session pinned at the bottom of every lens. Tiles **blink gold while working**, **pulse gold when finished** (and the browser tab title shows "🟡 N done"). Hover a tile → a full interactive terminal blow-up with **Usage / New-tab / Graceful-exit / Kill**. Viewing a session in the Sessions tab clears its gold flash.

## Sessions workspace (split-pane)
The Sessions tab is a modular split-pane workspace (replaced focus/grid/list): drag a session up from the taskbar into the main area, **split-screen** with an adjustable divider, pull in more, push any back down. The taskbar marks which sessions are currently "up."

## Drag anything into a session + the Basket
Any portal item — a Drive file, an email/thread, a calendar event, a deliverable, a Granola call, or **any extension item** — can be **dragged straight onto a session** (or a workspace pane); the agent instantly receives it as a real file. The **Basket** (sidebar) is a collection you fill from anywhere — drag items in, or files from your computer — then **drag the whole basket into a session** to hand the agent everything for a task at once. Save a basket as a reusable named **"context pack."**

## Notes — message between node operators
A human-to-human chat between the people running the nodes (e.g. Mission Control ↔ a tenant). Leave someone a note; it lands in their dashboard as a **can't-miss bottom-right corner alert** (plus a Notes-tab thread, a nav badge, and a Telegram ping if set) — they reply and it comes back to you. Threads are saved per peer. Separate from the agent-to-agent mesh.

## Nav categories
The sidebar groups tabs into **collapsed categories** by default (Google, Workspace, Agency, Team, Integrations, System) with your daily drivers pinned on top — and a category **glows + shows a count** when something inside it has a notification (new email, a pending change request, an unread note). Drag to reorder, rename, add categories, or flatten to a single most-used list.

## Pipeline Live-View
Live run-map of a node's scheduled pipeline. A loud full-width banner goes **red** on FAIL/STALL, **amber** on MISS — a silent failure can never go unnoticed. Drops in automatically when a node emits a manifest + heartbeat (`docs/PIPELINE_LIVEVIEW.md`).

## Agentic leverage (in progress)
The layer that makes the extensions **compose** instead of sit in silos. Shipped: the **Action Queue** safety spine (every outward action is staged & human-approved; `/api/actions`) + the first recipe (Smart Reply). Designed next: a **capability registry** every agent reads, a **recipe engine** (call→email+calendar+drive+notes; "state of client X"), in-surface AI across lenses, a **proactivity** scanner, and **mesh capability cards** so a peer learns what another instance can do.

## Reliability
- **Session watchdog** — a launchd nudger that rides Claude sessions through API outages (detects an idle session stuck on an API/rate-limit error, dismisses the feedback overlay, and nudges "continue" until it resumes).
- **Workflow resilience** — multi-agent workflows retry through transient API errors; dead background agents get relaunched.
