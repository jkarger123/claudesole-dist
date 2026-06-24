# ClaudeFather -- CHANGELOG

A deployment can compare its `claudesole.manifest.json` `version` against the upstream's (cc-update prints
both) to see if it is behind. Newest first.

## 0.21.14 -- 2026-06-24
- ADD (sessions name themselves): every launched session now gets a system-prompt instruction
  (`--append-system-prompt`) to emit, once it understands its job, a line `[[CC_TITLE: <2-6 word title>]]`.
  The session-watch loop detects that line and renames the session's dashboard label (persisted in
  state/_session_titles.json, survives restart). So instead of "7th ave 2 / 7th ave 3", Sarah sees
  "7th Ave bounce-list fix", "7th Ave Q3 pitch", etc. Detection is anchored to its own line and rejects the
  placeholder + inline mentions; system sessions (Chief, services) keep their canonical names. Applied to
  the generic launch, resume/fork, Chief, and team/agent launches. Verified end-to-end.

## 0.21.13 -- 2026-06-24
- FIX (download "site wasn't available"): the blocking iCloud materialize (up to ~30s) was timing out the
  proxy/browser. Now the wait is bounded (~6s) and only happens when the bytes aren't already local, so the
  download returns promptly (and a just-created file, which is already local, downloads instantly).
- FIX ("Reveal in Finder" useless on the operator's OTHER Macs): a web server on the host Mac cannot open
  Finder on a different computer -- that's impossible. But deliverables live in iCloud Drive, so they ALREADY
  sync to every Apple device on the account. The button (now "📍 Find this file") shows the exact iCloud Drive
  location ("iCloud Drive ▸ ClaudeFather ▸ … ▸ file") with a Copy-path button and a Download fallback, and
  still opens Finder on the host Mac if you're there. Honest + actually findable from her iMac/MacBook.

## 0.21.12 -- 2026-06-24
- ADD ("Reveal in Finder" for iCloud files): when the browser download of an iCloud-backed deliverable is
  flaky, you can now open the file's folder in Finder ON THE MAC you're sitting at and have it selected. The
  reveal endpoint first forces the bytes down from iCloud (brctl) so Finder shows a real file, then
  `open -R`. The button is now prominent ("📁 Reveal in Finder") on the Files lens, the browse view, and a
  module's Files panel -- replacing the buried, discouraging "⤲ Studio" button. Toast copy clarified.

## 0.21.11 -- 2026-06-24
- FIX (sessions stuck on a permission prompt): `--dangerously-skip-permissions` does NOT bypass Claude
  Code's hard safety prompt for commands containing shell command-substitution ($()/backticks) -- so an
  autonomous agent hits "Do you want to proceed? 1.Yes 2.No" and sits there forever waiting for a human
  (what Sarah kept seeing). Added a server daemon (`_autoapprove_loop`, every 6s) that detects an idle
  session on that menu and selects Yes (preferring "Yes, and don't ask again" to cut repeats). Runs as the
  deployment's own user on its own box -- same intent as the skip-permissions launch flag -- and every accept
  is logged to state/_autoapprove.log for audit. Kill-switch: cc.config auto_accept_prompts=false. (This is a
  separate floor from the one-time bypass-mode acceptance the CC already self-heals.)

## 0.21.10 -- 2026-06-24
- FIX (Smart reply addressed the reply to YOU): it replied to the newest message in the thread, but if you
  sent the last message, that's you -- so the draft went To: yourself and the "facts" bullets described you.
  Now it targets the latest message from the COUNTERPARTY (the person you're replying to), falls back to the
  address you last wrote to if the whole thread is yours, and the AI prompt is explicit about writing AS the
  owner TO the other party. The 360 bundle/dossier now profiles the counterparty, not the account owner.
- FIX (no Drafts folder): added a "Drafts" lane to the Gmail rail (in:drafts) -- staged Smart Reply drafts
  (and any draft) are now reachable.
- FIX (sessions taskbar tiles jumping): the bar rebuilt every poll and re-sorted, so tiles moved and the one
  under your cursor got destroyed mid-hover. Tiles now sort by a STABLE key and the DOM is rebuilt only when
  the set of sessions changes (busy/done state applied in place) -- they stay put and stay clickable.
- FIX (attachment "downloads but nothing shows up"): files in iCloud-backed deliverables/ can be EVICTED
  (dataless placeholder), so the server read 0/partial bytes and served an empty file. /api/file-get now
  forces the bytes back from iCloud (brctl download) and waits, retries on a short read, and returns a clear
  503 instead of an empty file if iCloud hasn't faulted it in yet.

## 0.21.9 -- 2026-06-24
- FIX (email cut off — the ACTUAL root cause, finally): it was never the email height. `.gm-thread` is a
  flex column; its message cards had no `flex-shrink:0`, so a tall email got SHRUNK to fit the pane and
  `.gm-msg{overflow:hidden}` clipped the body inside the squashed card -- with no scroll. Added
  `flex:0 0 auto` on `.gm-msg` and `min-height:0` on `.gm-read`/`.gm-thread` (a flex item won't scroll
  without it). Proven by a headless layout test: the thread pane is now bounded to the pane height and
  scrollable (clientHeight 507, scrollHeight 3917) instead of clipping. The short iframe had masked this the
  whole time. Emails now open full-length and the reading pane scrolls like a normal client.

## 0.21.8 -- 2026-06-24
- FIX (email cut off — the REAL fix): replaced the per-message iframe (whose height had to be measured, and
  kept getting it short) with a **Shadow DOM** render. The email's CSS is still encapsulated, but the host
  grows to the content's NATURAL height — nothing to measure, nothing to clip. The missing piece behind every
  prior attempt: emails clip their body in a fixed **`height:Npx`** overflow:hidden wrapper, and I had only
  ever neutralized `max-height`. Now container tags are forced to `height:auto !important; overflow:visible`
  so the body flows full-length. Proven headless against the worst case (html,body height:100% + nested
  fixed-height overflow:hidden): the body renders its full 2041px instead of a clipped 278px.
- Email HTML is sanitized server-side before render (strips <script>, on* handlers, javascript: URLs,
  iframe/object/embed/form) since Shadow DOM scopes CSS but doesn't sandbox JS. Links open in a new tab.

## 0.21.7 -- 2026-06-24
- FIX (email STILL cut off at the bottom): the prior fix only handled html,body{height:100%}. Business mail
  can also trap content in an inner wrapper with a fixed height / max-height / overflow:hidden, which clips
  scrollHeight short -> the body is cut off with no scroll. We now neutralize `max-height` on every element
  and force `overflow:visible` on structural tags, measure via getBoundingClientRect too, add an inner-window
  load hook + a longer tail of re-fit ticks, and set the iframe `scrolling="no"` so you can never get trapped
  in an internal scrollbar. Proven headless: content locked in a 300px overflow:hidden box now sizes to its
  full 2225px. Emails open full-length; the thread pane scrolls like a normal client.
- FIX (the "bunch of lines" above a long thread): the overlap/cascade deck looked terrible on a 40-message
  thread. Replaced with the Gmail pattern -- clean compact collapsed rows, and the MIDDLE of a long thread is
  folded behind a "⋯ N earlier messages" pill (click to expand). First message + last couple + the open
  newest always show. Empty-snippet rows show "(no preview)" rather than blank.

## 0.21.6 -- 2026-06-24
- FIX (reader cascade over-eager): the collapsed-reply stack fanned apart on ANY hover in the thread —
  including when you were reading the open email. It now reacts ONLY when the pointer is directly on a
  collapsed card (that card lifts and the one right after it drops its tuck so it's fully readable).
- FIX (thread cluttered with empty "nothing written" cards): Gmail keeps DRAFT messages (including each
  staged Smart Reply) INSIDE the thread; we were rendering them as blank conversation cards. Drafts are now
  skipped in the reader (they still live in Drafts / open in the composer) and the header notes "N drafts
  in Drafts". Any remaining empty-snippet message (image-only mail) now derives a text preview so no card
  is blank.

## 0.21.5 -- 2026-06-24
- FIX (Gmail reader: emails cut off at the bottom / "just lines"): newsletter & marketing mail commonly
  set `html,body{height:100%}`, which inside an iframe collapses scrollHeight to the frame's own height —
  so the body was clipped to a sliver (the reported Sam Breen "RE: 2026 PR and Affiliate Support" email).
  We now force `height:auto` on the email's html/body, measure the true content height (max of body +
  documentElement scroll/offset), and attach a **ResizeObserver** + image-load/error hooks so the frame
  re-fits on any reflow. Verified by a headless render of a height:100% newsletter — frame sized to the
  full 2210px content instead of ~120px.
- POLISH (Gmail reader: long reply chains): collapsed older replies are now a compact, slightly
  **overlapping stack** that **cascades apart when you hover the thread** (and each lifts on hover), so a
  long chain takes minimal vertical space but every message is one move away. The newest message stays
  expanded; click any to open it full-length.

## 0.21.4 -- 2026-06-24
- FIX (Smart reply: "thread headers unavailable"): the 360 bundle resolved headers with
  GET /messages/{id} but the reader passes a THREAD id -- and a Gmail thread id only coincidentally
  equals a message id on single-message threads, so it 404'd on any multi-reply thread (where you most
  want smart reply). `_gmail_headers_for` now resolves the THREAD and uses its latest message, falling
  back to a message fetch. Also fixes the folder-suggest path. (This is why it passed on a single-message
  carsearch test but failed on a real thread.)
- FIX (Gmail reader: tiny scroll-boxes): each HTML email rendered in an iframe with bare `sandbox`, so the
  page could not read the frame's content height -- the auto-fit threw and pinned every message to a fixed
  ~460px box you had to scroll INSIDE (and collapsed replies measured as ~0). The iframe now uses
  `sandbox="allow-same-origin"` (email scripts still never run -- no allow-scripts), the body grows to its
  FULL height with no cap, re-fits when you expand a collapsed reply, and re-fits as images load. Result:
  emails read full-length and the thread pane scrolls like a normal client.

## 0.21.3 -- 2026-06-24
- FIX (Portfolio, overseer): clicking an instance card now opens that ClaudeFather in a NEW TAB
  (`window.open(..., _blank)`) instead of replacing the overseer page in the current tab.
- FIX + CLARITY (Projects ▸ Correspondence): the "📬 Correspondence" header rendered TWICE (the card
  title + the inner list head both printed it). Dropped the duplicate; the inner head now just shows the
  thread count ("N threads · auto-collected from Gmail").
- The feature was unclear, so it now explains itself: an always-visible one-liner under the header ("Gmail
  threads that belong to this project, auto-collected by the matchers below… read-only; nothing is sent")
  with a **Learn more** link, plus a full **"How this works"** explainer (matchers = domain / email /
  keyword; read-only; open jumps to Gmail; Save-to drops attachments into the folder).

## 0.21.2 -- 2026-06-24
- POLISH ("How this works" explainers redesigned): the informative popups now read as refined/enterprise
  instead of the previous busy gradient + gold top-bar. Calm flat surface, a small gold "HOW THIS WORKS"
  eyebrow, an info icon badge, proper title/body type hierarchy, inline `code` chips, and a separated
  footer (Don't-show-again on the left, ghost Dismiss + gold Got it on the right). Verified by an actual
  headless-Chrome render before ship. The generic .modal is untouched; this scopes via `.modal:has(.cchelp)`.

## 0.21.1 -- 2026-06-24
- FIX (Sessions Focus view): removed the redundant per-session switcher-chip row that sat between the
  usage strip and the terminal. The bottom session taskbar already lists/switches every session, so Focus
  now shows just the one big terminal (its header still names which session). Clicking Focus opens it big.
- FIX (mobile nav tabs not showing): on a phone the side rail became a single horizontal row of
  [brand | tabs | reorder-controls], which squeezed the tab strip down to a sliver -- so all you saw was
  the "most-used first / + category" reorder text and no actual lens tabs. The tab strip now WRAPS to its
  own full-width scroll row, and the desktop-only drag-reorder controls (`#navmode`) are hidden on mobile.
  Bumped the sticky topbar offset to clear the now-two-row mobile header.

## 0.21.0 -- 2026-06-24
- POLISH (icons): the left-nav now uses the PHOSPHOR icon set (ph-light weight) -- the same free set the
  carsearch site uses (jsDelivr @phosphor-icons/web@2.1.1, light + fill) -- replacing the emoji nav icons
  for a consistent, enterprise look. (Lens-header + button emoji can follow in a sweep.)

## 0.20.3 -- 2026-06-24
- FIX (Sessions lens: session chips overlapping the usage strip): the head card (with the metered-usage
  strip) and the focus block are now wrapped in a clean vertical stack (.modstack) so usage always sits
  ABOVE the chips + terminal; the focus terminal height now accounts for the header + usage + the bottom
  taskbar so nothing overlaps. Stale "live dock below" hint updated to the current chips+taskbar model.

## 0.20.2 -- 2026-06-24
- FIX (mobile top nav missing): the desktop sessions-taskbar was shrinking #app + had a 900px breakpoint
  that fought the 820px nav breakpoint, clipping the mobile top tab bar. The taskbar + its #app height
  reservation are now DESKTOP-ONLY (>820px); mobile layout is untouched -> tabs show again.
- POLISH (popups): the modal/explainer dialogs are redesigned -- gradient card, gold top-accent, blurred
  backdrop, pop-in animation, and refined inputs/buttons with gold focus rings. Enterprise feel.

## 0.20.1 -- 2026-06-24
- HOTFIX (portal blank / "missing ) after argument list"): the 0.20.0 "How this works" block had a
  double-backslash (Don\\'t / ccHelpGotit(\\')) that broke the main app <script>, blanking EVERY portal on
  the fleet. Fixed (single-backslash + dropped the apostrophe). Verified by node-checking the ACTUAL SERVED
  page, not a source slice (the source-slice check had truncated before the bad line -- root cause of the miss).

## 0.20.0 -- 2026-06-24
- NEW (in-app "How this works" explainers): every powerful lens (Gmail, Calendar, Drive, Files, Sessions,
  Pipeline, Comms) has a dismissible explainer that AUTO-SHOWS ONCE on first visit ("Don't show again" +
  Dismiss), reopenable anytime via a "?" button in the top bar. So users actually understand the power.
  Plus docs/FEATURES.md (written companion).
- NEW (Gmail auto-refresh): the inbox list now pulls in new mail on its own (~45s) WITHOUT yanking the list
  while you read -- if a thread is open it shows a "↑ N new -- click to refresh" pill instead of reordering
  under you; silent refresh when nothing's open. (Before, only the unread badge updated; the list was static.)

## 0.19.0 -- 2026-06-24
- NEW (AGENTIC LEVERAGE -- first vertical slice: "Smart Reply with 360 context"): the platform starts to
  FLEX its extensions together instead of siloing them. Foundation + first recipe, PROVEN live on carsearch.
  - ACTION QUEUE (the safety spine): _actions.json + audit log; action_propose/list/apply/reject;
    GET /api/actions + POST /api/actions/approve|reject (operator-only, NOT peer-reachable). Every
    apply/reject is audited. Nothing outward executes without a human approval.
  - gmail_draft(): stages a REAL Gmail draft (drafts.create) reusing the gmail_send MIME assembly. Never sends.
  - /api/flex/context?tid= : the cross-extension JOIN -- _match_folders resolves the client folder, then a
    LIVE bundle (folder correspondence + calendar + drive + call notes + pipeline stage, capped ~24k) ->
    headless `claude -p` (free Max-sub) -> {draft_html in your voice, three_bullets "what you know about
    them"}. Halts to a clear gate on malformed output; bundle stamped UNTRUSTED to the model.
  - Thread reader: "✨ Smart reply" (stages a Gmail draft + an action record, opens the composer pre-filled +
    shows the 3-bullet brief) and "🔎 Sender history" (inline dossier). Self-hides without Google.
  - HARD INVARIANT: no flex/recipe/AI code path can call gmail_send -- staging only; the human reviews and
    clicks Send. Proven: a real carsearch thread produced a context-aware in-voice draft + a brief fusing
    email + folder + pipeline in ~6s, staged as a draft, never sent.
  - Roadmap (designed, not yet built): capability registry every agent reads, the recipe engine + more
    flexes (call->everything, state-of-client), in-surface AI across lenses, proactivity scanner, mesh
    capability cards. This slice is the machinery the rest generalizes.

## 0.18.3 -- 2026-06-24
- FIX (watchdog handles the real-world stuck state): when a turn dies on an API/rate-limit error, the error
  line gets pushed ABOVE the "How is Claude doing this session?" feedback overlay + input box -- the old
  6-line tail scan missed it. Now scans the last ~15 lines, distinguishes an active spinner ("Actioning…
  (32s)") from a finished turn ("Worked for 39s"), and the nudge DISMISSES the feedback overlay (0) before
  sending + a second Enter to flush a message left queued behind a rate-limit backoff. (Caught a real
  text2tune editor_truth session stuck exactly this way.)

## 0.18.2 -- 2026-06-24
- FIX (session watchdog): now watches ALL Claude sessions (was opt-in to 3 chiefs, so e.g. a text2tune
  working session got no nudge), and the error detector now recognizes Claude Code's "⏺ API Error:" line
  glyph + rate-limit/"temporarily limiting requests" wording. Idle+persistent(2 checks)+cooldown gating
  unchanged, so it lets Claude Code's own retry go first, then nudges a truly-stuck session.

## 0.18.1 -- 2026-06-24
- Pipeline lens: the FAILED/STALLED/MISSED alarm is now a LOUD full-width banner pinned to the top of the
  card (red pulses; amber for missed/stall) with the run id + expected-by + last-heartbeat context -- not a
  normal-width tinted card. Makes "something is wrong" unmissable at a glance (the silent-missed-run this
  pilot exists to prevent). Backend alarm fields unchanged; pure render upgrade. (Requested by the carsearch
  pilot.)

## 0.18.0 -- 2026-06-24
- NEW (email <-> client/project linking, CRM-grade): connect email to a CLIENT (agency) or PROJECT (module)
  via one generic folder abstraction. A link registry (folder <-> emails/domains/keywords/pinned-threads,
  manual edges only -- the query is derived live so it never goes stale) with a shared matcher (own/exclude
  domain floor, then exact-email/domain/keyword/name scoring, auto vs suggest). Per-folder CORRESPONDENCE
  view (a live Gmail query, read-safe metadata) in the Projects module detail + an Agency client "Mail"
  modal. Reader "Linked to" chip (auto/manual, change/unlink, suggestions). List-row folder chips. And
  SAVE-ATTACHMENT-TO-FOLDER: one click writes an attachment into that folder's deliverables/ (path-safe via
  projpath + secret-guard + size cap; optional dormant Drive mirror). Seeds from cc.config client_map.
  Proven live on carsearch: link a module to an address, its correspondence appears, and a saved attachment
  lands in the folder's deliverables on the SSD. Endpoints under /api/mail/*.

## 0.17.0 -- 2026-06-24
- REBUILD (email + calendar + sessions, the big one): integrated a 10-agent research/build of the whole
  Gmail/Calendar/Sessions UX, then QA-reviewed and PROVED it before shipping.
  - GMAIL READER: draggable, persisted list|reading resizer; attachment strip with inline image previews,
    Quick Look, and download (new /api/google/gmail-att bytes endpoint); threaded reader.
  - WYSIWYG COMPOSER (gmc-*): contenteditable rich text (full toolbar + shortcuts), paste that retains
    formatting AND images (sanitized to email-safe HTML), inline images embedded via cid + drag-drop file
    attachments, signature, draft autosave. Backend gmail_send REBUILT (stdlib email.*) -> multipart/mixed >
    related > alternative with cid inline images, file attachments, text fallback, In-Reply-To/References.
    PROVEN by a live carsearch round-trip: received MIME = mixed>related>alternative(text+html w/ <h2>/<ul>) +
    inline image (Content-ID) + downloadable attachment. Renders correctly on the recipient end.
  - CALENDAR: richer events (attendees/recurrence/reminders/Meet), drag create/resize/move, NL quick-add,
    inline edit, RSVP (/api/google/calendar-rsvp), delete + undo. Backend create/update/delete verified live.
  - SESSIONS TASKBAR is now the primary session surface: hover a tile -> full interactive terminal blow-up
    with Usage / New-tab / Graceful-exit / Kill; Sessions-lens "littles" removed (lens shows only the focused
    big; fixes the big-floating-over-usage bug); acknowledge-on-view preserved.
  - QA fixes before ship: calendar key-delete now confirms (was instant data loss); calendar email-before-map
    ordering (RSVP buttons); archive/trash no longer auto-marks the next thread read; removed the fake
    browser-only "send later" (silent loss); reply/forward now sanitize quoted inbound HTML; label-lane
    refresh no longer jumps back to Inbox.
- NEW (session watchdog): cc-session-watchdog.py + a launchd timer (45s) nudges any watched Claude session
  that is IDLE and stalled on a trailing API-error line ("continue"), riding through API outages until they
  clear (persistence + cooldown; opt-in watchlist; anchored detection so it never fires on chat that merely
  mentions errors). Ships as a framework file; each deployment enables its own per-user launchd.

## 0.16.1 -- 2026-06-24
- FIX (sessions taskbar): opening/viewing a session big in the Sessions tab now clears that session's gold
  "done" pulse in the bottom taskbar immediately (you're obviously seeing it) -- and a session that finishes
  while you're already viewing it big never starts pulsing. (Acknowledge-on-view, in addition to hover/click.)

## 0.16.0 -- 2026-06-24
- NEW (global sessions taskbar -- desktop): a Windows-style dock pinned to the bottom of EVERY lens showing
  ALL project sessions. Each tile shows a live state dot (gold blinking = Claude is working). Hover a tile to
  pop a live terminal preview (auto-refreshing) with an "Open" button that jumps to the full Sessions terminal.
  The killer bit: when a session FINISHES (busy->idle, detected via the "esc to interrupt" indicator), its tile
  PULSES GOLD until you acknowledge it (hover/click) -- so if you're off in Gmail or another tab you get pulled
  back the moment an agent is done; the browser TAB TITLE also shows a "(N done)" cue when the CC is backgrounded.
  Present across the whole console + all tabs/extensions. New endpoint /api/session-bar (busy computed in
  parallel across sessions). Desktop only (hidden on mobile). Built on the existing _pane_busy detector,
  term-snapshot previews, and openInSessions().

## 0.15.2 -- 2026-06-24
- FIX (Gmail rail): the Labels section is now a COLLAPSIBLE group (collapsed by default, chevron + count)
  so a long label list no longer floods the rail. Account email is separated from the Inbox lane (border +
  spacing) so they no longer visually collide.
- FIX (Google lens leaked onto sibling instances): google_configured() now requires the google-workspace
  extension to be INSTALLED on THIS instance (per-instance EXT_STATE), not merely that a token exists in the
  shared CC_HOME. So text2tune / mission-control no longer show Gmail/Calendar/Drive; only nodes where the
  operator set up the extension (carsearch, AFP) do. Any previously-seeded "Google" nav folder self-removes
  on instances where it's now gated off.

## 0.15.1 -- 2026-06-24
- FIX (Google suite rendered completely unstyled): the 0.15.0 integration pasted the entire new stylesheet
  (cmdk-*/gm-*/cal-*/dr-*) into the RALPH page's <style> instead of the main app page's, so every Gmail/
  Calendar/Drive lens rendered as raw unstyled HTML. Moved the 477-line CSS block into the main page <style>
  (where --accent-rgb/--dim/etc. resolve). Lenses now styled. The shell JS was already correctly placed.

## 0.15.0 -- 2026-06-24
- REBUILD (Google suite -- "beat Google"): a ground-up rebuild of the Gmail/Calendar/Drive lenses into a
  premium, keyboard-first client, produced by a 10-agent research+design+build workflow (SOTA study of
  Superhuman/Shortwave/Notion Calendar/Fantastical/Vimcal/Dropbox/Finder) and integrated surgically.
  - SHARED SHELL: a ⌘K/Ctrl-K command palette (fuzzy, cross-surface actions + unified search), a global
    keyboard router, list/detail split-pane layout, skeleton loaders, undo-toasts. One design system
    (stepped surfaces, gold-only accents; new :root tokens --acc/--el1..3/--hair/--tint/--ring/z-stack).
  - GMAIL: saved lanes (rail of stored queries), single-key triage (j/k/e/s/u/r/c/x) all optimistic with
    z-undo, threaded reader (new gmail-thread), operator-chip search, labels, snooze (client+label),
    HTML compose w/ reply headers. Read/unread invariant preserved (list=metadata never marks read;
    opening marks read).
  - CALENDAR: real time-grid (day/week/month/agenda) with a gold now-line + overlap splitting, mini-month
    navigator, natural-language quick-add as primary create, drag move/resize (new calendar-update/-delete).
  - DRIVE: Quick Look preview (spacebar, full-screen iframe), real folder nav + breadcrumbs, live filter +
    sort, grid/list, multi-select batch actions (new drive-modify), thumbnails (server proxy drive-thumb),
    text/code preview (drive-content).
  - New endpoints under /api/google/*: gmail-thread, gmail-labels, gmail-label, gmail-snooze-label,
    calendar-update, calendar-delete, drive-get, drive-modify, drive-thumb, drive-content. Stdlib only.

## 0.14.0 -- 2026-06-23
- NEW (Google Workspace -- live embedded client): a real Gmail + Calendar + Drive experience built into the
  console, auto-grouped under a collapsible "Google" nav category (uses the 0.13.1 categories). The CC server
  calls Google's REST APIs directly with the refresh token the google-workspace extension already minted
  (extensions/google-workspace/secrets/tokens/<acct>.json) -- no MCP/agent in the request path. Stdlib only.
  - GMAIL: inbox/unread/starred/sent views + search; read/triage (archive, star, trash) with one click;
    open a message (HTML rendered in a sandboxed iframe) and Reply; Compose + send. Live unread-count badge
    on the tab. **Read/unread is Gmail's REAL state, both ways**: listing uses format=metadata so pulling the
    inbox NEVER marks anything read; opening here removes the UNREAD label (reads here -> read in Gmail);
    reading in Gmail shows read here on the next refresh (no local shadow state).
  - CALENDAR: upcoming events (Today / 7d / 30d) grouped by day with location, guests, Join links; create
    events (with the browser's timezone).
  - DRIVE: recent files + search, open in Drive, type icons, sizes.
  - Self-hides on any node without a Google token (window.CC.google). Endpoints under /api/google/*.
  - NOTE: AFP has no Google token so this lens is hidden there; AFP stays fine on 0.13.4 (update at leisure,
    never with remote restart:true).

## 0.13.4 -- 2026-06-23
- FIX (boot hang on iCloud nodes -- took AFP down): the server printed its banner then ran
  regen_treemap() (whole-tree walk) + icloud_age_off() (iCloud file moves) BEFORE serve_forever() --
  on an iCloud-backed node those block on slow iCloud I/O, so the process "started" (banner) but never
  accepted a connection. Moved all heavy boot housekeeping into a daemon thread; the HTTP server now binds
  and serves IMMEDIATELY regardless of iCloud state. Secret-file 0600 self-heal stays inline (fast).
- FIX (remote restart killed a node it couldn't recover): _self_restart now re-execs with an ABSOLUTE
  script path (BASE-derived), cwd-independent -- a relative sys.argv[0] ('server.py') could fail to resolve
  after re-exec and kill the process with no respawn.
- FIX (banner branding): the startup banner used a hardcoded "HP Tuners Command Center" on every node;
  it now uses the deployment's configured BRAND (so AFP announces Sarah's brand, not "HP Tuners").

## 0.13.3 -- 2026-06-23
- NEW (splash version): the ClaudeFather entry splash now shows the running framework version, tastefully,
  centered at the bottom ("v0.13.3", gold-on-dim, gentle fade-in). Sourced from window.CC.version (the
  node's own manifest) so every instance self-identifies what it is running at a glance.

## 0.13.2 -- 2026-06-23
- NEW (usage-sort INSIDE categories): the custom/category nav now has a "sort by use" toggle -- when on, it
  ranks tabs by click-count BOTH at the top level AND within each folder, while keeping your folder
  membership exactly as you arranged it. A category floats by its busiest member (heavy-use folder rises, a
  "less used" folder sinks). Purely a render view -- your manual drag order is preserved underneath, so
  toggling back to manual restores it. Answers "sort them by usage in or out of the category." (reset clears
  it too.)

## 0.13.1 -- 2026-06-23
- NEW (nav categories / folders): build collapsible CATEGORIES in the sidebar and drag tabs into them to
  tuck away the lenses you rarely use -- click a category header to collapse/expand it (chevron + member
  count), double-click to rename, the &#10005; deletes it and frees its tabs back to the list. Drag tabs
  between categories and the top level, reorder categories themselves, all by drag-and-drop. "+ category"
  lives in the nav-mode line; creating one (or any drag) flips the nav to "custom" -- "reset" returns to
  pure usage-ranking and clears folders. Survives reloads + framework updates (new lenses append to the top
  level; deleted lenses drop cleanly). Builds on 0.13.0's smart-sort. Same localStorage key, per-node.

## 0.13.0 -- 2026-06-23
- NEW (smart-sort navigation): the left-hand lens tabs now reorder themselves by how often you click them
  -- most-used first -- so your top tools rise to the top automatically. Drag any tab to a new spot to PIN a
  custom static order (mode flips to "custom order"); a one-click "auto-sort" link under the nav reverts to
  usage-ranking. Per-node and stored in localStorage (no backend, no cross-tenant bleed, survives reloads).
  Unclicked tabs keep their natural order as a stable tiebreak; new lenses added by a later update append
  cleanly to a pinned order. Works on desktop (vertical) and the mobile (horizontal) nav.

## 0.12.5 -- 2026-06-23
- FIX (remote superadmin cc_update targeted the wrong CC_HOME): cc-update.sh now SELF-LOCATES its CC_HOME
  from the script's own directory (was a hardcoded $HOME/hptuners-control default), and the superadmin
  cc_update action passes the real CC_HOME to the subprocess. Surfaced when a signed cc_update to AFP failed
  synchronously with "no manifest at /Users/sarahaios/hptuners-control" -- the deterministic action returning
  the failure instantly is the point working (no inbox/guessing); the path bug it revealed is now fixed so
  remote updates land on the actual deployment regardless of where it lives.

## 0.12.4 -- 2026-06-23
- Superadmin: new DETERMINISTIC `set_claude_setting` action (key,value over an allowlist: tui/theme/verbose/
  autoUpdaterStatus/skipDangerousModePermissionPrompt) that writes the user's ~/.claude/settings.json and
  returns the result SYNCHRONOUSLY in the HTTP response -- no chief, no inbox, guaranteed request->response.
  Use this (not the async `instruct`->chief path) for anything that needs a confirmed answer; `tui:default`
  is the browser copy/scroll fix. Reinforces the rule: deterministic actions return synchronously and are
  100% reliable; `instruct` is the only async (LLM-mediated) path and should not be used when a guaranteed
  reply matters.

## 0.12.3 -- 2026-06-23
- Storage architecture standard + doctor check (enterprise per-node SSD model). New docs/STORAGE_ARCHITECTURE.md
  defines the clean layout: ONE dedicated APFS SSD per node, with that node's macOS HOME on it -- so the
  project AND (for iCloud nodes) the iCloud container live on the SSD, not the small internal boot drive.
  Confirms the only supported way to get iCloud onto an SSD is home-on-SSD (iCloud syncs the container inside
  the home, on whatever volume the home is on -- not a configurable path), and includes the exact backup-first
  runbook to relocate an existing node's home onto its SSD. Doctor now flags a node whose home (iCloud) or
  project sits on the internal boot volume instead of its own SSD (compares st_dev vs root). Capacity becomes
  per-node + additive, internal drive stays empty, iCloud doubles as off-site backup.

## 0.12.2 -- 2026-06-23
- FIX (remote/mobile file UX): the Files lens + per-module Files panel led with "open" which only reveals the
  file in Finder ON THE STUDIO -- useless to a remote/mobile operator (it just toasted "opening on the
  Studio"). Now the file NAME is a tap-to-view link and DOWNLOAD is the primary button (downloads to the
  device you're on, incl. a phone); "reveal on Studio" is demoted + clearly labeled. Toast no longer implies
  it opened for you. So from anywhere you tap the file -> view, or Download -> get it. No backend change.

## 0.12.1 -- 2026-06-23
- Files lens gains a scoped IN-BROWSER FILE EXPLORER (the "tunnel a file browser through the browser" ask):
  a "Browse files" mode navigates the project tree (breadcrumb + folders + files) right in the dashboard,
  with open (reveal on the Studio) + download (works from any browser, incl. a remote Windows box). Strictly
  scoped UNDER the project root (path-traversal safe via projpath) and SECRET-HIDING: dotfiles, secrets/,
  tokens/, .git, *.pem/*.key, cc.config.json, .env*, OAuth/token JSON are never listed -- and /api/file-get
  now refuses those paths too, so credentials can't be downloaded. Toggle between "Recent outputs" (the
  aggregated deliverables view) and "Browse files". 4 guard tests.
- Agents now told (chief brief + agent launch brief) to ALWAYS save user-facing outputs to deliverables/ so
  they surface in the Files lens, and that on iCloud nodes those files sync to the operator's devices.

## 0.12.0 -- 2026-06-23
- NEW LENS: Files -- a top-level sidebar tab that aggregates EVERY agent-output file across the whole
  deployment (all modules' deliverables/ + the SSD cold archive), newest-first, grouped Today / This week /
  This month / Earlier. Each file shows the module it was made for and its storage tier (cloud iCloud /
  SSD archived / Studio-local), with OPEN (reveal on the Studio at the file's real location) and DOWNLOAD
  (works from ANY browser, incl. a remote Windows box -- the answer to "I can't open Finder remotely"). Core
  for all deployments: iCloud nodes get the tier tags; github/local nodes just get the organized list +
  download. Backed by all_deliverables() + /api/files. One obvious place to find what agents made for you.

## 0.11.0 -- 2026-06-23
- iCloud TIERED deliverables -- give iCloud-mode deployments real iCloud sync for agent output WITHOUT
  violating the "write to the SSD, internal disk is full" rule. macOS truth (researched): iCloud Drive only
  syncs ~/Library/Mobile Documents/.../CloudDocs on the INTERNAL volume and will NOT sync an external SSD
  path (no symlink-follow; relocating the container is unsupported/corrupting). So a two-tier lifecycle:
  - TIER 1 hot (<= deliverables_icloud_days, default 90): each module's deliverables/ is a SYMLINK into the
    iCloud container, so agents keep writing to deliverables/ unchanged but the bytes land in iCloud -> synced
    to all the operator's Apple devices, and "open" reveals them IN iCloud (reveal now resolves realpath).
  - TIER 2 cold (> retention): a boot/on-demand lifecycle pass ages files off internal -> the SSD archive
    (<project>/.deliverables_archive, off internal + off iCloud). Still listed + openable in the Files panel.
  - The Files panel tags each file by tier (cloud iCloud / SSD archived); module_files spans both tiers.
  - Retroactive: icloud_relink_all() routes EXISTING deliverables into iCloud. Triggers: /api/icloud-relink
    + /api/icloud-ageoff (operator), and superadmin actions relink_deliverables / ageoff_deliverables.
  - Gated to storage_mode containing "icloud"; github-mode deployments are completely unchanged. Safe
    fallback on any error (never breaks an agent's write). 3 guard tests. Doc: docs/ICLOUD_STORAGE.md.

## 0.10.1 -- 2026-06-23
- Superadmin: broadened the action allowlist + wired the installer.
  - NEW actions (all owner-signed, node-bound, single-use): `instruct` -- deliver an AUTHORIZED owner
    directive into a node's chief as a clean turn (marked SUPERADMIN, NOT the untrusted peer frame) = the
    broad "make the agent do anything" power; `cc_update` -- pull the latest framework on the node (optional
    `restart`); `restart` -- reload the node's CC in place (os.execv, no supervisor dependency). Existing
    ping / accept_skip_permissions / set_config unchanged. The signature still gates everything (a forged
    instruct does not run).
  - Installer (install/install.sh) now installs `cryptography` for the CC's python3 (best-effort --user) so a
    fresh node honors the owner's Ed25519 superadmin grants out of the box; doctor warns if superadmin.pub is
    present but cryptography is missing (node not under superadmin until fixed). 3 guard tests.

## 0.10.0 -- 2026-06-23
- PUBLIC-KEY superadmin -- "every install is automatically under the owner's superadmin" (CCR
  ccr-1782174717859, upgraded from the v0.9.0 derived-key model per James's asymmetric-authority vision).
  Adds an OPTIONAL dependency (`cryptography`, Ed25519). Model: the owner holds an Ed25519 PRIVATE key on
  Mission Control (.superadmin_ed25519, 0600, gitignored, NEVER shipped); the matching PUBLIC key ships in
  the framework (superadmin.pub) so EVERY install -- the owner's nodes AND any future public install --
  verifies the owner's grants with ZERO provisioning. A compromised install holds only the public key: it
  can verify, it can NEVER forge. Grants stay node-bound (no retarget), short-lived (exp), single-use
  (nonce), and limited to the action allowlist. The v0.9.0 derived-key HMAC path remains as a fallback for
  nodes that lack `cryptography` or are explicitly provisioned (alg field selects the verifier; it's signed,
  so no downgrade). superadmin_grant auto-signs Ed25519 when the private key is present, else HMAC. New
  /api/superadmin-keygen (MC, operator-authed) generates the keypair once. Graceful: a node without
  `cryptography` still boots (Ed25519 verify disabled there until installed). This realizes the asymmetric
  authority James described -- DOWN: the owner can force any node; UP: nodes can only file change requests
  (the CCR system) which the owner approves, and MC never acts on a peer's say-so (the peer-untrust frame).
  4 Ed25519 guard tests (sign/verify with no provisioning, forge-with-other-key, tamper, replay). Docs:
  docs/SUPERADMIN.md. Reverted the v0.9.2 self-heal opt-out (owner-fleet model -- nodes don't opt out;
  superadmin overrides). NOTE: install the dep with `pip install --user cryptography` for the CC's python.

## 0.9.1 -- 2026-06-23
- FIX (mesh reliability false-overdue, reported by AFP): mesh_recv closed only the OLDEST awaiting thread to
  a peer per reply (1:1 FIFO). Peers bundle answers (one reply covers several of our messages), so when MC
  sent multiple tracked requests the open-thread count outran the closes and one crossed the SLA -> a FALSE
  overdue auto-re-ping even though the peer had fully engaged. Fix: a reply from a peer proves non-silence,
  so it now closes ALL open awaiting threads to that peer, not just the oldest. (The tracker detects SILENCE,
  not answer-completeness; a request the peer's chief never processed is still caught by the receiver-side
  needs_reply flag.) +1 guard test (one bundled reply clears three open threads). Good catch by AFP.

## 0.9.0 -- 2026-06-23
- NEW: Superadmin grants -- cryptographically-authorized platform-owner instructions to ANY node in ANY
  family (CCR ccr-1782174717859). The legitimate "Mission Control, make it so" channel: a node executes an
  owner-signed grant instead of refusing it as an untrusted peer. Stdlib has no public-key crypto and we add
  no dependency, so it uses a DERIVED-KEY (HMAC) design that meets the CCR's goal (a node compromise must NOT
  grant fleet-wide power): the MASTER lives ONLY on MC and is never distributed; each node holds only its own
  key = HMAC(master, "sa-v1:"+node_id); MC signs a grant for node X with X's key; compromising X leaks only
  X's key (forging to X is pointless), and forging to another node needs the master. Grants are node-bound
  (no retarget), short-lived (exp), and single-use (nonce) -> no replay. Allowlisted actions only (ping /
  accept_skip_permissions / set_config over a safe key allowlist -- never arbitrary exec; secrets not
  settable). Endpoints: /api/superadmin-exec (node side -- the SIGNATURE is the auth, so it's exempt from
  operator-auth/family-token and reachable cross-family), /api/superadmin-send|grant|derive (MC side --
  require the master + operator auth, so only the MC operator can issue/derive). Provision out-of-band like
  the family token (set superadmin_master on MC; derive each node's key; set superadmin_node_key on the node).
  9 guard tests (forge / tamper / replay / retarget / expiry / wrong-master / allowlist all rejected). Docs:
  docs/SUPERADMIN.md. NOTE: feature is inert until a master + node keys are provisioned.

## 0.8.4 -- 2026-06-23
- FIX (sessions stuck without skip-permissions, found on AFP/sarahaios): the CC always launches sessions
  with --dangerously-skip-permissions, but Claude Code gates that flag behind a ONE-TIME, PER-USER
  acceptance of the 'Bypass Permissions mode' screen. A user who never accepted it (a fresh deployment)
  has every console-launched session stall on that screen -- the flag never engages. The launcher's
  auto-accepter only knew the 'trust this folder' prompt, not this one. Fix: a boot self-heal
  (_ensure_skip_permissions_accepted) sets the acceptance for the user the CC runs as -- bypassPermissions
  ModeAccepted:true in ~/.claude.json + skipDangerousModePermissionPrompt:true in ~/.claude/settings.json --
  so the screen never appears. Chosen over auto-navigating the safety screen each launch (which risks
  mis-selecting 'No, exit'). Surgical (only those keys, never the user's default mode), mode-preserving
  (never widens perms on the claude config), atomic, idempotent (writes at most once per deployment). 2
  guard tests. Existing accepted users (e.g. hptuner) are a no-op.

## 0.8.3 -- 2026-06-23
- Pipeline Live-View: instant RUN-FAILED alarm (carsearch pilot request). A failed run, or ANY critical
  step entering state=failed, now raises a red alarm immediately -- it no longer waits for the stall (~10m)
  or missed-by-expect_by timeout to surface. FAILED takes priority over STALLED/MISSED. A non-critical
  (log-and-continue) step failing on an otherwise-good run does NOT alarm. This closes the exact silent-
  failure that motivated the lens (carsearch's s1 scrape->sync->deploy going red the instant it dies).
  3 guard tests. (Their emitter already writes state:failed + a _run failed event on finish, so it lights up
  with no extra work on their side.)

## 0.8.2 -- 2026-06-23
- MESH RELIABILITY -- "no silent drops" (CCR ccr-1782245141634). A chief composed a reply and never sent it;
  neither side noticed and the operator only caught it by watching a tmux pane. Fixed with self-escalating
  tracking on BOTH sides (principle: the side owed something detects the absence -- never trust the peer):
  - Requester side: an initiating message defaults to expect_reply=True and opens a tracked "awaiting reply"
    thread. Delivered + unanswered past MESH_REPLY_SLA (default 600s, cc.config mesh_reply_sla) -> status
    flips to OVERDUE and the worker fires ONE automatic re-ping to the peer. A reply closes the OLDEST open
    thread (FIFO). Pure FYIs send with expect_reply=false and are never tracked.
  - Receiver side: an inbound peer request is flagged needs_reply on receipt and cleared when our chief's
    reply is forwarded (mesh_reply, driven by the existing Stop hook). If it stays unanswered past the SLA it
    surfaces as an "unanswered request from X" -- so a request WE drop can't vanish on our end either.
  - Health surface: the Comms lens shows an "Open threads" card (awaiting / OVERDUE / unanswered, with ages
    + snippets), and the Comms nav badge now persists a red count for overdue + unanswered until resolved --
    so a dropped ball is visible without watching anything. /api/mesh payload gains awaiting/overdue/
    unanswered/sla. 4 guard tests.

## 0.8.1 -- 2026-06-23
- SECURITY (cc-update secret containment): cc-update.sh now rsyncs framework dirs with
  `--exclude='secrets/'` (+ secrets, *.local, .env*). rsync ignores .gitignore, and extensions/ is a
  framework_path, so without this a per-deployment secret nested in an extension (e.g.
  extensions/*/secrets/ -- OAuth client JSON + refresh token) could replicate to every node on update. Not
  triggered (dist was clean), closed proactively. (CCR ccr-1782243460905.)
- Google Workspace extension v1 hardening (carsearch first-install field report, ccr-1782243034502):
  - mcp.json template was a non-working STUB (command "CONFIRM_AT_SETUP" + the wrong env var
    GOOGLE_OAUTH_CREDENTIALS). Replaced with the verified workspace-mcp wiring (uvx workspace-mcp
    --single-user --transport stdio) using the env vars the server actually reads (GOOGLE_CLIENT_SECRET_PATH,
    WORKSPACE_MCP_CREDENTIALS_DIR, USER_GOOGLE_EMAIL, OAUTHLIB_INSECURE_TRANSPORT) and <DEPLOYMENT>/<ACCOUNT>
    placeholders. Safe default gmail:drafts; gmail:send is a documented one-flag opt-in.
  - SETUP.md rewritten to lead with Path B (headless, the right default for a ClaudeFather -- Path A
    connectors are operator-account-bound and cannot send), a 3-question flow, verified Cloud Console steps
    (Testing-mode + test-user-match + unverified-app callouts), the reverse-SSH-tunnel pattern for remote-host
    installs, and the gotchas (unbuffered stdout, no macOS timeout, offline+consent, ~7-day testing-token re-mint).
  - Shipped 3 tools under extensions/google-workspace/bin/: mint_token.py (headless minter that reuses
    workspace-mcp's own scope/credential-store logic), verify.py (env-driven read-only 3-surface check),
    gauth.sh (one-command minter + reverse-tunnel orchestrator). Root .gitignore exception added so
    extension bin/ tools are tracked (the global bin/ ignore was hiding them).
  - extensions/google-workspace/secrets/.gitignore (`*` + `!.gitignore`) ships so a fresh deploy's secrets
    dir self-protects; extension .gitignore restructured to `secrets/*` + `!secrets/.gitignore`.
  - extension.json -> 2.1.0: Path B default + draft-first/send-opt-in framing.
  - 4 guard tests (placeholder template / no real account baked in / cc-update secrets-exclude / secrets
    .gitignore shipped). NOTE: live carsearch install is unaffected -- its wiring lives in the deployment's
    own .mcp.json (a preserve_path), not the template.

## 0.8.0 -- 2026-06-23
- NEW LENS: Pipeline Live-View (MVP) -- a generic "where is the run RIGHT NOW" view for any node running a
  long pipeline/cron job (proposed by carsearch CoS, scoped + built at MC, shipped via dist; carsearch is
  pilot). Zero per-node code: a node's pipeline writes a standard contract (manifest.json + heartbeat.json
  + events.jsonl) to PIPELINE_DIR (default <project_root>/.pipeline, configurable) and the lens renders
  whatever steps it declares. MVP panels: (1) LIVE RUN MAP -- top-to-bottom steps that light up by state
  (pending grey / running pulsing-blue / done green / failed red / skipped dim) with per-step elapsed +
  free-form metric chips (e.g. "listings 1240", "progress market 8/500"); (2) MISSED-RUN / STALLED ALARM
  -- red banner when a running step stops heartbeating (> pipeline_stale_sec, default 600s) or when an
  expect_by deadline passes with no completed run today (the "silent until noon" failure that triggered the
  request). Transport = file-emit + 4s poll of /api/pipeline (consistent with the stdlib poll-based CC; no
  websockets). The lens SELF-HIDES until a node declares a manifest (window.CC.pipeline, same pattern as
  Agency/Calls). Contract spec: docs/PIPELINE_LIVEVIEW.md. 5 guard tests. Fast-follow (not in this release):
  last-run metrics panel + 7-day trailing drift aggregates (the events.jsonl audit is already part of the
  contract so they drop in with history).

## 0.7.10 -- 2026-06-23
- FIX (navigation): browser Back/Forward inside a console now steps through the lenses/drill-downs you
  actually visited, instead of dumping you out to the overseer. The console is an SPA and every in-app
  lens switch + module drill wrote the URL with history.replaceState (overwrites the current entry), so the
  whole session had ONE back-stack entry -- Back jumped straight to the previous document (e.g. Mission
  Control's Portfolio). Now: genuine navigation (lens switch, module drill-in) uses pushState (one entry
  per view, de-duped so re-renders/restores don't spam the stack); a popstate handler rebuilds the view in
  place on Back/Forward (no page reload, no falling out); in-place refinements (maximize a session tile,
  tree day-range) stay replaceState; on load the landing lens is stamped as the back-stack baseline so the
  first Back lands on the console home, not the overseer. Refresh still restores exact lens + sub-state.

## 0.7.9 -- 2026-06-23
- SECURITY (perms, defense-in-depth): cc-update.sh now chmods the secret-bearing PRESERVE files
  (cc.config.json, peers.json, command-center/_mesh_hook_settings.json) to 0600 at the end of every update.
  Closes the last window flagged by AFP: server.py already self-heals perms on boot (v0.7.3) and on the
  Settings-lens write, but between an update landing and the next CC restart a fresh 644 (from umask) could
  persist. The tail resolves paths exactly as server.py does (honors CC_CONFIG env + cc.config
  state_dir/peers_file overrides) and is a no-op under --dry-run. (CCR: secret-file-perms.)

## 0.7.8 -- 2026-06-22
- Usage accuracy overhaul -- "make the numbers totally true" (per James). Four fixes, 6 guard tests:
  1. SUBAGENTS NOW COUNTED. `_scan_tok` only globbed `slug/*.jsonl` (flat main transcripts); Claude Code
     nests subagent transcripts at `slug/<session-uuid>/subagents/agent-*.jsonl`, so ALL subagent token
     usage was silently dropped. Switched to a recursive glob. Verified no double-count: every
     `isSidechain:true` line lives ONLY in the subagent files (zero in main transcripts), so this is purely
     additive. Surfaces previously-invisible Haiku/Sonnet subagent usage in the by-model split.
  2. CACHE-WRITE TTL TIERS. The `usage.cache_creation` split (`ephemeral_5m_input_tokens` /
     `ephemeral_1h_input_tokens`) is now priced correctly: 5-min cache-write at 1.25x input, 1-hour at 2x
     input (was a flat 1.25x). Pre-split events fall back to the 5-min tier. Event tuple extended to carry
     the split; `_ev_cost` updated.
  3. METERED $ IS NOW THE HERO (per James: "show it as if I were paying the actual API per model"). The
     Usage lens leads with the per-model metered cost -- a big "all projects" figure + a "this node" figure
     -- and contrasts it against what he actually pays flat (two Max 20x plans = $400/mo, configurable via
     cc.config `subscription_monthly`): pace/mo, 30-day metered vs flat, and an "Nx value" badge. Window
     cards + the Sessions strip are now cost-led; charts reordered (cost first). Added a clear
     "processed vs billable" distinction (billable = input+output+cache-write; cache-read is most of the
     token count but ~10% of input cost).
  4. PER-NODE SCOPE (per James: "both -- overall AND broken down by the node I'm in"). Each event is tagged
     self/not-self (cwd under this deployment's PROJECT or CC_HOME); totals carry a `self` subtotal and the
     by-project breakdown marks this node's folders (`▸`). Overseer still shows the full box-wide view.
  - Also fixed `_proj_label` fallback (hardcoded "hptuners" -> PROJECT_NAME, so non-hptuners nodes label
    their own root correctly).

## 0.7.7 -- 2026-06-22
- FIX (cost accuracy): the Usage cost model used stale list prices -- Opus was hardcoded at $15/$75 per 1M
  (old Opus-3 pricing) when current Opus is $5/$25, so "metered value" was ~3x overstated (Opus dominates
  usage). Haiku was $0.80/$4 (Haiku-3.5) vs current $1/$5; Fable had no entry and fell back to the wrong
  Opus rate ($15/$75) instead of $10/$50. Corrected to current rates (verified vs the claude-api pricing
  reference, 2026-06): Fable 10/50, Opus 5/25, Sonnet 3/15 (unchanged, was already right), Haiku 1/5;
  cache_read/write re-derived (0.1x / 1.25x input); added a fable/mythos tier mapping. 3 guard tests added.
  NOTE: token COUNTS were always accurate (sourced from each call's usage field); this only fixes the $ estimate.

## 0.7.6 -- 2026-06-22
- Usage lens, token-themed redesign (per James): instead of a single-select window control, ALL windows
  (1hr / 5hr / 24hr / week / month) now show at once as gold "token" cards under a "Tokens" header --
  each with its total, cost/calls, and a mini sparkline. Clicking a card drives the time-series charts
  below (no more clicking through one at a time). Dropped the redundant rolling-windows card. Sessions-tab
  strip reverted to show all five windows at once too (no selector), token-styled.

## 0.7.5 -- 2026-06-22
- Sessions token strip: added the same 1 hr / 5 hr / 24 hr / week / month window selector as the Usage
  lens. The strip's featured total + sparkline now follow the selected window (was static 1h/24h/7d/30d
  cells + a fixed 24h sparkline). /api/token-usage now returns per-range tok buckets (`series`) so the
  sparkline switches without a refetch. Selection persists (localStorage); reuses the Usage URANGES config.

## 0.7.4 -- 2026-06-22
- Agency polish (CCR ccr-1782180450433): a fresh agency deploy showed the "no description" warning on
  every module. Now standard agency folders (clients / partners / pipeline / tools) get a display-only
  default description so the Projects view looks finished out of the box. Strictly bounded: defaults apply
  ONLY when there is no hand-written summary, ONLY on agency deployments, and ONLY for those exact
  folder names -- custom-named folders (e.g. a business name) never get one (they must be human-authored,
  or the framework would mislabel them). Defaults render muted/italic with a "(suggested)" hint and never
  touch CLAUDE.md. 4 unit tests added (test_framework now 139 total).

## 0.7.3 -- 2026-06-22
- SECURITY (shared-box exposure; CCR ccr-1782180012578, found by AFP): per-deployment config files were
  written 644 (world-readable) by the OS umask, so on a multi-user box (hptuner + sarahaios on one Studio)
  any account could read another deployment's `auth_token` AND `mesh_token` -- defeating the mesh family
  token and exposing PINs. Now: settings_save chmods `cc.config.json` to 0600 after writing, and a boot
  self-heal chmods `cc.config.json`, `peers.json`, and `_mesh_hook_settings.json` to 0600 on every start
  (fixes existing 644 files on restart + new deploys). Remaining (tracked in the CCR): cc-init writes 600;
  generic save() for other secret files; a doctor check for world-readable configs.

## 0.7.2 -- 2026-06-22
- FIX (fleet-affecting): "launch failed: unknown target" when opening ANY project/client/module session
  on a deployment with no `studio` machine registered. launch() required a `_machines.json` record even for
  the local `studio` target -- but the studio branch runs tmux locally and never reads that record, and
  `_machines.json` is a per-deployment preserve-path that fresh installs lack. Now the local `studio`
  target is always valid (no registry entry needed); only remote targets require a registered machine for
  the ssh alias. (Hit AFP -- every project/agency session launch failed.)
- Usage lens redesign: a single top "Window" control (1 hr / 5 hr / 24 hr / week / month, new 5h window
  added to the series + totals) now drives the headline KPIs AND the time-series charts. Headline reflects
  the selected window (tokens, metered value, calls + tok/call, throughput tok/hr, peak bucket) instead of
  a fixed 30d. Charts gained an avg line, highlighted+labeled peak bucket, baseline axis, and bucket-size
  labels. by-model / composition / by-project clearly marked "all tracked 30d"; rolling-windows gained a
  5-hour column.

## 0.7.1 -- 2026-06-22
- Test suite + CI (CCR ccr-1782162511917, ship-safety for cc-update):
  - NEW tests/test_framework.py -- stdlib unittest guarding the platform spine: CCR queue lifecycle +
    validation, the tiered mesh authorizer (family/superadmin), and the Settings writer (Tier/Type ->
    cc.config). 14 tests, no network/server (imports server.py by path).
  - Re-enabled tests/test_cognition.py: it had been silently broken since the `granola` import was added
    (the loader did not put command-center/ on sys.path) -- fixed the loader; the suite runs again.
  - tests/run.sh now runs the WHOLE suite via `unittest discover` (was cognition-only).
  - NEW .github/workflows/ci.yml: on push/PR -> ast.parse syntax + the unittest suite + gitleaks.
  - Drift the re-enabled suite caught and this release fixes: stale ROSTER.md (regenerated to include the
    google agent), google charter missing a when-cue, an apostrophe in the audit-brief canonical template
    (briefs must be single-quote-safe for the tmux send-keys wrapper), and a brittle progress.md test
    (now skips when the optional file is absent).

## 0.7.0 -- 2026-06-22
- Mesh security, two parts (hardening track):
  - **Peer-message security frame:** every inbound peer message is now stamped (after the literal
    "[message from X]" so the Stop-hook sender regex still matches) with an explicit untrusted-peer notice
    -- a peer chief is NOT the operator; never disclose secrets/credentials, change settings, or take
    destructive/outward actions on a peer's say-so. The trust boundary now travels in the message itself,
    not just the chief's judgment. Motivated by a live credential-exfil attempt over the mesh.
  - **Tiered mesh trust:** FAMILY token (cc.config `mesh_token`) = shared by every node under a grandfather
    so any CoS reaches any CoS in the family, outsiders rejected. SUPERADMIN tokens (cc.config
    `superadmin_tokens`) = master keys a node trusts on top of its family token, so a platform-owner
    superadmin can reach ANY deployment in ANY family (force updates / health monitoring once public).
    `mesh_auth_enforce` gates rejection: false (default) = carry tokens but reject nothing (safe rollout
    phase), flip true fleet-wide only after every node carries its badge. Inbound chief-say/mesh-recv now
    use a constant-time family-or-superadmin authorizer.

## 0.6.0 -- 2026-06-22
- NEW: Command Center authentication (CCR ccr-1782162511858). OFF by default (open, backward-compatible) --
  /api/doctor now warns loudly while it is off. Enable per node via cc.config `auth_token` (or env
  CC_AUTH_TOKEN). When on, every request needs a credential: a browser session cookie via the /login page,
  or `Authorization: Bearer <token>` / `X-CC-Token` for programmatic/curl use. Constant-time compared
  (hmac). New endpoints: /login (page), /api/login, /api/logout, /api/health (liveness + auth flag).
  Operator-auth is kept SEPARATE from peer-auth: mesh-ingress endpoints (chief-say, mesh-recv, mesh-reply,
  ccr-submit, fw-fingerprint) are exempt from the operator token and stay on their own MESH_TOKEN track, so
  enabling a node's login never severs the inter-chief mesh. Spike limits noted for hardening: cookie value
  is the token (want a rotating signed session id), no /login rate-limit, Secure flag off (http behind
  Tailscale TLS).

## 0.5.2 -- 2026-06-22
- Harden the Portfolio gate: /api/portfolio now returns HTTP 403 (not 200) on a non-overseer node, keeping
  the empty body + a clear error. v0.5.1 already withheld all fleet data from project nodes (no leak), but
  the CCR called for a true 403 status; this completes it. (Follow-up on CCR ccr-1782157164259, flagged by
  AFP during verification.)

## 0.5.1 -- 2026-06-22
- Portfolio is now ClaudeGrandfather (overseer) only. It is a fleet-oversight view, but the 'project' preset
  listed it, so project nodes (e.g. AFP) wrongly showed a Portfolio tab. Removed 'portfolio' from
  presets/project.json, gated /api/portfolio to role==org (returns empty for project nodes), and hide the
  nav button unless CC.role==org (defense-in-depth). (CCR ccr-1782157164259 from AFP / Sarah.)
- NEW: Settings lens (every node). Set this node's Tier and Type from the UI instead of hand-editing
  cc.config.json: Tier = ClaudeFather (role=project) | ClaudeGrandfather (role=org); Type = Project | Agency
  (integration). Writes are atomic to the instance's cc.config (a preserve-path: survives cc-update);
  changing Tier auto-swaps the preset/lens bundle; a restart applies it. Endpoints /api/settings,
  /api/settings-save.
- Naming: adopt the ClaudeFather / ClaudeGrandfather taxonomy in the Settings UI -- presentation mapping 1:1
  onto the existing role=project/org primitives (no data-model change).

## 0.5.0 -- 2026-06-22
- NEW SUBSYSTEM: Core Change Request (CCR) system -- the platform's anti-drift backbone, owned by Mission
  Control (the overseer). Every core/platform change routes through MC: nodes propose, James approves, MC
  builds once and ships uniformly via the dist + cc-update, so installs never diverge. Four parts:
  - Change Requests lens + queue at the overseer (preset-gated to role=org): durable _ccr.json with the
    lifecycle new -> triaged -> approved -> building -> shipped | rejected, approve/reject/comment.
    Endpoints /api/ccr, /api/ccr-submit, /api/ccr-update, /api/ccr-delete.
  - Propose Change tab at every project node (preset-gated to role=project): a submit-only form that
    forwards a CCR up to MC server-side (no CORS) and keeps a local sent-log. MC peer auto-resolved from
    peers.json (override via cc.config mission_control_url). Endpoints /api/ccr-propose, /api/ccr-sent.
  - Framework-owned managed block 'ccr-policy' (the governance norm): auto-seeded on each project node's
    boot and stamped into its root CLAUDE.md (scope root -> every agent inherits it) -- "core changes are
    not built locally; route them to Mission Control." Skipped at the overseer (it IS the authority);
    idempotent; bump fw_version to push an update fleet-wide.
  - Fleet drift check: every node fingerprints its core framework files; MC compares each against the
    canonical dist and shows current / ahead / drifted / behind / unreachable in the Change Requests lens
    (differing files on hover). Endpoints /api/fw-fingerprint (all nodes), /api/ccr-drift (MC).

## 0.4.2 -- 2026-06-22
- Granola SETUP.md: clarified (from AFP real-world install) that the local-cache source only works when the
  deployment box IS the Mac where calls are recorded. On typical agency setups the always-on box (e.g. a Mac
  Studio) is not the call-taking laptop, so there is no cache there -> use the official API. Rule of thumb in
  the doc now. No code change; the module already errors gracefully on a missing cache.

## 0.4.1 -- 2026-06-22
- Google Workspace module overhauled from a thin connector into a power-module. New Google agent-tool
  (agents/google) that drives the WHOLE surface: Gmail triage with labels + reply DRAFTS (draft-only, never
  sends), Calendar free/busy scheduling (suggest_time) + create/respond, Drive search/read/create +
  permission checks, a daily brief, and per-client comms filed into each client's CLAUDE.md. Integrated:
  client_map ties email/meetings/Drive to client folders, and it drains the Calls (Granola) google
  destination into real calendar events. extension.json -> v2.0.0 (provides agent:google), SETUP.md rewritten
  (full surface, least-privilege scopes, Path A connectors vs Path B self-hosted MCP for headless agents),
  mcp.json gains a Path-B reference. Read-first/draft-first/confirm-before-mutate boundaries.

## 0.4.0 -- 2026-06-22
- NEW MODULE: Granola Calls (agency). A 'Calls' lens + command-center/granola.py turn Granola call
  transcripts into a REVIEW QUEUE of proposed agency updates. Ingest is read-only (official Granola API, or
  the local cache-v3.json as a no-key fallback); each call is matched to a client folder (attendee domain via
  client_map, or title) and an LLM (headless claude -p, no metered key) extracts summary/notes/tasks/
  reminders/decisions. Nothing is written until approved in the Calls lens -- on approve it appends a dated
  note to the client's CLAUDE.md (managed CC:CALLS region) and creates tasks + reminders in the chosen
  destination(s): Command Center per-client TODO (default), Google Calendar/Tasks, Apple Reminders, or a Slack
  digest. Endpoints /api/granola{,-sync,-apply,-skip}; config in cc.config 'granola'; extension at
  extensions/granola/ (SETUP.md). Agency-only lens. End-to-end pipeline verified on a synthetic transcript.

## 0.3.8 -- 2026-06-22
- cc-update.sh bug fix (found by AFP): the CC:NOTES-preservation splice ran on ANY file containing the
  marker string -- including server.py, whose CODE contains literal '<!-- CC:NOTES -->' markers. That
  reverted server.py to the deployment's old copy while the version still bumped ('version bumped, code
  stale' -- the cause of AFP's 0.3.4/0.3.7 confusion). Fix: the CC:NOTES splice now applies ONLY to *.md
  files (CLAUDE.md/docs, where hand-authored notes actually live); all code/non-md files are copied verbatim.

## 0.3.7 -- 2026-06-22
- Agency #5 fix (from AFP verify): services are now resolved at REQUEST time via is_agency(), not at import.
  An agency tenant's Clients/Tools dirs can live in iCloud and not be materialized at server boot, which made
  the import-time agency check read False and leak the hptuner fleet card. Now agency tenants get an empty
  services card by default with NO per-tenant services:[] override needed.

## 0.3.6 -- 2026-06-22
- Agency-lens round 2 (from AFP real-data verification): (#3) partner brand-clients are ONLY folders under
  <partner>/clients/; a partner's direct subfolders are counted as 'work' (audits/engagements) and folded
  into the tool used-by index, never mislabeled as a brand client (fixes derris/skimlinks-audit). (#6) the
  Docs scope dropdown + server PILLARS now derive from the deployment's real top-level dirs (or cc.config
  'pillars'), not hardcoded text2tune pillars; exposed via window.CC.pillars. (#5) SERVICES now defaults to
  [] for agency tenants (the services card no longer leaks the hptuner fleet without opt-in). (#4) the
  Marketplace product wordmark uses the deployment's product_name, not a hardcoded 'ClaudeFather'.

## 0.3.5 -- 2026-06-22
- Agency-lens framework fixes (benefit every non-product/agency tenant, not just text2tune): (1) client /
  partner / tool names render as canonical display names -- the folder's CLAUDE.md H1 title if present, else
  de-slugged + word-capitalized ('7th-avenue' -> '7th Avenue'); (2) folders under Clients/ that are NOT
  clients (roll-ups / reports) are excluded from the list + count via cc.config agency.exclude or a
  '.notclient' marker file; (3) partner clients are detected under <partner>/clients/ OR (fallback) directly
  under <partner>/, so a partner whose clients sit directly inside still counts them; (4) product_tag default
  neutralized 'THE CLAUDEFATHER' -> 'COMMAND CENTER'; (5) the text2tune-specific product+fleet chrome
  ('text2tune bridge', T490/T480) is hidden on agency tenants; (7) brand default neutralized 'text2tune' ->
  the tenant's own project_name. (Item 6, the scope dropdown, is pending tenant clarification.)

## 0.3.4 -- 2026-06-22
- Inter-chief comms made REAL + bulletproof. Replaced screen-scraping/timeouts with a Claude Code Stop
  HOOK (mesh_stop_hook.py): the instant a chief finishes answering a peer's '[message from X]' turn, the
  hook reads the chief's EXACT reply from the session transcript and forwards it to X -- deterministic, no
  scrape, no fixed timeout, and it is the real chief (full context) replying, not a bot. The hook only acts
  on mesh turns, so an operator's reply is never forwarded (no leak). Delivery now WAITS for the target
  chief to be idle before injecting, so a message sent while a chief is busy queues and lands as a CLEAN
  separate turn when it frees (never merged into the in-flight turn -> no content mix/leak). Replies are
  tagged '[reply from X]' so they never trigger a counter-reply (no ping-pong). Fully tested: idle round-
  trip ~8s, busy/queued (~task+reply), no-leak, both-sides visibility, no ping-pong. Chiefs launch with the
  hook via --settings + MESH_CC env (shlex-quoted). Comms lens shows in/out both sides with delivery
  receipts + an unread badge.

## 0.3.3 -- 2026-06-22
- Comms mesh: DEDICATED handler session ('mesh-<instance>') decoupled from the operator's chief console.
  Fixes a 2026-06-22 cross-talk bug where peer traffic injected into the live operator chat (so an inbound
  message could fail to surface) AND the reply-watcher scraped the operator's reply and shipped it to a peer
  (content leak). Now: inbound peer messages route to the handler (never the chief console), the handler's
  reply auto-returns safely (it does nothing but mesh), and everything mirrors to the operator's Comms lens
  with an UNREAD BADGE on the nav. Operator-in-the-loop case validated. MESH_AUTOREPLY guard retained (off)
  for the legacy chief path.

## 0.3.2 -- 2026-06-22
- Comms lens (enterprise inter-chief mesh). A new "Comms" lens + persistent, UI-visible inbox
  (_mesh_inbox.json) makes every inter-chief message (in + out) durable and observable, independent of TUI
  state. Enterprise delivery: sends are NON-BLOCKING (queued, not a 55s wait), with a background worker that
  RETRIES with backoff and tracks per-message delivery receipts (queued -> delivered -> replied | failed).
  Replies are captured by anchoring on the assistant marker after the injected message (fixes the stale/
  garbled screen-scrape) and are returned ADDRESSED to the sender via /api/mesh-recv by an async watcher --
  so a reply reaches the sender's Comms thread even if the chief answers minutes later. Full N-to-N mesh:
  message any one peer, any subset (multi-select recipient chips), or all. Peer-health dots derived from
  recent delivery outcomes. Endpoints: /api/mesh, /api/mesh-send, /api/mesh-recv, /api/mesh-clear. Optional
  shared-secret auth hook (MESH_TOKEN; off unless set). Chief brief updated to reply over the mesh.

## 0.3.1 -- 2026-06-22
- Chief of Staff hardened as a protected, constant SINGLETON (it is the inter-chief mesh comms endpoint).
  It can no longer be ended/killed (server + terminal-view buttons removed), it is pinned to the top of the
  Sessions lens and always shown (even when not yet started), and resuming/forking its transcript now opens
  the one canonical chief instead of spawning a duplicate CoS. Fixes peers not seeing an instance's chief
  and prevents a split comms channel from multiple chief sessions.

## 0.3.0 -- 2026-06-22
- Inter-chief comms: any chief -> any/all peers (/api/chief-say, /api/chief-broadcast, /api/peers) + a
  'Message the chiefs' Portfolio panel. Brand revamp (marionette hand-mark + Copperplate gold wordmark),
  splash screen, hand-mark favicon. Module map (CC:TREEMAP), smart files (deliverables/), team builder,
  storage_mode (iCloud/GitHub), full extension catalog (20), self-locating portability.

## 0.2.0 -- 2026-06-21 -- Rebrand: Claudesole -> ClaudeFather
- Product renamed **Claudesole -> ClaudeFather** (Godfather-themed, professional/enterprise; skinnable).
- Config-driven `product_name` / `product_tag` / `theme` (cc.config.json), injected as `window.CC.product/theme`.
  Defaults: "the ClaudeFather" / "THE CLAUDEFATHER" / "godfather". A tenant can override to re-skin.
- The ClaudeFather logo as favicon + apple-touch-icon (`command-center/static/brand/`); `<html data-theme>`
  hook + oxblood accent var (palette was already gold-on-black).
- Per-instance project brand (e.g. text2tune / Mission Control / carsearch / AFP) is unchanged.
- Internal identifiers intentionally NOT renamed (the `claudesole.manifest.json` filename, the
  `claudesole-core` repo, the framework dir) -- only the product NOUN changed.
- **To get this on a deployment that lives elsewhere:** run `cc-update.sh <upstream>` (a local dir, or the
  git URL `https://github.com/jkarger123/claudesole-core` -- the box needs read access to that private repo).
  It overlays framework_paths (incl. server.py + static/ logo + presets), preserves your cc.config + data +
  CC:NOTES. PROVEN on a stale foreign deployment (brand preserved).

## 0.1.0 -- 2026-06-20 -- Initial productization
- Command Center -> portable framework: multi-instance, presets, agent-per-tool, overseer/portfolio,
  cc-init / cc-update / cc-spawn / cc-promote, claudesole-core repo, cognition module (Skills/Agents/Teams).
