# ClaudeFather -- CHANGELOG

A deployment can compare its `claudesole.manifest.json` `version` against the upstream's (cc-update prints
both) to see if it is behind. Newest first.

## 0.99.176 -- 2026-07-06  (fix: the Ralph "live" tab now actually shows on the node)
- The live-iteration tab spawned but was INVISIBLE on a node (it showed only on the overseer): the node's
  session-scoping stripped "ralph-" and looked up "<loop>-live" as a loop (which doesn't exist) -> didn't claim
  it -> hid it. Now the `-live` suffix is stripped so the live tab shares its runner's owner. Both tabs now show.
- Made the live tab SELF-HEALING: `ralph_list` (every dashboard poll) now (re)spawns the live tab whenever the
  loop is running but its tab is missing, and reaps it when the runner is gone -- instead of only spawning once at
  launch. So a transient never leaves a running loop without its live tab for the rest of the run.

## 0.99.175 -- 2026-07-06  (cc-ralph: stop/restart verbs)
- `cc-ralph` gains `restart` / `halt` / `kill` / `pause` / `resume` (were: only new/launch/list). `restart <name>`
  stops a loop and relaunches it -- it resumes from its saved progress AND picks up the latest runner code (so an
  agent can move a loop onto the new live-iteration tab with one command). Thin wrappers over /api/ralph-control.

## 0.99.174 -- 2026-07-06  (Ralph: watch the current iteration LIVE in its own tab)
- Every Ralph loop now has a SECOND tab -- `ralph-<name>-live` -- that shows what the CURRENT iteration is doing,
  live (tool calls, edits, commands, the assistant's text, the result), and auto-refreshes each iteration. Tab 1
  stays the clean runner/control view; tab 2 is the live agent activity, exactly the two-tab split requested.
- How: the runner now invokes each iteration as `claude -p --verbose --output-format stream-json`, tees that event
  stream to `<loop>/live.jsonl` (reset per iteration), and keeps a compact one-line-per-event summary in its own
  pane. `ralph_live.py` follows that file and pretty-prints it in the live tab. The loop's anti-gaming/convergence
  logic is untouched (it never parsed stdout -- it counts progress.md + verify.py).
- The live tab spawns on launch, is reaped when the loop ends (any path), shows as "Ralph: <name> (live)" in
  Sessions, and each running/paused loop card gets a "watch live" button.

## 0.99.173 -- 2026-07-06  (Resilience: MCP / extension process-hygiene reaper -- every install self-cleans)
- **Self-healing reaper for leaked MCP servers.** Third-party Claude Desktop MCP extensions that don't exit on
  disconnect orphan to launchd and busy-spin; dozens pile up and wedge the machine (real case: 41 leaked "Sidekick
  for InDesign" servers = load 200 + ~5GB RAM on an idle laptop). Core now ships a CONSERVATIVE reaper (daemon
  `mcp_hygiene`, ~2 min) that kills only ORPHANED (ppid 1) + recognizably-MCP + stuck (>=5% CPU or >=120s)
  processes -- a live/attached session (real parent) is NEVER touched. Runs on every node that installs
  ClaudeFather. Opt out: cc.config `mcp_hygiene=false`.
- **Visibility:** Doctor + `/api/mcp-hygiene` show what was cleaned in 24h + anything leaking now, and name known
  offenders (Sidekick -> sidekick@eastpole.nl). Alerts once per pile-up (>=3) then re-arms, so a chronic leaker
  gets reported/updated instead of silently reaped forever. Trail: `_mcp_hygiene.log`.
- **Prevention for our own code:** AUTHORING.md now makes exit-on-stdin-EOF a HARD RULE for any first-party MCP
  server, so ours can never make this mistake. docs/RESILIENCE.md documents the whole thing.

## 0.99.172 -- 2026-07-06  (Video Studio: generate clips with AI -- Veo/Gemini, BYO-key)
- **Generate a video clip from a text prompt** (or animate a still) with AI, using the deployment's own vaulted
  key (Google Gemini -> Veo 3.1). Two entry points, exactly as asked:
  1. **Builder "Generate a clip with AI" card** -> describe a shot -> it generates an 8s clip and OPENS THE EDITOR
     with that clip loaded.
  2. **Editor "AI clip" button** -> generate a clip and it drops straight onto the current timeline.
- Landscape/Portrait + Fast/Best (Veo fast vs full). ~1-2 min, 720p with audio. Generated clips become normal
  timeline clips (trim/split/color/speed/etc.).
- **Provider-gated + BYO-key:** the AI controls only appear when a generative-video key is vaulted
  (`providers.resolve` -> `can_generate_video`); the key is resolved server-side from the vault and passed via env
  (never in argv/logs). New engine module `engine/generate.py`; routes `/api/studio/generate` + `/api/studio/tools`
  now reports provider status. Agent-drivable (AGENT.md updated).
- **Guardrail kept explicit:** generative video can't depict real people/children (provider policy) -> the UI says
  so; that's what the analytical editor is for.

## 0.99.171 -- 2026-07-06  (Video Studio: big-file uploads -- 8GB cap, warnings, progress %)
- **Upload cap for the studio raised to 8GB** (was 500MB) -- 4K / drone clips are big. A 2GB drone MP4 was
  silently rejected before; now it uploads. (Config: cc.config `studio_upload_mb`.)
- **Clear messages:** over the cap -> "<name> is 2.1GB -- over the 8GB limit, so it won't upload. Trim/compress
  first." Over 100MB but under cap -> a heads-up: "<name> is big (2.1GB); it'll upload, but delete the project
  when you're done to free that space."
- **Upload progress:** uploads now show a live % (XHR upload.onprogress) in the clip row / status line, so a big
  multi-minute upload clearly shows it's working instead of looking frozen.

## 0.99.170 -- 2026-07-06  (Video Studio: images, split/cut + timeline delete, upload cleanup, agent-drivable)
- **Images:** upload photos (jpg/png/webp/heic/...) alongside video. Each lands on the timeline at a default 5s
  and is trimmable either way to make it shorter/longer; renders as a held still (ffmpeg -loop). Shows in the live
  preview + bakes into MP4/CapCut.
- **Split / cut tool (Premiere-style):** a **Split** button (or press **S**) cuts the clip at the playhead into
  two. Two splits + delete the middle = cut a section out of the middle of a clip.
- **Timeline delete:** every selected clip gets an **x** to delete it right on the timeline, and **Delete/Backspace**
  removes the selected clip. Reflows automatically.
- **Free disk from uploaded clips:** deleting a project now also removes its uploaded source clips that no other
  project uses; a **Clean up unused uploads** button sweeps all orphaned uploads. (New /api/studio/cleanup-uploads;
  delete-project reports MB freed.)
- **Agent-drivable (like every extension):** added `AGENT.md` -- agents on any node with the extension now know how
  to build a finished video for a user (the one-shot `studio.py` CLI, the project/EDL model, CapCut export), so
  "generate a video from these clips + this song" is a first-class agent capability. Analytical only (no
  generative model on real people).

## 0.99.169 -- 2026-07-06  (Video Studio: fit-to-width timeline, wheel-zoom, delete projects + free disk)
- **Timeline fits its area by default** (no more stretching off-screen) -- opens at a zoom that fits the whole
  video into the panel width, with a **Fit** button to snap back.
- **Scroll-wheel over the timeline zooms** (centered on the cursor) instead of stretching/scrolling it off-screen;
  + / - buttons still work.
- **Delete old projects + free disk:** each item in "Recent projects" now has a trash button that removes the
  project's .json AND its whole media cache (filmstrips, copied music, proxies) from the server. New
  `/api/studio/delete-project` (guarded to the studio cache dir; reports MB freed). Finished MP4s live in Files
  and are deletable there.

## 0.99.168 -- 2026-07-06  (Video Studio: fix + Clip; live trim preview)
- **+ Clip now actually adds the clip.** The handler cleared the file input (`this.value=''`) BEFORE iterating the
  FileList, which empties it -> nothing uploaded. Now it copies the files to an array first. (Backend add-clip was
  always fine.)
- **Trim preview:** dragging a clip's left/right trim handle now shows that exact frame in the preview canvas live
  -- drag the in-handle and you see the new start frame; drag the out-handle and you see the new end frame -- so
  you can see precisely where the cut lands.

## 0.99.167 -- 2026-07-06  (Video Studio: smooth live-preview playback -- stop the black-out)
- The live-preview Play went black after a couple seconds because it SEEKED the source <video> every single frame
  (video.currentTime=... 60x/sec) -- seeking isn't built for playback, so the decoder fell behind and drew nothing.
- Now it PLAYS the active clip's <video> natively (smooth) and draws its current frame each rAF, seeking ONLY at
  clip boundaries; playbackRate=clip speed keeps slow-mo in sync; the playhead is clock-driven and music plays
  continuously. Plus prebuffer(): all source videos + the audio are .load()ed when a project opens so they're
  buffered ahead. (For a pixel-exact smooth pass with every effect baked, Preview/Export still render a proxy MP4.)

## 0.99.166 -- 2026-07-06  (Video Studio: fix "add media" + move beat-cut into the editor)
- **Critical fix: the whole Studio was non-interactive as a lens.** loadStudio grabbed the FIRST <script> in the
  embed page -- which is a tiny boot script (window.CC=...) injected before the real one -- so the studio JS never
  ran (add media / buttons did nothing). Now it concatenates ALL <script> blocks, so every handler binds. Add
  media, Start editing, and every editor control work.
- **Restructured per feedback:** the first screen is now just *add clips -> Start editing*. Beat auto-cut is no
  longer a big card up front -- it's a small **Beat-cut** toggle in the editor toolbar that re-cuts your current
  timeline clips to a song (paste a link / upload / or use the current audio track), so it's an option once you're
  editing, not an assumption.

## 0.99.165 -- 2026-07-05  (Video Studio: render as a proper full-width native lens)
- Fixed the "shoved to the left / doesn't feel native" problem. Root causes: (1) loadStudio rendered into #main
  (the flex SHELL that holds the nav) instead of #grid (the real content area every lens uses), so it became a
  squished flex child; (2) the tool's own container has class "wrap", which collided with the dashboard's global
  .wrap{display:grid}, forcing the tool into the dashboard's card-grid layout.
- Now renders into #grid, framed in the dashboard's own cc-head + a full-width cc-panel (grid-column:1/-1), with
  the tool's .wrap layout reset to block -- so it's full-width and looks/feels like a first-class lens (dashboard
  header, back/forward, search, help, gold theme).

## 0.99.164 -- 2026-07-05  (Video Studio: a real editor first + a native inline lens)
- **Reframed as a general editor, not a beat-cut tool.** The primary flow is now **Start editing** -> a timeline
  where you trim, crop, color-correct, reorder, add audio + titles + effects. Beat **Auto-cut** and CapCut export
  are clearly-labeled OPTIONAL extras (you no longer must supply music up front). New `project.py manual` mode +
  `/api/studio/new-manual` place your clips full-length on the timeline.
- **Add media inside the editor:** **+ Clip** (upload -> appended to the timeline; `/api/studio/add-clip`) and
  **+ Audio** (upload a track OR paste a YouTube link, whole or a section; `/api/studio/add-audio`).
- **Color correction + crop:** per-clip brightness / contrast / saturation (ffmpeg `eq`) and Fill-vs-Fit crop
  (`edl._segment`), live in the canvas preview (canvas filter) and baked into MP4 + CapCut exports.
- **Native inline lens (was an iframe).** Clicking Studio now renders the tool directly into the dashboard
  (`loadStudio` fetches the tool, scopes its CSS under `#studioHost` so it can never touch the rest of the
  dashboard, and runs its JS in an IIFE) -- so it's a first-class lens with the dashboard's back/forward, search,
  and help, in the gold theme. No more navigating out to a separate page.
- Fixed a crash opening a project with no audio track (`drawWave` assumed an audio clip existed).

## 0.99.163 -- 2026-07-05  (Video Studio: make it a NATIVE in-shell lens in the dashboard style)
- Fixed two real problems: the Studio tab (1) opened a separate page that navigated you OUT of the dashboard, and
  (2) used a blue theme that didn't match ClaudeFather's gold/dark design.
- Now a **native lens**: clicking Studio renders in-shell (a `cc-head` header + the tool embedded, the same way
  Sessions embeds the terminal /term) -- no navigation away. Recolored the tool to the dashboard palette
  (gold accent #c9a227, matching cards/lines/fonts); an `?embed=1` mode drops the tool's own header so the
  dashboard provides the section header. Added HELP.studio. The standalone /studio page still works as a deep link.

## 0.99.162 -- 2026-07-05  (Video Studio: pin the Studio tab top-level)
- The Studio nav tab landed in the collapsed "Team" category (easy to miss). Pinned "studio" in NAV_PINNED so it
  stays a top-level daily-driver tab wherever the ai-video-studio extension is installed. (Reminder: the dashboard
  is an SPA -- hard-refresh the tab after a restart, or a newly-installed lens won't show in an already-open tab.)

## 0.99.161 -- 2026-07-05  (Video Studio: multi-track / picture-in-picture -- the "didn't build" list, pt 2)
- **PiP / overlay track:** tap a clip -> **+ PiP** drops it on a new overlay lane, composited on top of the base
  video. Tap the PiP block to cycle **position** (TL/TR/BL/BR/center) + **size** (25/35/50/70%) or delete; drag it
  to retime. Renders via `filter_complex overlay` (new `edl._pip_segment` + an overlay pass) and composites live
  in the canvas preview too. This is the "insert stuff" / multi-track piece.
- 3 of the 4 "deliberately didn't build" items now shipped: real-time preview (160), direct drag-trim (160),
  multi-track/PiP (161). The 4th -- a CapCut-verified `draft_content.json` -- is gated on testing against a real
  CapCut install (can't be done headlessly); the reliable clips + EDIT_PLAN export already covers the workflow.

## 0.99.160 -- 2026-07-05  (Video Studio: direct drag-manipulation + live preview -- the "didn't build" list, pt 1)
- **Drag manipulation** (was inspector-steppers only): select a clip -> drag its edge **handles to trim** in/out
  live; **drag impact/zoom pins** and **title blocks** to reposition (beat-snapped, tap still opens the menu);
  **scrub the ruler** by dragging the playhead. Pointer events -> works on touch + mouse.
- **Live preview compositor** (was proxy-render only): a real Canvas + `<video>` + WebAudio engine composites the
  frame at the playhead -- footage + zoom + flash + titles -- as you scrub, and a **Play** button plays it through
  with the music. (Considered but rejected for this: ffmpeg.wasm = 25MB + 5-20x slower + no HW accel; Etro/Omniclip
  need a build step our no-build embedded page can't use -- a focused vanilla compositor fits and is faster.) The
  proxy/Export render remains the pixel-exact smooth output; the canvas is the instant scrub/rough-play preview.
- Still on the list (next): multi-track / picture-in-picture compositing, and a verified CapCut draft via the
  Apache-2.0 pyJianYingDraft schema (replacing the hand-rolled draft_content.json).

## 0.99.159 -- 2026-07-05  (Video Studio P5: media-tools bootstrap -> renders on every node)
- Video Studio needs static **ffmpeg/ffprobe/yt-dlp** in the node's `bin/` (node-local, not shipped in the
  framework -- ~110MB of binaries don't belong in git). Until now Studio only rendered on the build Mac.
- **Bootstrap:** on the first render/build/export, if those binaries are missing, the node now downloads them
  ONCE from stable sources (ffmpeg/ffprobe: martin-riedl.de static macOS build; yt-dlp: its GitHub release) into
  `bin/`, with a "installing... (one-time)" job status. A fast no-op where they already exist. So Studio now works
  on ANY macOS fleet node, not just here -- the packaged-product goal. Fails cleanly (clear error) with no network.
- `GET /api/studio/tools` reports whether the media tools are present (diagnostics/Doctor).
- Video Studio P1-P5 COMPLETE: auto-build -> timeline editor -> MP4 + CapCut export, renderable fleet-wide.

## 0.99.158 -- 2026-07-05  (Video Studio P4: CapCut export)
- **Export -> CapCut** button in the editor. Produces a zip (lands in Files) with, most-reliable-first:
  `clips/clip_NN.mp4` (every cut, in order, speed baked in, normalized to canvas) + `music.mp3` +
  `EDIT_PLAN.txt` (clip order/durations, flash + zoom times, titles) -- drop the clips into any CapCut template
  on the beat (CapCut auto-fits) and follow the plan. Plus an EXPERIMENTAL `draft_content.json`
  (pyJianYingDraft-style, microsecond timeranges) to try opening the draft directly. Honest: the clips+plan
  always work; the auto-draft may need CapCut-version tweaks (README in the zip explains both).
- NEW `engine/capcut.py` (`export(project, out.zip)`); server `/api/studio/export-capcut` (background job);
  the zip downloads via the Range media route (application/zip).
- Video Studio now covers P1-P4: auto-build -> timeline editor (trim/speed/reorder/flash/zoom/titles) -> MP4
  export + CapCut export. Remaining: P5 packaging (distribute the ffmpeg/yt-dlp binaries so every node renders).

## 0.99.157 -- 2026-07-05  (Video Studio P3: titles, zoom, cleaner auto-build)
- **Titles track:** add a title (+Title button or tap the titles lane), tap a title to edit/delete. Burns in over
  the video (white text + box, top-third). Renders via the existing drawtext path.
- **Zoom punch effect:** add from a clip's inspector (or it shares the impacts lane). A scale/crop zoom-in on the
  beat (scale eval=frame -> time-varying, then fixed crop). New `edl.apply_zooms`; the impacts lane shows flash
  pins (amber) vs zoom pins (violet).
- **Cleaner auto-build:** cuts now target a LENGTH by pace (frantic ~0.55s / punchy ~0.95s / cinematic ~1.7s)
  instead of a fixed beat count -- no more 0.5s machine-gun when the tempo detector doubles (a 13s song went from
  ~23 choppy cuts to ~12). Cut boundaries still snap to beats.
- **In-point clamp:** a clip's trim never runs past its source end anymore (was silently truncating cuts near a
  short clip's tail, shrinking the final video); render duration now matches the timeline.
- Clip inspector: trim in/out, speed (0.4/0.5/1/2x), reorder, flash, zoom, delete -- all live on mobile + desktop.

## 0.99.156 -- 2026-07-05  (Video Studio P2: the manual timeline editor)
- Auto-build now produces a SAVED, editable **project** (not just an MP4) and drops you into a real timeline
  editor. Fine-tune, then Preview (fast 480p proxy) or Export (full MP4 to Files).
- **Timeline UI** (mobile + desktop, in the /studio page): a time ruler with the song's **beat grid**, a video
  track of clip blocks with **filmstrip thumbnails**, an **impacts lane** (tap to add a beat-snapped flash; tap a
  pin to toggle big / delete), and a **waveform** music track. Tap a clip -> an inspector to trim in/out, set
  speed (0.4x/0.5x/1x/2x slow-mo), reorder, add a flash, or delete. Zoom in/out; Save; reopen recent projects.
- The editor edits the SAME project/EDL JSON the renderer consumes -- edits reflow the cut and re-render exactly.
- Engine: NEW `project.py` (`emit` = build + save project + per-source **filmstrip sprites** + a music
  **waveform**; self-contained -- copies the resolved music into the project cache). `edl.py` gains `--proxy`.
- Server: `/api/studio/{build-project,render-project,project,project-save,projects}`; the Range media route now
  also serves the project cache (thumbnails/waveform/music). Projects + cache live on the SSD (`_studio/`).
- Next: effects/text lanes polish (P3), CapCut-draft export (P4), packaging incl. per-node media binaries (P5).

## 0.99.155 -- 2026-07-05  (Video Studio P1: auto-build a beat-synced video from clips + a song)
- NEW **Video Studio** -- a built-in video editor (Phase 1: one-tap Auto-build). Drop in clips, add music (upload
  a track or paste a YouTube link + optional section), pick a pace, and it beat-detects the song, motion-detects
  the clips, cuts every cut onto a beat, slow-mos the finisher, fires impact flashes on the big hits, and renders
  an MP4 that lands in the Files lens. Works on real family footage -- analytical editing (no generative model,
  so no child-safety block); runs on the bundled ffmpeg, no API key required.
- Opens as a dedicated **/studio** page (the /term /ralph pattern), mobile + desktop; a **Studio** nav tab appears
  when the `ai-video-studio` extension is installed. Foundation for the full multi-track timeline editor (mark
  points, trim, insert, effects lanes, CapCut-draft export) landing in later phases.
- Engine (`extensions/ai-video-studio/engine/`): NEW `edl.py` renders one shared project/EDL JSON -> MP4 (the
  single source of truth the auto-build, the coming timeline, and a CapCut exporter all speak);
  `autocut.build_project()` emits that project; `music.py` hardened (retry + full-download-then-local-trim
  fallback so YouTube's intermittent range-fetch 403s don't kill a render).
- Server (`server.py`): `/studio` page + `/api/studio/{render,job,upload,media}` routes; a background
  `threading.Thread` render-job worker (never blocks the request); a NEW HTTP **Range/206** media route so
  `<video>` can seek renders (the whole-file `/api/file-get` can't). NOTE: rendering needs the node's `bin/`
  media tools (ffmpeg/yt-dlp); binary distribution to every node is a later-phase packaging item.

## 0.99.154 -- 2026-07-05  (Attach cap: /term now uses the real 500MB limit, not the 50MB fallback)
- 0.99.153 raised the upload cap to 500MB, but the terminal attach still rejected anything over 50MB: the `/term`
  page is served as a standalone string with NO `window.CC` bootstrap (only the main dashboard PAGE gets it), so
  `TMAXMB=(window.CC&&window.CC.maxUploadMb)||50` fell through to the hardcoded 50. FIX: `/term` now injects a tiny
  `window.CC` (real `maxUploadMb` from config + protectedSessions + chiefSession) so the attach uses the true cap;
  client fallback bumped 50->500 to match the server default.

## 0.99.153 -- 2026-07-05  (Session file attach: streaming upload -- videos + mobile now work)
- The terminal attach (📎 / drag-drop) used to base64-encode the whole file in the browser then POST it as JSON.
  On mobile Safari that silently OOMs on ANY video (even a 6s clip) -> the picker "prepared" the file then did
  nothing, and the only error went to a status pill invisible on phones. FIX: new **`/api/session-upload-raw`**
  streams the File body straight to disk in 1MB chunks (no base64, nothing whole in memory, browser OR server);
  the client now sends the File directly and shows a **visible centered toast** for uploading/attached/too-big/
  failed. iOS picker hardened (persistent offscreen input w/ accept, not a display:none throwaway). Default upload
  cap raised 50MB -> **500MB** (safe now that it streams to disk; `max_upload_mb` still overrides). Desktop
  drag-drop uses the same streaming path.

## 0.99.152 -- 2026-07-05  (Edge MCP: Sidekick/InDesign driving lessons made standard-issue)
- Baked the hard-won Sidekick/InDesign driving knowledge into `extensions/edge-mcp/AGENT.md` so no future
  install relearns it the slow way. Corrected the misleading "long ops are fine / no micro-batch" note: the
  600s transport timeout is real, but a `plugin-app` (Sidekick/InDesign) has its OWN ~30s response cap -- a
  long script returns "Plugin response timeout" while it keeps running, so long ops must **fire-and-poll** a
  completion marker. Added the InDesign rules that cost real hours: `snapshot` is ~72dpi (rough layout ONLY --
  export a 200dpi raster to verify color/opacity/edges); export path must be a plain string in a real user
  folder (UXP File / InDesign File / /tmp all fail -- sandbox); every script must set `NEVER_INTERACT` or a
  modal freezes the engine; `snapshot` renders `app.activeDocument` (set it first); no remote screen capture
  (macOS TCC); UXP enum-identity (`String(page.side)`) + reduced-opacity-image (bake watermarks flat) gotchas.
- `edge-mcp` CLI: added first-class `sh` / `pull` / `push` / `host-key` so the host shell+scp workflow (pull an
  export back to inspect, push an asset up) is a documented command instead of hunting for `edge_key_*.pem`
  under `/var/folders`.

## 0.99.151 -- 2026-07-04  (Auto-nudge: a paused/stale Ralph loop no longer suppresses nudges forever)
- Fix: `waiting_on_loop` (auto-nudge's "don't nudge a session that's waiting on a loop" guard) suppressed a
  session's nudges whenever ANY same-project Ralph loop's tmux was alive and its state wasn't one of
  done/halted/stopped/stalled -- so a **paused**, **blocked**, or hours-**stale** loop (even one the session never
  launched, notify_session=None) silently muted an armed chief's nudges indefinitely. Now suppression requires the
  loop to be genuinely IN FLIGHT: `state == "running"` AND its status advanced within `_LOOP_FRESH_SEC` (30 min);
  a paused/finished/blocked/stalled or wedged-"running" loop releases the nudge. Found live on an armed CoS that
  had a paused emulator loop in its project. NOTE: a running auto-nudge loop holds old code -- it picks up this fix
  when its process restarts (lazy-restarts on next arm, or restart `cc-autonudge loop`).

## 0.99.150 -- 2026-07-04  (Add-a-ClaudeFather: choose which macOS account hosts the node)
- The "Add a ClaudeFather" wizard now has a **Run as user** picker (populated from the box's real local
  accounts via `/api/host-users`). **This account** -> created & started automatically as today. **Another
  account** (e.g. `sarahaios`) -> the bundle is staged on the shared `noowners` SSD (so that account can run
  it), and the result hands back the exact two commands to run in THAT account's own login session (launch +
  optional launchd-persist), each with a Copy button, plus the login token. This mirrors how the `afp`
  (sarahaios) node is hosted -- the platform can't launch/persist as another user (no TTY/sudo across accounts),
  so it does everything it can and cleanly hands off the one step it can't. `--user` was already plumbed through
  the engine; it only affected a hint before.

## 0.99.149 -- 2026-07-04  (Add-a-ClaudeFather: show the new node's access token with a Copy button)
- The "Add a ClaudeFather" result now surfaces the **per-node access token** (minted at birth) in a prominent
  callout with a **Copy token** button and a clear message: copy it now, you enter it the moment the new
  dashboard opens, then you can reset it in Settings -> Login token. Previously the UI wrongly said "no token
  yet -- the dashboard will ask you to set your own", so the operator hit an unexpected token prompt with
  nothing to paste. The token was always returned by the engine (`CC_NEWINSTANCE_JSON.auth_token`); the UI just
  discarded it. Also corrected a stale "new nodes start open" code comment (they mint a token at birth).
- Terminal **auto-reconnect** (rode into 0.99.148): the `/term` view and the Ralph-loop viewer now silently
  reconnect through a server restart (~5-9s) instead of freezing on "detached" until a manual refresh.

## 0.99.148 -- 2026-07-04  (Edge MCP Host: run remote-computer MCP servers over the mesh, transparently)
- NEW core extension **Edge MCP Host** (`extensions/edge-mcp/`, v1.0.0): run MCP servers that must live on a
  user's OWN computer -- GUI apps (Adobe InDesign/Photoshop/Blender), their real logged-in browser, local
  files/devices -- and drive them from ClaudeFather over the Tailscale mesh (no remote desktop). Vault-keyed
  SSH transport, a warm daemon that keeps the session hot, and a transparency proxy that logs every tool call.
  Recipes: `plugin-app` (app + in-app plugin, e.g. Sidekick/InDesign) and `browser-attach` (the user's real
  Chrome). `edge-mcp` CLI (hosts/servers/start/status/call/run/probe/stop + add-host/add-server with vault key
  mint + Mac/Windows authorize snippets). Proven at scale (built a 356-page InDesign book through it).
- Edge MCP **dashboard lens**: hosts (reachable/asleep), servers (warm/cold), and a live transparency-proxy
  activity feed. Read-only `/api/edge-mcp/lens`.
- Sessions now launch with **`--mcp-config`** so extension-wired MCP servers reach every interactive work
  session as native tools regardless of cwd (previously only sessions rooted at DEPLOY_ROOT saw `.mcp.json`).

## 0.99.147 -- 2026-07-04  (every session-injector defers to a running compact -- consistent coordination)
- Shared coordination signal: the graceful-auto-compact lock ("running") is now honored by EVERY autonomous thing
  that types into a session, not just auto-nudge:
  - `_mesh_deliver` (ralph-notify, mesh replies, Slack/Telegram, superadmin) waits out a running compact instead of
    grabbing the post-HANDOFF_DONE idle window and breaking the /compact.
  - the API-error watchdog (cc-session-watchdog) skips nudging a session mid-compact.
  So the compact worker cleanly OWNS the input box; nothing else fights it. (auto-nudge already did this in .145.)

## 0.99.146 -- 2026-07-04  (Ralph notifications work however the loop was launched)
- Ralph loop notifications no longer depend on launch-time wiring: (1) the runner DERIVES the notify URL from the
  node config when CC_NOTIFY isn't in its env (a loop run directly, not via /api/ralph-launch, still notifies), and
  (2) the server falls back to the project's CHIEF (cwd match, realpath-normalized) when a loop has no recorded
  notify_session. Fixes iteration/completion pings silently going nowhere for agent-launched loops.
- realpath-normalized the same-project cwd match (auto-nudge waiting_on_loop + the notify target), so /tmp vs
  /private/tmp and other symlinked roots match correctly.

## 0.99.145 -- 2026-07-04  (Ralph loop notifications + auto-nudge coordination; auto-nudge is now fleet-clean)
- Ralph loops now PING the session that started them: on COMPLETION (as before) and after EACH ITERATION (new --
  "finished iteration N: checked M new item(s) (Y/Z done), next: ..."). Runner `_notify`/`_notify_iteration` +
  server `ralph_notify(body)` branches on kind (iteration=per-pass, complete=idempotent). Per-loop `notify_iters`
  (default on). Dashboard-created loops now ping the Chief of Staff.
- Auto-nudge no longer fights the things it shouldn't: it SKIPS a session that (a) is watching a running Ralph loop
  (explicit notify_session link OR same-project cwd match -- works even for loops with no recorded launcher) or
  (b) is mid graceful auto-compact (compact-lock state). Skip guards are tail-scoped (the live prompt only, not
  message prose) so mentioning "compaction"/"usage" no longer blocks a real nudge.
- Auto-nudge is now fleet-clean: arming a session lazy-starts the loop (pidfile-guarded, no duplicates), so the
  dashboard toggle is never a dead button on a fresh node. Ships cc-autonudge.py + cc-ralph + the module doc.
- Preship now has a PAGE-JS syntax gate (node --check every inline dashboard <script>) -- catches the unescaped-
  apostrophe class that broke v0.99.144 before it can ship again.
- Genericized the illustrative tenant residue across ~40 framework files via the hybrid convention (generic
  placeholders for paths/IDs, a fictional "Acme"/"Robin" only where a concrete example teaches). Scrubbed: 12
  product docs, 16 agent-charter + extension + install docs, 2 dense docs (security ROTATION_CHECKLIST + the engine
  module CLAUDE.md -- every procedure step + engineering learning preserved verbatim), ~10 code files (comments/
  docstrings only). server.py: neutral brand default (ClaudeFather, still replaced live by the tenant's cc.config
  brand), genericized user-facing help copy, and config-drove the last functional bits (PROJECT fallback, new-bundle
  dest -> cc.config "bundle_root", disk gauge -> cc.config "extra_disks", protected-session checks -> exposed
  protectedSessions). Also removed 2 internal planning/handoff docs from the ship surface (Phase 2).
- VERIFIED lose-nothing: master renders identically (brand text2tune, SSD in the disk gauge), ralph loops alive, all
  path derivations resolve to the same values, every syntax check passes. Residue 213 -> 47 (remaining = server.py
  internal code comments + selftest fixture names, gated by residue_lint for a final mop-up).

## 0.99.143 -- 2026-07-03  (clean-core Phase 4a: functional path hardcodes -> derived-from-location)
- Scrubbed the remaining HARDCODED tenant PATHS from framework scripts so a renamed/relocated tenant works, not
  just an install literally at ~/hptuners-control: ralph_runner (loop dir), git-backup.sh + git-backup-secretscan
  (repo/CC/log from cc.config + script location), security scan.py (repo + ralph dir), and the CC_HOME fallbacks in
  cf-key-backup/restore, make-install-package, install_gate/scanners. Each now derives its base from the script's
  OWN location (or cc.config), with a fallback that resolves IDENTICALLY on the master. VERIFIED lose-nothing: ralph
  loop dir, backup REPO, scan _project_root all resolve to the exact same paths as before. Residue 227 -> 213.
- Remaining residue (213) is illustrative-only: shipped-doc examples, code comments, and multi-tenant UI copy --
  Phase 4b, gated by residue_lint so it can only shrink.

## 0.99.142 -- 2026-07-03  (clean-core: residue gate excludes the changelog + linters)
- Follow-up to .141: the residue gate flagged docs/CHANGELOG.md (and preship.py's own gate message) because they
  NAME tenant terms by design -- the changelog narrates tenant work on every ship, so gating on it self-blocks.
  Excluded the changelog + the two linter files from the residue scan; re-baselined to 227 real code/doc hits.
  The product-changelog strategy (ship a clean one vs the tenant-narrated one) is tracked as clean-core Phase 4.

## 0.99.141 -- 2026-07-03  (clean-core Phase 1+3: engine portability + a tenant-residue ship gate)
- **Engine portability (Phase 1):** made the last hardcoded TENANT values config-driven so a fresh node boots
  NEUTRAL instead of inheriting hptuners/text2tune defaults -- pillar list, project-path fallback, ssh user, the
  text2tune bridge/edge health probes (now cc.config "product_health"), the default services list, protected
  session names, and name fallbacks. The master keeps its behavior by declaring these in its own (never-shipped)
  cc.config; other instances now come up blank. Verified: overseer boots pillars=[] while hptuners is unchanged.
- **platform_map.json off the ship surface:** it was static tenant STATE in framework_paths -- shipped to every
  node (leaking our component map) AND clobbering each tenant's own map on update. Removed from framework_paths;
  /api/platform-map already degrades to empty. (-132 residue hits.)
- **Residue ship-gate (Phase 3):** new command-center/residue_lint.py + a preship gate that FAILS the ship if a
  framework file gains NEW tenant residue (hptuners/text2tune/carsearch/Sarah/...). Ratchet model with a baseline
  (339 hits today) that only moves DOWN toward 0 -- so the clean-core cleanup can't silently regress. Remaining
  residue is comments + docs + CHANGELOG + multi-tenant example copy (Phases 2/4, tracked by the gate).

## 0.99.140 -- 2026-07-03  (node-builder git-init + stale-CCR auto-detect)
- **Node-builder git-init (CCR from shopos):** cc-newinstance.sh + cc-init.sh now git-init the project repo (starter
  .gitignore + a "node scaffolded" baseline commit) AND the central deliverables store (its own repo, versioned docs)
  at instance creation, so every node is BORN with a diff/rollback baseline instead of hand-initializing mid-work.
  Guarded on `command-v git` so a git-less box still scaffolds; the starter project CLAUDE.md now orients agents that
  deliverables/ is a separate git repo (commit docs there, not the project repo).
- **Stale-CCR auto-detect:** the CCR queue now flags open CCRs whose named code CHANGED in git since they were filed
  ("possibly addressed -- verify + likely close"), so a shipped-but-not-closed CCR gets caught instead of re-worked
  (we found 4 by hand this week). `_ccr_staleness` + `ccr_recheck()` + POST /api/ccr-recheck + a "Re-scan for
  already-done" button + a gold pill on the card. Churn-capped (>30 commits on a file = high-churn like server.py, not
  signal) so it doesn't cry wolf on every CCR that merely names the big file.

## 0.99.139 -- 2026-07-03  (Ralph loops: stop the relaunch churn -- CCR ccr-1783114463894)
- A finished Ralph loop, when re-invoked by some external trigger, was burning a full agent turn + the ~2min
  verifier before exiting, because the completion check was gated on n>START. Two fixes (from an hptuner-node CCR,
  auto-reviewed PASS): (A) `ralph_runner.py` checks is_complete() UNCONDITIONALLY at the top of the loop -> a done
  loop exits instantly on relaunch (safe: is_complete requires total>0 AND unchecked==0 (+capstone), so a fresh loop
  never false-completes); (B) `ralph_launch` no-ops a finished loop (runner marked done + progress has no unchecked)
  -> the relaunch trigger becomes harmless. Either ends the churn; both make it robust.
- Deliberately did NOT auto-archive-on-completion (the CCR's fix C): archiving needs operator review of the final
  report first, so that stays operator-driven (can be an opt-in later). A+B fix the waste without changing the
  review workflow.

## 0.99.138 -- 2026-07-03  (Claude Code capability catalog: refreshed + a when/why decision layer + surfaced to agents)
- We DID have docs/CLAUDE_CODE_REFERENCE.md, but it was 13 days stale (zero workflow/ultracode coverage, thin --agent),
  a "what exists" reference with no "when/why to reach for it", and not surfaced to agents. Fixed: added **section 14
  "Capability -> WHEN/WHY to reach for it (ClaudeFather playbook)"** -- the decision layer (one bounded expert answer
  -> _agent_run; MANY agents to be comprehensive/confident -> a dynamic workflow/ultracode; recurring -> skill/agent-
  tool; hard rule -> hook; external -> MCP) + the three agent tiers + where CF wires specialists into its lifecycle
  (and where it deliberately doesn't). Also refreshed the cheat-sheet.
- **Surfaced to agents:** the launch capabilities-brief now names the cc-review/cc-vitals/cc-email CLIs, the Agent Lab,
  `_agent_run`, and dynamic workflows, and points at the when/why guide -- so an agent knows these powers exist and
  when to reach for each, instead of rediscovering them.

## 0.99.137 -- 2026-07-03  (AI incident triage on loud failures + opt-in weekly security beat)
- **AI incident triage:** a loud failure no longer just says "X broke" -- `_incident(source, summary, detail)`
  records it and (async, deduped 30min) has `incident-scanner` triage it into the likely cause + the single
  highest-value next action. Wired into the real failure points: vitals warn/critical (generalizes the earlier
  auto-diagnosis), the fleet watchdog killing a wedged node, and a scheduled routine failing. Surfaced in a new
  **Incidents panel in the Server lens** + `/api/incidents`. Advisory -- it explains, never auto-acts.
- **Security beat (opt-in `security_beat`):** a weekly `security-auditor` posture sweep over the install (repo +
  config) for drift the static Doctor checks miss (exposed secrets, auth off, world-readable creds); a HIGH finding
  raises an incident. Off by default.
- Deliberately DROPPED the "scheduled cost digest" candidate as redundant -- the Usage lens + account fuel-gauges +
  Morning Brief already cover spend; an AI cost digest there would be noise, not power.

## 0.99.136 -- 2026-07-03  (Change-review gate: the platform reviews its own changes before they hit the fleet)
- The first deep core use of the _agent_run specialist primitive. `_review_change(diff|proposal, deep=)` runs
  code-reviewer (deep=+security-auditor, in PARALLEL -- a mini review workflow) over a change BEFORE it propagates,
  reading the REAL repo (new `cwd` param on _agent_run) for context; returns a VERDICT (PASS/CONCERNS/BLOCK). ADVISORY,
  never a hard gate.
- **`cc-review` CLI**: reviews `git diff HEAD` (--deep, --staged); exit 2 on BLOCK so a ship script / autonomous job
  can gate. **CCR intake auto-review**: a node's proposal is auto-assessed on submit (off-thread, concurrency-bounded)
  and the verdict surfaces on the CCR card -- vetting semi-trusted node changes before MC implements them. `/api/review-diff`.
- DOGFOODED: the gate reviewed its OWN implementation and caught (1) a real parser bug (first-vs-last VERDICT), (2) a
  prompt-injection vector (a submitted diff/CCR could try to coerce a PASS) + that calling it a "GATE" overstated its
  authority, (3) missing dedup + a swallowed exception -- all fixed here (last-verdict parse, untrusted-content prompt
  framing, a review semaphore + logging, honest advisory wording). The change-review gate improving its own code is the point.

## 0.99.135 -- 2026-07-03  (Experimental category + Agent Lab + _agent_run primitive + resilience auto-diagnosis)
- **New "Experimental" nav category** -- a staging area for features being worked out; they graduate into core or
  ship as an extension once proven.
- **`_agent_run(agent, prompt, model=None)`** -- run a NAMED Claude Code subagent headless on the node SUBSCRIPTION
  via `claude -p --agent <a> --output-format json` -> {ok, result, cost, ms}. Validates the agent, obeys the `smart`
  toggle, never raises, uses each agent's own configured model unless one is passed. `_subagents_available()` lists
  the installed specialists. (Built via an ultracode workflow: 2 codegen agents + a review pass.)
- **Agent Lab lens** (Experimental): run a specialist as a one-shot function, OR a **Panel** -- several specialists
  on the SAME task in parallel, side by side (a dynamic mini-workflow). `/api/lab-agents` + `/api/lab-run`.
- **Resilience auto-diagnosis:** the vitals monitor now fires `incident-scanner` (non-blocking, once per episode on
  the first warn/critical) to auto-explain a resource spike, persisting the read to `_vitals_diagnosis.json`.
- Review fixes applied: namespaced routes (avoid the existing /api/agent-run), optional model, injection-safe
  attribute escaping, @keyframes spin. Verified: both endpoints + the lens headless.

## 0.99.134 -- 2026-07-03  (Server lens graph: fixed axes + y-axis labels)
- The history charts now use FIXED axes instead of auto-ranging (which made small wiggles look dramatic and made
  the scale jump around): **utilization pinned 0-100%**, **temperature pinned 80-220°F** (idle-to-throttle range).
  Both charts gained left-edge **y-axis labels** (100/50/0% and 220/150/80°) so the scale is explicit. Temps that
  sit at ~110°F now honestly read as low on the axis, not filling the chart.

## 0.99.133 -- 2026-07-03  (Server lens: CONTINUOUS metrics history -- records always, not just while watching)
- The graph now draws from a PERSISTED machine record instead of a client-only buffer that vanished when you left
  the tab. A background daemon (`_metrics_sample_loop`) records one light sample/minute -- load, CPU%, memory%,
  CPU/GPU degF, watts -- FOREVER, deduped across the co-located nodes by shared-file freshness (~one sample/min
  total regardless of node count) to a tiny shared ring buffer (`/Users/Shared/claudefather-metrics/history.json`,
  ~3 days / ~200KB). Cost: ~1s of work per minute -- negligible. New `/api/metrics-history?range=` (downsampled to
  ~200 pts). The History panel gains a **range picker (1h / 6h / 24h / 3d)** so you can look back at trends -- a
  spike or a climb -- even if no one was watching when it happened. Everything still in Fahrenheit.

## 0.99.132 -- 2026-07-03  (Server lens: live CF-themed graphs + Fahrenheit)
- Added a **Live** panel to the Server lens: two beautiful CF-themed SVG charts (gold/azure/orange/teal, gradient
  area fills, grid, legends, current-value dots) tracking the last ~6 min -- **CPU % + Memory %** on one, **CPU +
  GPU temperature** on the other. Client-side rolling history (72 x 5s samples), no charting library, redraws each
  poll. **All temperatures are now shown in Fahrenheit** across the lens (KPI chip, thermal line, and the graph).

## 0.99.131 -- 2026-07-03  (Server lens: live CPU/GPU temperature + power -- sudoless, via macmon)
- The Server lens now shows REAL SoC temperatures (CPU + GPU degC) and power draw (total / cpu / gpu watts),
  read sudolessly from the Apple Silicon sensors via `macmon` -- no root daemon, no sudo helper. `_server_metrics()`
  reads `macmon pipe` best-effort (falls back to thermal-pressure-only where macmon isn't installed). The Temp KPI
  outlines red past 95degC. macmon is a static binary (pulled from the Homebrew bottle registry to /opt/homebrew/bin);
  a future install-time auto-fetch would give every Mac node live temps by construction.

## 0.99.130 -- 2026-07-03  (Resilience phase 2: external watchdog + a Server metrics lens + agent awareness)
- **Server lens** (Mission Control + every node, System category): whole-machine metrics so the operator can
  VISUALLY confirm nothing's running away -- load vs cores, CPU (user/sys/idle), memory, disk per volume, thermal
  PRESSURE, the heaviest processes (a runaway pegging cores is obvious), and every co-located CC node's OWN vitals
  (fds/threads/cpu/level). Refreshes every 5s. `_server_metrics()` + `/api/server-metrics`. (Exact CPU/GPU degC
  needs a sudo helper on macOS; thermal pressure -- the throttling signal -- is shown without one.)
- **External watchdog (phase 2, overseer-only `_fleet_watchdog_loop`):** the in-process monitor self-heals a node
  that can still run its own thread; this catches what it can't -- a node CRITICAL/degraded and NOT recovering, or
  a ZOMBIE pegging >300% CPU while unreachable. After ~3 bad checks (self-heal gets first crack) it kills the wedged
  PID for a clean supervised respawn, **then verifies the respawn took** (the gap that let the original zombie
  survive every restart); alerts + `_watchdog.log`; cross-user (AFP) surfaced for a superadmin restart.
- **Agent awareness:** the capabilities brief every chief/agent launches with now states the platform self-monitors
  + self-heals -- so a DEGRADED banner or an empty list is the immune system, not their bug -- and points to the
  Server lens / `GET /api/vitals?dump=1` / the new **`cc-vitals`** CLI (this-node / `server` / `dump`). See docs/RESILIENCE.md.

## 0.99.129 -- 2026-07-03  (CORE RESILIENCE: a self-healing immune system so a node can never silently drown again)
- Post-mortem of a self-inflicted outage (an 11-core zombie server ran 6h unchecked; another EXHAUSTED its file
  descriptors -> tmux calls failed -> /api/sessions returned a silent empty list -> the operator's chief looked
  "gone"). Root failure: no immune system. Built one into the core (`command-center/server.py`, "CORE RESILIENCE"
  block + `_vitals_loop` daemon; full write-up docs/RESILIENCE.md):
  - **Raise the ceilings:** `_raise_fd_limit()` lifts RLIMIT_NOFILE from the ~256 launchd default to **65,536** at
    boot -- the exact fd-wedge becomes effectively impossible.
  - **Watch our own vitals:** `_vitals_loop` samples fds / threads / self-CPU% / child-procs every ~45s. WARN ->
    log LOUD + notify the operator; CRITICAL twice -> **self-heal** (shed leaked tmux-attach children, clean
    supervised restart; loop-guarded). Symptom-based -> a 1080%-CPU zombie trips it at ~90s, not 6 hours.
  - **Fail LOUD:** `tmux_sessions()` distinguishes "no sessions" from "the call FAILED" -> marks the node DEGRADED
    (never a silent empty list again); an EMFILE reason self-heals immediately.
  - **Smoking gun:** `_thread_dump()` records every thread's stack at self-heal + on demand (`_vitals_stacks.log`) --
    so the NEXT runaway's exact hot loop is captured (this one's wasn't; we could only infer a spinning handler).
  - **Surfaced:** `/api/health` carries vitals+degraded; new `/api/vitals?dump=1` captures a live runaway; Doctor
    flags resource pressure; a can't-miss dashboard banner shows on degraded/critical.
- Phase 2 (documented, RESILIENCE.md): external watchdog + restart-verification for a process too wedged to self-heal.

## 0.99.128 -- 2026-07-02  (Fix: restarts no longer trigger a full transcript rescan -- Usage/Sessions slowdown)
- **Root cause of "usage/sessions load really slow":** the token-scan cache (`_TOK_STATE`) was memory-only,
  so EVERY server restart re-scanned the whole transcript store from byte 0 (1.7GB / 12.4k .jsonl files on
  the Studio) -- and co-located instances share one store, so each trio restart tripled it. Today's ship
  cadence (5 restarts) made the latent gap acute: /api/usage blocked 30s+ and the overseer pinned CPU.
- **Fix:** `_TOK_STATE` (offsets + parsed events) now persists to `STATE_DIR/_tok_state.json` (atomic
  writes, throttled 300s; first post-scan save immediate). A restart now costs an incremental catch-up of
  only the bytes appended since the last save -- worst case ~5 minutes of re-parse, never a full rescan.
  Known remaining tail (catalog): co-located instances each keep their own cache of the shared store; a
  cross-instance shared cache would cut cold-scan work 3x further.

## 0.99.127 -- 2026-07-02  (Context store Phase 1: bi-temporal edges + deterministic freshness + entity resolution)
- **Bi-temporal edges** (VISION 3.2 / plan 2.1): the graph's edges now carry valid_at/invalid_at
  (world-time) + created_at/expired_at (system-time). Conflict rule: INVALIDATE, NEVER DELETE -- asserting
  a new value for a functional relation (e.g. project status) sets the old edge's invalid_at to the new
  edge's valid_at, so "what was true WHEN" is always answerable and corrections never destroy history.
  New API: assert_edge / invalidate_edge / current_edges (the DETERMINISTIC freshness resolver -- pure
  max(valid_at), never an LLM) / edge_history. v1 `link()` stays as a compat wrapper. One-time migration
  rebuilds the edges table (the v1 UNIQUE(src,dst,rel) forbade re-asserting a superseded fact) -- proven
  zero-row-loss against a copy of the live store before shipping.
- **Entity resolution** (plan 2.2): upsert_entity is now a two-tier resolver -- (1) deterministic key
  match (an email/source-id held by an existing same-type entity wins outright, so "Sarah K
  <sarah@x.com>" and "Sarah Karger sarah@x.com" become ONE person), (2) stdlib Jaro-Winkler >= 0.87
  name similarity for person/org/client (merges as an alias). merge_entities() is non-destructive:
  keys union + aliases + merged_ids on the keeper, edges repointed, the duplicate tombstoned with
  merged_into (reversible by construction, never deleted); subjects() skips tombstones. LLM
  adjudication tier deliberately deferred (deterministic-first per the research).
- selftest extended with the new invariants (freshness, time-travel, invalidate-at-handover,
  re-assertion after supersession, key-unify, fuzzy merge, reversible tombstone); stats() reports
  edges/edges_current.

## 0.99.126 -- 2026-07-02  (Access guarantees documented + MESH_ENFORCE fleet-wide + approvals audit + last fleet literals)
- **THE ACCESS GUARANTEES documented** (docs/ACCESS_RECOVERY.md): the six structural invariants that mean
  the operator can ALWAYS get back in (operator login is its own code path; break-glass needs only a
  terminal; the superadmin DOWN channel is signature-authed and NOT mesh-gated; every auth knob has a
  remote rollback; credential changes are never silent; worst-case mesh blast radius is chatter, not
  access) -- plus a STANDING GATE: any auth-touching ship ends with a 3-point recovery verification.
- **MESH_ENFORCE flipped fleet-wide** (catalog C2, executed under the access protocol): all 8 nodes
  verified carrying the identical family badge FIRST (hash-compare); local trio flipped + verified
  (unbadged 403 / badged 200 / operator login 200); 4 tenants flipped via signed set_config + safe
  restart with post-enforce superadmin ping proven; AFP staged via set_config only (applies at her own
  deferred restart -- zero disruption). Unbadged mesh traffic is now rejected fleet-wide.
- **Automatic prompt approvals: audit surface + operator switch** (item 1.12 / catalog C3):
  `/api/autoapprove-log` + a Settings panel showing the full audit trail of every auto-accepted
  permission prompt, with a live-applied ON/OFF toggle (cc.config auto_accept_prompts). Previously the
  audit log existed but nothing surfaced it and disabling meant hand-editing config.
- **Last fleet-specific literals out of the framework** (item 1.3 / catalog B3): remote machines'
  project root now comes from the machine registry entry (`root` key; generic `%USERPROFILE%` default)
  instead of a hardcoded `C:\hptuners` in both remote-launch paths; the Backup lens 3-2-1 cards render
  from `cc.config backup_tiers` (+ the node's own project path) instead of hardcoded Mac-Studio/T490
  rows. This fleet's values moved into per-node state/config where they belong.

## 0.99.125 -- 2026-07-02  (The node watches its own health: daemon supervisor + headless-login preflight)
- **Daemon supervisor** (plan item 1.11 / catalog D4): all ~28 background loops now launch via
  `_daemon(name, fn)` instead of bare `threading.Thread` -- a loop that RAISES is respawned with
  exponential backoff (30s -> 10min cap) and the crash is recorded to `_daemons.log`; a loop that
  RETURNS cleanly is a one-shot that finished (boot housekeeping, warm-views) and is marked ended, not
  respawned. `/api/daemons` lists live state (alive/restarts/last_error); **Doctor flags any daemon with
  a recorded crash**. Before this, a crashed loop was silently gone until the next full restart, its
  print() buried in tmux scrollback.
- **Headless-login preflight** (item 1.6 / catalog B11): Doctor now errs when the Morning Brief is
  enabled but the macOS user has NO live Claude keychain login (a stored setup-token is not enough --
  it runs API-mode without subscription auth). Previously the 8am synthesis just failed silently.
- **`cryptography` at install** (item 1.8): `cc-init.sh` best-effort installs it when missing (Ed25519
  superadmin verification; Doctor already flagged the HMAC-only fallback -- that check stays).

## 0.99.124 -- 2026-07-02  (Mesh peers UI, server-side browser act gate, routines operator controls)
- **Mesh peer registration from the dashboard** (plan item 1.2): `/api/peer-add` + `/api/peer-remove`
  (operator-auth ONLY -- never mesh ingress, since peers.json is the routing map for mesh + superadmin
  sends) + a "Mesh peers" panel in Settings that lists peers with Remove and an add form. Writes are
  atomic + chmod 600. Ends "hand-edit peers.json on N machines" for the local side; the far side still
  adds you back (the panel says so).
- **Server-side act-for-me gate for the agent-driven browser** (item 1.4 / catalog C1): `browser_queue`
  now REFUSES `click`/`type` unless the operator enabled "Browser act" in Settings (`cc.config
  browser_act`, applied live -- no restart). The desktop toggle remains the client-side consent; both
  must be on. Show-me actions (open/scroll/highlight/screenshot) stay free. Previously the only gate was
  client-side in the desktop shell -- an agent could POST straight to the queue.
- **Routines operator controls** (item 1.7 / catalog B5): Enable/Disable + Archive buttons on every
  routine card (`/api/routine-set`, `/api/routine-delete`). The scheduler already honored
  `enabled:false`; now operators can flip it without editing `_routines.json`. Delete-means-archive: the
  entry moves to `_routines_archive.json` (recoverable); a running routine can't be archived mid-run.
  Disabled routines show dimmed with an amber badge and can still be run manually.

## 0.99.123 -- 2026-07-02  (Safety floor: nodes are never born open + truthful VERSION stamps)
- **Per-node auth_token minted at birth** (NODE_SETUP_STREAMLINE.md #3/#4, plan-of-attack item 1.1):
  `cc-newinstance.sh`, `cc-spawn.sh`, and `cc-init.sh` now mint a per-node login token (24-hex) instead of
  creating an open dashboard gated only by the shared PIN. The token is printed loudly at creation (and in
  the `--json` summary for the provisioning agent); `cc-recover.sh` remains the break-glass that reads it
  back, which is what made the old "born open to avoid lockout" rationale obsolete. `cc-init.sh` mints ONLY
  when no token exists -- an existing node's token is never touched (lockout hard rule). Child/new configs
  are chmod 600 at write; `cc-spawn.sh` children now also carry the family `mesh_token` from the parent.
- **VERSION stamps can no longer drift** (item 1.10): `cc-update.sh` restamps a bundle's/mirror's `VERSION`
  file from the freshly-updated manifest (the public dist mirror had been advertising `0.12.5` while
  shipping 0.99.x; the manifest is the single source of truth).
- Housekeeping: `.gitignore` hardening at MC (`secrets/`, runtime stores, `.claude/`); the conceptsandideas
  module now carries the platform charter docs (system reference / improvement catalog / plan of attack).

## 0.99.122 -- 2026-07-02  (Fix: "Resume failed: unknown machine" on installs with an empty machine registry)
- Resuming/forking a past conversation looked up its machine in `_machines.json` BEFORE the local-resume branch,
  so the LOCAL host ("studio") had to be a registered machine. On a fresh install or a tenant with no/empty
  `_machines.json` (e.g. shopos), every local resume failed with "unknown machine". Fixed: the local host is
  always a valid resume target (it's whatever runs this server) and needs no registry entry; only REMOTE (ssh)
  machines are looked up. Resume + fork now work on any node out of the box.

## 0.99.121 -- 2026-07-02  (Email Archive: smart -- Ask-your-email + facets + threads, token-bounded)
- Turned the archive from keyword FTS into a genuinely smart tool over 21k+ emails WITHOUT stuffing the corpus
  into an LLM. Two layers:
  - **Deterministic smarts (free):** the index now carries **thread id + normalized from-address**, so results
    collapse into **conversations**, and search narrows by **contact / year** facets (`/api/email-facets`,
    `mb_facets`) + a **thread view** (`/api/email-thread`, `mb_thread`) + a **contacts** rollup. Stats report
    threads + contacts. All via SQL, zero tokens.
  - **Ask your email (token-bounded AI):** `mb_ask` = plan (1 cheap Haiku call turns the question into a query) ->
    DETERMINISTIC retrieval does the heavy lifting -> synthesize a **cited** answer over only the ~12 most-relevant
    emails. Runs on the node SUBSCRIPTION (`_claude_text`, no metered key), OR's terms for recall, degrades to
    pure retrieval if AI is off. **~2k tokens/question**, not the corpus. `/api/email-ask` + `cc-email ask`.
  - Lens rebuilt: an **Ask** hero (answer + draggable cited sources + `[#n]` + token count), keyword search with
    **narrow-by** contact/year chips, and a thread viewer. `cc-email` gains `ask`/`thread`/`contacts`; AGENT.md
    steers agents to `ask` first ("never dump the archive into context"). Index rebuilt (new schema) on both nodes.
- Verified end-to-end: cited answers (~1.6-2k tokens), facets, threads, draggable sources -- server, CLI, headless UI.

## 0.99.120 -- 2026-07-02  (Email Archive: fully functional -- draggable results + an agent CLI)
- Rounded the email-archive extension out from a lens into a first-class capability agents + people can both use:
  - **Draggable results.** Every result row is now a sendable -- drag it onto a Claude session (or the Basket) to
    hand the agent the FULL email (headers + body). New `emailarc` resolver (`register_sendable`) fetches the
    message from the local index by id; `ssAttr` on the row; declared in extension.json `draggables`.
  - **Agent CLI `cc-email`** (on the session PATH): `cc-email search "<query>" [limit]` / `get <id>` / `stats` --
    so an agent can find + pull an archived email into context without the dashboard. Read-only; FTS5 query syntax.
  - **`AGENT.md`** so an enabled node's agents know the tool exists, when to reach for it, and how (CLI + drag).
  - Allowlisted `email_archive_mbox` + `email_archive_db` for superadmin `set_config` (remote node configuration).
- Verified: CLI search/get/stats against the real 21,606-msg index; resolver + draggable wired; ast/lint/preship green.

## 0.99.119 -- 2026-07-02  (#8 reframed: end-of-day DIGEST + quiet filing, no more re-proposing declined moves)
- The first end-of-day pass (.116) re-surfaced work the operator had DECLINED to move -- which quietly re-nagged
  the exact move they'd said no to, in tension with #7 ("a declined move is final"). Reframed to what was actually
  asked for: a passive **end-of-day digest** + quiet filing. `_drift_sweep` no longer relaxes the decline/cooldown
  gates for EOD (a declined move is final EVERYWHERE). `_housekeeping_eod_once` now runs the thorough tidy (curate
  records, retire idle, refresh the map, propose ONLY genuinely-new drift) then writes a read-only day recap via
  new `_eod_day_digest`: where today's work is filed + an FYI list of off-lane threads (never a kept-here one, never
  a dismiss-me proposal). Surfaces as an "End-of-day recap" block in the Automatic-housekeeping card + a gentle
  notify; nothing to action. Added a manual "End-of-day recap" button (`/api/housekeeping-run {eod:true}`). Verified
  end-to-end (real pass emits the digest; the recap + button render in the Transfers lens).

## 0.99.118 -- 2026-07-02  (#4 Terminal selection rebuilt: smooth client-side highlight, no flicker)
- The browser terminal's drag-to-select drove tmux copy-mode on EVERY mouse-move (~45ms), re-rendering the pane
  each tick -> a distracting flicker while you tried to see what you were selecting. Rebuilt: a drag now draws a
  SMOOTH client-side highlight overlay (linear text-selection shape) and reads the selected text straight from
  xterm's OWN buffer on release -- ZERO server round-trips, zero flicker, instant copy. Dragging PAST the top/bottom
  edge (to grab MORE than one screen) transparently hands off to the old tmux copy-mode auto-scroll path, so the
  select-across-history power feature is preserved. Verified in headless Chrome: exact single- + multi-line text
  extraction and a real simulated drag. auto-copy + the "select & copy" full-history overlay are unchanged.

## 0.99.117 -- 2026-07-02  (#5 Email Archive extension: instant full-text search over an exported mbox)
- New **email-archive** extension: point it at a Gmail Takeout `.mbox` and get an instant, searchable lens over
  years of old email. `command-center/email_archive.py` (stdlib: `mailbox` + `sqlite3` FTS5) builds a one-time
  local index and serves ranked, highlighted-snippet search + a message reader. Benchmarked on a real 7.2 GB /
  **21,606-message** export: index build ~2 min, search **~40 ms**. Read-only; the archive never leaves the node.
- Wiring: helper `email_archive.init()` + `GET /api/email-stats|email-search|email-get`; `loadEmailArchive()` lens
  (search box -> results -> reader), install-gated via `_ext_lenses` (nav button only where installed); config
  `email_archive_mbox` + `email_archive_db`. Verified end-to-end in headless Chrome (nav button, 60-hit search with
  highlights, reader). See `extensions/email-archive/SETUP.md`.

## 0.99.116 -- 2026-07-02  (#8 End-of-day housekeeping: a once-a-day thorough tidy that sorts even DECLINED work)
- New opt-in **end-of-day housekeeping** (`cc.config housekeeping_eod`). Once a day -- at `housekeeping_eod_hour`
  (default 6pm) OR after the node's been ~2h idle in the afternoon, whichever comes first -- it runs a thorough
  housekeeping pass AND re-surfaces the day's work the operator DECLINED to move in-conversation. Rationale: keeping
  a session open doesn't mean the work shouldn't be filed (Sarah). Everything lands in the Transfers/housekeeping
  review queue -- PROPOSE-ONLY, one-click to apply, never an in-session nag (that's what the .113 guidance stopped).
- Mechanism: `_drift_sweep(eod=True)` relaxes the decline-suppress + cooldown gates (so declined/cooled day-work
  re-appears once a day for review, not every hour); `_housekeeping_eod_once` combines it with the normal pass +
  writes an `eod` digest; `_housekeeping_eod_loop` fires it on the evening-hour OR 2h-idle trigger, once/day,
  project nodes only. Safe to run live because it only ever proposes -- tune thresholds from what it surfaces.

## 0.99.115 -- 2026-07-02  (allowlist deliverable_gdoc + housekeeping_eod for remote config-set)
- Add `deliverable_gdoc`, `housekeeping_eod`, `housekeeping_eod_hour` to `SA_ALLOWED_KEYS` so Mission Control can
  toggle the Google-Doc delivery + end-of-day housekeeping on a node via a signed superadmin `set_config` (they're
  per-node feature flags; nothing runs until flipped).

## 0.99.114 -- 2026-07-01  (Deliver agent output as GOOGLE DOCS, + self-healing Google token vault re-sync)
- **Agent .md deliverables can now land as native Google Docs** (opt-in `cc.config deliverable_gdoc` + Google
  connected). A background sweep converts each new `.md` in a deliverables/ folder to a Google Doc via Drive
  import (formatting preserved), drops a `<name>.gdoc` pointer beside it, and hides the raw markdown. The Doc
  flows through the SAME delivery path as any file: it shows in Files (and the 'new deliverable' popup) with
  **Open in Google Docs**, **Download .docx** (server-side Drive export), and an inline **text Preview**. New:
  `_drive_import_as_gdoc`, `_gdoc_export`, `GET /api/gdoc-export?id=&fmt=docx|txt|pdf`. Verified end-to-end
  (create -> Files card -> export) in headless Chrome.
- **Self-healing Google token vault re-sync (real bug).** A re-mint (`bin/gauth.sh`) writes a fresh token FILE,
  but the server reads the VAULT first and the env-import SKIPS an already-present key -- so every re-mint
  silently kept the server on the dead vaulted token (Google looked "not configured" despite a good file).
  `_google_vault_resync()` now pushes any fresher token FILE into the vault on boot AND on a refresh failure
  (then retries once) -- so a re-mint takes effect immediately, no restart, and this can't strand a node again.

## 0.99.113 -- 2026-07-01  (Sarah/AFP feedback wave 1: brief date-accuracy, full-text session search, sticky decline)
- **Morning Brief is no longer date-blind.** The calendar + email sources captured each item's date in a `ts`
  field, but `mb_generate` fed ONLY each item's text to the writer -- the dates were dropped, so the brief
  couldn't tell which day a call/reply referred to (it collapsed a Jul-8 reschedule into "today"). Now every
  calendar/email item is PREFIXED with its real date (`Wed Jul 8 3:00pm -- Client call`; `arrived Jun 30 -- ...`)
  via a robust date parser, and the prompt carries a hard date-precision rule (never assume "today"; tie a reply
  to the specific dated event; flag ambiguity instead of guessing). `morning_brief.py`.
- **Session search now searches the FULL transcript, with snippet previews.** The History filter only matched a
  session's title + last ~30 lines, so "find where I discussed X" failed unless X was at the very start/end. New
  `transcript_search` (`GET /api/transcript-search`) full-text-scans this node's `~/.claude/projects` transcripts
  (fast byte-level pre-filter -> only real candidates parsed), and the History lens renders matching sessions with
  highlighted snippet previews + resume/fork. Node-local, stdlib.
- **A declined folder-move is now final.** The dashboard drift-sweep already suppressed a declined transfer; the
  in-session agent guidance now matches it: if the operator says no to a move suggestion, DROP IT and don't re-raise
  unless the conversation later shifts to a genuinely new topic -- if they insist on staying, respect it.

## 0.99.112 -- 2026-07-01  (Per-session MODEL selection from the Sessions tab -- see it, switch it; Fable 5 included)
- **Every session shows a model chip** (Opus / Sonnet / Fable / Haiku, color-coded) on its pane header, the
  bottom taskbar tile, and the hover preview -- so you can tell at a glance what each agent is running. The chip
  reads the ACTUALLY-running model from the session's latest transcript turn (falls back to the model it was
  launched on / Default).
- **Click the chip to switch** -- a picker sends `/model <id>` into that session's tmux pane (the same slash
  command you'd type), records the choice so the chip updates immediately, and rejects unknown models. Works on
  desktop and mobile, and in a **broken-out `/term` tab** (a Model button + picker in its top bar).
- **Fable 5 is now a first-class choice.** The model list is config-overridable (`cc.config "models"`), so a new
  tier needs no core release. New endpoints: `GET /api/models`, `POST /api/session-model`. Pricing/labels already
  knew Fable; this adds the selection UI.

## 0.99.111 -- 2026-07-01  (Built-in help on EVERY tab + hover-text discipline -- so a new owner can actually learn the tool)
- **Persistent per-tab help header.** Every tab now shows a slim one-line explainer under its title, with an
  "ⓘ Learn" toggle that expands an inline deep panel: WHAT the tab is, WHY you'd use it, and HOW to drive it
  (including "ask your Chief of Staff to ...", e.g. starting a Ralph loop or an agent team). Built on the existing
  `HELP` registry, now authored for all 48 built-in tabs in plain, non-technical language. The old auto-popup
  help modal (only 8 tabs, fired once per tab) is retired in favor of the always-available header; the topbar "?"
  still opens the full modal. Full-screen/immersive tabs (Gmail/Calendar/Drive/Sessions/Desktop) keep just the "?".
- **Extension tabs get help too.** `extension.json` `lens.help` ({sub,h} or a string) flows into the same header,
  so third-party tabs are documented the same way.
- **Discipline baked into the ship gate (`ui_lint.py`):** (5) every rendered tab MUST have a HELP entry — add or
  rename a tab without its help and the ship FAILS, so help can't drift out of sync with the tabs; (6) every
  icon-only button (glyph / <=2-letter label) MUST carry a `title=`/`aria-label=`. Audited + fixed the existing
  gaps (RSVP, refresh, download, dismiss, snooze, close, ralph-launch, module-link, idle-archive steppers). See
  docs/DESIGN_SYSTEM.md (now 6 hard rules).

## 0.99.110 -- 2026-07-01  (HOTFIX: Morning Brief catch-up must only run where the operator enabled it)
- **Regression from .109:** the new `_brief_catchup_loop` decided whether to (re)generate via `mb_should_catchup()`,
  which reads `morning_brief._cfg()` -- and `_cfg()` returns a FULL default config (8am / weekdays / all sources) on
  EVERY node, even ones where nobody ever set up a brief. So the catch-up sweep auto-generated a brief on every node,
  and with no real personal data the synthesis model HALLUCINATED a plausible-sounding brief (invented customers etc).
- **Fix:** catch-up is now gated on `_brief_is_enabled_here()` -- true only when THIS node has the "Morning Brief"
  routine (which `brief_config_save` creates when the operator configures the brief), enabled + not paused. A node on
  default config never auto-generates. (The manual "Generate now" button is unchanged -- that's explicit user intent.)
- Operational cleanup on ship: the bogus auto-generated briefs on non-configured nodes were wiped.

## 0.99.109 -- 2026-07-01  (Morning Brief FAIL-LOUD + self-heal: a missed/failed brief can no longer fail silently)
- **Root cause of a silently-missed brief.** The scheduled routine fires `cc-brief`, which POSTed `/api/brief-generate`
  and got an instant `{"started":true}` (generation is a detached background thread), so `cc-brief` exited 0 and the
  routine logged **"ok"** -- even when `mb_generate` then produced nothing. And `mb_generate` only PERSISTED state at
  the very end (after slow synthesis+TTS), so a failure/timeout/process-kill mid-generation saved nothing and left
  YESTERDAY's brief showing, with no error and no alert. Observed live: routine "ok" at 08:00 while the module's own
  `last_run` never advanced past the prior day.
- **`mb_generate` is now fail-loud.** It writes a `running` checkpoint UP FRONT (so `last_run` advances immediately and
  a hang/kill shows as a stuck `running`, never a phantom `ok`), wraps everything in try/except, and EVERY exit path
  (empty sources / synthesis-failure sentinel / exception) persists `last_status`+`last_error` and **alerts the
  operator** (Telegram/notify, newly injected). A failed synthesis is no longer saved AS a brief. A concurrency guard
  stops overlapping generations from piling up.
- **`cc-brief` now VERIFIES the outcome.** After kicking off generation it polls to a terminal status and exits
  non-zero if today's brief wasn't produced -- so the scheduled routine marks itself blocked and fires its failure
  alert instead of reporting a phantom success.
- **Self-heal catch-up loop.** A new bounded sweep re-attempts a missed/failed brief when the scheduled time has
  passed and there's still none for today -- a transient 8am failure (slow/limited synthesis, a restart mid-run) now
  lands the brief late instead of losing the whole day.
- **Also: Ralph loop taskbar scoping.** A running Ralph loop leaked onto EVERY co-located source-trio node's session
  taskbar (hptuners' loop showed on carsearch etc.). `RALPHDIR` is `CC_HOME/data/ralph`, and the trio share one
  checkout -> one `CC_HOME`, so the old "does this loop's dir exist in RALPHDIR" ownership test was true on every
  trio node. Now a loop is owned by the node whose PROJECT its recorded `cwd` (loop.json) belongs to -- the same
  `_session_in_project` test as any other session -- so it shows only on its real owner.

## 0.99.108 -- 2026-07-01  (terminal scroll polish: 'jump to live' auto-hides at the bottom; copy toast is gold, not green)
- **'Jump to live' pill now clears when you scroll back down to the bottom.** The pill only hid on an explicit tap
  before -- manually wheeling/swiping all the way back to the live screen left `inMode` set, so the pill lingered
  over live output. `term_scroll` now checks tmux `#{scroll_position}` after a scroll-DOWN: reaching the bottom
  (position 0) drops copy-mode and returns `mode:"live"`, and the browser's `drain()` loop hides the pill on that
  signal. (Tapping the pill still works as before.)
- **Copy confirmation toast is now the standard gold**, matching the rest of the UI (the 'jump to live' / 'Copy
  selection' pills and every accent). It was an off-palette GitHub green (`#16351f`/`#7ee787`); now `#e8c547` on
  `#15120a`, same format as the pills.

## 0.99.107 -- 2026-07-01  (payload is now a pure function of the SESSION -- identical from any co-located dashboard; auto-compact headroom)
- **Cross-instance payload parity.** Many ClaudeFather instances share ONE tmux server on a box (the source trio
  hptuners/overseer/carsearch + co-located tenant installs atem/homeassistant/shopos), and the unscoped overseer
  sees ALL their sessions -- but a session's payload (its enabled tools especially) is a property of the NODE that
  launched it, so computing it against the VIEWER gave a different number per dashboard. Each instance now
  publishes a tiny descriptor (`/tmp/cf-instances/<id>.json`: project_root + local port) at boot; `context_package`
  resolves a session's OWNING instance by cwd and, when it's a different co-located node, PROXIES the payload to it
  (localhost, short timeout, falls back to local). So the popup + the per-session chip read IDENTICALLY whether
  viewed from the node or Mission Control. The chip's computation is NON-BLOCKING (warms in a background thread,
  never stalls the Sessions poll; a transient miss retries in 20s instead of caching wrong for 5m).
- **Auto-compact default lowered 95% -> 90%.** At 95% the graceful handoff-write (which itself burns context) was
  peaking a huge session to 99% before `/compact` ran -- a near-miss with Claude Code's own hard-limit compaction.
  90% gives the handoff room to finish first. Per-node `autocompact_pct` overrides still win.

## 0.99.106 -- 2026-07-01  (the per-session payload CHIP now shows the real per-trip weight, matching the popup, on every dashboard)
- The little context-package chip on each session was a single **node-level baseline** (`_payload_baseline` =
  system briefing + ROOT CLAUDE.md + tools), the SAME number on every session and ignoring the per-session cwd
  cascade -- so it read ~8k on a node and a flat ~5k for every session on the overseer, while the click-through
  popup (correctly, after 0.99.105) showed ~36k. Now `token-usage` returns `payload_by_sess` -- a PER-SESSION
  weight computed with the same cwd-anchored cascade as the popup (`_payload_tokens_for_session`, cached by cwd
  so the Sessions poll stays light) -- and the chip renders its own session's number. Chip == popup, and both are
  consistent whether viewed from the node or Mission Control (the only residual cross-dashboard delta is the
  per-node 'enabled tools' line, which genuinely differs by which extensions each instance has enabled).

## 0.99.105 -- 2026-07-01  (two context-accuracy fixes: catch inline-backtick @imports; payload cascade anchored on the session's own tree)
- **Doctor now catches the `@import` footgun even inside inline `backticks`.** A bare `@path` in a CLAUDE.md
  (e.g. a `curl --data-binary @_dist/portal.html` example) is parsed by Claude Code as a MEMORY IMPORT and pulls
  the whole file into context ("over the 150.0k-char limit" warning). The detector previously stripped inline
  code spans before scanning, assuming backticks protect them -- but they do NOT: only a FENCED ``` block is
  import-safe (observed live: a backticked curl example imported a 1.3 MB built portal.html). `_stray_at_imports`
  now strips ONLY fenced blocks, and the Doctor advice is corrected ("move INTO a fenced block, inline backticks
  do not protect it"). Prevents the context-poisoning on every node + every future install, automatically.
- **Payload / Context-package panel now reads identically from any dashboard.** It walked the CLAUDE.md cascade
  from the VIEWING instance's `PROJECT` root, so the unscoped Mission Control overseer -- whose own root differs
  from a tenant's tree -- dropped the entire intermediate cascade (the `relpath('..')` guard), showing the SAME
  chat as ~5k/3-parts from the overseer vs ~36k/6-parts from its home node. Now the cascade is anchored on the
  SESSION'S OWN cwd (walk up collecting every CLAUDE.md-bearing dir), mirroring exactly what Claude Code
  auto-loads -- so the payload is accurate and consistent whether viewed from the node or the overseer.

## 0.99.104 -- 2026-07-01  (warm transfer works on EVERY node: file unfiled root conversations, not just off-lane sub-folder drift)
- **Drift/warm-transfer now fires on single-project + control-brain nodes**, not just agency trees with per-client
  sub-folders. Before, the housekeeping drift sweep only watched conversations FILED in a sub-folder lane and
  proposed a move when their topic drifted OUT of it -- so nodes whose work runs at the project ROOT (hptuners
  control brain, carsearch, etc.) essentially never saw a transfer proposal. Now the sweep ALSO watches UNFILED
  root conversations and proposes filing one into the specific home it clearly belongs in (e.g. root work about
  firmware brick-gates -> `patches/`).
- **High-precision + cost-bounded.** A root conversation is only proposed on a STRONG lexical/model route AND a
  fresh model-confirm (`_confirm_file_llm`) that it squarely belongs there -- cross-cutting / platform-wide root
  work is left put. Every examined root session stamps its cooldown (proposed or not) so it's re-examined at most
  once per 6h, bounding subscription-model spend on nodes where most sessions live at root.
- **Overseer still excluded** (ROLE=org): the unscoped Mission Control instance shares the tmux server and must not
  manage individual conversations. **Off switch unchanged:** Settings -> "Warm transfer (the front desk)" (`handoff`).

## 0.99.103 -- 2026-07-01  (terminal: auto-copy-on-release toggle + a 'copied to clipboard' confirmation popup)
- **Auto-copy toggle** (⧉ auto-copy in the terminal ⋯ menu, default ON, persisted per device): when ON and the
  origin is secure (https/localhost), releasing the mouse writes the selection straight to the clipboard and snaps
  back to live -- no Ctrl+C needed. On plain http (browsers block programmatic clipboard writes off a gesture) it
  falls back to the one-tap ⎘ Copy chip; Ctrl+C always works. Toggle OFF = never auto-write (chip / Ctrl+C only).
- **Copied-to-clipboard confirmation popup** (`#cliptoast`): a small green "✓ Copied N chars to clipboard" pops at
  the top on EVERY successful copy -- auto-copy, the ⎘ Copy chip, Ctrl/Cmd+C of a drag selection, or Ctrl+C of an
  on-screen selection. No more guessing whether it landed.

## 0.99.102 -- 2026-07-01  (session terminal: real scroll + native select/copy; graceful-End vacates the pane)
- **Graceful End now vacates the pane immediately.** The in-terminal ⏏ End only knew how to navigate a standalone
  /term tab; embedded as a workspace pane it sat forever on the '[filed away]' screen. New `leaveNow()` posts a
  `cf-session-dead` message to the parent dashboard, which drops the pane at once (the handoff still finishes in
  the background); a matching listener in PAGE calls `paneDown`. Force-kill uses the same path.
- **Terminal scroll finally works like a terminal, with NO scroll/select mode toggle** (removed). The history
  lives in tmux (xterm only ever holds the repainted visible window) AND Claude Code grabs mouse reporting -- so a
  raw wheel reached Claude as arrow keys. Now the wheel (desktop) and swipe (mobile) are intercepted in JS and
  drive tmux copy-mode server-side (`/api/term-scroll`), scrolling the full history. '↓ jump to live' + typing snap back.
- **Native drag-to-select across the full history** (`/api/term-select`): a mouse drag drives tmux's OWN copy-mode
  selection -- anchor on mousedown, extend on drag, AUTO-SCROLL past the top/bottom edge through the whole
  scrollback (not just the visible screen). We fully own the mouse during a drag (stopPropagation) so xterm can't
  forward mouse-report bytes that were tearing down copy-mode on release. Requests are serialized (concurrent ones
  raced tmux's copy-mode state) + coalesced.
- **Copy that actually lands + returns to live.** On release the selection is copied to a buffer (kept, via
  `copy-selection-no-clear`). Ctrl/Cmd+C (a real gesture -> works on plain http), the ⎘ Copy chip, or a secure-origin
  auto-write deliver it to the clipboard; then the highlight clears and the pane snaps back to live. A plain click
  dismisses a selection. Ctrl+C used to fall through to SIGINT -- it now copies the tmux selection.
- **⎘ select & copy panel loads the FULL history** (`/api/term-capture`, ~15k lines) as real selectable text, so
  drag-past-edge selection works there too (desktop + mobile) -- not just the on-screen buffer.

## 0.99.101 -- 2026-07-01  (fix serif-default font in the session-terminal confirm popups)
- **The session-terminal pages now use the UI sans font in their popups.** The browser-terminal PAGE and
  RALPH_PAGE never set a `font-family` on `body`, so their `confirmM` dialog (e.g. "Compact this session?") and
  toolbar buttons fell back to the browser default serif (Times) -- visibly off vs the rest of the dashboard.
  Fix: set the `-apple-system,...,sans-serif` stack on both pages' `html,body`, add `button,input,select,textarea
  {font-family:inherit}` (form elements don't inherit font by default), and `font-family:inherit` on `.tdlg-b`.
  The main dashboard PAGE was already correct (cc-* design system). Pure CSS; no behavior change.

## 0.99.100 -- 2026-07-01  (auto-updates DEFER during a node's business hours -- don't restart Sarah mid-workday)
- **Auto-updates now skip a node during its BUSINESS HOURS** so a release never restarts it mid-workday (AFP =
  Sarah's node). New per-node cc.config `business_hours` {days:'weekdays'|'all', start, end}; the node reports
  `quiet_now` in its fingerprint (computed on its OWN clock, so timezone is correct). BOTH auto paths honor it:
  the node's own 30-min self-update defers, and the overseer's auto-converge (auto=True) skips a node reporting
  quiet_now. A deferred node converges automatically after hours (its self-update / the backstop sweep). A
  **MANUAL** `/api/fleet-update` (or the "Update all behind" button) IGNORES business hours -- that's the explicit
  override ("unless I tell it to"). No `business_hours` set -> node is always updatable (unchanged for other nodes).
  AFP configured to weekdays 8am-6pm (adjustable in its cc.config).

## 0.99.99 -- 2026-07-01  (fleet auto-converges on ship -- the manual "force converge" step is GONE for good)
- **The overseer now auto-converges the fleet the instant a ship lands -- no manual `/api/fleet-update`.** The
  manual force-converge kept getting forgotten, leaving tenant nodes silently behind. `_fleet_converge_loop` now
  WATCHES the dist mirror version and, the moment it advances past the last version the fleet was converged to (a
  PERSISTED marker `_fleet_converged_ver`, so it survives an MC restart and doesn't depend on ship-step ordering),
  converges every behind tenant within ~1-2 min. Runs ONLY on the overseer (ROLE==org) so co-located instances
  don't race. The manual `POST /api/fleet-update` and the ~3h offline-backstop sweep remain. Tunables:
  `fleet_watch_sec` (default 90), `fleet_converge_min` (backstop, default 180 min); kill-switch
  `fleet_auto_converge:false`. MISSION_CONTROL.md updated: pushing the mirror is now the only required ship step.

## 0.99.98 -- 2026-07-01  (nav category notification: GOLD haze + "new since you looked" semantics)
- **The collapsed-category notification is now a GOLD haze, not red** (matches the brand accent; red read as an
  error). Border/background/pulse/count-badge all use the accent.
- **The haze now means "something NEW arrived since you last opened this folder", not "unread exists".** Before,
  a folder holding permanently-unread email glowed forever, so the signal meant nothing. Now: opening a folder
  ACKNOWLEDGES its current items (haze clears), and it only re-glows when something arrives ON TOP of that -- the
  count badge shows the NEW count. If the count drops (you cleared some elsewhere) the acknowledged floor lowers
  so a later arrival still registers. Per-device (navseen in the nav state). Headless-verified: glow is gold,
  clears on open, re-glows only on a fresh arrival showing the new count.

## 0.99.97 -- 2026-07-01  (nav re-seed fix: catch legacy PARTIAL layouts, not just fully-flat ones)
- **Nav auto-organize now also fixes a legacy PARTIAL layout** (v0.99.96 only caught fully-flat navs). A sidebar
  with a couple of old folders (e.g. "Google" + "Utilities") but a TON of tabs left loose was wrongly treated as
  a "real custom layout" and preserved -- so it stayed a cluster. The re-seed signal is now **loose non-pinned
  tabs** (any non-daily-driver tab sitting outside a folder = not following the current scheme) rather than
  folder count: SEED VERSION bumped to 3, and any nav that isn't a COMPLETE categorized layout re-seeds to the
  current default categories. A layout where every non-pinned tab already lives in a folder is preserved untouched.
  Headless-verified: a simulated "Google + Utilities + loose cluster" re-seeds to clean collapsed folders with
  ONLY the pinned daily-drivers on top and zero visible loose non-pinned tabs.

## 0.99.96 -- 2026-07-01  (morning brief: all sources on by default; nav auto-organizes a stuck-flat sidebar)
- **Morning Brief: ALL sources ON by default.** The default source set is now every registered source
  (calendar, inbox, tasks, calls, doc-comments, slack, notes) instead of five -- so a fresh brief uses everything
  it can, and each source degrades to nothing when its backend isn't set up. Future sources are auto-included.
  (The **Brief lens/tab already exists** and shows today's brief + past briefs whenever the morning-brief
  extension is enabled -- no change needed there; it was just buried under an un-organized nav, see below.)
- **Nav sidebar auto-organizes even if it got stuck flat.** The one-time category migration only re-ran for
  brand-new browsers, so a console whose sidebar stayed FLAT (no folders) kept its un-organized layout (a node's
  nav "never got organized like Mission Control's"). Bumped the nav SEED VERSION: the default categories
  (Google/Workspace/Agency/Team/Integrations/System + pinned daily-drivers) are now force-applied ONE more time
  to any nav still stuck flat/legacy -- including one left in "flat" mode -- with NO manual action. A genuine
  custom multi-category layout is preserved untouched (so Mission Control's own nav is unaffected). Takes effect
  on the next page load; the nav "reset" link remains the instant manual option.

## 0.99.95 -- 2026-07-01  (google-workspace SETUP fixes so FUTURE installs never hit tonight's traps -- v2.2.3)
- **SETUP.md now enables ALL SIX Cloud APIs + explains the scope-vs-API gate.** Step 2 previously enabled only
  Gmail/Calendar/Drive APIs, so a fresh install using sheets/docs/forms would 403 `SERVICE_DISABLED` even with the
  scopes granted (a granted OAuth scope authorizes access, but the Cloud PROJECT must ALSO have that API turned
  ON -- two separate gates). Added Sheets/Docs/Forms with direct activation URLs + the explicit rule:
  `SERVICE_DISABLED` -> enable the API; missing scope -> re-mint (don't conflate).
- **Corrected the restart semantics** (was misleading in tonight's v0.99.90/.94 docs). The Path-B google agent
  spawns its stdio MCP FRESH per launch, so new tools appear on the agent's NEXT launch -- NO whole-node restart
  needed (bouncing the node can kill the setup session itself). SETUP.md gained a "Restart semantics" note; AGENT.md
  updated to match + to route a `SERVICE_DISABLED` 403 to "enable the API," not "re-mint."
- Docs-only extension change (google-workspace -> **v2.2.3**); the remaining hardening (split-brain guard,
  SERVICE_DISABLED live-probe in verify/Doctor, diagnostics naming their token file, gauth --remote preflight, a
  bin/doctor.sh health check) is specced in extensions/google-workspace/HARDENING_TODO.md for a follow-up batch.

## 0.99.94 -- 2026-06-30  (AFP CCRs: google scope-drift detection + PORTABLE secret paths -- google-workspace v2.2.2)
- **CCR ccr-1782880284334 -- google secret paths are now PORTABLE (CC_HOME-relative), so a deployment can move
  drives without split-braining the token store.** AFP hit this live: the wired `.mcp.json` froze ABSOLUTE
  `/Users/.../secrets` paths at install, while the dashboard derives them CC_HOME-relative -- so moving CC_HOME
  onto the SSD made the MCP read a stale off-SSD token while the dashboard read the SSD one. Fixes: (1)
  `_ext_wire_mcp` now expands the `<DEPLOYMENT>` placeholder to the current install root at wire time (no frozen
  absolute); (2) a boot self-heal re-points the google MCP's `WORKSPACE_MCP_CREDENTIALS_DIR` +
  `GOOGLE_CLIENT_SECRET_PATH` to the SAME canonical CC_HOME paths the dashboard uses (idempotent; follows a drive
  move automatically); (3) a Doctor check flags path drift. **This makes moving a node onto the SSD safe.**
- **CCR ccr-1782880284369 -- token-scope vs mcp.json-perms DRIFT is now detected, and `mint --check` no longer
  under-reports.** (1) `mint_token.py --check` reads the ACTUAL granted scopes from the stored token file and maps
  them faithfully (gmail.send->gmail:send, spreadsheets->sheets:full, documents->docs:full, forms.body->forms:full)
  instead of echoing the requested PERMS -- so it no longer claimed 'gmail:drafts' right after a mint that granted
  send/sheets/docs/forms. (2) `google_status()` + Doctor now reconcile the token's granted scopes against the wired
  `--permissions` and surface "RE-MINT NEEDED: run bin/enable-services.sh" with the exact missing services (they
  were silently 403-ing). (3) the minter + verify.py now print the final on-disk scope set + granted perms.
- google-workspace extension -> **v2.2.2**.

## 0.99.93 -- 2026-06-30  (BUG: extension Setup button opened an invisible session on scoped nodes)
- **FIX -- Marketplace "Set up" now actually opens the setup-agent session on a scoped node (AFP).** The setup
  agent launches in the EXTENSION dir (under the install root), which is NOT under `PROJECT` on a node where
  `PROJECT != CC_HOME` (e.g. AFP, whose project is the agency tree). `tmux_sessions()` scope-filtered it out, so
  the session was created but invisible -- the workspace then reconciled that pane away and fell back to the
  session already open (Sarah: "it's just the same session it was already on"). Now an `ext-*` session is always
  treated as in-scope for the node that launched it (same exception the chief + Ralph loops already had). Affects
  every extension's Set up button on any scoped node, including the new airtable one.

## 0.99.92 -- 2026-06-30  (Sarah field-feedback batch 5: one-command Google activation + NEW Airtable extension)
- **F/G1 activation is now ONE command (google-workspace v2.2.1).** New `bin/enable-services.sh` does BOTH steps
  in a single run: idempotently adds the services (default `sheets:full docs:full forms:full`) to the LIVE
  deployment `.mcp.json`, then re-mints the token so Google consents the new scopes (reuses gauth.sh -- prints one
  consent URL, supports `--remote` for a remote browser). So an existing install activates in-place editing +
  Forms by: `ACCOUNT=you@gmail.com bin/enable-services.sh` -> approve the ONE URL -> restart. An agent can STAGE
  that single line into the Admin shell (sessions/sudo protocol); the operator hits enter + approves. AGENT.md +
  SETUP.md now document this; `mint_token.py` default PERMS also updated so a bare re-mint grants all six services.
  (Fresh installs already mint with all six -- no action needed.)
- **G2 -- NEW `airtable` extension.** Read + EDIT Airtable bases IN PLACE (list bases/tables, read schema,
  query records, create/update/upsert rows) via a self-hosted MCP (`domdomegg/airtable-mcp-server`, `npx`) authed
  with ONE Personal Access Token in the vault (`AIRTABLE_API_KEY`) -- headless, no OAuth. Least-privilege PAT
  (data.records:read/write + schema.bases:read, granted per-base); AGENT.md enforces edit-in-place + Airtable's
  hard 5 req/s-per-base limit (batch <=10, throttle, prefer UPSERT). Appears in the Marketplace; dormant until
  installed + a PAT is pasted. Ships extension.json + mcp.json + SETUP.md + AGENT.md + CLAUDE.md.

## 0.99.91 -- 2026-06-30  (Sarah field-feedback batch 4: daily brief reads full Drive comment THREADS -- C1)
- **C1 -- the Morning Brief now reads full Google Drive comment THREADS + resolution state.** New read-only
  `drive_open_comments()` (server.py) fetches UNRESOLVED comments on recently-modified Docs/Sheets/Slides with
  the WHOLE thread (opening comment + every reply + times); a new `drive_comments` brief source hands the model
  the full back-and-forth marked "STILL OPEN". Resolved threads are dropped entirely. Fixes Sarah's report: the
  brief had read only the FIRST comment, missed the resolving replies, and wrongly chastised her -- now it has
  the full context (and with batch 2's assistant tone + business-hours it won't scold or miscount elapsed time).
  Enabled by default; degrades to nothing when Google isn't configured. **This completes Cluster C.**

## 0.99.90 -- 2026-06-30  (Sarah field-feedback batch 3: Google in-place Sheets/Docs editing + Forms -- google-workspace v2.2.0)
- **F -- the Google agent can now EDIT existing Sheets/Docs IN PLACE (not just create new files).** Root cause:
  workspace-mcp only registers tools for services listed in `--permissions`, and the template listed only
  gmail/calendar/drive -- so Sheets/Docs had NO tools and the agent worked around it by creating a new copy
  (Sarah's "it can only create new files"). Added `sheets:full docs:full` to `mcp.json`; AGENT.md now instructs
  the agent to edit the SAME file (keep its ID/sharing/links), never spawn a duplicate. Enables the overnight
  use case: walk a contact sheet, research emails for the bounced rows, write them back into that sheet.
- **G1 -- Google Forms.** Added `forms:full` so the agent can create/edit Google Forms + read responses.
- google-workspace extension -> **v2.2.0** (summary/description/provides advertise sheets/docs/forms; SETUP.md +
  CLAUDE.md scope model updated).
- **ACTIVATION (per node, one-time human step): re-mint the token to consent the new scopes.** Shipping the
  template does NOT change a running node's LIVE `.mcp.json` or its already-minted token. To turn F/G1 on for a
  node: (1) add `sheets:full docs:full forms:full` to that deployment's `.mcp.json` google args, (2) re-run
  `extensions/google-workspace/bin/gauth.sh` with `PERMS="gmail:drafts calendar:full drive:full sheets:full
  docs:full forms:full"` (re-consent in the browser), (3) restart. Until then the new tools 403. See SETUP.md.

## 0.99.89 -- 2026-06-30  (Sarah field-feedback batch 2: client/Granola matching + daily-brief tone & business hours)
- **D -- client + Granola auto-matching now matches a folder NAME against a sender/attendee DOMAIN LABEL.** A
  `Clients/Avonler` folder now auto-matches abe@avonler.com (and @mail.avonler.com) with zero config -- both in
  email folder-matching (`_match_folders`, +2 "folder name matches sender domain") and Granola call-matching
  (`match_client` fallback via `_alias_matches`). 'Big Sky' collapses to match @bigsky.com. Precise: skips
  free-mail (never matches a client by 'gmail') + TLD-ish labels; no unanchored substrings. Also: manual "assign
  to folder" no longer LEARNS a free-mail domain (would have matched all gmail senders to that client). Known
  long-tail: a folder named after a PERSON with a different company domain still needs one manual file (which then
  learns the domain) or dossier-derivation -- tracked for a follow-up.
- **C2 -- daily brief tone: assistant, not manager.** The brief now writes as your trusted ASSISTANT reporting TO
  you, never a boss: no scolding/lecturing, never "don't let this slip again", never implies you failed to do
  something (was "my chief of staff", which drifted managerial -- Sarah's report).
- **C3 -- daily brief respects business hours.** New configurable `work_days` + `work_hours` (Settings row in the
  Brief lens; default Mon-Fri, 9-5). The brief now measures "overdue/unanswered/stale" in BUSINESS time only --
  never counts nights, weekends, or non-working days -- so a Friday-evening item is not "days old" Monday morning.
  (C1, reading full Google Drive comment THREADS + resolution so a handled comment isn't re-flagged, is a separate
  in-progress capability -- next batch.)

## 0.99.88 -- 2026-06-30  (Sarah field-feedback batch 1/4: UI friction + deliverables discipline + email hygiene)
- **A1 -- graceful End now closes the window.** After a session's handoff finishes, the standalone /term tab
  auto-returns to the dashboard (was: sat on a dead terminal you had to refresh/minimize -- Sarah's report). The
  inline workspace pane VACATES the moment you hit End (pushed to the taskbar; the tile drops when the session
  actually dies). Same for the taskbar blow-up End button. Embedded panes never redirect the iframe (guarded on
  window.top===self); the parent reconciles them away.
- **A2 -- basket clears after it's dropped into a session.** Dragging the whole basket into a session now empties
  it afterward (save a reusable set as a "pack" BEFORE dragging). Saved packs are untouched.
- **A3 -- deliverable "new file ready" card hides after an action.** Download now dismisses the card (Email already
  did); only Preview keeps it open.
- **B -- deliverables discipline (agent brief, chief + agent-tools).** (1) FORMAT: user-facing deliverables go out
  in a shareable format -- Google Doc/Sheet, Word .docx, PDF, .xlsx, or plain .txt -- never a raw .md unless the
  user asks; ask when the format is ambiguous. (2) SCOPE: only files the user SPECIFICALLY asked for go in
  deliverables/ (each one notifies them); scratch/working files stay out, and never auto-email a file they didn't
  ask for. Stops the "MD handoff" + "emailing every file" noise.
- **E -- email replies stop inheriting signature images.** _gmail_attachments now excludes inline embedded images
  (signature logos, tracking pixels, quoted-thread images -- Content-ID and/or Content-Disposition: inline), so a
  sender's signature logo no longer shows as "1 attachment" or rides along on a reply. Genuine image attachments
  (no Content-ID, marked attachment) still surface. The Google power-agent's AGENT.md now also forbids re-attaching
  anything from the incoming message/thread on a reply.

## 0.99.87 -- 2026-06-30
- FIX (Doctor false positive): "N secret(s) live OUTSIDE the central vault" fired on EVERY node for
  GOOGLE_CLIENT_SECRET_PATH -- which is a FILE PATH (where the Google OAuth client-secret lives), not a secret
  value; the scanner matched it only because the key name contains "SECRET". _loose_secrets_scan now skips
  location/path vars (keys ending _PATH/_FILE/_DIR/_HOME, or values that are filesystem paths) -- they hold WHERE a
  secret is, not the secret, and vaulting one would orphan its consumer. No real loose secret existed; the warning
  clears fleet-wide.

## 0.99.86 -- 2026-06-30
- Doctor now catches the stray-@import footgun fleet-wide. Claude Code reads "@path" in a CLAUDE.md as an IMPORT
  directive, so a bare @path written as a command arg (e.g. "PUT @_dist/portal.html") makes it load that whole file
  into context on launch -> the "over the 150k-char limit" warning + bloat. doctor()/_stray_at_imports flags any
  BARE @path (not in backticks/fenced code) resolving to a real file over 150k chars -- precise: backticked @paths,
  small/legit imports, and non-file @tokens (@media, @4, user@host) are ignored (no false positives). Runs in the
  hourly housekeeping sweep on every node + surfaces in the digest with the fix. Proven across 4 cases.

## 0.99.85 -- 2026-06-30
- "Add sub-tool" now CONFIRMS before adopting a non-empty existing folder. Adopting an existing folder (v0.99.83)
  was silent, so documenting a whole app as a sub-tool felt like "I made a new thing and it was magically full."
  Now module_add returns needs_confirm with the item count + a hint ("looks like a Vite app/Node/Python project")
  for a non-empty undocumented folder; the UI asks "X already exists (N items - looks like a Vite app). Document it
  as a sub-tool? Nothing inside is changed." and only adopts on yes. Empty/new folders create silently as before.
  (Both the Projects "+ add sub-tool" and the launch-picker add-subfolder paths.)
- NOTE (not shipped, a user-doc fix): a CLAUDE.md that writes a curl/deploy arg as bare "@_dist/portal.html" makes
  Claude Code try to IMPORT that path on launch (the 1.3MB build artifact -> "over the 150k-char limit" warning).
  Neutralized the bare ones in text2tune-web/CLAUDE.md (kept the real backticked curl). Watch for this @path footgun
  in authored docs -- candidate for a claude-md-lint rule.

## 0.99.84 -- 2026-06-30
- FIX (fuel gauge): the 5-hour window reset time jumped to ~24h the instant the window rolled over (e.g. James
  showed "5h 98% -> resets 23.9h"). Cause: a BARE reset time (which is exactly what the 5h session window reports)
  that had just passed was projected to TOMORROW (+24h) by _parse_reset_ts. A 5h reset is always <=5h out, so now:
  if today's occurrence passed, tomorrow's is used ONLY if it's within a window length (a genuine crossing-midnight
  reset); otherwise the shown time is stale/just-flipped and the next boundary is +5h. This also fixes the
  account-rotation recommender, which was mis-reading James as "locked ~24h" off that bogus timestamp. Self-corrects
  on the next /usage poll; proven against stale-flip / crossing-midnight / normal cases.

## 0.99.83 -- 2026-06-30
- FIX: "add sub-tool" no longer dead-ends on a baffling "already exists" for a folder you can't see. The Modules
  lens only shows folders carrying a hand-authored CLAUDE.md, but module_add collided against EVERY directory on
  disk -- so on a code project (e.g. text2tune, full of worker/data/src/... folders without a CLAUDE.md) adding a
  sub-tool whose name matched an invisible code folder failed. Now: if the folder already exists but ISN'T a
  documented sub-tool, module_add ADOPTS it (writes its CLAUDE.md so it becomes navigable -- exactly the intent);
  it only errors when a real documented sub-tool already exists there ("a sub-tool named X already exists here").
  Non-destructive (writes the CLAUDE.md only when there's no hand content to lose); the toast says "adopted".

## 0.99.82 -- 2026-06-30
- FIX (mesh reliability): a chief's reply to a peer could be silently dropped when an OPERATOR turn interleaved
  between the incoming "[message from X]" and the chief's reply -- the Stop hook's _reply_after severed at the next
  user turn, so the reply got attributed to the operator turn and never forwarded (this lost carsearch's Step-7.7
  confirmation to Mission Control). Now _reply_after skips interleaved operator turns and captures the chief's
  actual reply block, stopping only at the next mesh message. Flush-retry widened to ~20s for loaded boxes. Because
  an unforwarded message's uuid is never marked done, the stuck reply self-heals on the chief's next turn. Doctor
  now warns if a chief's mesh reply-hook isn't wired at all. Ships to every node + every future install (the hook
  is a signed framework file referenced by absolute path -- existing chiefs pick it up on their next turn, no
  restart).

## 0.99.81 -- 2026-06-30
- RUNNING-CODE version marker -- you can finally tell whether a node actually RELOADED a fix vs just had its files
  synced. BOOT_VERSION is frozen at process start (re-frozen on every os.execv self-restart); /api/health and
  /api/fw-fingerprint now report `running_version` + a `stale` flag alongside the on-disk `version`. drift_report
  judges behind/current by the RUNNING version (a files-synced-but-not-restarted node now shows behind +
  stale_process, not falsely "current"), and fleet_converge RESTARTS a stale-process node even when the pull is a
  no-op -- so a converge actually takes effect instead of leaving old code running. Doctor warns when a process is
  running stale code. This is the systemic gap behind "I shipped the fix but nothing changed."

## 0.99.80 -- 2026-06-30
- FIX (enforced, not advised): a spoke node can no longer page a SIBLING node over the chief-mesh. Every proactive
  chief-mesh from a node now routes UP to Mission Control at the ROUTING layer (mesh_send), where the model can't
  override it -- the brief has asked chiefs to escalate to mission-control (not a sibling) for versions and they
  kept paging siblings anyway (AFP repeatedly paged hptuners). Now any sibling target a chief passes is auto-
  rerouted to Mission Control (logged). The hub (Mission Control) keeps full freedom to address/broadcast DOWN.
  Replies are unaffected (they go via /api/mesh-reply to whoever asked). Brief updated to state the enforcement.

## 0.99.79 -- 2026-06-30
- Skimlinks extension (v1.1.0): hardened the merchant fetch against the Skimlinks API's frequent read timeouts.
  The old fetch_all aborted the whole pass at the first timeout (dying at ~3,400 of ~32k); now it RETRIES the same
  page with escalating backoff (timeouts + 429/5xx), and either returns the COMPLETE catalog or RAISES -- never a
  silent partial. The caller aborts WITHOUT writing on a raise, so an incomplete fetch can never false-delete the
  merchants that simply weren't fetched (count-independent guard, on top of the existing MIN_EXPECTED check).
  Dedups by advertiser_id. (First step of the Fleet Jobs migration -- docs/FLEET_JOBS.md -- making Skimlinks a
  reliable central job before it moves onto the overseer.)

## 0.99.78 -- 2026-06-30
- FIX: auto-compact orphaned by a restart. The compact worker is a daemon thread in the server process; a restart
  mid-compact (every ship / auto-converge / crash) killed it -- leaving the handoff WRITTEN but /compact + re-read
  never run, and the session stuck. Now: the lock persists the handoff path; _compact_worker gains resume=True
  (skip the handoff step, go straight to /compact + re-read); _compact_recover() runs on boot and, for any
  'running' lock owned by THIS instance whose process is gone, RESUMES the compact if the handoff is written +
  the session is live (else releases the stale lock). So a restart during a compact self-heals instead of stalling.

## 0.99.77 -- 2026-06-30
- ACCEPT A TRANSFER -> graceful origin stand-down: after the destination opens (warm), a gentle countdown popup
  offers to FILE AWAY the previous conversation you moved from -- "Keep it open" (pin) or "File it now" (or let the
  ~90s timer expire) which harvests + closes it. When the origin tmux session dies, loadSessions reconciles PANES
  so its split-pane just drops out -- works in split-screen + mobile single-pane. Broken-out /term tabs (desktop +
  mobile) now check /api/session-exists on disconnect and say "filed away (resumable)" instead of the wrong
  "session lives on". (hoOriginStandDown/#soAlert; handoff_accept returns from_session+origin_label.)

## 0.99.76 -- 2026-06-30
- FIX: accepting a warm transfer that opens a FRESH session now actually feels warm. The packet was being passed
  only as a silent --append-system-prompt (the agent HAD the context but never surfaced it), so you landed in a
  cold blank Claude prompt. Now the fresh launch also gets a SEED first-turn (_handoff_kickoff) that makes the
  agent OPEN by greeting + summarizing what it's picking up (goal, where it left off, next step) and asking to
  proceed -- no re-explaining. (The resume-into-existing path was already warm via _handoff_message.)

## 0.99.75 -- 2026-06-30
- PRE-ARCHIVE HEADS-UP: idle conversations are no longer tidied up silently. When one first becomes eligible, a
  calm corner popup shows what'll happen + why, with a live COUNTDOWN (30-min grace window) and Keep it open /
  Snooze 2h / Let it go now. A separate 10-min reconcile loop makes the countdown honest; it only retires after
  the grace window AND only if still idle/un-held. (reconcile_once grace; pending_archives + /api/pending-archives;
  session_hold gains an hours snooze + cancels the pending; #arAlert popup + countdown. Manual "Reconcile now"
  stays immediate.)
- FIX 1 -- decluttered the Transfers desk: housekeeping digest shows a "docs tidied" chip + only 3 sample doc
  issues (not a dump); the archived list collapses behind a count.
- FIX 2 -- auto-tidy over-managed docs: housekeeping strips the redundant system-primer (CC:BEGIN block) from
  deep sub-tool CLAUDE.md files (an ancestor already delivers it) -- clearing the "carries a managed CC block"
  Doctor warnings (178 of them on AFP) and the context bloat. Hand content untouched; idempotent. Proven.

## 0.99.74 -- 2026-06-30
- "Review the move" is now a FOCUSED POPUP, not the whole admin desk. The gentle drift prompt's "Review the move"
  opens a clean modal for THAT one transfer: what drifted, where it'd go (from -> to box), a plain "why we move
  things" explainer (records stay clean, your current session stays put, declining won't ask again), how many
  pieces of context it carries, and Move it there / Keep it here. Decide in one place; the full Transfers desk
  stays available for power users. (hoReview/hoReviewAccept/hoReviewDecline; the corner prompt routes here.)

## 0.99.73 -- 2026-06-30
- Drift-sweep PRECISION (a "well-formed but wrong" false positive seen on AFP: Pipeline/solawave -> Pipeline):
  - SAME-LINEAGE GUARD: never propose moving a conversation into its own ANCESTOR or descendant (a client folder
    up into its generic parent category isn't a transfer -- it's demoting specific work into the container above it).
  - ALWAYS model-confirm an auto proposal when `smart` is on (drift proposals are rare -> precision > a cheap call),
    with a sharper prompt: a CLIENT/PROJECT folder is a proper noun, and a budget/proposal/call ABOUT it still
    BELONGS to it even when the name isn't repeated -- so on-topic work no longer gets flagged. (smart off -> only a
    strong lexical route proposes, conf>=0.6.) Cleaned the stray proposals.

## 0.99.72 -- 2026-06-30
- MULTI-NODE-PER-INSTALL hardening (the real production topology: an overseer + one-or-more project nodes share
  one Mac's tmux server). Session-acting loops were using the UNSCOPED _live_sessions() and could act on OTHER
  co-located nodes' sessions. Now ownership-gated like auto-compact already was:
  - reconcile/auto-archive only retires sessions in THIS node's project tree (_session_scope is not None) -- so
    node A can no longer archive node B's idle session.
  - (with v0.99.71: drift sweep requires a real sub-folder lane + the org/overseer skips session-acting entirely.)
  Each node manages only its own conversations; the overseer oversees the fleet.

## 0.99.71 -- 2026-06-30
- FIX drift-sweep false positive: the unscoped OVERSEER (ROLE=org) shares the tmux server and sees every node's
  sessions, so it was proposing warm transfers on OTHER nodes' conversations -- scoped against the wrong project
  root, producing garbage ("a conversation in ? drifted to ...; belongs in command-center"). Now (1) the org/overseer
  skips the session-acting passes entirely (drift sweep + reconcile) -- each PROJECT node manages its own sessions;
  (2) drift requires a REAL sub-folder lane (skip None + root "") -- no lane = nothing to drift from. Cleaned the
  stray proposals.

## 0.99.70 -- 2026-06-30
- DOC: docs/ENGINEERING_AUTOPILOT.md -- the canonical reference for the whole discipline system: how the context
  payload is controlled (Menu/Scout/Vault) AND how engineer-grade habits are auto-enforced (folder structure,
  filing, warm-transfer routing, record-keeping, self-curating notes, housekeeping) -- Assisted/transparent/opt-out.
  Pointer added to command-center/CLAUDE.md so agents touching context/lifecycle code read the model first.

## 0.99.69 -- 2026-06-30
- SELF-CURATING RECORDS -- folder memory stays tight + high-signal automatically (no manual upkeep, no bloat):
  - DEDUP ON WRITE: module_note skips a learning that substantially repeats one already filed (token overlap >=0.75).
  - NO MORE POINTER CRUFT: stopped filing "a conversation ran here (date)" lines into CC:NOTES on archive -- a
    session's existence + resumability lives in the archive ledger, so folder notes hold ONLY durable learnings.
  - PERIODIC CURATION: _curate_notes_once() (hourly housekeeping, gated by smart) -- when a folder's learnings pass
    a threshold, a free claude -p pass dedupes, merges, drops superseded/stale, and resolves [CONFLICT?] tags,
    rewriting CC:NOTES as a curated index. Conservative (only accepts a shorter result), throttled ~once/day per
    folder, BACKS UP originals (_notes_curate_backup.jsonl). Shown as "records tightened" in the housekeeping digest.
    Proven: 16 bloated notes -> 10 clean (paraphrases merged, .env-vs-vault conflict resolved), backup written.

## 0.99.68 -- 2026-06-30
- Warm-transfer UX (James's spec): the drift proposal is now transparent + gently insistent + opt-out.
  - GENTLE POP-UP: when a conversation drifts, a dismissible gold corner prompt appears on ANY lens -- "this looks
    like it belongs elsewhere: <from> drifted to <topic>, belongs in <dest> -- want to move it there?" with
    Not now / Review the move. Suggestion, not alarm (no red, no pulse).
  - CLEARER CARD: spells out exactly what accepting does (open/resume the home agent, or CREATE a new <subject>
    folder under <parent>), notes your current session stays put. Buttons: "Move it there" / "Keep it here".
  - STICKY DECLINE: "Keep it here" now suppresses that same drift so it is NOT re-proposed (topic-keyed; a
    genuinely new drift later still asks). Proven: propose -> decline -> next pass proposes 0.

## 0.99.67 -- 2026-06-30
- WARM TRANSFER + HOUSEKEEPING, now ENFORCED by the platform (not just asked of the agent). Root cause of "no
  agent ever passed me off": the transfer was an ADVISORY line in the agent's prompt that models never self-act
  on (0 proposals in the system's entire history). Fix = the server now does the watching.
  - `_drift_sweep()` (in the hourly housekeeping pass): watches every live SCOPED work conversation, and when its
    topic has drifted off the folder it sits in, the SERVER proposes a warm transfer to the right home -- routed
    deterministically, with the `smart` subscription model confirming ambiguous cases (high-precision, deduped,
    6h cooldown). Proven live: a read_write session working on patches -> auto-proposed read_write->patches (90%).
  - VISIBLE housekeeping: new `Automatic housekeeping` digest card in the Transfers lens (+ `/api/housekeeping-digest`,
    `/api/housekeeping-run` to run a pass on demand) -- shows conversations watched, transfers proposed, idle retired,
    doc issues, map regen, + a recent-activity timeline. The discipline is no longer invisible.
  - Archive tuning: service/infra sessions (node servers / live product / brain) are now protected from auto-archive
    (`_is_service_session`), so reconcile only retires real idle WORK conversations.

## 0.99.66 -- 2026-06-30
- DESIGN SYSTEM LOCKED IN (so the unified look never needs re-sweeping):
  - Finished the de-emoji sweep -- extended it to card titles/headers/labels (h3/h2/span/label/summary), removing
    the last 28 decorative emoji (module 🧩, folder 📁, etc.) the earlier pass missed. Icon-only controls keep a glyph.
  - NEW `command-center/ui_lint.py` -- the design-system ENFORCER. Flags native confirm/prompt/alert, off-palette
    GitHub hexes in inline styles, inline-colored badges, and decorative chrome emoji. Wired into the preship gate
    (`preship.py`), so ANY future feature/extension that hand-rolls a one-off UI primitive FAILS THE SHIP.
  - NEW `docs/DESIGN_SYSTEM.md` -- the one standard (components + 4 hard rules + how to add a lens). Pointers added
    to `command-center/CLAUDE.md` and `extensions/AUTHORING.md` so agents building features/extensions see it first.

## 0.99.65 -- 2026-06-30
- Badge code-hygiene: moved 30 status badges from inline `style="background:#x22;color:#x"` to an exact-match
  `.badge.bdg-*` palette in CSS (zero visual change -- verified the computed colors match to the pixel). The 11
  remaining inline badges are runtime-COMPUTED colors (e.g. status-driven), which legitimately stay inline.
  All badge styling is now centralized + named.

## 0.99.64 -- 2026-06-30
- FINAL polish: tokenized the last off-palette surfaces that used hardcoded GitHub colors (off-brand blue/green).
  - Login page (first screen): GitHub green/blue -> gold-brand dark card w/ gold accent bar, gradient button, focus
    ring, emoji dropped. The secure-credential modal (#cfsec), the "brief ready" banner (was GitHub blue), and the
    Drive preview overlay (#pvOverlay) all reskinned to design tokens (gold theme).
  - Code hygiene: 19 delete/remove buttons moved from inline `style="color:#f85149"` to the `.mini.danger` class.
  - (Remaining #0d1117 are intentional dark code-block backgrounds.)

## 0.99.63 -- 2026-06-30
- Finished the dialog sweep: the embedded terminal page (TERM_PAGE, 3 confirms) and Ralph-loop page (RALPH_PAGE,
  1 confirm) now use self-contained styled dialogs matching the palette. ZERO native browser pop-ups remain
  anywhere in the product (verified across all three page strings). node --check clean on every page script.

## 0.99.62 -- 2026-06-30
- PRO DIALOGS: replaced all 56 native browser pop-ups in the dashboard (the gray OS `confirm()`/`prompt()`/`alert()`
  boxes -- the most "vibe-coded" thing left) with styled, promise-based modal dialogs that match the design system.
  - New helpers `confirmM()` / `promptM()` / `alertM()` (after showM): own `#ccDlg` overlay at z-index 10050 so they
    STACK above any open modal/sheet; Esc + backdrop-click cancel; Enter confirms; danger variant for destructive ops.
  - Converted all 56 call sites to `await`; made 9 sync handlers async; `gmcCmd` link-insert saves/restores the
    contenteditable selection (a focus-stealing modal would otherwise lose it). Validated with `node --check` on the
    full 617K-char dashboard script (0 syntax errors) + headless functional tests (confirm resolves true/false,
    prompt returns value/null, 0 console errors).
  - Also added `.btn.danger` / `.mini.danger` semantic classes.
  - NOTE: the embedded terminal page (TERM_PAGE) still has 4 native dialogs (separate surface, no helpers yet) -- next.

## 0.99.61 -- 2026-06-30
- DE-CARTOONY emoji sweep (site-wide, James-approved direction): removed DECORATIVE emoji from all lens headers,
  section labels, panel titles, buttons, and dropdown options across every screen -> clean, enterprise/SOTA chrome.
  - Done POSITIONALLY (stripped only at label-START: after <b>, button/option open-tags, cc-h-ic header glyphs,
    sec() titles) so FUNCTIONAL status indicators embedded in data rows/badges are untouched: 🟢/⚪ account state,
    ⚠ warnings, ⏳ running, the ✅/⬆️/⚠️/⬇️/❔ fleet-drift legend + chips, task source icons, file-type icons.
  - Monochrome UI glyphs kept as affordances (▶ start, ✕ close, ＋ add, ✓ accept, ↻/⟳ refresh).
  - GUARD: never strips an icon-ONLY control (📎 attach, ⏰ snooze, 🗑 archive, ☰ menu) -- those keep their glyph
    so the button stays visible. Verified headless across lenses: 0 empty controls, 0 console errors.

## 0.99.60 -- 2026-06-30
- SLEEKNESS pass (de-cartoony, brand preserved): global visual-treatment refinements that calm the whole UI
  uniformly without a rebrand (gold identity + logo kept).
  - `--glow` gold bloom (0 0 26px gold) -> neutral depth shadow (0 10px 28px black). Kills the "neon/casino" pop
    on every card/hover/panel at once.
  - `--grad` 3-stop shimmer (#c9a227,#e8c547,#c9a227) -> refined 2-stop (#d6b23c,#c9a227). Calmer CTAs.
  - Logo wordmark: removed the continuous `brandsheen` shimmer animation (now a clean static gold wordmark).
  - `.badge`: bubbly fully-rounded 800-weight pill -> crisp 7px-radius 700-weight tag (matches the cc-tag system);
    instantly upgrades all ~75 badge usages site-wide.
  - `.modal`: 18px radius + theatrical 80px shadow -> 14px + restrained shadow.
  - CONSISTENCY: the `COMMS_INP` input constant (~19 hand-rolled inputs across Brief/Calls/Capture/Context/Build)
    now uses design tokens (var(--card2)/--line/--ink) instead of hardcoded GitHub hexes -> matches `.cc-in`.

## 0.99.59 -- 2026-06-30
- STANDARDIZATION: core-integrity no longer fingerprints markdown docs (`.md`, esp. per-module `CLAUDE.md`).
  Those legitimately carry per-node `CC:NOTES`, so signing them made EVERY appliance perpetually report the
  same file as "drifted" (109/110 of AFP's integrity-log entries) and lit a red Doctor error -- a cosmetic
  "why is this node different" wart. Docs were never meant to be in the hashed set (code/config only). Now every
  install reports clean + identical integrity. (Ships with the uniform-UI work; re-signed core drops the .md files.)
- (carries the 0.99.58 uniform-UI design system below to the full fleet.)

## 0.99.58 -- 2026-06-29
- UNIFORM UI design system (cc-*): one consistent, modern style for every repeated surface, replacing the
  per-lens stacked full-width "cards" that wasted horizontal space and read as unfinished.
  - FIXED a real layout bug: the masonry grid resolved its auto rows too short (~74px), so any tall card
    OVERFLOWED and visually OVERLAPPED the cards below it (40 overlaps on Marketplace alone). One-line global
    fix (`.wrap{grid-auto-rows:max-content}`) -> 0 overlaps on EVERY card-grid lens.
  - New shared classes: `.cc-head` (slim lens header), `.cc-list`/`.cc-item` (dense action rows),
    `.cc-grid`/`.cc-tile` (equal-height tiles, pill badges that never clip, footer-pinned actions),
    `.cc-panel` (uniform form/config blocks), `.cc-tag`/`.cc-pill`/`.cc-sec`/`.cc-chip`, `.cc-in` (uniform inputs).
  - Applied to: Tasks, Notes, Marketplace/Extensions, Ideas, Change Requests (CCR), Propose, Claude Accounts,
    Settings. Each verified headless (0 overlaps, 0 console errors).
  - Next: site-wide consistency pass (modals/popups, inputs, buttons) to collapse the remaining ad-hoc variants.

## 0.99.57 -- 2026-06-29
- ENTERPRISE secret UX: agents no longer have to re-learn the vault each session.
  (1) cc-* CLIs now resolve on EVERY launched session's PATH (chief, agents, teams, ralph, resume, audits) --
  one _CC_PATH constant (includes BASE) replaces 10 inline PATH exports where only the main launch had BASE,
  which is why agents hit "command not found: cc-secure" and hand-located it.
  (2) NEW `cc-secure get <KEY>` + localhost-only, token-gated /api/secret-resolve -- the missing "USE a stored
  key" primitive (resolve vault-first for a probe: K="$(cc-secure get <KEY>)"). No more hand-decrypting the vault.
  (3) The brief's SECRETS contract now points at `cc-secure get` for using a key and notes the cc-* CLIs are on PATH.
## 0.99.56 -- 2026-06-29
- Chief brief: two routing/diagnosis rules baked into every node's Chief of Staff launch prompt.
  (1) ESCALATION ROUTING -- operator-facing issues go UP to Mission Control (target 'mission-control'), never
  to a sibling node (which can't act on them); operator<->operator relays use operator-notes (Messages), not
  the agent mesh. Fixes AFP's chief sending Sarah's escalations to hptuners instead of MC.
  (2) VAULT-AWARE secret diagnosis -- when checking if an API key is configured, the VAULT is ground truth
  (keys resolve vault-first); a blank field in cc.config.json does NOT mean the key is unset. Fixes the false
  "Granola api_key not set" alarm (the key was in the vault and authenticating fine; the chief only read cc.config).
## 0.99.55 -- 2026-06-29
- Running Ralph loops now also appear in the bottom Sessions TASKBAR (dock), not just the Sessions list --
  session_bar() was filtering out kind=loop. Pairs with v0.99.54 so you can click a live loop tile and watch
  it. Only running loops show (no session = no tile); services + web-server processes stay hidden.
## 0.99.54 -- 2026-06-29
- Running Ralph loops now appear in the Sessions taskbar of the node that owns them, so you can open the
  terminal and watch one live. They were scoped out because a loop's tmux session runs with cwd = the engine
  dir (not under the project root), so it failed the "in this project" test. Now a ralph-<name> session counts
  as this console's when its loop dir is in this node's RALPHDIR. Labelled "Ralph: <name>", kind=loop, protected
  (can't be casually closed). Co-located instances (one shared tmux server) can watch each other's; a separate
  machine has its own tmux server and won't see them. Only running loops show (stopped/archived have no session).
## 0.99.53 -- 2026-06-29
- Ralph lens: "🗄 Clear N done/stopped" button in the Active header bulk-moves every FINISHED loop
  (done / halted / stopped, and not still alive) to Previous loops in one click, so the active list stops
  stacking up. Running/paused/idle/blocked loops are left alone. Reversible (they stay readable under Previous).
  New ralph_archive_finished() + POST /api/ralph-archive-finished; button only shows when there's something to clear.
## 0.99.52 -- 2026-06-29
- Account recommender now keeps a ~10% EMERGENCY RESERVE on each weekly window (operator's "get lean" idea):
  an account at <=10% weekly free is parked as reserve (was a 5% hard floor), so it's no longer recommended for
  burning. This (a) fixes the thrash where, right after switching to a fresh account, it flipped back to a
  near-maxed one over its last ~7% (a sliver that risks a hard weekly lock + a wasteful switch round-trip), and
  (b) leaves a backup sliver on every login. NEW emergency path: if EVERY usable login is down to its reserve,
  it spends the reserve of the one whose weekly resets SOONEST (refreshes first) to limp along, keeping the
  others as backup -- flagged "⚠ emergency". The model-vs-raw 95/93% flip across the old 5% line is moot now.
## 0.99.51 -- 2026-06-29
- Account recommendation "why" now states the REAL reason instead of a hardcoded "weekly resets soonest" on
  every pick. The score still prefers the soonest-resetting account, but only among READY ones -- the truly
  soonest-resetting accounts are often excluded (maxed -> resting, or live on another node -> reserved). So:
  with 2+ usable logins it says "resets soonest of your N available logins"; when the pick won by elimination
  it says "the only login with headroom right now -- your others are maxed or reserved". (Fixes the misleading
  case where the recommended account actually resets LAST.) Compact-strip ▶ tooltip now shows the real why too.
## 0.99.50 -- 2026-06-29
- Account fuel gauges: show each window's reset by its own % (5h reset next to the 5h %, weekly reset next to
  the weekly %) instead of a single combined "soonest reset"; and mark which readings are LIVE vs VIRTUAL.
  An account idle on every machine accrues nothing, so its gauge is its last live reading carried forward with
  the reset clock advanced virtually -- now labelled "idle · est" (compact strip) and "est." with a hatched
  track (detail cards), so a confidently-correct idle 0% no longer looks like broken/no-data. The live login on
  each machine reads for real (per v0.99.49's settle fix).
## 0.99.49 -- 2026-06-29
- FIX the 5h/weekly fuel gauges reading a false 0%. The /usage scrape (_read_usage_session) broke its poll
  loop as soon as session OR week parsed -- but `claude /usage` fills the windows PROGRESSIVELY ("Scanning
  local sessions…"), so it captured the SESSION window mid-scan at 0% with no Resets line the instant `week`
  appeared. Now it waits until both windows are present, the session has rendered its Resets line, AND the
  reading is STABLE across two consecutive polls before accepting (proven: captures the true 3% + reset clock
  instead of 0%/none). This also restores the reset timestamp the gauges need to VIRTUAL-RESET idle accounts.
  Context: an account only burns tokens while it's the live login on a machine (~2 live max, one per macOS
  user); accounts idle on both provably accrue zero, so _win_view carries their last reading forward and
  rolls the reset clock virtually -- which only works once the live read captures an accurate pct + reset_ts.
## 0.99.48 -- 2026-06-29
- Per-account usage attribution on single-account (account_wallet) nodes. Their usage was ALL falling to
  "(before tracking)" because the active-account log is only written on a SWITCH, and a wallet node never
  switches (and the keychain baseline doesn't fire under headless/token auth). Boot now falls back to
  _current_email() (~/.claude.json) and, on a wallet node with an empty log, seeds it BACKDATED so ALL of the
  node's usage attributes to its one account. Fixes e.g. AFP's usage showing under "(before tracking)" instead
  of Sarah's account (so per-account usage now moves).

## 0.99.47 -- 2026-06-29
- Notes notebook: full searchability + summarizer hardening + ecosystem wiring fixes.
  - Lens now has a search box (server-side full-text over title/summary/raw text/tasks/decisions/tags).
  - Summarizer (_structure) parses robustly (strips fences, retries once if invalid) so summary + action
    items reliably come back; nb_apply now routes BOTH tasks AND follow-up reminders into the Tasks list.
  - Notes ingest the raw text (not just the paraphrased summary) into the context layer, so they're findable
    by anything they contain in the global context search + assemble + brief.
- CONTEXT LAYER fixes (pre-existing, fleet-wide): context.search() crashed on a no-match query (_fetch([])
  returned a list, then .values()) -- now returns []; added PRAGMA busy_timeout=8000 so concurrent writes
  wait for the lock instead of failing with "database is locked" (which was silently dropping ingests).

## 0.99.46 -- 2026-06-29
- NEW: Notes notebook (core) + renamed the old Notes lens to "Messages".
  - "Notes" is a new core lens: write OR dictate a note naturally; on Save a headless claude -p structures it
    into {title, summary, tasks, decisions, reminders, tags}. Review-first: tasks are added to the Tasks list
    on approval; the note is ingested as a context event (kind: note) so it feeds retrieval AND the Morning
    Brief (new "notes" brief source); notes are draggable into any session.
  - Voice: the browser records mic audio and uploads it; the server transcribes via Deepgram (key VAULT-FIRST,
    DEEPGRAM_API_KEY) -- so it works from any device the user opens the dashboard on, key never exposed to the
    browser. Shows "voice off" until the key is added.
  - `notebook.py` engine + /api/note-{list,save,apply,delete,transcribe}; the "note" sendable.
  - The previous operator<->operator Notes lens is now labelled "Messages" (id unchanged) and its layout bug is
    fixed (it lacked grid-column:1/-1 so it rendered narrow + overlapping inside the card grid).

## 0.99.45 -- 2026-06-29
- Routine scheduler: `_routine_last_fire` now honors a `weekdays` LIST (was single `weekday` only) -- a
  multi-day schedule like the Morning Brief's Mon-Fri silently fell through to DAILY (it would also fire on
  weekends). Morning Brief now schedules Mon-Fri correctly (launchd Sun=0 convention).

## 0.99.44 -- 2026-06-29
- Files preview: the slide-out "new file ready" card now opens the SAME full-format preview modal as the
  Files lens (was a limited image/PDF/text inline that showed "No inline preview for this type" on Office
  docs). Both entry points now handle every supported format.

## 0.99.43 -- 2026-06-29
- FILES PREVIEW for common formats (was images-only). A "Preview" button on every file opens an in-dashboard
  modal: images / PDF / audio / video / HTML / text+markdown+code render natively; Office docs convert
  SERVER-SIDE via macOS built-ins (no new deps) -- Word/RTF/ODT -> HTML (`textutil`), and
  xlsx/pptx/keynote/pages/numbers/etc -> a Quick Look PNG (`qlmanage`). New `/api/file-preview` endpoint +
  `file_preview()`; honors the same secret guard as file-get. Audio preview means a Morning Brief mp3 plays
  right in the Files lens.

## 0.99.42 -- 2026-06-29
- Morning Brief robustness + UX: each source is now isolated in try/except (one bad source can't kill the
  whole brief -- a calendar event with a string `start` was crashing generation); the brief is marked
  `unread` and the dashboard SURFACES it as a top banner on open (pop up if already open / there when she
  opens), tap to open+play, then it's marked seen (`/api/brief-seen`). Source errors are surfaced too.

## 0.99.41 -- 2026-06-29
- Morning Brief: completed the official extension authoring -- added the required SETUP.md + AGENT.md +
  CLAUDE.md (extension.json declared them; only extension.json existed). No code change.

## 0.99.40 -- 2026-06-29
- Morning Brief: its config now UPSERTS the run routine (creates it if missing) so the brief owns its own
  schedule regardless of a node's extension_routine_host gate -- needed so it runs on tenant nodes (AFP).

## 0.99.39 -- 2026-06-29
- NEW EXTENSION: **Morning Brief** (`morning-brief`, lens:brief). A scheduled, voice-read brief of your day +
  what's coming, synthesized from your real data.
  - Runs ~an hour before your start (configurable: open_time - lead_minutes -> the routine's schedule).
    Per-project (each console briefs its own day).
  - **Extensible SOURCE registry** (`morning_brief.py`): calendar + gmail + tasks + granola + slack today;
    add a source = add a function. Built on the existing context layer + live Google/Granola accessors. Each
    item stays cited.
  - Synthesis via headless `claude -p` (Max sub, no metered key) -> 2-3 spoken paragraphs (today's shape /
    coming up / prep). Written in the owner's **VoiceMatch style** (their smart-reply writing profile) so it
    sounds like them.
  - **Natural voice (browser playback, never the server's speakers):** the server renders an mp3 (ElevenLabs
    or **OpenAI tts-1-hd** -- vault key, female voices like nova; macOS `say` only as a last-resort
    file-writer) and the Brief lens plays it in an `<audio>` element on the operator's OWN device, with
    best-effort autoplay (browsers need one click for audio). TTS fallback reason is surfaced when it can't
    use the preferred voice.
  - Brief lens: today's brief + play + history + config (start time, lead, horizon, sources, voice, autoplay);
    `/api/brief`, `/api/brief-generate`, `/api/brief-config`, `/api/brief-audio`; `cc-brief` CLI for the routine.

## 0.99.38 -- 2026-06-29
- ADMIN-SHELL staging made reliable (CCR from homeassistant, ccr-1782711953408). Staging a sudo/interactive
  command for the operator via raw `tmux send-keys` failed silently for two reasons: (1) the admin session
  slug didn't match the `cc-<node>` server slug (`admin-home-assistant` vs `admin-homeassistant`), so an agent
  guessing the name staged into a session the operator wasn't viewing; (2) a pane in tmux copy-mode swallows
  send-keys with no surfaced error.
  - New **`POST /api/admin-stage {text[,run]}`** primitive + `admin_stage()`: resolves the CANONICAL admin
    session (creating it if needed -- no guessing), drops copy-mode first (`send-keys -X cancel`), sends the
    LITERAL text (no Enter unless run=true), then reads the pane back and returns `staged:true` only when the
    line is CONFIRMED present.
  - `_admin_session_name()` is the single canonical name (cc.config `admin_session` can override); `/api/sessions`
    now flags the admin session with `is_admin:true`; `/api/admin-shell` returns the canonical name.
  - Chief + agent launch briefs now tell agents to use `/api/admin-stage`, not hand-rolled send-keys.
  - docs/SESSIONS_AND_SUDO.md rewritten around the primitive (with the why + discoverability fallbacks).

## 0.99.37 -- 2026-06-29
- GRANOLA matcher PRECISION (ext v1.2.1) -- follow-up CCR from AFP (ccr-1782713093843). The v0.99.35 attendee
  fix made client-matching FIRE, which exposed that `match_client()` matched aliases as UNANCHORED SUBSTRINGS
  against title+emails -> false positives (alias 'OMM' matched inside 'vlivcommunications.com'; bare slug
  'aldo' inside 'ronaldo'). Now precise: a DOMAIN alias matches attendee email domains STRUCTURALLY (equal or
  subdomain); a NAME/brand alias matches the TITLE by word boundary OR an exact email-domain label ('acme' ->
  @acme.com, not @acmecorp.com); free-mail domains (gmail/outlook/...) are ignored; the slug fallback is
  word-boundary anchored. 10 matcher cases tested (good matches kept, false positives killed).

## 0.99.36 -- 2026-06-29
- RESILIENCE hardening (post-DoS, items 2+3 of the fleet resilience plan):
  - **Doctor SSD / Full-Disk-Access read-probe (detect, never act).** `doctor()` now probes a node's external
    (`/Volumes/...`) project/deliverables path and classifies: readable (ok) / present-but-EPERM (FDA grant on
    the tmux binary lapsed -- e.g. after a `brew upgrade tmux` changes its signature -> `sev:err` with the
    re-grant steps) / not-mounted (`sev:warn`). This is the early-warning for the exact "Operation not
    permitted" SSD failure that wedged the fleet -- it ALERTS, and explicitly does NOT restart/kill (a restart
    re-attaches the same un-granted binary and hides the cause).
  - **Pre-ship `kill-server` footgun gate.** `preship.py` now FAILS the ship if `tmux kill-server` appears in
    any shipped `.sh` (it nukes the shared brain tmux server -> every node + chief + the operator's terminals
    at once; the 2026-06-28 self-DoS was a one-shot kill-server script under launchd KeepAlive). Allowed only
    with an explicit `# preship-allow: kill-server` marker on an interactive break-glass tool.
  - Removed the disabled incident artifact `/tmp/cf-storage-recovery.sh.DISABLED` (its contents are preserved
    in the post-mortem deliverable).

## 0.99.35 -- 2026-06-29
- GRANOLA CALLS (ext v1.2.0) -- 3 fixes from AFP's first live API sync (CCR ccr-1782711514956):
  - **Client-matching now works out of the box on the API source.** `list_meetings()` reads the sparse
    `/v1/notes` LIST (no attendees), so `match_client()` had no emails and `client_map` domains never matched.
    New `get_detail()` pulls `attendees[].email` + `calendar_event.invitees[]` from the DETAIL endpoint
    (already fetched for the transcript -- no extra request), and `gr_sync` matches AFTER fetching detail.
  - **Sync no longer looks hung.** `gr_sync` persists state INCREMENTALLY per proposal + exposes
    `sync_progress {processed,total,running}` (was: one save after the whole multi-call loop).
  - **Sync errors are visible.** `gr_sync` records `last_sync_status`/`last_sync_error` into state on every
    return, surfaced by `gr_proposals()` + the Calls lens -- so a bad key / E2E-on failure shows instead of a
    silent empty list (the daemon-thread `/api/granola-sync` that discarded the return no longer hides it).
  - `get_transcript()` kept as a back-compat wrapper (used by the drag-a-call-to-session sendable).

## 0.99.34 -- 2026-06-29
- CHIEF DURABILITY (fleet resilience): the Chief of Staff is now hard to leave detached.
  - **Length-safe `chief_open`**: the launch prompt (instruction block + system brief + full roster) is now
    written to a file and passed via `"$(cat ...)"` instead of inlined as a tmux command argument. Inlining
    overflowed tmux's command buffer ("command too long", rc=1) once a node's roster grew past ~16KB, which
    silently prevented the chief from ever starting and surfaced as a MISLEADING "check claude auth/login"
    error. The biggest-roster node (Mission Control) hit this first; it was a scaling time-bomb for all nodes.
  - **Real error surfacing**: `chief_open` now branches on the actual `new-session` stderr (e.g. "too long")
    instead of always blaming auth.
  - **Out-of-process revival**: each node writes a launch descriptor to `/tmp/cf-chief-launch/<chief>.json`;
    the launchd `cc-session-watchdog.py` (45s) now RECREATES a dead chief from that descriptor -- so a chief
    is revived even when its own server is down/crash-looping (the in-process watchdog dies with the server).
    Descriptor is (re)written on every `chief_open` incl. the resumed path + a boot-time ensure, so a
    continuously-alive chief is still revivable.
  - **Tightened in-process watchdog**: 15s boot settle / 60s poll / 120s thrash-bound (was 75 / 300 / 540).
  - **SSD-gone fallback**: chief/session `cwd` falls back to `CC_HOME` when the SSD project path is missing,
    so the chief (the mesh comms endpoint) stays up even if `/Volumes/Samsung990PRO` is unmounted.

## 0.99.33 -- 2026-06-28
- SELF-CONTAINED NODE LAYOUT is now the enforced standard (fixes the ATEM "console shell vs codebase split").
  A node's project lives INSIDE its bundle at `<bundle>/project/` (project_root in-bundle), so each node is ONE
  tidy, portable folder -- never an external path with a leftover stub + a chief stranded in it.
  - **New `--adopt-source <path>` in `cc-newinstance.sh`** + `adopt_source` through `instance_provision` + an
    **"Adopt from" field** in the Add-a-ClaudeFather wizard: adopting EXISTING code now COPIES it INTO the
    bundle's project/ at provision time (project_root stays in-bundle). Onboarding then structures it in place and
    the Chief launches there -- no repoint, no stub, no stale chief. Previously "adopt" forced you to point
    project_root externally, which created exactly that split (ATEM: chief stranded in the stub `/project`,
    reading "self-contained bundle" while the real code sat at a sibling path).
  - Converted the live nodes to the standard: ATEM + Home Assistant code moved into `<bundle>/project/`, chiefs
    relaunched in the right cwd, external dirs removed, HA secrets re-locked to 0600. shopos already conformed.

## 0.99.32 -- 2026-06-28
- ONBOARDING BRIEF -- folded back the JUDGMENT learnings from the first real runs (so future installs don't
  depend on the model being clever that day):
  - **Secrets nuance:** vault LOOSE/hardcoded keys, but NEVER delete/relocate a secret the app itself reads as
    its config mechanism (HA `secrets.yaml`, a runtime `.env`) or that is the node's OWN access path (a token
    that, if removed, cuts access) -- leave those in place (mirror to the vault if useful), and don't move
    individually-deployed config files. HA's agent had to override the old "vault everything" brief by hand; now
    it's the instruction. When unsure -> propose, don't act.
  - **Orientation:** the agent runs INSIDE the codebase (cwd); the ClaudeFather node is a SEPARATE bundle whose
    command-center holds the cc-* CLIs (on PATH) and serves the Doctor at the node's local port. Both first-run
    agents wasted effort untangling node-vs-codebase -- now stated up front.

## 0.99.31 -- 2026-06-28
- CONSISTENCY (from the first real onboardings -- ATEM + Home Assistant):
  - **cc-* CLIs now resolve as bare commands in every session.** The bundle's `command-center/` (BASE) is prepended
    to each launched session's PATH, so `cc-secure` / `cc-note` / `cc-handoff` / `cc-task` / `cc-hold` work unqualified.
    Before, onboarding/agents reported them "not reachable" and couldn't auto-vault secrets or file learnings (the
    briefs invoke them bare). This was why HA's found secrets weren't vaulted.
  - **Per-account fuel gauges (5h / weekly batteries) now AUTO-ENABLE.** `account_wallet` defaults on when this macOS
    USER already has saved Claude accounts with usage windows (`~/.claude/_cc_acct_windows.json`, shared per user) --
    explicit cc.config `account_wallet` still wins. Co-located appliance nodes (ATEM/HA) were silently `false`, so the
    Sessions-tab batteries never rendered though the data existed. Fresh users with no accounts stay off (no empty wallet).
  - **Onboarding report has a fixed name + path.** The agent now writes EXACTLY `deliverables/ONBOARDING_REPORT.md`
    (HA wrote `ONBOARDING_REPORT.md`, ATEM `ONBOARDING-REPORT.md` -- inconsistent surfacing). Always a clean download.

## 0.99.30 -- 2026-06-28
- FIX: a launched agent's kickoff turn (onboarding) was TYPED into the fresh session but not always SENT -- the
  post-launch send-keys raced claude's boot (splash / MCP-auth / trust), leaving the message unsubmitted. Now the
  kickoff is passed as claude's positional SEED prompt (`launch(seed=...)`), which claude runs reliably once
  booted -- same mechanism as the new-folder brief. No more "message sitting unsent."

## 0.99.29 -- 2026-06-28
- ONBOARDING wired into ADD (the gap: creating a project landed in the Chief, onboarding never fired). The "+ Add
  a ClaudeFather" wizard now has an **Onboarding** choice (Adopt existing code / Scaffold new / none); it threads
  wizard `onboard` -> `instance_provision --onboard` -> the new bundle's cc.config `onboard_pending`, and a
  FIRST-BOOT hook (`_onboard_first_boot`, run-once marker) auto-launches Project Onboarding on the new node, which
  structures the project then hands to the CoS. (`cc-onboard` is still the manual trigger for existing nodes.)

## 0.99.28 -- 2026-06-28
- ONBOARDING model split (correction): the STRUCTURING is high-judgment, so the Onboarding agent now runs on the
  node's BEST model (Opus default) and itself writes the layout/CLAUDE.mds; only the high-volume READING is
  delegated to CHEAP `claude-sonnet-4-6` subagents (config `onboard_reader_model`) that read + summarize and
  report back. (Was: whole agent on Sonnet.) `_onboard_brief` instructs the agent to pass the cheap model to the
  Task tool for readers and never structure on them; `onboard_start` launches with model=None (best). Verified.

## 0.99.27 -- 2026-06-28
- PROJECT ONBOARDING -- bring a just-added project up to ClaudeFather spec automatically, then hand to the Chief.
  Two modes: ADOPT (point at an EXISTING codebase -> the Onboarding agent fans out parallel SUBAGENTS to read the
  whole tree, then structures + documents it to spec -- lean root CLAUDE.md + per-folder CLAUDE.mds + the module
  map + Doctor-clean + secrets into the vault -- WITHOUT moving code, proposing any reorg for review) and SCAFFOLD
  (new product -> a lean starter shell). Runs on a CHEAP model (`claude-sonnet-4-6`, config `onboard_model`); the
  CoS (Opus) takes over the actual work. `_onboard_brief()` + `onboard_start()` + `/api/onboard` + `cc-onboard
  [adopt|scaffold]` CLI; `launch()` gained a `model` tier. The Setup agent now points an existing-codebase node at
  `cc-onboard adopt`. Verified: onboarding launches on Sonnet with the playbook + a kickoff turn.

## 0.99.26 -- 2026-06-28
- FLEET-WIDE "All nodes" taskbar. The taskbar is built from LOCAL tmux, so cross-user/remote nodes (AFP runs as
  `sarahaios` on its own tmux; future T490 nodes are another machine) never appeared. Now the unscoped overseer's
  "All nodes" view ALSO aggregates each remote peer's sessions over HTTP (`_remote_sessions`, family-auth scrape,
  cached ~15s + refreshed in a background thread so the poll never blocks). Remote sessions show as read-only
  tiles tagged by node (e.g. "7th avenue - afp ↗") that DEEP-LINK to that node's dashboard -- a remote terminal
  can't be attached cross-user/cross-machine, so the tile opens the node's console instead. Co-located nodes stay
  live/drivable. "Mine" hides all of it; "All nodes" shows the whole fleet.

## 0.99.25 -- 2026-06-28
- SESSIONS TASKBAR CLARITY (the bottom bar). It was showing raw infrastructure on the unscoped overseer --
  the CC SERVER processes (cc-overseer/cc-carsearch/cc-shopos/hpcc) and the product SERVICES (t2tbridge =
  "Live bridge" blank, t2tcrons = "Bridge crons" stuck at an ssh password prompt) mixed in with real work.
  - Session classification: `_session_kind()` (work | chief | service | loop) + `_is_server_session()`. The
    taskbar now shows WORK + CHIEFS only -- server processes are hidden everywhere; services/loops live in their
    own lenses. Each session carries `kind` + `node` + `mine`.
  - Clear labels: a node's Chief shows "Chief of Staff - <node>" (your own just "Chief of Staff"), not a raw
    `chief-carsearch`. Other nodes' chiefs are protected (not casually killable).
  - OVERSEER toggle (your ask): a Mine / All nodes switch on the taskbar (shown only on an unscoped overseer) --
    "Mine" = just this console's sessions; "All nodes" = every node's, labeled by node. Persists per device.

## 0.99.24 -- 2026-06-28
- INSTALL TYPE asked at provisioning + a naming-collision fix. The "+ Add a ClaudeFather" wizard now ASKS the
  node **Install type** -- **agency** (official signed tools only; locked + safe; what a client/tenant gets) vs
  **developer** (also builds + runs operator-approved custom tools in the sandbox; your own installs) -- with an
  inline explanation of the difference. Threaded through: wizard `node_type` -> `instance_provision` -> new
  `cc-newinstance.sh --node-type` -> the bundle's cc.config `type`.
  - Collision fixed: the wizard's old "Type" selector was actually the TREE SHAPE (product vs agency clients/tools
    tree -> `integration`), not the sandbox node-type. Renamed to "Tree shape"; `instance_provision` no longer
    reads `type` as integration. The safe default stays agency when nothing is chosen.
  - (Local config, not shipped) all of James's nodes set `type=developer` (hptuners/MC/carsearch/shopos); AFP
    stays `agency` (Sarah's locked tenant). Net node model: every node identical; the overseer is the workbench/
    signer; AFP differs only by running as `sarahaios` + being agency.

## 0.99.23 -- 2026-06-28
- VAULT COMPLETION -- the central vault is now the verified single source of truth, and the node-uniformity
  answer (every node leases its SCOPED secrets from the overseer; adding a node never touches secrets). The
  authoring/appliance "two families" confusion + the node-forking detour resolved in favor of this. Docs:
  `docs/NODE_ARCHITECTURE.md` (overseer + uniform nodes), `docs/HANDOFFS.md` (the agentic flow).
  - GAP 1 (active bug FIXED): the external Google MCP server in agent sessions was orphaned (the import scrub
    removed google_oauth.json + tokens/ that `.mcp.json` points at, while the live creds moved into the vault).
    `_vault_materialize_google()` re-hydrates those files 0600 from the vault at boot (vault stays source of
    truth; just re-hydrates what an external process can't read from the vault). Verified files reappear.
  - GAP 2: Doctor now flags any secret living OUTSIDE the central vault (live .env.claudefather keys, extension
    mcp.json env literals) -- detection only, never auto-moves (moving could orphan an MCP server). `_loose_secrets_scan()`.
  - GAP 3: per-node SCOPE was already supported (Vault lens sets scope + per-node overrides; vault_lease enforces).
    Confirmed -- the only "gap" was that everything is scope=["*"] today, a data choice the operator tightens per secret.
  - GAP 4 (the keystone): central-pull verified end-to-end -- a node leases a scoped secret from the overseer
    vault (auth-gated by the family mesh token, scope-enforced: a carsearch-scoped secret is granted to carsearch,
    denied to shopos; bogus token denied). Activated live on shopos (`vault_url` -> overseer); it boots healthy
    and is now capable of leasing its scoped secrets centrally. This is how every node (co-located, appliance, or
    a new T490 project) gets credentials uniformly.

## 0.99.22 -- 2026-06-28
- SMART FIXES -- closed the quality gaps in routing/harvest/drift, using the node's Claude SUBSCRIPTION (headless
  `claude -p`, NO metered cost) deterministic-first (the model fires ONLY on ambiguous cases). `_claude_text()`.
  - SEMANTIC ROUTING (fix 1): when keyword routing is unsure (<0.6), the model picks the real home -- "firmware
    brick pre-flash gate" now routes to `patches` (keyword logic missed it). Confident routes skip the model
    entirely (verified 0.009s, llm=False). `_llm_route()`.
  - SMART HARVEST (fix 2): an abandoned conversation's transcript tail is distilled into REAL durable notes for the
    folder records (not just a pointer); pointer remains the always-safe fallback. `_distill_harvest()`,
    `_session_transcript_path()`, `_transcript_tail()`.
  - TOPIC REFRESH (fix 4, free): housekeeping refreshes each live conversation's topic from its recent transcript
    (`_refresh_topics`), so relevance-matching tracks what it's ACTUALLY on now, not just its launch subject.
  - DRIFT FLAG (fix 3, free): the hygiene panel flags a conversation working OFF its scope (recent keywords vs
    folder) with an off-scope badge -- a nudge to warm-transfer it.
  - CONFLICT FLAG (fix 5, free): a harvested note that flips a known opposite of an existing note is tagged
    [CONFLICT?] for the operator instead of two contradictory notes silently coexisting. `_conflict_tag()`.
  - ARCHIVE DIAL (fix 6): the idle-before-archive window is now a live, adjustable dial (Workspace hygiene panel
    + cc.config `idle_archive_sec`), read dynamically -- no restart to change.
  - Toggle `smart` (on by default; off = pure keyword/heuristic, no model calls). (The single-Mac/stdlib scale
    boundary is by design -- multi-node is the mesh/federation story, not a bug to fix.)

## 0.99.21 -- 2026-06-28
- RECONCILIATION -- many conversations per folder converge on the FOLDER's memory (the office-records model). The
  fix for "Sarah opens 5 sessions in a folder and it's chaos": conversations are ephemeral meetings; a folder's
  CLAUDE.md + CC:NOTES are the durable records; each meeting files its minutes there and idle ones retire.
  - RELEVANT-CONVERSATION matching: a transfer/launch into a folder now resumes the conversation whose TOPIC
    matches the task (`_best_session_in_scope`, topic tags in `_session_meta.json` set at launch/handoff) -- or
    starts a fresh one if none fits. No more dumping a new task into an unrelated live conversation.
  - HARVEST (both): agents file durable learnings to the folder records via `cc-note` (briefed at every launch);
    a server safety-net pointer-harvest guarantees an abandoned conversation's existence + resumability is never
    lost. The folder records are the single convergence point (you never merge transcripts).
  - AUTO-ARCHIVE (~4h idle, configurable `idle_archive_sec`): idle + harvested + un-held conversations are retired
    -- NEVER deleted: minutes are in the records and the conversation is one-click resumable in its scope. Keeps
    offices clean automatically. Protected: Chief / admin / Ralph / pinned / held / on-screen.
  - KEEP-ALIVE: Pin (indefinite), Hold +Nd (expiring), and agent self-hold (`cc-hold`) for "I'm coming back."
    A browser heartbeat (`/api/session-active`) keeps on-screen sessions from being archived under you.
  - WORKSPACE HYGIENE panel (Transfers lens): folders with multiple conversations, each with idle/hold state +
    Pin / Hold / Archive, a "Reconcile now" button, and the resumable archive. `hygiene()` / `/api/hygiene`.
  - APIs: `/api/session-hold|active|archive|resume`, `/api/reconcile`. Toggle `reconcile` (Context tab). CLIs
    `cc-note` + `cc-hold` shipped; launch now exports `$CC_SESSION` so an agent can self-identify.

## 0.99.20 -- 2026-06-28
- WARM-TRANSFER LIFECYCLE (the session topology, completing v0.99.19). When you confirm a transfer:
  - RESUME-DON'T-DUPLICATE: if a live session already owns the destination scope, the packet is delivered INTO
    that home agent (one coherent conversation per home) instead of spawning a parallel twin. An "open separate"
    option forces a parallel session for deliberate concurrent work (Ralph/teams/refactors still fine).
  - MOVE TO DESTINATION: accepting now opens the destination session in your workspace (you follow the topic).
  - GRACEFUL ORIGIN STAND-DOWN: the origin session is told the topic was transferred and to return to its lane --
    it is NEVER killed (that would destroy its context); it persists as the home for its own scope.
  - SAME-FOLDER AWARENESS: launching a manual New session into a folder that already has live session(s) warns you
    they share its files (`launch()` returns `siblings`). `_sessions_in_scope()` / `_live_sessions()`.
  - Router tokenization fix: folder names are split on `_`/`-` and matched on name-part subset, so "mongoose seed
    key read write" correctly routes to `read_write` (was missing it).

## 0.99.19 -- 2026-06-28
- THE WARM TRANSFER DESK -- agent routing + handoff (the "good customer-service desk" for your agents). The
  orchestration layer that finally USES the substrate (context + scout + scoped CLAUDE.md memory + launch):
  - ROUTER (`route()` / `/api/route`): deterministic-first -- maps a topic to the best HOME scope by lexical match
    over the module map + each folder's one-liner; low confidence => needs_new_home + a suggested parent. The
    agent's own judgment is the agentic fallback.
  - HANDOFF PACKET (`_handoffs.json`): structured (goal / where-it-left-off / decisions / open / next / POINTERS),
    never a transcript dump; pointers auto-attached from assemble() citations + scout().
  - PROPOSE -> ACCEPT (Assisted): an out-of-lane agent prepares a transfer (`cc-handoff propose ...` /
    `/api/handoff-propose`); you confirm in the new **Transfers** lens (one click). Accept launches a session in
    the destination with the packet + that scope's CLAUDE.md + a fresh context slice injected, and -- when no home
    fits -- CREATES one (charter CLAUDE.md + deep-dive brief) under the suggested parent.
  - ANTI-TAINT: the durable summary is written to the DESTINATION scope's memory (CC:NOTES), NEVER the origin's --
    fixes "launch in folder A, drift to topic B, A's memory gets polluted." Each scope stays clean.
  - GUARDRAILS: hop limit + no-bounce-back + every transfer operator-visible (notify on propose).
  - AGENT AUTHORITY: every scoped launch brief now tells the agent to stay in its lane + how to hand off on drift;
    the Chief brief makes it the triage FRONT DOOR (route before going deep). Toggle `handoff` (Context tab).
  - The Transfers lens also has a live router demo ("where would this topic go?"). `cc-handoff` CLI shipped.

## 0.99.18 -- 2026-06-28
- THE SCOUT -- proactive context surfacing (the answer to "an agent can't know what it doesn't know"). Beyond the
  cited brief (the obvious subject matches), a cheap index pass over the WHOLE substrate now flags the items --
  an email, a file, a call -- that are FRESH and relevant to what you're working on but that nobody pulled into
  view, as POINTERS (never a dump): the email sitting in the inbox that would make the agent a superstar. New
  `context.scout()` primitive (freshness-biased half-life, relevance gated on lexical-match membership not the
  brittle bm25 magnitude, deduped, excludes what was already handed). Surfaced in: the launch brief
  (`_scout_brief` injected via --append-system-prompt, deduped against the brief's own citations), the persistent
  Chief brief (focus-routed to the current subject), a `/api/scout` API, and a "Scout -- what you might be
  missing" panel in the Context lens. Toggle `scout` in the Context tab (on by default; obeyed everywhere).
- DOCTOR budget now counts AUTHORED lines only -- framework-managed regions (CC:TREEMAP / CC:CHILDREN /
  CC:BEGIN..CC:END) no longer count against the <200-line CLAUDE.md index budget (a lean root index that carries
  the whole-tree map was being falsely flagged). `_authored_lines()`.
- (Local, not shipped) the HP Tuners project-root CLAUDE.md was re-indexed 906->208 lines (~34K->5K tok/trip for
  its agents) -- deep prose moved to docs/, doors kept. Demonstrates the index-not-dump rule the Doctor fix enforces.

## 0.99.17 -- 2026-06-28
- PAYLOAD CHIP IN THE SESSION: right next to each session's context-% gauge there's now a 📦 badge showing the
  ~token weight of the "payload" (everything sent to that agent EVERY trip beyond your message). Hover = a
  one-line explainer; CLICK = a popup with the EXACT per-session breakdown (system briefing + the CLAUDE.md chain
  + the cited context brief + enabled tools, each with a token bar + expandable content). Makes context
  engineering visible exactly where people watch context. Backend: `_payload_baseline()` (cheap, cached
  node-level estimate added to `/api/token-usage` as `payload_tokens`); `ctxChip` renders the badge; shared
  `ctxPkgHTML` renderer powers both the Context-lens inspector and the per-session popup (`ctxPkgPopup`).
  Verified headless (chip shows "📦 35K", click opens the breakdown).

## 0.99.16 -- 2026-06-28
- THE CONTEXT TAB -- one home for all context-engineering features, fully documented, with toggles + a payload
  inspector:
  - CONTROLS + DOCS: the Context lens now has a "Context engineering" panel that toggles the features that make
    sense to toggle -- `context_brief` (auto brief at launch), `context_ingest` (the substrate), `housekeeping`
    (auto map/Doctor upkeep), `autocompact` -- each with a one-line explainer (persists to cc.config, live), plus
    a note on the native no-toggle levers (cascading map, path-scoped rules, skills, hooks). The features now obey
    their toggles (`_launch_sys_context`/chief brief, backfill loop, housekeeping loop).
  - CONTEXT PACKAGE INSPECTOR (demystify the "payload"): pick a session or subject -> see EVERYTHING beyond your
    message that reaches the agent each trip -- the injected system briefing, the CLAUDE.md chain Claude Code
    auto-loads, the cited context brief, and the enabled tools -- each with a token weight bar + plain note +
    expandable content + a total. New `context_package()` + `/api/context-package`; `/api/context-settings`.
  - NAV CATEGORIES FIX: older browsers whose nav stayed flat (or carried only the legacy "Google" group) now
    MIGRATE once to the default categories (`_catseed`); genuine custom multi-group setups are preserved. Fixes
    "only Mission Control got auto-categories." Verified: a simulated legacy state migrated to full categories.

## 0.99.15 -- 2026-06-28
- AUTOMATIC HOUSEKEEPING (Track B core of the context strategy): the doc/context tree now stays clean with zero
  manual upkeep. New `_housekeeping_loop` (hourly, idempotent, daemon): regenerates the module map (every
  folder's CC:CHILDREN + the root CC:TREEMAP) so it never drifts even on a node nobody is viewing, runs Doctor,
  and surfaces NEW issues (over-budget CLAUDE.md, managed-block drift, missing docs) -> logged to
  `_housekeeping.log`, ERRORs notified once/day per issue (anti-spam). CLAUDE.md budget aligned to Anthropic's
  **<200 lines** (Doctor flags past 200). Remaining Track B levers (path-scoped `.claude/rules/`, procedures->
  skills, API tool-result clearing/compaction, SessionStart/PreCompact hooks) are native Claude-Code/API
  mechanisms documented as available-to-adopt in docs/CONTEXT_STRATEGY.md (the launch context brief already
  carries the lockdown/files awareness, so those are additive). Track A (context quality) documented as shipped.

## 0.99.14 -- 2026-06-28
- CONTEXT QUALITY (Track A.2/A.4/A.5): the substrate now knows our whole operation + every relevant tool's intel.
  - BROADENED INGEST (`_context_backfill`): added operator NOTES (our comms), TASKS (commitments), IDEAS, and
    ACTIONS (our interactions with tools/the world via the review-gated queue) on top of calls/email/calendar/
    clips/web/slack/zoom. Verified live: the store now carries task/action/idea events, subject-keyed.
  - EXTENSION CONTEXT HOOK: any installed+authorized extension can declare `context_source` (a function returning
    `{events:[...]}`); the backfill ingests its RELEVANT intel into the context layer, subject-keyed, so it
    surfaces in the right brief. Comms extensions (granola/google/slack) already feed it directly; this is the
    standard hook for all the rest (affiliate/AI-visibility/billing/etc.). Sandboxed + idempotent. Documented in
    AUTHORING.md ("Feeding the context layer") + docs/EXTENSIONS.md.
  - CHIEF "RECENT ACROSS THE OPERATION" (A.5): the Chief brief now includes a budgeted, cited recency slice
    (calls/emails/tasks/actions/notes) so it's already caught up. Plus a "WHO YOU SERVE" operator profile hook
    (A.4): cc.config `operator_profile` is injected so the chief acts in-context about whom it serves.

## 0.99.13 -- 2026-06-28
- CONTEXT QUALITY (Track A.1 of the context strategy, docs/CONTEXT_STRATEGY.md): launched sessions now ride in
  ALREADY KNOWING their subject. `launch()` injects a SYSTEM-level block via `--append-system-prompt` (no forced
  turn): `_files_brief` (place files by relevance) + `_extend_brief` (locked core / how to extend) + a budgeted,
  cited **context brief** about the module/client the session opens into (`_launch_context_brief` -> the context
  layer's `assemble()`: time-decayed, trust-weighted, ~900-token slice of recent calls/emails/decisions/people).
  Self-skips when the context layer has nothing -> no empty injection, no rot. Verified live (session opens
  clean on Claude Code v2.1.195 with the appended context; flag confirmed real). Next: broaden what the context
  layer ingests (tool interactions, comms/tasks, AI-landscape) so the briefs get richer (Track A.2).

## 0.99.12 -- 2026-06-28
- CONTEXT ENGINEERING audit + two efficiency wins (agents get exactly what they need, no more):
  - **Extension awareness TIERING:** the Chief now also hears a TINY "also in the Marketplace, NOT enabled" tier
    (id + one-line summary only; `_ext_available_brief`) so it KNOWS a capability exists and can offer to enable
    it -- without paying for full docs it can't use. ENABLED extensions still get their full AGENT.md
    (`_ext_agent_context`). Scoped agent-tools stay lean (enabled-only) -- right context by ROLE.
  - **Right-place file output:** new shared `_files_brief()` -- agents place deliverables under the module the
    work BELONGS to (via the root Module map), NOT merely where they were launched; new tools/areas get their own
    CLAUDE.md + CC:NOTES so the tree stays self-describing for the next agent. Injected into the Chief + every
    scoped agent-tool (replaces the old cwd-bound deliverables note).
  - Audit doc: `docs/CONTEXT_ENGINEERING.md` -- the model (cascading CLAUDE.md CC:CHILDREN/CC:TREEMAP/CC:NOTES,
    220-line budget, retrieval-over-preload context router, self-organizing folders), the SOTA principles it
    embodies, and the invariants to keep it efficient as projects grow. Audit finding: the cascading-doc +
    treemap + budget + retrieval system was already strong; these close the extension-tiering + placement gaps.

## 0.99.11 -- 2026-06-28
- AGENT AWARENESS of the lockdown + sandbox: launched agents now KNOW that core + official `extensions/` are
  signed/locked and how to ADD capability the right way, so they guide the user instead of hand-editing signed
  core. New node-aware `_extend_brief()` injected into the Chief brief (`_system_brief`) AND every scoped
  agent-tool (`agent_open`): authoring node -> build official ext to AUTHORING.md + sign; appliance -> raise a
  Change Request to Mission Control; developer-type -> build a custom programmatic ext in the sandbox (Build lens
  / ext-run). Plain project sessions stay protected by the integrity backstop regardless. docs/EXTENSIONS.md (new
  "Agent awareness" section).

## 0.99.10 -- 2026-06-28
- CUSTOM SANDBOX + PROGRAMMATIC RUN ENGINE (Ship B of the extension-system standardization) -- the place users
  BUILD, and the engine that runs non-agentic programmatic extensions end to end.
  - **Sandbox:** `custom/extensions/<id>/` (under DEPLOY_ROOT, writable, PRESERVE, gitignored, NEVER signed) on a
    `type:developer` node. A custom ext is programmatic ONLY (functions{} + inputs[]/outputs[]); it runs only
    after the operator APPROVES it (`custom/_approved.json`). `_ext_dir`/`_ext_category` now resolve custom exts;
    `_ext_fn_run` runs an approved-custom function in the restricted tier -- NO core secrets, 120s ceiling,
    CPU/file/mem limits, path-confined, audited.
  - **Run engine:** `ext_run` -> `_ext_marshal_inputs` (validate/coerce; files resolve to safe bounds-checked
    paths) -> `_ext_fn_run` -> `_ext_route_outputs`. The output-destination registry (`_ext_route_one`) is
    EXTENSIBLE: deliverable/download (file), inline, agent (drop into a session), extension (chain into another
    ext), email/telegram/slack/webhook (staged to the review-gated action queue -- never auto-sent), tree, vault.
  - **Build lens** (developer-type only; hidden otherwise): scaffold a new custom ext, edit its `server/run.py`,
    Approve/Revoke, and Run it with an auto-rendered input form + routed-output display. APIs: `GET /api/custom-list`,
    `POST /api/custom-scaffold|custom-approve|ext-run`.
  - Verified live on a developer-type node: scaffold -> blocked-while-unapproved -> approve -> run-in-sandbox ->
    deliverable file written + inline returned + a real file input marshaled (read 340 chars); Build tab shows on
    developer, hidden on agency. Docs: `docs/EXTENSIONS.md` + `AUTHORING.md` updated (runtime now live).

## 0.99.9 -- 2026-06-28
- EXTENSION AUTHORIZATION (Ship A of the extension-system standardization). A node now runs ONLY extensions it
  is authorized to: **official** (the `extension.json` is in the MC-signed `core.sig.json`, verified vs
  `superadmin.pub` -- reuses the existing signing, no new keys) or an operator-approved **custom** one. Anything
  else is UNAUTHORIZED: refused at install, skipped by every loader (`_ext_lenses`/`_ext_agent_context`/
  `_ext_fn_run`), and a rogue dir under `extensions/` is QUARANTINED to `_quarantine/` on an appliance (reversible,
  never deleted) + raised in Doctor. New: `_ext_authorized`/`_official_ext_ids`/`_ext_unauthorized`/
  `_ext_quarantine_rogue` (in the integrity loop). FAIL-OPEN safety: if the signed manifest can't be verified we
  never block/quarantine a whole catalog (the missing/invalid manifest is flagged separately). Proven with a
  6-scenario harness (clean appliance, rogue quarantined, fail-open no-brick, empty-set skip, authoring-permissive,
  custom dev/agency gating).
- STANDARDIZED installs: `type` axis (`agency` | `developer`) added (cc.config `type`; default `agency`),
  orthogonal to `edition` (authoring | appliance). `developer` unlocks the custom sandbox. Bootstrapped to
  `window.CC.type`. `/api/extensions` now returns each item's `authorized` state + an `unauthorized` block + `type`.
- FORWARD-LOOKING SCHEMA (for non-agentic/programmatic extensions): documented `inputs[]` (file/text/select/...
  with `accept`/`from`) and `outputs[]` with an OPEN destination registry -- deliverable file, inline, download,
  email/telegram/slack (review-gated), and the forward ones `agent` (drop into a session) + `extension` (chain
  into another extension) + webhook/tree/vault. Fields are standard now; the routing ENGINE + the custom-sandbox
  runtime + approval flow are Ship B.
- DOCS: new `docs/EXTENSIONS.md` (canonical system reference); `AUTHORING.md` (authorization + I/O + type
  sections, `inputs`/`outputs`), `extensions/CLAUDE.md` (authorization). Audit result: AFP is CLEAN (all
  extensions official, zero rogue) and all 24 official extensions conform to the standard.

## 0.99.8 -- 2026-06-28
- DOCS: documented this stretch's work in the module CLAUDE.md files + the standards (no code change).
  `command-center/CLAUDE.md` (compact cross-instance lock; operator-notes section; drag-anything + Basket;
  nav-categories frontend + how-to-extend note; granola vault-first helper). `extensions/CLAUDE.md` +
  `AUTHORING.md` (the `default_category` key + the rule that a `lens:{id,label,icon}` OBJECT — not
  `provides:["lens:x"]` — is what surfaces a nav tab). `extensions/granola/CLAUDE.md` (the lens-object fix +
  vault-first key). `command-center/vault/CLAUDE.md` + `docs/CREDENTIALS.md` (engine modules resolve secrets
  vault-first via the `secret`=`_deploy_env` resolver; Granola the reference). `docs/FEATURES.md` (Sessions
  workspace, drag-anything + Basket, Notes, nav categories).

## 0.99.7 -- 2026-06-28
- NOTES: an operator-to-operator chat between the PEOPLE running the nodes (e.g. James @ Mission Control <->
  Sarah @ AFP), separate from the chief(agent) mesh. Leave a note; it lands in the other operator's dashboard
  as a CAN'T-MISS bottom-right corner alert (slides in, pulses, stays until opened/dismissed) + a Notes tab
  thread + a nav badge + a Telegram ping if configured; they reply and it comes back here. New "Notes" lens is
  a real messaging-app UI (peer rail + conversation bubbles + composer); threads are saved per peer.
  - Rides the SAME durable, secure transport as the mesh (own retry worker, X-Mesh-Token auth) but delivers to
    /api/opnote-recv -> the peer's HUMAN, never their agent. Endpoints: /api/opnotes[,-unread], /api/opnote-send,
    /api/opnote-read, /api/opnote-recv (mesh-ingress allowlisted). State: per-node `_opnotes.json` (gitignored).
  - Verified live: MC->carsearch note delivered + reply round-tripped; headless: corner alert fires on a
    non-Notes lens with the sender+preview+Open, badge counts, and the chat renders both bubbles.

## 0.99.6 -- 2026-06-28
- NAV CATEGORIES (declutter the crowded sidebar). The nav now ships GROUPED into default categories that are
  COLLAPSED by default, with a few daily-driver tabs pinned at the top (Sessions, Chief, Comms, Notes, Tasks,
  Files). Categories: Google, Workspace, Agency, Team, Integrations, System. Built-in lenses are mapped in JS;
  every extension declares its `default_category` (backfilled all 24; surfaced via `_ext_lenses().category`) so
  an installed extension's lens lands in the right folder. Fully built on the existing grouping engine, so users
  keep drag-to-reorder, rename, +category, and can "flatten" to the old most-used list or "reset" to defaults.
  - CATEGORY NOTIFICATION GLOW: when a lens INSIDE a collapsed category has an unread badge (new Gmail, pending
    CCR, etc.), the category header GLOWS and shows the summed count -- so nothing is ever buried in a folder.
    Reads the existing per-lens badge spans uniformly; updates live with the badge pollers; clears on expand.
  - The old one-off "Google" auto-seed is superseded by the default tree (kept only its cleanup-when-disabled).
  - Verified headless: default collapsed categories on node + overseer, pinned drivers top-level, nothing
    stranded, and System glowed "3" with a CCR badge then cleared on expand.

## 0.99.5 -- 2026-06-28
- Granola API key now resolves VAULT-FIRST (`_deploy_env("GRANOLA_API_KEY")`), falling back to the legacy
  `cc.config granola.api_key`. Before, granola.py read ONLY cc.config -- so a key added the standard way (Vault
  lens / secure-field, which is where install reserves the slot) was silently ignored, and Granola looked
  "broken" even though a key had been provided. Now adding the key to the vault "just works" -- no cc.config
  hand-edit. (granola.init gets the `secret` resolver; `_api_key()` used by source/_api_get/_gr_ready/has_key.)

## 0.99.4 -- 2026-06-28
- FIX: the Granola "Calls" lens never appeared on ANY node -- a latent framework bug. The dashboard surfaces
  an extension's lens from `_ext_lenses()`, which reads `extension.json` -> `"lens":{id,label,icon}`. Granola
  declared only `"provides":["lens:calls"]` (a different, informational field the lens code never reads), so it
  contributed no lens; and `calls` is in no preset lens list, so the nav button was always hidden. Added the
  `"lens"` object to granola's extension.json. Now the Calls tab shows on any node where granola is INSTALLED
  (and is_agency). (Granola still needs the node's grn_ API key + workspace E2E OFF to produce proposals.)

## 0.99.3 -- 2026-06-28
- BASKET: a persistent sidebar collection you fill with anything draggable, then drag the WHOLE thing into a
  session at once -- "hand the agent a basket of everything it needs for this task." Replaces the old
  hardcoded SYSTEM / Bridge / Edge / T490 / T480 machine-status widget (that was this-deployment-specific and
  not portable -- gone; the config-driven Machines lens stays).
  - Fill it: drag any `[data-ss]` item (Drive doc, email/thread, calendar event, Granola call, deliverable,
    or any extension entity) onto the basket; drag files from your computer in (uploaded via /api/basket-upload
    -> a new `upload` sendable kind); or "Add to basket" from any item's send picker. Dedup'd; remove per item;
    Clear.
  - Use it: drag the basket onto a taskbar session tile OR a workspace pane -> every item is resolved to a real
    file and handed over in ONE message + a summary line (new /api/session-send-batch; reuses the existing
    per-kind resolvers at full fidelity). Live basket persists in localStorage.
  - Saved PACKS: save the basket as a reusable named "context pack" (server-side /api/baskets*, survives
    cache-clears + follows you across browsers); one click re-loads a pack into the basket. Delete packs inline.
  - Refactor: extracted `_resolve_sendable_to_path` (shared by session_send + the new batch path; centralizes
    the secret guards). Verified: backend (save/list/delete, batch-send materializes entity body+fields to real
    files) + headless UI (panel present, SYSTEM widget gone, add/dedup/remove/persist/collapse/clear).
  - NEXT (filed): let an extension declare a drop-target action so you can drop a basket/item onto its nav
    button and it runs a function on them.

## 0.99.2 -- 2026-06-28
- FIX duplicate AUTO-compact (James: "on auto-compact it asks twice to write the handoff, then ~4x to read
  it -- never happens on a manual /compact"). Root causes, both proven from the `_autocompact.log`s:
  (1) co-located instances share the tmux server and the overseer (ROLE=org) is UNSCOPED -> it saw every
  session and raced the owning node's watcher (hpcc + overseer both logged the SAME session's auto-compact
  within 1s); the dedup state was per-process so neither saw the other's in-flight compact. (2) the cooldown
  lived in memory, so a server restart (every ship) wiped it and re-fired on a session that was mid-compact
  (chief-mission-control fired 69s apart, bracketing a restart -> the two duplicate handoff files).
  - Fix: a cross-instance + restart-DURABLE file lock (`/tmp/cf-compact-locks/<session>.lock`). `O_EXCL`
    create = only the first co-located instance wins the race; on-disk = survives a restart. Auto-compact
    now gates on `_compact_lock_acquire` (replaces the in-memory 900s cooldown); both manual + auto stamp
    the lock 'running' for the whole compact and 'done' on completion (cooldown then blocks an immediate
    auto re-fire). Manual /compact is unchanged (it never raced -- one click, one worker).
  - Verified: 6-scenario lock harness passes (race=1 winner, restart-while-running=skip, within-cooldown=skip,
    after-cooldown=fire, steal-crashed-lock, manual-running-blocks-auto).

## 0.99.1 -- 2026-06-28
- ACCOUNT BURN-ROTATION follow-ups (on the v0.98.0 system):
  - FLEET-AWARE recommendation: `_acct_recommend` now EXCLUDES any account already LIVE on another node
    (status 'elsewhere') -- two nodes on one subscription would share its limits + risk concurrent-use flags,
    wasting a separate subscription. So each node gets a DISTINCT account (e.g. AFP keeps sarah; hptuners is
    recommended the soonest-reset of the *remaining* accounts). Important for multi-node + multi-subscription.
  - VERIFY ROBUSTNESS: the switch verification now retries the /usage read and, crucially, distinguishes a
    GENUINE auth failure (login/expired -> roll back) from a slow/flaky telemetry scrape. Newer Claude Code
    renders /usage as a TABBED view whose rate-limit windows load via a separate API call; if the login
    AUTHENTICATES but the windows don't render in time, the switch is now ACCEPTED (login valid; windows
    refresh in the background) instead of false-rolling-back a perfectly good account.

## 0.99.0 -- 2026-06-28
- SESSIONS WORKSPACE: replaced focus/grid/list with a modular split-pane workspace. DRAG a session up from the
  bottom taskbar into the main area to open it; drag a SECOND up and the screen SPLITS into resizable columns --
  drag the bar between panes to set widths, pull in as many as you want. Each pane has a "push down" button back
  to the taskbar; the taskbar highlights which sessions are currently "up" (click a tile to toggle in/out). Never
  empty (auto-shows one big; dragging the last down auto-promotes the next). Mobile = one full pane, tap a tile
  to swap. State (which panes are up + their widths) persists per device. Built on the existing per-session
  iframes; the view-mode toggle is gone. New PANES/PANEW state + renderWorkspace/paneHead/wkWire (splitter drag +
  dock->workspace drop) + draggable, "up"-marked taskbar tiles; sized to the proven offset so the page never
  scrolls. Verified headless (split / resize / push-down / no overflow).

## 0.98.0 -- 2026-06-28
- SMART ACCOUNT BURN-ROTATION ("which login to burn next") overhaul, for multi-subscription installs:
  - RECOMMENDATION BRAIN rewritten (`_acct_recommend`): rank by SOONEST WEEKLY (7-day) reset first =
    minimize LOCKED-UP capacity (draining an account makes its capacity dead until that account resets, so
    spend the soonest-resetting one and preserve far-from-reset accounts as reserve). The 5h window is now a
    pure THROTTLE (near-full -> 'cooling', fall through), never a ranking input. Uses the limit-model's
    predicted live % when READY. (Replaces the earlier perish-rate model, which optimized the wrong objective.)
  - TIME-OF-DAY diagnostics (`_acct_tod_report`, `GET /api/account-tod`): weekly capacity is FLAT (fixed
    budget, ruled out); 5h shows ~34% spread but low-n -- measured, NOT folded into the model.
  - VERIFY-THEN-ROLLBACK switch (`account_switch_verified`): confirms the new login is live AND can read
    /usage, else auto-rolls-back to the prior login. Switch-health ledger (`_cc_acct_switch_health.json`) +
    `auto_proven` gate (>= SWITCH_PROOF_N consecutive verified-good switches; one failure resets). Live-proven.
  - ACT LAYER: per-node opt-in `account_autopilot` = off | alert | auto, but stored PER macOS-USER (shared by
    all co-located nodes -- they share ONE Claude login, so the choice can't differ between them; a different
    user e.g. AFP is independent). 'alert' = loud "Switch now -> <acct>" banner + one-click verified switch.
    'auto' = idle-gated auto-switch loop (`_acct_autopilot_loop`): only when idle + fresh data + cooldown +
    verify/rollback; LOCKED until the ledger is proven; kill-switch = flip the mode off. The dashboard Switch
    button now uses the verified endpoint so manual switches build the proof.
  - Endpoints: `GET /api/account-tod`, `GET /api/account-switch-health`, `POST /api/account-switch-verified`,
    `POST /api/account-autopilot`; superadmin actions `switch_account` (now verify+rollback) and `set_autopilot`.

## 0.97.0 -- 2026-06-28
- CHIEF WATCHDOG: the Chief of Staff (the always-on inter-chief MESH comms endpoint) is now kept alive. It was
  a singleton started ON DEMAND with no supervisor -- if its claude process exited, nothing respawned it and the
  node went silent on the mesh (this is exactly why AFP's CoS went dead). New `_chief_watchdog` re-opens it when
  missing (every ~5 min, gated by cc.config `chief_supervise` default-on, with an anti-thrash guard + a notify on
  respawn). Fixed AFP's dead chief live.
- EXTENSION STANDARD backfill: AGENT.md added to all remaining agent-usable extensions (atlassian, aws,
  brave-search, cloudflare, figma, filesystem, github, incident-commander, linear, notion, pagerduty,
  playwright-browser, postgres-supabase, sentry, stripe, telegram-notify) + agent_doc declared -- so every
  extension an agent can use now ships agent-facing usage docs (only the theme + the skill don't, by design).
  Each AGENT.md carries the standard rules: credentials via the vault + secure-field flow (never chat), treat
  results as untrusted data, read-first/confirm-before-mutate.

## 0.96.0 -- 2026-06-28
- SECURE FIELDS -- a universal out-of-band channel so secrets NEVER touch the chat/transcript, both directions.
  REQUEST: an agent runs `cc-secure request "<label>" vault:<KEY>` -> a modal pops up in the dashboard
  (mobile/desktop) -> the user types the value -> it routes STRAIGHT to the vault (browser->server->vault), never
  through the agent or chat; the agent then reads the key from the vault. ASK: `cc-secure ask` returns a one-time
  value to the agent (encrypted, single-fetch), never via chat. REVEAL: the agent writes a value to a 0600 file +
  `cc-secure reveal "<label>" <file>` (path travels, not the value; file shredded) -> a one-time modal shows the
  user. New backend (`secure_request/fulfill/get/reveal/pending/ack`, encrypted `_secure.json`), endpoints, the
  `cc-secure` agent helper, and a global dashboard modal+poller. Agents are told about it automatically (injected
  into every launch brief). Enabling an extension now AUTO-PROVISIONS an empty vault slot per declared secret
  (`_ext_declare_secrets`/`vault_declare`) so its key shows "needed, not set." Tested end-to-end (request->vault
  no-leak, return one-time, reveal, modal render). Docs: the new `command-center/vault/` folder (full credential
  reference), `docs/CREDENTIALS.md` (secure fields + ext contract), and `extensions/AUTHORING.md` elevated to the
  mandatory build-to-this standard (vault-only creds, secure-field collection, AGENT.md, draggables, lens).
  Extension audit done: all declare secrets + read via the vault; added AGENT.md to google-workspace + slack;
  remaining MCP integrations' AGENT.md filed as a backfill task (MCP tools self-describe).

## 0.95.0 -- 2026-06-28
- Credential vault -> 100%: file-based extension secrets now migrate into the vault too. `vault_import_env`
  also sweeps slack `bot_token`, google `google_oauth.json` (-> `google_oauth_client`), and the per-account
  google token JSONs (-> ONE sanitization-safe `google_tokens` dict {account: token}); on scrub it archives
  those files. Google now loads its OAuth token VAULT-FIRST (`_google_token_load`, file fallback) -- the token
  is read-only at runtime so this is lossless; slack `_token()` resolves the vault (deploy_env) BEFORE its
  legacy file. Verified airtight on carsearch: google secret files archived + node restarted (cache cleared)
  -> Gmail/Calendar still configured + canRead, resolving purely from the vault. After this, no credential
  (env or file) lives outside the per-install vault. (docs/CREDENTIALS.md.)

## 0.94.0 -- 2026-06-28
- CREDENTIALS unified into ONE per-install vault (the only way; docs/CREDENTIALS.md). There is now a single
  encrypted credential store per install at <DEPLOY_ROOT>/.vault/ (shared by co-located instances; under
  DEPLOY_ROOT so it's writable even on a read-only-core appliance), and a single resolver: `_deploy_env(key)`
  now resolves process-env -> the install VAULT (local store, scope+per-node aware; or leased from the overseer
  for remote nodes) -> legacy .env.claudefather (bootstrap/import only, being retired). Sharing model = central
  vault + per-secret SCOPE: a secret carries scope=[nodes] with a shared value OR per-node values (billing
  isolation); rotate once, all in-scope nodes get it. New `_vault_local` (quiet scope-aware local read),
  `vault_import_env(scrub)` + `POST /api/vault-import`: migrates every key out of plaintext .env into the vault,
  verifies each reads back, and (scrub) archives the plaintext (.env.claudefather.migrated-<ts>, reversible) so
  the vault is the ONLY store. Rollout is additive (vault empty -> .env still answers; nothing breaks) then
  import -> verify -> scrub. Our install migrated: 15 secrets moved into the vault, .env retired, all still
  resolve. Extensions converge automatically (anything reading via _deploy_env now reads the vault); bespoke
  secret FILES (google/slack) are the remaining per-extension cleanup. Vault dir/key + migrated .env archives
  gitignored, never shipped.

## 0.93.0 -- 2026-06-27
- NEW EXTENSION: Substack (read + draft -- Substack has no publish API, so this is the honest shape). TRACK:
  poll configured publications' PUBLIC RSS feeds into a node-local cache + a Substack lens (your pub +
  competitors/sources); post content is untrusted data. DRAFT: a headless Claude (Max sub, no metered key)
  turns a topic + optional source into a publication-ready markdown draft, saved to deliverables/substack/ for
  review -- you paste into Substack + publish (nothing auto-publishes; no unofficial/cookie endpoints used).
  New stdlib engine command-center/substack.py (RSS via urllib+ElementTree; draft via claude -p), server wiring
  (GET /api/substack, POST /api/substack-sync, POST /api/substack-draft, a ~45m RSS poll loop), and a Substack
  lens (KPI strip + tracked-posts table + draft composer + drafts list; reuses the .aff-* dense layout). Ships
  as the `substack` extension (lens:substack + context:substack; self-shows when installed); cc.config
  substack.publications = [handles | domains | /feed URLs]. Tested: real RSS parse (20 posts), idempotent sync,
  draft flow, lens render.

## 0.92.0 -- 2026-06-27
- Security audit: new Secrets check (A5-keybackup) flags a plaintext key backup (cf-key-backup's
  PAPER-BACKUP.txt -- Ed25519 PRIVATE keys in cleartext) lingering on disk, so "print it to a safe + remove
  the plaintext" surfaces in the next audit you run instead of being forgotten. Self-clears once the plaintext
  file is gone (the keys are also in the encrypted .cfkeys.enc bundle, so nothing is lost). agents/security/
  tools/scan.py.

## 0.91.0 -- 2026-06-27
- FIX: cf-key-restore.sh --verify listed bundle contents with `ls -1`, which hides dotfiles -> the PRIVATE keys
  (.superadmin_ed25519/.recovery_ed25519/.vault_key) didn't appear, only the .pub files + MANIFEST, making a
  perfectly good backup look incomplete. Now `ls -1a` so the private keys show. The keys were always in the
  bundle (it tars `.`); this was display-only. (No change to backup/restore behavior.)

## 0.90.0 -- 2026-06-27
- FIX: account fuel-gauge went stale ("100% used, resets in 0m" on a window that had actually reset). Root
  cause: there was NO periodic refresh -- account windows were only re-read on manual trigger / account-switch,
  so after an overnight weekly reset the gauge kept the pre-reset reading whose reset-timestamp was now in the
  past (-> floored to "0m"). Two fixes: (1) `_win_view` now detects an expired window (reset_ts in the past),
  treats it as RESET (0% used, full), rolls the reset clock forward to the next boundary, and flags `expired`
  -- so a rolled-over window self-corrects instead of lying. (2) New `_acct_windows_loop` refreshes the LIVE
  login's 5h/weekly windows on a ~30m cadence (only the live keychain login exposes them), deduped across
  co-located instances via a shared CC_HOME lock so the overseer+nodes don't each spend a /usage read; plus an
  on-view debounced kick so opening the Accounts lens with stale data refreshes immediately. Net: the gauge
  stays accurate and the "use this account next" recommendation sees real free capacity again.

## 0.89.0 -- 2026-06-27
- SLACK per-session comms -- the TEAM twin of the Telegram tool. Toggle 'Slack' in any session's terminal bar;
  when it goes busy->idle the bot posts to a per-session THREAD in your `comms_channel`, and a teammate REPLIES
  in that thread to inject back into the session (a reply in a session's thread is inherently unambiguous). At
  channel level: '#N your text' routes to session #N, bare '#N' sets focus, plus /list, /focus N [time]|off,
  /off N, /mute N [time]|/unmute N, /help -- same smart routing + stable numbering as Telegram (single session
  auto-routes). Built on the existing `slack` extension (bot token via slack._api); inbound is POLLED
  (conversations.replies per thread + conversations.history for commands) so it needs NO public webhook / Socket
  Mode -- works behind NAT/tailnet. New: slack_session() + POST /api/slack-session, _sk_outbound_loop /
  _sk_inbound_loop daemons, the term-bar Slack toggle. No-ops until the slack extension is installed + a bot
  token + a comms_channel are set. slack extension -> v2.1.0 (provides comms:slack; SLACK_COMMS_CHANNEL).

## 0.88.0 -- 2026-06-27
- SUPER-CREATOR RECOVERY (never get locked out) + LICENSE AUTO-ACTIVATION. Recovery: every node now trusts a
  SECOND owner key (`recovery.pub`, ships) ALONGSIDE the primary -- all four authority checks (superadmin grants,
  core integrity, licenses, entitlements) route through `_verify_trusted` (primary OR recovery). So losing/
  compromising the primary is RECOVERABLE without bricking the fleet: restore the offline recovery key, sign
  (verifies everywhere), rotate a fresh primary. Three independent recovery paths: encrypted multi-location
  bundle, paper/QR backup, and the cold recovery key. New `recovery_keygen` (POST /api/recovery-keygen),
  `cf-key-backup.sh` (AES-256 bundle + printable paper backup of the crown jewels), `cf-key-restore.sh`
  (reinstate onto a new MC; --verify mode). Runbook: docs/RECOVERY.md. Auto-activation: a sold box self-activates
  by POSTing its hardware fingerprint + a single-use purchase CODE to the activation server (cc.config
  activation_url) on boot; `license_code_new` (POST /api/license-code) mints codes, `POST /api/license-activate`
  (public, code- or family-mesh-gated) issues the hardware-bound license, codes are single-use + bound to the
  first machine. `POST /api/license-activate-self` + a boot loop. All tested (recovery-key-signed licenses verify;
  code single-use/hardware-bind/family-bypass).

## 0.87.0 -- 2026-06-27
- CODEBASE / IP PROTECTION (anti-clone) -- phase 3a: LICENSE ACTIVATION shipped (soft-enforce). A license is
  Ed25519-signed by us, BOUND to the machine's hardware fingerprint (macOS IOPlatformUUID), and EXPIRES -- so
  copying the tree to another Mac fails (fingerprint mismatch -> invalid), and a license is revocable + carries a
  customer watermark. `_hw_fingerprint`, `license_issue` (authoring/MC only), `license_status`/`_licensed`,
  `license_install`. APIs: GET /api/license, POST /api/license-issue (MC mints for a box's fingerprint), POST
  /api/license-install (node stores it). SOFT by default (health `licensed` + doctor warn; never bricks our
  fleet); set cc.config `license_enforce=true` on a SOLD box and the auth gate hard-refuses service with a
  "license required" page showing the fingerprint to send the vendor. Tested: validates on the issuing machine;
  rejects wrong-machine/tampered/expired. Phase 3b SCAFFOLD: `cf-build-appliance.sh` obfuscates the SHIPPED
  appliance Python (PyArmor preferred, Cython fallback) -- authoring stays plaintext; needs a PyArmor purchase to
  run (never ships plaintext silently). Full strategy + honest limits + how-to-license-a-box: docs/IP_PROTECTION.md.

## 0.86.0 -- 2026-06-27
- TURNKEY HARDENING phase 2 -- the OS-level enforcement that makes "can't modify core" REAL, plus the codebase
  IP-protection strategy. New `cf-appliance-install.sh` (run with sudo on a fresh Mac): creates a dedicated
  NON-ADMIN runtime user (cfrun), installs the framework CORE root-owned + READ-ONLY to cfrun (so the agent
  running --dangerously-skip-permissions literally cannot write server.py -- the OS is the boundary, not Claude
  Code), redirects ALL writable state (state/deliverables/custom/secrets) OUT of core via cc.config
  (state_dir/deploy_root/deliverables_root/custom_dir), marks the box edition=appliance, and installs two
  launchd services: the runtime (as cfrun) + a privileged HEALER (as root). New `cf-update-healer.sh` (root,
  every 30 min): pulls the signed dist, VERIFIES the core manifest signature with superadmin.pub, restores any
  drifted/updated core file (copying only dist files that match the signed hash), resets read-only perms, and
  restarts the runtime if anything changed -- update + self-heal with the privilege the read-only runtime lacks.
  `DEPLOY_ROOT` now honors cc.config `deploy_root` so secrets/.mcp live outside a read-only core. Runbook:
  docs/APPLIANCE_BRINGUP.md (Mac mini bring-up + verification). Codebase IP protection (anti-clone/jailbreak)
  strategy + honest limits: docs/IP_PROTECTION.md (license activation bound to hardware + signed + expiring;
  obfuscate the shipped artifact only; heartbeat/duplicate-fingerprint revocation; watermark + legal).

## 0.85.0 -- 2026-06-27
- TURNKEY HARDENING phase 1 -- the software backbone for shipping ClaudeFather as a tamper-resistant appliance
  (full design + threat model: docs/HARDENING.md). New EDITION tier: `authoring` (us -- modifies/signs core,
  mints grants) vs `appliance` (a shipped/customer box -- locked + self-healing). Default: a SOURCE node is
  authoring; any other install is a locked appliance. New SIGNED CORE INTEGRITY: `core_sign()` (authoring-only,
  POST /api/core-sign) hashes every framework code/config file (.py/.sh/.json/.pub/.css/.html -- docs + vendored
  JS excluded so per-node CC:NOTES never trip it) and signs the manifest with the Ed25519 private key ->
  core.sig.json (ships via dist). On boot + every 15 min an appliance runs `core_verify()`: it verifies the
  manifest signature with superadmin.pub (a tampered manifest is rejected), checks every hash, and SELF-HEALS
  any drifted file from the signed dist mirror (only if the dist copy matches the signed hash), logging to
  _core_integrity.log + alerting if it can't. So edits to core on an appliance silently revert. Authoring boxes
  only DETECT (they're the source of truth). superadmin keygen is now authoring-only. New GET /api/core-integrity
  + `edition`/`integrity` in /api/health + doctor checks (unsigned/drifted/sig-invalid). Zero behavior change on
  authoring nodes; appliances with no signed manifest yet just no-op (then warn in doctor). OS-level hardening
  (dedicated runtime user + read-only core) + the sandbox arena are phase 2/3 (docs/HARDENING.md roadmap).

## 0.84.0 -- 2026-06-27
- Granola Calls hardened into a clean, shippable, agent-accessible extension. The engine now gives CLEAR,
  actionable errors instead of opaque states: an empty key says "no Granola API key set", and a 401/403
  explicitly names the real cause -- "your Granola workspace has END-TO-END ENCRYPTION enabled, which blocks
  the public API; turn E2E off and recreate the key" (this is the "encryption" message users hit, surfaced
  honestly). `/api/granola` now returns `ready` + `hint` + `has_key`, and the Calls lens shows the exact next
  step ("needs setup" with the precise fix) instead of a generic "not configured". Granola calls are draggable
  into sessions (already wired -- now declared in extension.json) and the extension ships an AGENT.md so agents
  on an installed node know the propose->approve->apply flow. SETUP.md documents the E2E-encryption + Business-
  plan prerequisite and a Troubleshooting section. extension.json -> v1.1.0 (agent_doc, draggables, publisher,
  clearer requires). No behavior change to the apply path (review-first intact).

## 0.83.0 -- 2026-06-27
- Enterprise CREDENTIAL VAULT -- MC-hosted, encrypted-at-rest, checkout/lease on demand. Mission Control
  holds ONE encrypted vault; nodes LEASE a secret at runtime over the family-authenticated channel and cache
  it in RAM only (never on disk), re-leasing on TTL -- so revoking at MC stops a node within one lease window
  and a stolen disk image holds no plaintext. Each secret is SCOPED (which nodes may lease: `*` or a node-id
  list) and carries a SHARED value plus optional per-node OVERRIDES (billing isolation -- a shared key, or
  each node its own). Encryption-at-rest is Fernet (the cryptography lib, already the superadmin dep); the
  key (`.vault_key`, 0600, gitignored, MC-only) is the sole authority -- `_vault.json` alone can't be
  decrypted. New: `vault_set/revoke/delete/list` (operator-only via `_operator_only()` -- a family mesh token
  can lease but NEVER manage), `vault_lease` (family-token authed, on the mesh ingress track), node-side
  `vault_get` + a transparent `_deploy_env` fallback (set `cc.config.vault_url` and every missing secret read
  resolves from the vault), and a full audit log. New **Credential Vault** lens on the overseer (KPI strip +
  secrets table + add-form + live audit). Zero impact on nodes without `vault_url` (the env path is unchanged).
  Docs: docs/VAULT.md.

## 0.82.0 -- 2026-06-27
- Telegram per-session comms got SMART for many sessions on one node (one bot per node). Each enabled
  session now has a STABLE number; pings are tagged `#N node/Title`. Reply routing, in order: reply-TO a
  ping -> that session; `N your text` -> session #N (one-shot); bare `N` -> set focus to #N; an active
  FOCUS -> there; if exactly ONE session is on -> it auto-routes (no number needed); else the bot replies
  with the numbered list and asks you to pick -- so you never need the cryptic tmux name. Manage from the
  phone: `/list` (numbered sessions + busy/idle/focus/muted), `/focus N [30m|2h]` (bare = 1h) + `/focus off`,
  `/off N` (disable from your phone), `/mute N [time]` + `/unmute N`, `/help`. Bot creds now resolve
  PER-INSTANCE (cc.config `telegram_bot_token`/`telegram_chat_id`) then the shared deploy env, so co-located
  nodes can each carry a distinct bot; a `getUpdates` 409 (two consumers on one token) backs off instead of
  spinning. The term-bar toggle shows the session's number ("Telegram #2: on"). State (routed/index/focus/
  mute/offset/msgmap) stays node-local. (server.py TG module + telegram-notify SETUP.md.)

## 0.81.0 -- 2026-06-27
- Telegram per-session comms -- route ANY tmux session to your phone. Toggle "Telegram" in a session's terminal
  bar (the moremenu, next to compact): when that session goes busy->idle (task finished OR blocked waiting), the
  bot pings your phone with the pane tail; you REPLY (reply-TO the ping, or prefix `name: text` / `s name text`)
  and it's injected straight back INTO that session via the mesh-deliver typer. Toggle on/off mid-conversation.
  Built on the existing telegram-notify extension (the bot + creds); state + getUpdates offset are node-local
  (`_tg_sessions.json`). The whole feature no-ops until telegram-notify is INSTALLED and TELEGRAM_BOT_TOKEN +
  TELEGRAM_CHAT_ID are in the deployment env -- so it ships fleet-wide safely; each node BYO bot via the
  Marketplace "Set up telegram-notify" flow. New: `telegram_session()` + `POST /api/telegram-session {name,on}`,
  two daemon loops (`_tg_outbound_loop` busy->idle edge; `_tg_inbound_loop` getUpdates->route->`_mesh_deliver`),
  and the `#tgbtn` term-bar toggle (hidden unless the extension is installed on this node).

## 0.80.0 -- 2026-06-27
- AISearch now runs 100% INSIDE ClaudeFather -- the worker->server-function port is done. analyze + compare are a
  stdlib-only Python server FUNCTION (extensions/aisearch-pro/payload/server/aisearch_fn.py) on the new server-
  function runtime: reads BYOK keys from the injected env, fans out concurrently to OpenAI(gpt-4o)/Anthropic
  (claude-sonnet-4-5)/Gemini(gemini-2.5-flash), and writes the node-local SQLite store. extension.json declares
  the `functions`, so the unified /api/ext-action runs them LOCALLY (the lens is unchanged -- same call, same
  result shape). Cloudflare worker + Supabase are now OUT of the request loop (the deployed worker is dormant
  fallback; can be decommissioned). Verified in-console end-to-end: Cabeau 100% across all 3 providers, logged to
  the local store. Faithful port of the worker's prompts/parsing; the simple analyze/compare paths (compare here
  is the mention/position/winner core, not the web-grounded-report variant -- that + Perplexity + real cost are
  follow-ons). The AISearch deliverable now: serverless-free, DB-free, BYOK, self-contained in the platform.

## 0.79.0 -- 2026-06-27
- Extension Data Store (node-local SQLite) -- the unified store primitive so an extension's data lives ON the node
  (self-contained, no external DB). Generic: data_sources `backend:"sqlite"` + a shipped `schema` (.sql, applied
  idempotently); the lens reads it through the SAME data_sources contract as supabase (whitelisted table/select/
  order from the manifest; user search/filters are BOUND params -- no injection); server functions get their OWN
  scoped DB via CF_STORE_DB (per-extension file -- no cross-extension reach). AISearch moved to it: shipped
  store_schema.sql (accounts/requests/reports incl. per-account byok/api_keys) and MIGRATED the existing Supabase
  data into the local store (verified: 25 requests / 11 reports / 2 accounts read back through the lens). The
  in-console search still renders live; the analytics tab now reads local. (Final step: port the worker's AI fan-out
  to a server FUNCTION that writes the local store -- then Cloudflare/Supabase are fully out of the loop.) Docs:
  extensions/AUTHORING.md.

## 0.78.0 -- 2026-06-27
- Extension Server Functions -- a unified, sandboxed runtime for extensions to run SERVER-SIDE code inside
  ClaudeFather (no external worker/host), so future extensions that need server compute all use ONE managed,
  secure path instead of per-extension hacks. Declared via extension.json `functions` {entry, runtime, secrets[],
  timeout_sec, mem_mb, tier}; invoked through the unified `/api/ext-action` (a local function is preferred over a
  remote `worker`, so lens code is identical for either). SECURITY (it runs extension code on a box with secrets):
  subprocess isolation; RESTRICTED env -- only the secrets the function declares are injected, never the node's
  auth/mesh tokens or other extensions' keys (proven: node_auth_leaked=false); hard timeout + CPU/file-size (+best-
  effort memory) limits; stdin/stdout JSON contract; path-confined entry; official-tier only (third_party sandbox +
  per-account BYOK secret store + OS-level net egress enforcement are the designed-in next steps); every call
  audited to _ext_fn.log. This is the foundation for moving AISearch fully in-server (next: port its AI fan-out to
  a server function + node-local data store + migrate the Supabase data). Docs: extensions/AUTHORING.md.

## 0.77.0 -- 2026-06-27
- AISearch runs IN-CONSOLE now (was a link-out to the website). The AI Visibility lens gained a Search tab: enter a
  brand + query (or brand vs competitor), Run, and see the live result inline -- a grid of per-engine cards
  (ChatGPT/Claude/Gemini/Perplexity: mentioned? position, top brands) + an overall AI-visibility %. BYOK: the
  search runs as the node's account (access code), so it uses that account's own AI keys; the access code stays
  SERVER-SIDE. New generic `/api/ext-action` proxy forwards an in-console request to an extension's hosted worker
  (auth header from the deploy env; browser UA so Cloudflare doesn't 1010-block) -- reusable for any worker-backed
  extension. extension.json gains a `worker` block (url/auth/actions). Analytics moved to a second tab.

## 0.76.0 -- 2026-06-27
- AISearch Pro -- 2nd paid extension ($5/mo, BYOK). The Mac daemon/tunnel are GONE: the worker is redeployed as a
  serverless Cloudflare Pages Function (aisearch-pro.pages.dev) under MC -- killing the TCC/launchd/SSD headache.
  Per-account BYOK: each account uses its own AI keys (effEnv override + 402 gate for external accounts with no
  keys; owner/admin falls back to MC's Pages secrets = Sarah's keys, auto-filled). Stale model IDs refreshed
  (claude-sonnet-4-5, gemini-2.5-flash; gpt-5.2 via Responses API) -- verified all 4 providers return live results.
  New "AI Visibility" lens (KPI strip + 2-col request table | reports/accounts side panel; no stacked cards),
  reading the analytics tables via the read-only /api/ext-data proxy; draggable brand rows. extension.json declares
  the BYOK keys + data_sources + lens; schema.sql adds per-account api_keys/byok. (External-BYOK needs a one-time
  SQL migration in Supabase -- the mgmt API is unreachable from the build env.)

## 0.75.0 -- 2026-06-27
- Host-designated extension routines: an extension's scheduled routine now registers on install ONLY where
  `cc.config extension_routine_host` is true (default true -> single-node installs run their own routines). In a
  multi-node fleet, set view-only tenant nodes to false so they get the extension LENS/data but the SYNC runs on a
  central host. Durable across reinstall (a non-host never re-registers the routine), unlike deleting the entry.
  Added `extension_routine_host` to the superadmin set_config allowlist so MC can set it remotely. Applied: AFP =
  view-only (false), Mission Control = sync host -- Skimlinks syncs on MC, AFP just views.

## 0.74.0 -- 2026-06-27
- Affiliate Intel lens REBUILT to match the original dashboard's layout (the first cut was a lazy vertical stack
  of full-width cards -- wrong). Now: a compact KPI strip (merchants / active / removed / changes), a search +
  sort (daily sales, commission, eCPC, conversion, tenure, # changes) + status toolbar, and a real 2-column body
  -- a dense merchant TABLE (Commission / eCPC / Daily sales / Conversion / Status / Tenure, default-sorted by
  daily sales so the heavy hitters lead) beside a Top-movers side panel (recent commission changes). Rows are
  draggable into a session; click a row for its commission timeline. Fix: the lens container now spans the full
  dashboard grid (grid-column:1/-1) instead of collapsing into one cell. Data proxy select expanded with
  ecpc/aov/daily_sales/conversion. (UI rule going forward: never lay a lens out as stacked full-width cards --
  study the reference + design dense/laid-out screens.)

## 0.73.0 -- 2026-06-27
- Skimlinks Affiliate Intelligence -- the first paid extension ($5/mo, run-gated via the v0.70 signed-entitlement
  system; free on internal fleet nodes). Brings the old external skimlinks.html dashboard IN-HOUSE: a built-in
  "Affiliate Intel" lens (stats + searchable merchant grid with draggable rows + top movers + per-merchant
  commission timeline), gated to appear only on nodes where the extension is installed. Ships a parameterized,
  multi-tenant sync payload (publisher ID / Supabase URL+key / min-merchant guard all from the deploy env, nothing
  hardcoded), the exact schema.sql, AGENT.md (agent usage, auto-injected only where installed), and SETUP.md.
  Install registers the weekly routine (Sun 03:00) via the new runner; uninstall removes it. Reads data through a
  NEW generic, reusable extension data proxy (GET /api/ext-data) -- read-only Supabase REST, the DB key stays
  server-side (never in the browser). Also new + generic: extension.json `lens` (extensions contribute a nav lens,
  per-node-clean) + the install->routine auto-registration. VERIFIED end-to-end in an isolated worktree test
  instance against live data: entitlement gate, install+payload+routine, the read-only proxy (35,221 merchants),
  and the lens render (headless). Docs: extensions/skimlinks-merchant-sync/.

## 0.72.0 -- 2026-06-27
- Two extension framework primitives (running themes across core + extensions), built generic so any extension
  uses them — Skimlinks will be the first consumer:
  - Extension-scoped AGENT CONTEXT: an extension can ship an `AGENT.md` (agent-facing usage doc) that is
    auto-injected into the launch brief (`_system_brief`) ONLY on nodes where that extension is installed/enabled.
    Per-node-clean by construction: a node without the extension never tells its agents the tool exists (a
    CarSearch node without Skimlinks gets zero Skimlinks context). Capped ~1.6KB each. Safe no-op until an
    installed extension ships an AGENT.md.
  - Extension-declared DRAGGABLES: the generic `entity` sendable lets any lens/extension make any item draggable
    into a Claude session (taskbar dock) with ZERO server code — the descriptor carries its own content
    (`ssAttr({kind:'entity', name, title, fields|body, kind_label})`); extensions declare their draggable types
    in extension.json `draggables`. Built on the existing register_sendable/session-send spine (drag a merchant,
    a row, anything → the agent gets a clean markdown card). Verified end-to-end. Ship a payload resolver only
    for server-side enrichment. Docs: extensions/AUTHORING.md (AGENT.md + Draggables sections; extension.json
    gains optional agent_doc + draggables).

## 0.71.0 -- 2026-06-27
- Routines runner — the platform's scheduled-job heartbeat (was a stub: registry, no runner). A stdlib
  server-side tick loop (`_routines_loop`/`_routine_run`) executes due routines IN THIS NODE'S OWN server
  process — which has Full Disk Access — and NEVER reaches across user-home boundaries. That cross-user/SSD
  reach is exactly what silently broke the legacy launchd job when it was loaded under a different user (a TCC
  denial with no log) — so each node runs its own routines on node-local paths. Hard-won rules baked in from
  the legacy Skimlinks/CarSearch setup: de-dupe by NAME (a routine can't double-fire — the old setup had a
  LaunchAgent AND a duplicate crontab line racing the same DB rows), failure alerts from day one (non-zero
  exit/timeout -> notify_send; the old job had ZERO alerting and a failed run sat unnoticed for two weeks),
  and catch-up (a missed calendar window runs once on the next tick). Routine schema in _routines.json gains
  cmd/cwd/when/env/timeout_sec/alert/enabled; run-state + per-run logs persisted; Routines lens shows cadence
  + last-run/status + a "Run now" button. APIs: GET /api/routines, POST /api/routine-run. VERIFIED: a test
  routine auto-fired on cadence (the exact failure mode that was broken) and via manual run. Docs:
  agents/routines/CLAUDE.md. (This is the prerequisite for shipping the Skimlinks sync as a scheduled extension.)

## 0.70.0 -- 2026-06-27
- Paid extensions / entitlements — the monetization layer for the Marketplace, built so it can't be self-granted.
  A `"tier":"paid"` extension is LOCKED by default and unlocks ONLY with a Mission-Control-SIGNED entitlement
  token (Ed25519, the same owner key as superadmin — private key MC-only, superadmin.pub already shipped to every
  install). A node/agent cannot forge one (no private key) and editing the stored `_entitlements.json` just yields
  a token that fails signature verification (PROVEN: a tampered grant is rejected on read). No honor-system plan
  flag — the signature is the only authority. Internal fleet nodes get a perpetual wildcard grant; external
  customers get a per-extension grant with an expiry, re-minted monthly to renew (lapse re-locks; tenant data
  untouched). Mechanism: extension.json gains optional `tier`/`pricing`/`publisher`; `_entitled()` gates install;
  `entitlement_grant(node,ext,days)` mints+delivers (local or via signed superadmin set_entitlement); superadmin
  actions set_entitlement/del_entitlement; APIs GET /api/entitlements + POST /api/entitlement-grant|revoke;
  Marketplace cards show 💳 Paid · $X/mo + ✓ licensed / 🔒 locked and a "Request access" path. Billing automation
  (Stripe) stays separate — a future webhook just calls entitlement_grant. Docs: extensions/AUTHORING.md.
- Usage/metered-spend portability fixes (from the enterprise audit): CTX_WINDOW is now `context_window`-configurable
  (non-1M models like Haiku 200K get a correct per-session gauge AND autocompact threshold); `_PRICING` accepts a
  cc.config `pricing` override so a tenant can patch a stale rate without a core release; the Accounts "no reading
  yet" hint no longer leaks our macOS usernames into a tenant's UI; the shared `~/.claude/_cc_acct_windows.json` +
  account-log are written 0600 (account emails/usage no longer world-readable to other users on a shared box).
  Audit verdict: pricing current, secrets clean, graceful zero-config degrade, multi-tenant isolation holds.

## 0.69.0 -- 2026-06-27
- Auto-update HARDENED for packaged/white-label installs (was tuned to our one fleet). Update identity is now
  ONE white-label point — three named constants in server.py (OFFICIAL_DIST_GIT / OFFICIAL_DIST_DIR /
  CORE_AUTHORING_REPO); everything else is config, no scattered literals. Version probe is host-agnostic:
  local-dir upstream → read its manifest; GitHub/GitLab → raw probe; ANY other git host → shallow-clone-and-read
  fallback (private GitLab/Gitea/Bitbucket fleets work). `update_source` accepts a git URL on any host OR a
  local/shared-mount directory. Source-node detection is portable + git-independent: cc.config
  `update_role:"source"` → `.cc-source` marker file → is-the-dist-dir → git-remote heuristic (dropped the
  one-off `hptuners-autonomous` reference). Our 3 source nodes are now marked explicitly (update_role + marker)
  so protection never depends on git. Provisioning (cc-init.sh) seeds `auto_update:true` on new tenants. Net: a
  downloaded ClaudeFather with ZERO config is a tenant that auto-updates from the canonical dist and self-restarts
  when idle; a private fleet repoints to its own dist with config only. Docs: command-center/update/UPGRADE_SYSTEM.md
  §5 + §6b (white-label checklist).

## 0.68.0 -- 2026-06-27
- Enterprise auto-update — the fleet now converges itself; updates are no longer "whoever remembers to push to
  each node." Root cause this kills: shopos sat 39 versions behind (0.28 vs 0.67) because the push ritual only
  ever named AFP — detection (Fleet-drift lens) existed but was decoupled from action. Two idempotent,
  version-gated convergence paths: (A) PULL — every TENANT node self-checks the public dist (~150s after boot,
  then every auto_update_check_min=30) and, if behind, overlays the latest framework via `cc-update.sh <git-url>`
  (real git clone, so freshness never depends on a local mirror) and self-restarts WHEN QUIESCENT (no session
  mid-turn; 2h grace backstop for always-busy nodes). This is the guarantee — nobody has to remember a node, and
  NEW/just-provisioned nodes converge on their own first boot. (B) PUSH — Mission Control's `fleet_converge`
  refreshes the dist mirror then drives cc_update + a SEPARATE safe restart into every behind tenant in one shot;
  exposed as "⬆ Update all behind" / "⟳ Force all" on the Fleet-drift lens + `POST /api/fleet-update`, plus a 3h
  MC backstop sweep. SOURCE nodes (the authoring checkout — git remote claudesole-core — and the dist mirror) are
  detected and NEVER self-update or get pushed to, so a converge can't clobber in-progress edits. Cross-user
  restart (AFP) always uses the node's own superadmin `restart`, never `cc_update restart:true`. Config: auto_update,
  auto_update_check_min, auto_update_restart(+_grace), update_source, update_role, fleet_auto_converge. APIs:
  GET /api/update-status, POST /api/update-now, POST /api/autoupdate, POST /api/fleet-update. Log: _autoupdate.log.
  Full design + invariants + ops: command-center/update/ (CLAUDE.md + UPGRADE_SYSTEM.md).

## 0.67.0 -- 2026-06-27
- Auto-compact: a session's context never blows its window unattended. A server-side daemon watches every
  session's context fill level; when one crosses the threshold (default 95% full) it runs the SAME graceful
  compact the operator runs by hand — write a COMPREHENSIVE handoff -> /compact -> re-read the handoff — so the
  agent keeps its memory across compaction. Reuses compact_session()/_compact_worker() wholesale; the new code
  is just the threshold watcher + a 15-min per-session cooldown (so it can't re-fire while the post-compact
  context measurement still lags). Fires even with no browser open. Aborts untouched if the handoff can't be
  written (same safety as the manual flow). Config (cc.config.json): `autocompact` (bool, default on) +
  `autocompact_pct` (% full, default 95). UI: a "♻ Auto-compact on · 95%" toggle in the Sessions toolbar —
  click to flip, Shift-click to set the %. API: GET/POST `/api/autocompact`. Log: `_autocompact.log`.

## 0.66.1 -- 2026-06-27
- Sessions strip fuel: the account LIVE on the machine you're viewing now LEADS the row and gets the bright slot
  outline — previously the ▶ recommendation got first-position + the glow, which on a node you're NOT logged
  into read as "this box is on that account." The gold ▶ stays as the separate, subtler "use next" marker.

## 0.66.0 -- 2026-06-26
- Live-login integrity — the account switch (`_kc_write`) now writes `~/.claude.json` AND VERIFIES it persisted
  (retry + a loud WARN to `~/.cc-credential-changes.log` on failure), so the keychain login and the
  displayed/attributed account can never silently desync — the live-account the overseer trusts stays truthful.
  (Investigation confirmed detection was already correct: each node's live account is fingerprinted by its real
  `/usage` reading — sarahaios→sarah at 73% weekly vs getcalibrated at 11% — so attribution was never wrong.)
- Friendly machine labels: `side_label` = "hptuners" (the 3 hptuner-user nodes) and "AFP" (sarahaios), so the
  Sessions strip's "● live on <machine>" markers read unmistakably across the fleet.

## 0.65.0 -- 2026-06-26
- Sessions strip — distinguish LIVE from RECOMMENDED (the overseer already tracked which macOS user is on which
  account via current_email/live_on per store; this SURFACES it). Each account in the fleet-fuel barometer now
  shows a green ● LIVE marker — "● live" when it's the login on the machine you're viewing, "● <user>" when it's
  live on another user (e.g. sarah ● sarahaios), "○ idle" when logged in nowhere (last-known usage + reset
  dates remembered) — DISTINCT from the gold ▶ "use next" recommendation. Fixes mistaking ▶ for "logged in"
  (e.g. on AFP, where sarah is live but getcalibrated is the pick).
- Plus: a ↻ soonest-reset countdown per account, display names shortened to first-name, and a subtle gold
  border on every battery slot so each gauge shows its full footprint even at 0% used.

## 0.64.0 -- 2026-06-26
- Sessions "Usage · Account Meter" strip — ground-up redesign of the bar above the Sessions terminal into ONE
  cohesive instrument (design "A3"; no bordered boxes, tabular-mono numbers, monochrome gold, hairline dividers):
  * SPEND stat-rail — the 5 metered windows (1h/5h/24h/wk/mo) each with $ + an over/under-30-day-avg caret;
    click a window OR the trend graph to cycle which window the sparkline shows (persisted).
  * FLEET FUEL barometer — two rows (5-hour + weekly), each N EQUAL per-account gauges that FILL with % used
    (monochrome gold rises as an account is consumed; warms slightly near the limit); names + 5h/wk used%
    underneath, the recommended account marked ▶. Reads /api/token-usage + /api/account-windows.
  * Minimize + remember — a Windows-style `_` button collapses the strip to a slim "📊 Usage · Account Meter"
    title bar (with a faint live summary); the choice persists in localStorage.
  Designed by iterating standalone retina HTML mockups delivered to the Files lens, then porting the final.

## 0.63.0 -- 2026-06-26
- Autopilot CAPTURE layer (prerequisites for safe unattended account-switching; the switch LOOP is intentionally
  NOT enabled yet -- let the limit model bake first):
  * Cross-user switch: new signed superadmin action `switch_account` -- the overseer can switch ANY node's live
    login (so it can orchestrate the fleet: assign each macOS user a distinct account). Single-node switch was
    already one-click.
  * Login freshness: a successful live /usage read (or a snapshot) stamps `~/.claude/_cc_acct_login_validated.json`
    {email->ts} -- proof this user's stored login for that account currently works -- so autopilot never switches
    onto a stale/expired login. Surfaced per account (validated Xago / "stale, re-snapshot").
  * Wallet inventory + idle reported up: each node's store now reports its wallet (which accounts it can switch
    to + freshness) and an idle signal (seconds since last session activity). account_windows_all merges these
    into per-account `switchable_on:[{side,validated_ts,fresh,idle_secs}]` + per-side `idle_secs`, so the overseer
    knows WHERE each account can be safely switched to and WHEN a machine is idle enough to switch.
  * UI: "Logged in now" shows ● active / idle per machine; each account shows its login-freshness.

## 0.62.0 -- 2026-06-26
- Account LIMIT MODEL (reverse-engineer the hidden window budgets) -- Anthropic doesn't publish the token
  budget of a 5h/weekly window, so we LEARN it: at each /usage scrape we log the observed % alongside our
  cumulative per-account token telemetry since the window started (cost / context / billable / raw), then fit
  capacity = the slope of feature-vs-(%/100) through the origin, keeping the best-R² weighting per window. New
  shared calibration log `~/.claude/_cc_acct_calib.jsonl` (per macOS user). Each node fits + predicts for its
  OWN accounts and ships the model in `/api/account-windows-store`; the overseer merges so a model calibrated
  on another user still shows. Once enough samples land it surfaces a per-account "limit model" panel:
  estimated capacity, a LIVE %-prediction between scrapes, recent burn rate, and a MAX-OUT ETA vs reset (with a
  warning when an account will cap before it resets). Shows "calibrating (n/6)" until ready. Foundation for the
  predictive/auto-switch autopilot (not yet enabled).
- account_windows_store cached 25s (it now does telemetry scans) + busted on every new reading.

## 0.61.1 -- 2026-06-26
- Account fuel self-heals a flaked /usage read instead of waiting the full 30m poll: (1) the poller now
  RETRIES SOON after a failed live-account read -- escalating 3/6/9… min up to the normal interval -- so a
  transient scrape flake recovers in minutes; (2) opening the Accounts/Usage lens kicks a background re-read
  when the live account's reading is stale (>10m) or errored (at most once / 5m). Failed reads still preserve
  the last-good gauges (never blank).

## 0.61.0 -- 2026-06-26
- Accounts/Usage -- merged the standalone "Claude Accounts" lens INTO the Usage lens (one "Accounts / Usage"
  tab) and added per-account RATE-LIMIT FUEL GAUGES: each Claude subscription account's 5-hour session + weekly
  (all-models / Sonnet) windows as % used + live reset countdowns, with a "use this next" recommendation that
  minimizes wasted capacity (drain the soonest-resetting account that still has headroom; rest one near its
  weekly cap).
- FLEET-aggregated at the overseer: new mesh-gated `/api/account-windows-store` (cached) lets the overseer roll
  up EVERY macOS user's report and show ALL accounts with the FRESHEST reading per account + which user each is
  live on. Per-user shared cache + single-poller file lock under `~/.claude` so co-located instances (overseer +
  nodes on one user) no longer collide on the `/usage` scrape.
- LIVE-account-only reads: a setup-token (`CLAUDE_CODE_OAUTH_TOKEN`) runs `/usage` in API mode with NO
  subscription windows, so only the live keychain login is readable; non-live accounts show last-known windows
  (refreshed whenever they're next the live login -- here or on another user). The setup-token path was removed.
- One-click account switching kept + improved (reads the newly-live account's windows right after the switch).
- Root CLAUDE.md: added the Mission Control "SHIP AN UPDATE TO THE WHOLE FLEET" playbook + a hard rule that any
  server.py/lens edit must restart ALL co-located instances (hpcc/cc-overseer/cc-carsearch), not just one.
- Verified headless on 8800 (no JS exceptions; gauges, recommendation, live-on/last-seen, switch buttons render).

## 0.60.0 -- 2026-06-26
- TASKS hardening -- fix the "list full of repeat/junk tasks" failure (hit on a bulk-outreach inbox):
  * ROOT CAUSE: the commitment regex used optional-apostrophe contractions (`i'?ll`/`we'?ll`), which ALSO
    match the plain words "ill"/"well" -- so every "Hope you're well!" outreach greeting was extracted as a
    "(you committed)" task. Contractions now REQUIRE an apostrophe (straight or curly); "ill"/"well" no longer match.
  * Greeting/pleasantry/sign-off denylist (`_is_task_boiler`): "hope you're well", "let me know what you think",
    "looking forward", "thanks so much", "hi/hello/dear ...", etc. are never extracted as tasks.
  * Titles are HTML-unescaped + tag-stripped in task_add (no more raw `&#39;`); whitespace collapsed.
  * Dedup hardened: a fingerprint already seen never re-adds in ANY status -- dismissed/done suggestions don't
    resurrect on the next scan (the morning loop is now safely idempotent).
  Verified: greetings/"ill"/"well" no longer match; real commitments/requests still do. AFP task list cleaned.
- TASKBAR drag-to-reorder: press-and-hold a session tile in the bottom dock -> the dock WIGGLES and the tile
  lifts (clearly grabbable) -> drag left/right to reposition -> release. The order is saved PER DEVICE
  (localStorage `hpcc_sb_order`) and survives refresh; new sessions append after your arranged ones. Pointer-
  based (mouse + touch): a 300ms hold starts it, a quick tap still opens the session, an early move scrolls.
  sbRender now orders tiles by the saved order; sbHover is suppressed during a reorder. Verified end-to-end.
- NEW-SESSION PICKER rebuilt from scratch (the old nested tree was scrapped entirely). Researched against
  best-in-class pickers (VS Code Quick Open, Raycast, Linear). It is now a SEARCH-FIRST DRILL palette:
  * The launch TARGET is your current location -- no separate "select" step. The breadcrumb AND the footer
    button always name exactly where it'll launch ("▶ Launch in agents/cost"). Fixes "who knows where I'm
    launching."
  * Sticky header (search + breadcrumb + "＋ New folder") and sticky footer (name + machine + Launch); the
    BODY is the only scroller (flex column, overflow on the list) -- nothing is ever cut off, any-size group
    scrolls (the root cause of the old cut-off was nested scroll containers).
  * Type to fuzzy-search every launch place (all projects/agents/extensions) -- one keystroke to any of them.
  * Tap a row = drill in (it becomes the target); per-row "▶ launch" = launch there directly; folders only.
  * Live sessions surfaced as "resume →" rows (jump into a running agent); ● N badge per folder.
  * ＋ Add subfolder at any location (header button + permanent last row) -- reuses the Projects /api/module-add.
  * Full keyboard: ↑/↓ highlight, Enter drill, Cmd/Ctrl+Enter launch, Backspace up, Esc clear/close. Touch-OK
    (no hover-only actions). Removed ALL old ns*/nstree code + CSS.

## 0.57.1 -- 2026-06-26
- FIX Claude Accounts: the "save this account" button was HIDDEN once an account was saved, so there was no way
  to RE-SNAPSHOT (refresh) a stale/expired saved login -> switching to it 401'd with no recourse. Now there's
  an always-available "📸 Snapshot this login" button (labeled "Re-snapshot (refresh)" when already saved).
  Fix a 401 account: switch to it (or /login it) -> /login to re-auth -> 📸 Re-snapshot to save fresh creds.

## 0.57.0 -- 2026-06-26
- NEW-SESSION TREE revamp (sleek, two-line, session-aware):
  * Two-line rows -- bold name over a CLIPPED one-line description (readable but can never overflow the modal;
    proper fix, not a tooltip). Folders only (no files).
  * LIVE SESSIONS surfaced: a folder shows a green "● N" badge for agents already running in it; expanding it
    lists those sessions as "resume →" rows (click jumps into the running session instead of launching new).
    Backend: `_sessions_by_rel()` maps live tmux sessions to their project-relative folder; launch_tree +
    browse_dir annotate places/dirs with `sessions`.
  * ＋ ADD SUBFOLDER at ANY node (hover action) -- same mechanism as the Projects tab (`/api/module-add` ->
    CLAUDE.md scaffold); the new folder appears in place, ready to launch into.

## 0.56.1 -- 2026-06-26
- FIX New-session picker overflow: launch-point rows showed the full (often long) CLAUDE.md description inline,
  which ran past the modal and triggered a horizontal scrollbar. Rows are now COMPACT (icon + name); the full
  description shows as a hover tooltip. Plus the label clips with ellipsis + tree is overflow-x:hidden.

## 0.56.0 -- 2026-06-26
- LAUNCH POINTS are now a FRAMEWORK MECHANISM (the New-session picker, built right):
  * `register_launch_provider(name, fn, order)` -- a provider registry mirroring `register_sendable`. Core
    providers: Projects / Agents / Extensions. `launch_tree()` merges them into recognizable, collapsible
    groups. Each place drills into WHATEVER REAL FOLDERS live inside it (browse); descriptions come from the
    folder's CLAUDE.md one-liner (`_msummary`).
  * EXTENSIONS declare their own launch points in `extension.json` (`launch_points[]` + `launch_group`); ONE
    core provider reads every extension manifest, so a NEW/unbuilt extension lights up with ZERO core change.
    `browse_dir` also honors an extension's declared launchable subdirs. Documented in extensions/AUTHORING.md.
  * PRESETS can declare `launch_groups` (config-not-code) so deployments/future lenses add launch points with
    no server.py edit.
  * AUTO-LEARN: launching into a folder with no CLAUDE.md briefs the agent (`_NEW_FOLDER_BRIEF`) to create one
    (H1 title + one-line description matching the preview parser) -> the place becomes a recognized, previewable
    launch point next time. The system learns its launch points as work happens.
  * UX: groups COLLAPSED by default (compact, no modal overflow); picker shows FOLDERS only (never individual
    files -- you launch an agent in a folder); per-place one-line descriptions; "Show all folders" escape hatch.

## 0.55.0 -- 2026-06-26
- NEW SESSION picker = launch places at top, real folders underneath (the model James actually wanted):
  * Top level = the logical launch PLACES (modules/extensions with a CLAUDE.md / extension.json + pillars),
    matching the Projects tab. Marked 🧩.
  * Expand ANY of them -> WHATEVER REAL FOLDERS live inside (lazy /api/browse), not just CLAUDE.md sub-modules.
    Designated places 🧩, plain folders 📁, files dimmed. Drill + launch at any depth.
  * EXTENSIONS (and any place) designate their claude-launchable locations: browse_dir marks a folder
    "designated" if it has a CLAUDE.md / extension.json, OR if the parent extension's extension.json lists it
    under "launchable". So an extension self-declares where agents should launch.
  * "Show all folders" now toggles the TOP level too (curated launch places <-> raw folder list); auto-fallback
    to raw folders when a project has no designated places.

## 0.54.0 -- 2026-06-26
- REVERT the Projects-tab pin/hide curation (0.53) -- wrong surface. The logical launch-place picker is the
  NEW SESSION button (Sessions topbar -> openLaunch): a curated tree of where you'd launch an agent (project
  folder + subfolders, extensions, modules), drillable, with "Show all folders" as an escape hatch. The
  Projects tab is back to the clean drill-down browser (no pin/hide). Removed /api/launch-curate + state.

## 0.53.0 -- 2026-06-26
- PROJECTS tab = a curatable list of launch places (auto + pin/hide). Each project/module card now has a clear
  "▶ launch agent here", plus 📌 pin (float to top) and 🚫 hide (tuck behind a "show hidden" toggle). The list
  is still auto-detected (modules/pillars), but you control what's prominent vs hidden -- per node, persisted.
  * New GET/POST /api/launch-curate (pinned/hidden rels in _launch_curate.json); modCard renders pin/hide;
    loadModules partitions pinned -> top, hidden -> collapsible section.

## 0.52.0 -- 2026-06-26
- OVERSEER "Projects" tab now matches the nodes: it used a different lens (a flat platform-component card list)
  than the nodes' polished drill-down module browser, so it looked worse and didn't drill. Overseer preset now
  uses the `modules` lens -> same breadcrumbed, click-to-drill, "launch here" browser, rooted at the control
  plane (the overseer manages the ClaudeFather infrastructure itself: agents, command-center, extensions, etc.).
  (presets/overseer.json: "projects" -> "modules".)

## 0.51.0 -- 2026-06-26
- NEW SESSION tree is now CURATED (enterprise/installable): instead of the raw filesystem, it shows only
  INTENTIONAL launch targets -- folders that are recognized UNITS (carry a CLAUDE.md / extension.json, plus the
  configured pillars) + the ancestors needed to reach them. Convention-driven (zero config -> works on any
  install). Designated units are bold; navigation-only ancestors are dimmed.
  * New GET /api/launch-tree -> nested curated tree (depth-capped walk, CC_SKIP-pruned, fast).
  * "Show all folders" toggle = escape hatch to the full filesystem browse when you need to launch somewhere
    without a CLAUDE.md. If a deployment has NO designated targets (a non-ClaudeFather project) it auto-falls
    back to all-folders so the picker is never empty.

## 0.50.0 -- 2026-06-26
- FIX (New session tree): the root auto-expanded its caret but its children container stayed display:none, so
  only the project root row showed ("just shows hptuners-control"). nsTreeInit now actually reveals the root's
  children. Verified visible (computed offsetParent), not just present in the DOM.

## 0.49.0 -- 2026-06-26
- NEW SESSION redesign -- pick the working dir by BROWSING the project/client tree:
  * The "Folder" picker is now an INTERACTIVE, lazily-expanding tree rooted at the project root (each folder
    expands to show its contents on demand via /api/browse; click a folder to launch the session there). Files
    shown dimmed for context. Replaces the old flat "Pillar (working dir)" dropdown (limited to registered
    components) -- you can now launch anywhere down the tree (clients, projects, subfolders).
  * Launch in any folder: /api/launch now passes `rel` through to launch() (the backend already supported a
    project-relative working dir). Verified end-to-end (session cwd lands in the selected subfolder).
  * The machine selector ("Run on") only appears when there's MORE than one machine -- on a single-box
    deployment a session always runs locally, so we no longer ask. (Answers "why is there a Where?")

## 0.48.0 -- 2026-06-26
- FIX: "New session" was unusable on the overseer + fresh nodes -- the "Where" (machine) dropdown was built
  only from the per-deployment machines registry, which is empty there, so there was nothing to select.
  Now ALWAYS offers the local box ("This machine" -> the backend's "studio" local-launch sentinel, which
  works with no machines registered); existing nodes still list their real machines (no duplicate).
- DESKTOP CTA restyle: the "Try ClaudeFather Desktop" button was far too prominent (top of nav). Now a small,
  subtle "Get the desktop app" link under the brand (web-runtime only, same download menu) -- professional,
  not in the way.

## 0.47.0 -- 2026-06-26
- DESKTOP delivery + auto-update (so we can ship the shell often with minimal labor):
  * Dashboard CTA "🎩 Try ClaudeFather Desktop" (sidebar, prominent) -- Mac (Apple Silicon/Intel) + Windows
    download links to GitHub Releases `latest/download` (stable filenames). WEB-runtime only (auto-hidden
    inside the desktop app via body.cf-desktop). Auto-marks the recommended OS.
  * Shell auto-update via electron-updater + GitHub Releases (jkarger123/claudesole-dist) -- ONE release is
    both the download source and the update feed. Windows: silent download + install on quit (works unsigned).
    macOS: notify + open download (unsigned can't silently update; sign with an Apple Developer ID for silent).
    No-op in dev; never crashes the app.
  * package.json: publish=github, stable artifactNames (ClaudeFather-Desktop-${arch}.dmg/.zip,
    ClaudeFather-Desktop-Setup.exe), release:mac/release:win scripts. First release published: v0.1.0.
  * THE MODEL (key): the desktop app is a THIN SHELL loading the LIVE dashboard -> dashboard/feature/server
    changes need NO rebuild (users just reload); ONLY shell-file changes (main.js/preload/dashboard-preload/
    package.json) require a release. Playbook: desktop/RELEASE.md; one-shot: cf-desktop-release.sh (MC-only).

## 0.46.0 -- 2026-06-26
- HOMING (docs/VISION.md Phase 3, "context follows you"): when focus moves to a NEW subject and you have a
  session open, ClaudeFather auto-delivers that subject's CITED context slice to the session -- you never
  navigate to the right context, it comes to you. Opt-in (default OFF), safe by construction:
  * server.py: `_homing_maybe`/`_homing_fire` fire from `/api/focus-report` on a focus switch; trailing-edge
    DWELL debounce (6s -- briefs the subject you SETTLE on, not ones you fly past) + per-(subject,session)
    cooldown (10 min). Reuses the exact `context_brief` "catch me up" path (additive, cited, NOT auto-run).
  * `/api/focus-set` now MERGES (toggling the trust dial no longer wipes homing); new `homing` flag.
  * GET `/api/homing` (on/off + recent auto-briefs); `/api/focus` reports the homing flag.
  * Context lens: a "🧭 Homing" row -- one-tap on/off + a live log of recent auto-briefs (subject -> session,
    N cited). Independent of the macOS trust dial (in-app focus signal is always available).
- DESKTOP: macOS installer build verified (electron-builder -> arm64 + x64 DMG/zip); Windows NSIS via dist:win.

## 0.45.0 -- 2026-06-26
- BROWSER v2 -- indistinguishable-from-Chrome + agent-drivable, fully inside the context loop:
  * SERVER command channel (server.py): POST /api/browser/queue (open/navigate/new_tab/scroll_to/highlight/
    screenshot/reload/back/forward/act); GET /api/browser/commands (the desktop polls; marked sent on read);
    POST /api/browser/ack (a returned page snapshot is RE-INGESTED into context = browser->context).
  * CONTEXT-DRIVEN: POST /api/browser/show {subject} picks the page WE ALREADY KNOW about a subject (a saved
    clip/email/link) FROM the context graph and opens+highlights it = context->agent->browser. Agents are told
    they can do this (the SYSTEM MAP brief). Verified end-to-end (queue->poll->ack->re-ingest; show resolved
    the right URL).
  * DESKTOP executor (desktop/): polls /api/browser/commands and runs them in a real Chromium tab
    (open/scroll/highlight/screenshot/nav); a "🤖 Agent control" toggle (DEFAULT OFF) gates write actions
    (click/type) -- show-me actions always run, with a visible "agent did this" toast; only ever obeys the
    user's own server. Persistent profile + multi-tab were already in the shell -> now a real, agent-drivable
    browser.
  THE FULL CONTEXT LOOP is closed + tested: browse->context (ingest-page), context->co-read (page-intel),
  context->agent->browser (browser/show), browser->context (ack re-ingest).

## 0.44.1 -- 2026-06-26
- FIX (capture): a saved screenshot whose subject didn't resolve to a project folder was written to the
  managed store but then DROPPED (image_rel returned None when the file landed outside PROJECT). Now it keeps
  the reference (abs path) so a screenshot is never silently lost; resolvable subjects still file into the
  client's deliverables/clips and show in Files. Found by the comprehensive test pass.

## 0.44.0 -- 2026-06-26
- RUNTIME AWARENESS + agents understand the system (enterprise; works with OR without the desktop app):
  * The client reports its runtime -- the Electron desktop shell injects window.cfDesktop (runtime/platform/
    capabilities) via a workspace preload; the web app detects it, sets window.CC.runtime ('desktop'|'web'),
    POSTs /api/runtime, and tags <body class=cf-desktop>. No desktop app -> plain 'web', everything still works.
  * GET /api/system -> a self-describing capability map (node + runtime + live surfaces: context, capture,
    google, agency, slack, zoom, focus, mesh). UI gating + agent awareness source.
  * Agents UNDERSTAND the whole system: a live SYSTEM MAP (_system_brief) is injected into the chief launch
    brief -- the architecture (context layer + router/brief, capture loop, focus engine), what's configured on
    THIS node, and the user's runtime (so an agent never offers a desktop-only capability on web, and uses the
    context router to catch up instead of guessing).
  * Desktop app is now Windows + Mac (electron-builder win/nsis target + dist:win/dist:all); capability
    detection degrades per-OS. Brain server stays Mac-first; users can be on either.

## 0.43.2 -- 2026-06-26
- HARDEN (turn the 0.43.0 incident into a permanent fix -- a node must never die over one file):
  * DEFENSIVE engine imports: granola/context/focus/slack/zoom/clips are now imported via `_opt_import`; a
    missing/broken optional module substitutes an inert stub (every call returns {"ok":false,...}) so the
    FEATURE goes dark but the NODE STAYS UP -- no more crash-loop on a missing import.
  * PRE-SHIP invariant (`command-center/preship.py`): verifies every local command-center/*.py that server.py
    imports is in framework_paths (the exact thing I missed with clips.py). Run before every ship; exit 1 on
    a gap. (Root cause of the AFP outage: server.py imported clips.py but it wasn't in framework_paths, so
    cc-update didn't propagate it.) Also observed + noted: a dead peer can stall a node via mesh/superadmin
    blocking -- follow-up to bound all peer-contacting calls so an unreachable peer can never hang a node.

## 0.43.1 -- 2026-06-26
- HOTFIX: add command-center/clips.py to framework_paths. 0.43.0 shipped a server.py that `import clips` but
  clips.py wasn't in framework_paths, so cc-update didn't propagate it -> remote nodes (AFP) crash-looped on
  the missing import. (Local fleet was fine -- shared file.) Re-shipped; AFP restored. Follow-up: make the
  new-module imports defensive so a missing optional module can never take a whole node down.

## 0.43.0 -- 2026-06-26
- VISION: the CAPTURE system -- turn the world into context (docs/CAPTURE.md). One review-first loop
  (Capture -> Triage -> Propose -> you Approve -> Applied with receipts), built fleet-wide by a fan-out of
  agents, all additive (web app unchanged):
  * SPINE (clips.py + server.py): POST /api/clip saves a page/clip to a subject's tray (+ screenshot to
    deliverables/, + a provenance-stamped context event); /api/clips lists; /api/clips/process runs a headless
    triage agent (cluster, dedup, summarize, extract tasks/decisions/contacts) and PROPOSES a CC:CLIPS digest
    + tasks + files; /api/clips/apply applies on approval, every line citing its source; /api/clips/skip. New
    Capture lens (clip tray + review queue, styled like Calls). Optional EOD Routine (off by default, never
    auto-applies).
  * page-intel: POST /api/context/page-intel {url,title,text} -> what we ALREADY know relevant to a page
    (related + flags) -- powers the desktop AI co-reading sidebar.
  * DESKTOP (desktop/): ⭐ Save (cmd-shift-S) + 📸 screenshot clip + 🧠 co-reading sidebar (cmd-shift-E),
    all explicit/opt-in, talking only to the user's own server.
  * SLACK (slack.py + extensions/slack): read client channels into context (trust=contact) + save-thread;
    no-op until a bot token is configured.
  * ZOOM (zoom.py): cloud recordings + dropped .vtt/.txt transcripts -> the SAME granola proposal pipeline
    (appear in the Calls lens -> CC:CALLS + tasks). /api/zoom-sync, /api/zoom-drop.
  Review-first + provenance/trust throughout; stdlib-only; nothing edits a CLAUDE.md or sends without approval.

## 0.42.0 -- 2026-06-26
- VISION: make focus work for REMOTE users + lay the desktop track. Two additive pieces, web app unchanged:
  1) WEB CONTEXT-BRIDGE (server.py, additive): the focus signal now comes from the BROWSER, not the server's
     macOS reader (which only sees the unattended Studio). POST /api/focus-report {lens,subject,session,url,
     title,text} -> focus_now() PREFERS a fresh (<120s) browser report (explicit subject = 0.9 conf; else
     classify) so "🎯 you're on X" works from anyone's laptop/phone, even with the macOS dial off (in-app
     activity is the user's own workspace). A debounced client reporter fires on lens/subject/session change.
     POST /api/context/ingest-page {url,title,text} -> ingests a viewed page as a "web" event (honors the
     trust dial: skipped unless capture>=context; size-bounded; skips obvious auth/secret URLs). All existing
     routes/behavior untouched.
  2) CLAUDEFATHER DESKTOP (new desktop/ -- optional Electron client, does NOT change the web app): loads the
     user's dashboard in one tab + a REAL Chromium browser (WebContentsView) in another, and a context bridge
     reports the active page (url/title/text) to the user's own server's /api/{focus-report,ingest-page} so
     the AI sees what you browse. Capture OFF by default with an always-visible toggle; config (server URL +
     auth) persisted 0600; reports only to the user's server (no telemetry). Web/phone/any-device access over
     Tailscale keeps working with NO install; the desktop app is pure addition that unlocks the browser +
     page-vision. (GUI not testable headlessly; runs on a Mac with a display -- see desktop/README.md.)

## 0.41.0 -- 2026-06-26
- VISION Phase 3 (the magic) + the CONTEXT X-RAY (show users why this is hard to replicate):
  * FOCUS/INTENT engine (focus.py): reads a lightweight activity signal -- frontmost app + bundle id (NO
    macOS permission), and (when granted) window title + active browser URL -- and classifies it to a SUBJECT
    in your context graph (rules -> lexical match). On-demand only (no background capture); gated by a TRUST
    DIAL (off|app|context|deep, default OFF, per-deployment). /api/focus (read) + /api/focus-set (dial). A
    "🎯 you're on X" row in the Context lens with one-tap enable + "brief a session on this". Degrades
    silently when Accessibility/Automation isn't granted.
  * CONTEXT X-RAY: a sleek, plain-language "behind the curtain" panel rendered on every assemble -- a
    horizontal pipeline (memories in store -> candidates matched -> ranked by relevance·recency·trust ->
    duplicates/noise removed -> fit the window -> every source cited), source + trust chips, and the punchline
    contrast: a blank chat box starts with nothing; ClaudeFather just handed the agent N sourced, ranked,
    cited facts from your tools automatically. The router now returns a `pipeline` summary to power it.

## 0.40.0 -- 2026-06-26
- VISION Phase 2 -- the context layer becomes USED, not just visible: "CATCH ME UP". /api/context/brief +
  a "Brief a session" button on the Context lens: name a subject/question, the ROUTER assembles the cited,
  budgeted, edge-placed slice, and it's injected straight into a chosen session (reusing the upload path-
  injection) -- the agent rides in ALREADY KNOWING. Plus VISION Phase 1 seed: ingest now deterministically
  seeds the entity graph (person from the actor/email, keyed so the same person resolves across sources; +
  subject entities), so the flat log becomes a real graph the lens + router can use. No new deps; stdlib.

## 0.39.0 -- 2026-06-25
- HARDEN (mesh trust + authority -- turn a real incident into a permanent fix): a relayed peer request
  carried no trustworthy metadata, so the receiver had to GUESS freshness from a hand-typed version string
  (which was wrong) and a peer chief argued a false disk claim from memory. Two framework fixes:
  1) MESH ENVELOPE: every inter-chief message is now auto-stamped by the SENDING server with its real
     manifest version (from_version) + send time (sent_at) + msg id, and the RECEIVER renders a
     machine-generated "[mesh envelope -- transport-verified, trust over body claims: node vX | sent ... (Nm
     ago) | msg ...]" header before the security frame. No agent ever guesses staleness or trusts a
     hand-typed version again. (Back-compat: old senders just omit the fields.)
  2) AUTHORITY CHARTER in the chief launch brief + peer security frame: operator > Mission Control (the
     fleet's DEFINITIVE source of truth) > untrusted peer chiefs. Chiefs must VERIFY against ground truth on
     disk (ls/read the file, cite the command+output) before disputing any state claim -- "I believe I did X"
     is not evidence X happened; they may flag a genuine blind spot ONCE with evidence, but MC's call is
     final (not mute, but no looping/re-litigating); never state your own version/timestamp from memory --
     read the envelope. Ships to every node so no future agent repeats it.

## 0.38.1 -- 2026-06-25
- FIX: add the Context nav button (data-l="context") -- the lens was in the preset + NAV map but had no nav
  button to render, so it didn't appear. Verified in a headless browser: button present, lens loads, Assemble
  works.

## 0.38.0 -- 2026-06-25
- NEW: THE CONTEXT LAYER (foundation for the "perfect context, every time" north star -- see docs/VISION.md).
  command-center/context.py: a stdlib sqlite3 event store (append-only, WAL, FTS5) + entity/edge graph with
  PROVENANCE + TRUST on every row, and THE ROUTER (assemble): retrieve (FTS + recency + subject) -> rank
  relevance×recency×trust -> dedup -> budget to the window -> EDGE-PLACE the highest-signal items
  (lost-in-the-middle) -> return a CITED bundle. Completeness lives in the store; agents get a small curated
  slice (because context rot makes "more context" worse, not better). Idempotent ingest adapters backfill the
  surfaces we already have (Gmail/Calendar/Granola/deliverables) on boot + every 15 min. New routes
  /api/context/{stats,assemble,search,backfill} + a Context lens (watch the router assemble a cited slice for
  a subject/question). Self-tested (python3 context.py selftest) and verified live (ranked, edge-placed,
  cited). Grounded in deep 2025-26 research (context engineering, tiered memory, bi-temporal graphs,
  federation security) captured in docs/VISION.md -- the new product north star (single-user sovereign +
  federated combine layer, context-follows-intent, the trust dial, provenance-bound capability).

## 0.37.11 -- 2026-06-25
- FIX (mobile terminal resize -- now VERIFIED in a headless mobile browser, not guessed): two root causes
  found by actually driving the page: (1) termAvail() called window.scrollTo(0,0), and mobile scrolling fires
  'resize', so the page got pinned to the top = "can't scroll at all"; (2) the max was derived from the
  unstable element top and equalled the current height, so + could never grow it. Now: max = innerHeight -
  (measured dock height) - 18 (STABLE, no scrollTo, no scroll-lock); default = 78% of the screen (tall);
  - shrinks, + and drag grow up to ~full screen; per-device save + restore-on-refresh confirmed. Test (Chrome
  headless, iPhone viewport): default 658px, +x4 -> 779 saved, -x2 -> 599 saved, reload -> 599 (match), and
  page scroll is no longer reset.

## 0.37.10 -- 2026-06-25
- FIX (mobile terminal resize: page scrolled while dragging + forgot size): on mobile the PAGE (not .wrap) is
  the scroller, so the clientHeight max inflated and the terminal grew past the screen -> page scrolled, the
  bottom grip couldn't be dragged in one motion, and the scroll hijacked the gesture so save-on-release never
  ran (= forgot). Now the max is the true viewport space (measured from the unscrolled top), the terminal is
  capped there so it fills but never exceeds the screen, and scrolling is LOCKED during the drag. Result: one
  smooth drag fills it, no page jumping, and the size saves + restores on refresh.

## 0.37.9 -- 2026-06-25
- FIX (mobile terminal resize: forgot size on refresh + still scrolled the page when expanding): the max
  height was derived from the element's viewport top (getBoundingClientRect().top), which is unreliable -- when
  off, the terminal grew past the screen and the page scrolled ("only goes a little, then scroll, then more").
  Now max = the .wrap scroll container's clientHeight (scroll-independent, already excludes the dock) minus the
  grip row, so the terminal fills the screen exactly and never pushes the page. And termApplySaved now waits
  (rAF) for the list to lay out before applying the saved height -- it was running at clientHeight 0 and
  clamping the remembered value to junk, which is why it 'forgot' on refresh.

## 0.37.8 -- 2026-06-25
- FIX (mobile terminal resize -- - grew instead of shrank + drag was janky): root cause was the "grow past
  the viewport with page-scroll" design -- once the terminal scrolled the page, its top went negative and the
  floor calc inflated above the current height, so BOTH -/+ clamped upward (everything grew), and the
  auto-scroll made the page lurch under your finger. Removed all of that: the terminal is now BOUNDED to the
  visible space above the dock (xterm keeps its own scrollback), so the page never scrolls, dragging is smooth,
  - actually shrinks (floor 240px), + and drag grow up to fill-screen. Default = fill screen; remembered per
  device (old oversized saved values self-heal by clamping to the viewport).

## 0.37.7 -- 2026-06-25
- Mobile terminal resize WORKS (root cause: the CSS var --cf-term-h wasn't applying through the cascade).
  Now the bigsess element is sized directly via inline !important; the − / ＋ buttons and the drag bar both
  resize it; height is shown live (↕ NNNpx) and remembered per device; increase-only floor = full-screen fit.
  Removed the temporary tap-counter diagnostic now that it's confirmed working.

## 0.37.6 -- 2026-06-25
- FIX/DIAGNOSE (mobile terminal resize still dead): now size the bigsess ELEMENT directly with inline
  !important (height/flex/min-height) instead of relying on a CSS var the cascade may have been dropping;
  added a tap counter to the readout (↕ NNNpx (N)) so we can distinguish "taps not reaching JS" from
  "height won't change"; and gave the grip row 64px clearance above the dock so the buttons aren't tucked
  behind the fixed dock. Per-device memory + drag retained.

## 0.37.5 -- 2026-06-25
- FIX/DIAGNOSE (mobile terminal resize): added guaranteed − / ＋ step buttons (taps, not a gesture) flanking
  the drag bar, and the handle now shows the LIVE pixel height. If the buttons + number move but drag
  doesn't, it's the touch gesture; if even the buttons don't move the terminal, it's the CSS var not
  applying -- so this both gives a working control NOW and pinpoints the remaining issue. Drag bar retained
  (delta-based). Increase-only floor + per-device memory unchanged.

## 0.37.4 -- 2026-06-25
- FIX (mobile terminal resize STILL didn't move): two real bugs. (1) The scroll container on mobile is the
  .wrap list, NOT the window -- my window.scrollBy/scrollY math was inert. (2) iOS fires `resize` during
  scroll (address bar), so the resize handler was resetting the height mid-drag. Rewrote it: DELTA-based
  sizing (height-at-grab + finger delta + container-scroll delta) so it always tracks the finger; scroll the
  real .wrap container; claim the gesture on touchstart (non-passive preventDefault); and a TERM_DRAG flag so
  resize/rotate never resets mid-drag. Bigger grip touch target (30px). Floor = full-screen fit (increase-only).

## 0.37.3 -- 2026-06-25
- FIX (mobile terminal resize didn't grow): the drag grip lit up but wouldn't increase the terminal because
  the max-height clamp was computed BELOW the default height (so every drag clamped downward) and the grip sat
  right above the fixed dock with no room to drag down. Now: the full-screen fit is computed in JS and used as
  the DEFAULT + the FLOOR (mobile = increase-only), the cap is ~3x viewport, and holding the grip near the
  bottom edge AUTO-SCROLLS the page so you can grow the terminal past the viewport. Per-device persistence
  unchanged.

## 0.37.2 -- 2026-06-25
- UI (reclaim the Sessions lens -- two control bars -> one): the Sessions controls (🟢 live count, ⊞/▦/☰
  view modes, 🔑 Admin shell) are now MERGED into the always-visible global topbar via a new #lensTools slot
  (sessToolsHTML/paintSessTools), and the redundant full-width header card (title + hint + duplicate ＋New)
  is DELETED. Only the slim metered-usage strip remains above the terminal. ＋Add is hidden on Sessions
  (▶ New session is the action). Reclaimed vertical space goes to the terminal: focus height offset 300->255px
  desktop, 104->76px mobile. Generic framework pattern (#lensTools) any lens can use to avoid a 2nd bar.
- UI (mobile focus terminal -- taller + drag-to-resize, remembered per device): the mobile focus terminal
  is taller by default, and a grip below it (⋯) drag-resizes it (touch + mouse). The chosen height persists
  in localStorage PER DEVICE (separate phone/desktop-viewport keys) and is clamped to the current viewport on
  load/rotate so it never strands off-screen or under the dock. Driven by a --cf-term-h CSS var
  (termApplySaved/termResizeInit); desktop layout unchanged (grip hidden, var ignored).

## 0.37.1 -- 2026-06-25
- WIRE + TEACH (drag-anything, round 2): (1) Granola CALL TRANSCRIPTS are now draggable from the Calls lens
  -- the card carries data-ss {kind:granola, id:meeting_id} (keyed on meeting_id, what get_transcript wants,
  NOT the proposal id) + a ➔ "send to session" button on the title. Completes the built-in sendable kinds.
  (2) A ONE-TIME animated coach-mark that SHOWS users how it works: the first time a draggable item AND a
  session dock tile are both on screen (post-splash, no modal open), a chip flies from the item DOWN INTO a
  real dock tile -- the real tile lights up (ss-over glow) + a ✓ burst -- looped twice, with a caption
  ("Drag an email/file/Drive doc/event/call onto a session") and a mobile hint ("press & hold, then drag").
  Shown ONCE EVER (localStorage ss_tut_v1); "Got it" or a backdrop tap dismisses; honors
  prefers-reduced-motion (caption only, no motion). The real #sessbar is lifted above the dimmer so the
  landing is visible. Pure frontend, no backend, no deps.

## 0.37.0 -- 2026-06-25
- FEATURE (drag ANYTHING into a session/agent): a generic "sendable -> session" pipeline. Drag a Drive file,
  an email, a calendar event, or a deliverable onto a session (the bottom dock tiles, or the focused
  terminal) and the agent RECEIVES it -- the item is resolved to readable content and its path is typed into
  the session (review + Enter, like the existing file attach). NEW endpoint POST /api/session-send {session,
  kind, id, ...} + a RESOLVER REGISTRY (register_sendable): each kind registers ONE resolver, so
  calendar/granola/future extensions are a one-line addition, no per-type branching. Resolvers return either
  an existing path (inject in place, e.g. a deliverable -- no copy) or bytes/text (materialize to the uploads
  dir, then inject); emails/events become a readable .md, Google-native Docs/Sheets export to txt/csv/pdf.
  Built-in kinds: deliverable, drive, gmail (message or whole thread), calendar, granola. UX: desktop uses
  native HTML5 drag (items are draggable; dock tiles + the terminal overlay are drop targets, highlighted on
  hover); mobile uses long-press to "pick up" -> a floating ghost follows the finger -> drop on a dock tile,
  PLUS a reliable "send to session" (->) picker on every item (and in the Drive context menu / email reader /
  calendar event popover). Self-hides Google kinds when Google isn't configured; read-only + secret-clean;
  bounded by the existing upload size cap; stdlib-only. Reuses + refactors the session-upload path-injection
  (new _deliver_to_session / _inject_path_into_session shared by uploads and sendables).

## 0.36.2 -- 2026-06-25
- HARDEN (kill EVERY remaining flaky-uplink spinner on Google -- fail fast, keep content, warm on boot):
  - LIST fetches now use a SHORT timeout (cc.config google_list_timeout, default 9s) instead of the 30s
    _g_api default, so a cold Gmail/Calendar/Drive list during an uplink flap BAILS in ~9s -> SWR serves
    last-good (or the UI shows 'offline, retrying' + auto-retries) instead of a ~40s hang. Mutations
    (send/modify/upload) keep the 30s default. Also applied to the unread-badge poll + Drive thumbnails so
    a flap can't tie up server threads.
  - TOKEN refresh is now bounded (google_token_timeout, default 10s, was 20s). The refresh runs under the
    google lock, so an unbounded refresh during a flap serialized EVERY google call behind it -> cascade of
    spinners. Now bounded; access token still cached to ~90s-before-expiry and only refreshed when expired.
  - FRONTEND keeps content on a slow/stale/offline refetch: Gmail no longer blanks to 'Loading...' when a
    refetch of the SAME view is slow/errors (only a genuinely new view or first paint shows the spinner);
    Calendar + Drive likewise keep the grid/listing on screen and flip a freshness badge to 'offline'
    instead of replacing everything with an error card. Extended the Gmail 'synced Xs ago' badge to
    Calendar + Drive (shared gSyncText helper).
  - BOOT-WARM the UI's exact default views (gmail inbox max=50, drive root) into the cache + warmer active
    set on startup (non-blocking), and prime the OAuth token, so the first load after a fresh deploy is
    covered ASAP rather than serving a cold fetch. (Calendar's window is computed client-side from
    tz/locale, so its exact key can't be pre-matched; we warm a 7d window to prime the token/API path.)

## 0.36.1 -- 2026-06-25
- FIX (the cold-cache-after-restart spinner -- disk-persist the Google caches): SWR fixed staleness, but a
  RESTART left the cache cold, and a cold fetch during an uplink flap times out ~40s = 'stuck loading'. Now
  the Gmail/Calendar/Drive caches persist to disk (_google_cache.json) on every refresh and LOAD ON BOOT, so
  the cache is warm immediately after a restart and SWR serves it instantly -- no cold window. PROVEN:
  populate -> restart -> first fetch 0.00s from disk. (Only the very first fetch ever, before any disk cache
  exists, can still wait during an active outage.)

## 0.36.0 -- 2026-06-25
- FIX (the REAL 'Google stuck loading' fix -- stale-while-revalidate): the cache served instantly only while
  FRESH (<60s); once stale it BLOCKED on a live fetch, which during an uplink flap takes 7-30s = the spinner.
  Now any cached copy is served INSTANTLY (flagged stale if old) and refreshed in the background -- the user
  NEVER waits on a live fetch when there's data to show. Applied to Gmail + Calendar + Drive. Only a truly
  cold first-load during an active outage can still spin (nothing cached yet); the warmer fills it ASAP.
- UX (popped-out /term terminal, mobile top bar): the cluttered corner bar (~9 controls wrapping 2-3 rows) is
  now a single ~44px row -- session name + copy + file + a '...' overflow holding scroll/select, font, compact,
  end, and kill (kill divided off + red, never a stray tap). Every control kept; desktop bar unchanged.

## 0.35.0 -- 2026-06-25
- FEATURE (Calendar + Drive get the resilient cache too): factored the Gmail cache spine into a generic
  _g_cached (short-TTL cache + background warmer + serve-last-good-on-error) and applied it to the Calendar
  and Drive lenses. Now when the uplink flaps, ALL three Google lenses show last-synced content (flagged
  stale) instead of spinning forever -- the durable fix for the recurring 'Google loading'. /api/google/
  calendar + drive accept fresh=1 to force-refresh; a _gc_sync_loop keeps recently-viewed views warm.

## 0.34.4 -- 2026-06-25
- FIX (mobile session dock was empty/black): sbPoll() did `if(!sbDesktop()){bar.innerHTML='';return;}` -- it
  WIPED the dock and bailed on any non-desktop width, so the constant mobile dock showed as an empty black
  bar. Now it populates at all widths (tap a tile = switch); the hover-blowup preview stays desktop-only.
- UX (mobile nav: flatten categories): collapsible tab CATEGORIES don't fit the horizontal mobile tab strip,
  so on mobile the nav now lists every tab flat (no folders). Categories remain a desktop-only feature.

## 0.34.3 -- 2026-06-25
- FIX+FEATURE (mobile session dock made constant): ROOT CAUSE of 'mobile sessions looked unchanged' -- every
  session mobile feature was gated behind body.cf-sessions, which is set in lensTopbar() via render(), but the
  LANDING lens (Sessions) doesn't route through render() at boot, so the class was never set and nothing
  applied. Fix: loadSessions() sets the class directly. Then, per request, the bottom session taskbar is now
  CONSTANT across EVERY mobile lens (like the desktop dock) -- tap a tile to switch session from anywhere.
  Reserved its space fleet-wide (--cf-dock-h, #main padding-bottom); the Gmail full-screen reader + compose
  FAB now sit above it; the focus terminal is much taller (usage strip + hint dropped on mobile sessions).

## 0.34.2 -- 2026-06-25
- FIX (mobile sessions: no way to switch sessions): the desktop bottom session taskbar (#sessbar) was
  display:none on mobile, so you were stuck on the one open session. It now shows on mobile ON THE SESSIONS
  LENS as a touch dock -- tap a tile to switch (tap already maps to openInSessions). Taller tap targets,
  safe-area bottom padding, and the focus terminal/grid reserve space so the dock never covers content. The
  hover-blowup preview (#sessprev) stays desktop-only (no touch hover).

## 0.34.1 -- 2026-06-25
- FIX/UX (mobile chrome + Gmail): (1) the topbar no longer leaves a gap under the nav -- it's now flush in
  normal flow (not sticky-with-measured-offset) and slides up under the nav as you scroll, no content
  overlap. (2) The generic topbar (title + Add/New-session) is hidden on Gmail/Calendar/Drive (they have
  their own headers) -- whole bar hidden on mobile, the irrelevant buttons hidden everywhere. (3) Mobile
  Gmail now has a Compose FAB (circular bottom-right). (4) Gmail load-more: scrolling near the bottom pages
  the next batch (Gmail pageToken) and appends -- backend page_token (bypasses cache), client-side thread
  collapse/append, scroll-near-bottom trigger on both the desktop list-pane and mobile window scroll.

## 0.34.0 -- 2026-06-25
- UX/MOBILE (maximize real estate): on phones the chrome now gets out of the way. SCROLL-AWAY top chrome --
  the global nav (#side) + topbar slide up as you scroll into content and reveal on any scroll-up (iOS
  Safari/Gmail pattern), reclaiming ~180px so Gmail/Calendar/Drive use the full 100dvh while reading; tabs
  are one swipe-up away. SEARCH-ON-DEMAND -- the always-on search rows (topbar filter, Gmail search, Drive
  search, Calendar quick-add) are replaced by a tap-to-reveal minimal field (🔍/⚡ toggle) that collapses
  after, instead of permanently eating a row. Transform/CSS-only, strictly mobile-gated (≤820/760px) -- zero
  desktop/tablet change. Note: Calendar's internal time-grid scroll doesn't trigger scroll-away (acceptable).

## 0.33.0 -- 2026-06-25
- FEATURE (mobile Google): Gmail/Calendar/Drive lenses rebuilt for phones (iPhone-Google-app style) behind
  @media(max-width:760px) so desktop is untouched. Gmail = single-pane: full-width list -> tap -> full-screen
  reader with back, labels drawer (hamburger), full-screen compose, sticky reply/reply-all/forward bar.
  Calendar -> day/agenda + bottom-sheet event detail. Drive -> mobile file list + full-screen preview. Every
  feature preserved (VoiceMatch, attachments, sync badge, event create/edit, browse/preview/download).
- FEATURE (give Claude a file): drag-drop a file/image onto the session terminal (drop overlay) or use the
  '\u1f4ce Attach' bar / tap-to-pick (mobile) -> POST /api/session-upload saves it to a config-driven uploads
  dir (extension-preserving, size-capped via max_upload_mb) and types the path into the tmux session so Claude
  picks it up (no auto-Enter). Also on the standalone /term page.
- FEATURE (deliverable slide-out): when an agent writes a file to deliverables/, a self-contained global
  overlay slides out offering Download / Preview / Email-to-me -- built on the EXISTING deliverables spine
  (/api/files detection, file-get download/preview with new ?inline=1, gmail_send for email via
  /api/deliverable-email, owner email resolved server-side). Polls ~15s, only pops files newer than page-open.

## 0.32.0 -- 2026-06-25
- FEATURE (fleet usage rollup + enterprise visibility): a ClaudeGrandfather-level view that aggregates usage
  across BOTH macOS users (your hptuner side + Sarah's sarahaios/AFP side) into OVERALL + by Claude account
  (tallied against whichever login was active, wherever it ran, with a where-breakdown) + by node (per project
  folder, grouped by side). Each macOS user = one transcript store (instances share it), so the aggregator
  dedupes by store_id; peers expose /api/usage-store over the family mesh; cached 60s. Enterprise knobs
  (Settings -> Fleet usage visibility, also superadmin-settable): fleet_view full|own (show whole fleet vs
  only own) + fleet_share on|off (expose this node's usage to peers). Default full/share = single-owner full
  visibility. 'Admin sees all, nodes see own' = children {share:on,view:own} + grandfather {view:full}.
  (Also: AFP was missing the family mesh_token -- set to the verified family value so it joins the mesh.)

## 0.31.1 -- 2026-06-25
- FIX (per-account usage: stop misattributing pre-tracking history): usage from before the account-activity
  log existed (it began when 0.30.0 shipped) was lumped under whatever account was logged in now. It's now a
  separate '(before tracking)' bucket -- transcripts don't record the account, so older usage genuinely can't
  be split. Going forward each account accrues correctly. The Usage 'By Claude account' card shows the
  tracking-start date and labels the pre-tracking bucket distinctly.

## 0.31.0 -- 2026-06-25
- FEATURE (Gmail list: server-side cache + background sync + outage resilience): the inbox was a full live
  Gmail pull on EVERY browser refresh (two users = 2x the work; a flaky uplink = spin forever). Now each node
  serves a short-TTL (60s) per-view cache to every browser (one sync serves everyone -> fewer API calls,
  instant refreshes), kept warm by a background loop that only polls views requested in the last 5 min (idle =
  no calls). KEY: if a live fetch fails, it serves the LAST good inbox flagged stale instead of erroring, so a
  flaky uplink shows the last-synced inbox, not a dead spinner (would have softened today's incident). The
  Gmail header shows a "✓ synced Xs ago" badge (turns "⚠ offline · synced Xs ago" when serving stale), and the
  ↻ button now forces a live pull (fresh=1). Verified on a live mailbox: cache hit 0.002s vs live 0.4s.

## 0.30.1 -- 2026-06-25
- FIX (prefer IPv4 for outbound): a dead/flaky IPv6 leg made stdlib urllib block ~60s on the AAAA address
  before falling back to IPv4 (Gmail/Drive stuck loading, mesh stalls). The server now returns IPv4 addrinfo
  when present so a dead IPv6 route can't hang it (disable with CC_IPV6=1). Surfaced during the network incident.

## 0.30.0 -- 2026-06-25
- FEATURE (usage by account + over/under-average tinting): usage is now attributed to the Claude account that
  was logged in at the time of each call (a switch-activity log records account changes; events are bucketed
  by the account live at their timestamp) -> a new "By Claude account" inventory in the Usage lens, on top of
  the existing by-model/by-project. Each window (1hr/5hr/24hr/week/month) now also carries a rolling AVERAGE
  (a typical window of that length over the trailing 30 days) + a ratio; the window cards (Usage lens) AND the
  sessions usage strip TINT warm when you're over your average and cool when under (intensity scales), show a
  ▲/▼N× glyph, and display the average number. The sessions strip stays combined totals. Backend: usage_payload
  adds totals[*].avg/avg_cost/ratio + by_account; account log wired into the keychain switch + a boot baseline.

## 0.29.0 -- 2026-06-25
- FEATURE (Type: Product vs Agency in the Add-a-ClaudeFather wizard): the wizard previously relied on
  auto-detect for install type. Now there's an explicit Type selector -- Product (a single product/operation)
  or Agency (clients + tools tree, like AFP). It writes cc.config integration=product|agency via
  cc-newinstance.sh --integration, so the deployment shape is deliberate, not inferred. Default Product.

## 0.28.0 -- 2026-06-25
- UX (no more copy-the-auto-token-or-be-locked-out): a provisioned node now starts with NO login token (open
  on the private tailnet, which is already access-gated by Tailscale). On first open the dashboard shows a
  "Set a login token" prompt where the operator picks their OWN token (PIN or passphrase, or 🎲 generate),
  with a note that it's changeable anytime in Settings → Login token. Dismissible ("Skip for now"); only
  nags while the node is still open. The wizard no longer prints a token to write down. (window.CC.authOn
  drives the prompt; setting it re-issues the session cookie so you're never locked out.)

## 0.27.0 -- 2026-06-25
- FIX (no more raw-port SSL footgun + full e2e-verified provisioning): provisioned nodes now set
  cc.config bind_host "127.0.0.1" (server.py honors bind_host/HPCC_HOST, default 0.0.0.0 so existing nodes
  are unchanged). Result: the ONLY tailnet-visible surface is the clean `tailscale serve` HTTPS URL -- there
  is no raw plain-HTTP port on the tailnet for a browser to hit and get ERR_SSL_PROTOCOL_ERROR. Verified the
  whole create-flow end-to-end on a throwaway node: local up, tailnet HTTPS reachable (real TLS), raw port
  correctly unreachable, login works, Chief of Staff warmed + live, launchd persistence, mesh registration.

## 0.26.0 -- 2026-06-25
- FIX (provisioned node couldn't start: tailnet serve port collided with the local port): auto-expose used
  `tailscale serve --https=<port>` with the SAME number as the local server, but the server binds
  0.0.0.0:<port> (which includes the tailnet IP) -> EADDRINUSE, the node failed to (re)bind after a restart.
  The tailnet port is now offset (+1000, e.g. 8802 -> tailnet 9802), matching how the other nodes already use
  a distinct tailnet port. (shopos was repaired live: serve moved 8802->9802, registry/peers updated.)
- FIX (login bounced you to Portfolio): an expired session 302'd to /login, losing the #lens hash, so after
  sign-in you always landed on the default lens. The login form is now served INLINE at the requested URL
  (hash preserved) and sign-in does location.reload() -> you land back where you were.

## 0.25.2 -- 2026-06-25
- FIX (mobile session header: ↗ open-in-new-tab button pushed off-screen): the location chip was
  flex:0 0 auto / max 280px, so on a phone it filled the bar and shoved the ↗ / end / kill buttons past the
  edge. Now the chip shrinks (flex:0 1, max 200px) and is hidden entirely on mobile (location is still in the
  Sessions list + title tooltip); the action buttons pin right and stay reachable with bigger tap targets.

## 0.25.1 -- 2026-06-25
- FIX (new instance's Chief of Staff: "can't find session"): opening a fresh node's Chief raced a cold start
  -- the terminal attached before the session existed (or to one that exited on first-run). Two fixes: (1)
  chief_open() now verifies the session actually survived launch (~1.3s) before telling the UI to attach, and
  returns a real error (with the pane tail) instead of a false "started" -> no more ghost attach; (2)
  provisioning WARMS the Chief of Staff (calls the new node's /api/chief-open after it's alive) so an
  enterprise node boots with a live Chief, not one that starts on first click. Wizard shows "Chief of Staff:
  ✅ warmed up & ready".

## 0.25.0 -- 2026-06-25
- FEATURE (change the login token from the dashboard): Settings now has a "🔑 Login token" card -- type a new
  token or 🎲 auto-generate, confirm, and it applies LIVE (no manual cc.config edit, no restart). It persists
  to cc.config (auth_token, chmod 600), updates the in-memory AUTH_TOKEN, re-issues THIS session's cookie so
  you are never locked out, shows the new token to copy, and logs the change to ~/.cc-credential-changes.log.
  Endpoint POST /api/auth-token-set (auth-gated). Min length 4 so 4-digit PINs (the existing convention) work.
  cc-recover.sh remains the break-glass that prints every node's current token.

## 0.24.0 -- 2026-06-25
- FEATURE (provisioned nodes are reachable from your other devices): a new node was registered at
  127.0.0.1:<port> -> only reachable ON the Studio, so the Portfolio link gave "site can't be reached" from a
  phone. instance_provision() now auto-publishes a new node on the tailnet via `tailscale serve --https=<port>`
  (same pattern as the existing nodes), then registers that https://<tailnet-host>:<port> URL in the Portfolio
  registry + peers + the wizard result ("Remote access: ✅ ..."). Tied to the "join the mesh" checkbox; falls
  back to local-only with a warning if tailscale isn't available.

## 0.23.1 -- 2026-06-25
- UX/MOBILE (Add-a-ClaudeFather layout redo): the wizard modal overflowed and clipped behind the nav on
  mobile, and the card-header "Add" button hid behind the sticky topbar. Rebuilt: responsive field grid
  (auto-fit -> single column on phones, inputs box-sizing:border-box so nothing overflows), mobile modal
  sizing (96vw / 92dvh), an output panel that wraps + scrolls. Moved the primary action into the always-
  visible topbar as "➕ Add a ClaudeFather" (shown only on the Portfolio lens) and hid the generic "＋ Add"
  + "▶ New session" there (they don't apply to an overseer portfolio) -- so it's never buried in a scrolling
  card again.

## 0.23.0 -- 2026-06-25
- FEATURE (self-completing provisioning + Setup agent): "Create & start" now finishes a new node end-to-end
  so the operator never has to hand-run launchd or edit peers. A "Make it permanent & join the mesh" checkbox
  (default on) makes instance_provision() install the per-user LaunchAgent server-side (same-user; cross-user
  reports the one command to run as that user) AND add the node to peers.json. New agents/setup charter: a
  guided onboarding agent that runs INSIDE the new instance and walks the operator through configuring it
  (purpose -> project CLAUDE.md scaffold from a pasted spec -> agents -> extensions -> first goals -> hand off
  to the Chief). Wizard result now shows running/permanent/mesh status and points to the Setup agent instead
  of dumping manual commands. Dedicated "setup" entry in the Projects tree; docs/PROVISIONING.md updated.

## 0.22.2 -- 2026-06-25
- FIX (provisioned node now appears in Portfolio): a new instance was registered into the engine's
  default-config registry (state_dir of cc.config.json), which is NOT necessarily the registry the calling
  overseer reads -> the node was alive but invisible in Portfolio. cc-newinstance.sh now takes
  --register-into <path>; instance_provision() passes the running overseer's own INSTANCES, so the node lands
  where its Portfolio looks. (CLI use without the flag keeps the prior default-config behavior.)

## 0.22.1 -- 2026-06-25
- UX (clearer provisioning wizard buttons): the "Add a ClaudeFather" actions were ambiguous ("Stage bundle"
  vs "Stage & launch"). Renamed to 👁 Preview plan / 📦 Create (no start) / 🚀 Create & start now, each with a
  tooltip, plus a one-line legend under the buttons explaining exactly what each does.

## 0.22.0 -- 2026-06-25
- FEATURE ("+ Add a ClaudeFather" -- one-click provisioning of a new instance): the overseer Portfolio lens
  now has an "➕ Add a ClaudeFather" button + wizard. It provisions a NEW, self-contained, PORTABLE bundle --
  one movable folder holding the full framework + its own config/secrets/state/project/deliverables -- via a
  new deterministic engine `cc-newinstance.sh`. The engine copies framework_paths, mints a fresh dashboard
  auth token, carries the FAMILY mesh token (joins the mesh), ships superadmin.pub (never the private key),
  seeds peers.json, stages a launchd plist, makes a starter project tree, and registers the node in the
  parent's _instances.json (so it appears in Portfolio). NOTHING starts until approved: the wizard previews
  the plan (--dry-run), stages the bundle, and -- optionally -- launches it on the brain tmux server and
  verifies the port; launchd persistence + cross-node mesh registration are printed for the operator. Backed
  by a new `agents/provision` charter (the "fluent" brain that turns a design plan into the right invocation).
  Endpoint: POST /api/instance-provision (overseer-only). Portability fix: cc-instance-supervise.sh now derives
  its own command-center dir from the script location, so a relocated bundle runs its OWN server.py.

## 0.21.53 -- 2026-06-25
- DOCS + FEATURE (full platform documentation + overseer Projects tab): a multi-agent sweep read all of
  ClaudeFather and wrote accurate CLAUDE.md's (command-center, extensions + google-workspace + granola, agents,
  install, presets), a master docs/ARCHITECTURE.md, a root-CLAUDE.md "where everything lives" index, and a
  platform_map.json. New overseer-only "Projects" tab (ClaudeGrandfather) renders the whole platform as a tree
  -- Core / Lifecycle / Extensions (with each extension nested) / Agents / Docs -- each opening its CLAUDE.md.

## 0.21.52 -- 2026-06-25
- FEATURE (install as a desktop app / PWA): the dashboard now serves a web-app manifest (/manifest.webmanifest,
  branded per node) + standalone display + app meta, so it can be "Add to Dock" (Safari) / Installed (Chrome) as
  a resizable native-feeling app window with NO browser chrome and its own Dock icon (the ClaudeFather mark).
  Added an in-app ⟳ Refresh button in the topbar (since standalone windows have no address bar).

## 0.21.51 -- 2026-06-25
- IMPROVE (Tasks AI scan reads FULL email bodies): the AI scan already covered email both directions (incoming +
  sent) + Granola notes, but only fed subject+preview snippets. Now it reads the FULL message bodies (quoted
  chains stripped, fetched in parallel) so it catches action items buried deeper -- still ONE batched call.

## 0.21.50 -- 2026-06-25
- FIX (Tasks tab was hidden): applyPreset() hides any nav tab not in the node's preset lens list, so the new
  Tasks tab never showed on preset nodes (AFP/carsearch). Tasks now gets an always-on override (like the Google
  lenses) -- it's a built-in feature, visible on every node.

## 0.21.49 -- 2026-06-25
- FEATURE (Tasks Phase 2): (1) DAILY-MORNING auto-scan -- programmatic sweep + AI scan run automatically ~6am
  so the operator sits down to a fresh list (cc.config tasks_morning_scan/_ai/_hour; default on). (2) Calendar
  suggestions now CREATE the real Google Calendar event on accept ("📅 Add to calendar"), timed or all-day.
  (3) Agent task_propose -- agents add suggestions via the new `command-center/cc-task` helper (in every agent
  brief now). (4) Granola call notes (CC:CALLS) folded into the AI scan. Endpoints: /api/task-calendar,
  /api/task-propose. Nothing auto-commits -- all suggestions still require approval.

## 0.21.48 -- 2026-06-25
- FEATURE (Tasks -- the "Morning Command Center"): a new Tasks tab. (1) FREE programmatic suggestions from
  recent email in+out (requests TO you + commitments YOU made + natural-language deadlines, balanced signal, no
  AI). (2) Opt-in "AI scan" -- ONE batched headless-claude pass over recent correspondence -> todos + calendar
  suggestions. Nothing auto-commits: everything lands as Suggestions you Accept/Dismiss. (3) ▶ Start LAUNCHES an
  agent on a task -- in its client folder if known, else a self-filing misc inbox -- briefed with the task +
  source. Grouped Today/Overdue/This-week/Suggestions, client chips, links back to the source email. Per node.
  Endpoints: /api/tasks(+add/update/status/launch), /api/tasks-sweep, /api/tasks-ai-scan.
  (Phase 2 next: daily-morning auto-scan, agent task_propose, real calendar-event creation from suggestions.)

## 0.21.47 -- 2026-06-25
- FIX (per-message reply buttons visible on EVERY message): removed the hover-reveal opacity gate -- Reply /
  Reply all / Forward now show on every message in the chain, always, so you can reply back in the chain
  without hunting. (The earlier fix had shipped to carsearch+repos but AFP was held at 0.21.44, so it looked
  unfixed there; now pushed everywhere.)

## 0.21.46 -- 2026-06-25
- FIX (smart reply respects WHICH message you reply to): replying to an OLDER message in the chain now scopes
  the agent to THAT message + the thread UP TO it only -- it never sees messages sent after it (which may have
  gone to someone else). The reply is addressed to that message's sender, and the prompt is told not to
  reference anything after it. Default (reply to newest) now also gets the full earlier-thread context.

## 0.21.45 -- 2026-06-25
- UX (never looks frozen): reusable spinner + busy overlay (busyOn/busyOff, .spin). Shown during the slow ops
  -- Learn my voice (build), Optimize my voice, and Smart-reply "Draft in my voice" -- plus spinners on the
  Voice Studio + Sender-history modal loads. Clear "it's working" feedback instead of a dead-looking UI.
- FIX (per-message reply/forward): the controls only appeared on the newest message (gated on 'open'), so you
  couldn't reply back in the chain. Now EVERY message has them -- revealed on hover when collapsed, always when
  expanded -- with clear text labels ("Reply" / "Reply all" / "Forward") + tooltips.

## 0.21.44 -- 2026-06-25
- FIX (Voice Studio overflow, for real): .vstudio was set to 88vw/680px -- WIDER than the modal box
  (min(560px,94vw)) -- so it and its textareas spilled out. Now .vstudio fills the modal (width:100%) and the
  modal widens to ~760px for the studio specifically.

## 0.21.43 -- 2026-06-25
- FIX (attachments keep their file type): when a sender names an attachment WITHOUT an extension, saving to a
  folder / downloading now appends the correct extension derived from the MIME type (incl. Office types
  mimetypes misses: xlsx/docx/pptx). Existing saves already kept extensions; this covers the typeless case.
- FIX (Voice Studio modal): the Style-profile / Hard-rules textareas overflowed the modal -> added border-box
  sizing so they fit.

## 0.21.42 -- 2026-06-25
- UX (email, Gmail-style replying): Reply/Reply-all/Forward moved to a bar UNDER the newest message, and every
  OPEN message in the chain has its own ↩/↪/➤ controls so you can reply/forward an OLDER message out of order
  (quotes that specific message). Top toolbar keeps thread actions (Sender history/Archive/Trash/Snooze/Unread).

## 0.21.41 -- 2026-06-25
- FEATURE (Voice Studio + self-improving voice): the "Learn my voice" button now opens a studio where you
  VIEW/EDIT the learned style profile directly and set always-obeyed HARD RULES (injected on top of every
  draft). Smart-reply drafts you EDIT before sending are quietly logged (no tokens). "✨ Optimize from my edits"
  sends the agent your profile + those edits ONCE, learns your corrections, updates the profile, and clears the
  buffer -- so learning cost is on-demand, not per-email. Built-in "How it works" explainer spells out every
  piece. New: /api/voice/profile-save, /api/voice/optimize, /api/voice/edit-log.

## 0.21.40 -- 2026-06-25
- UX (email): (1) threads now render CHRONOLOGICALLY (oldest at top, newest at bottom) with the NEWEST message
  expanded -- fixes the confusing "reply collapsed above the open original". (2) Smart reply moved OUT of the
  reader and INTO the reply composer as "✨ Draft in my voice" -- so it drafts for exactly who you hit Reply /
  Reply-all on (recipients drive the voice + most-formal-wins). (3) "🎙 Learn my voice" moved to the email rail
  (inbox/sent nav) instead of the per-thread actions.

## 0.21.39 -- 2026-06-25
- FEATURE (VoiceMatch smart-reply engine): smart reply now (1) learns the owner's writing voice from their Sent
  mail ("Learn my voice" button -> per-node style profile: tone, punctuation incl. em-dash habit, greetings,
  sign-offs), (2) weights HEAVILY toward how the owner actually writes to THIS recipient (per-recipient samples)
  and escalates to the most-formal register on multi-recipient threads, (3) pulls richer context -- past mail
  with the sender (capped), the client/project CLAUDE.md, Granola call notes, and calendar availability when the
  email is about scheduling, (4) returns 2-3 variants (concise/warm/detailed) you switch between in the composer,
  (5) kills AI tells (no em-dashes unless you use them, no stock filler) and auto-retries the occasional refusal.
  New: /api/voice/build, /api/voice/profile; flex/context + stage-reply take rel_override + source toggles.

## 0.21.38 -- 2026-06-24
- FEATURE (adjustable terminal font size): the session terminal toolbar now has A-/A+ controls (with the
  current size shown) that live-resize the xterm font and re-fit; the choice persists in localStorage and
  applies to every /term view. Range 8-28, version-safe across xterm option APIs.

## 0.21.37 -- 2026-06-24
- FEATURE (brand title in a display font that ACTUALLY renders for every user): self-hosted Cinzel Decorative
  (SIL OFL 1.1 -- commercial-OK + redistributable) via @font-face from /static/brand, applied to the brand
  wordmark (Mission Control / AFP / text2tune / per-node brand). Self-hosting means it renders on every
  browser, not just machines that happen to have the font. (The requested 1001fonts "Godfather" face is
  personal-use-only / non-commercial / non-redistributable, so it can't ship here; Cinzel Decorative gives the
  same epic film-title feel, license-clean.)

## 0.21.36 -- 2026-06-24
- FIX (taskbar hover-peek): removed the duplicate Exit/Kill/New-tab buttons (the embedded terminal already has
  end/kill/copy/compact/dashboard) -- peek now keeps only Usage + Focus. Added the 📍 launch-location before the
  title and switched the peek title from the raw tmux name to the friendly session label.

## 0.21.35 -- 2026-06-24
- TWEAK (session location placement): the 📍 location chip now sits BEFORE the session title (location then
  title), on the far left of the header, across list/grid/Focus views.

## 0.21.34 -- 2026-06-24
- FIX (location now shows in the Focus/big session view too): the big window header (`bigHead`) never rendered
  the launch location -- only the list/grid did -- so in the default Focus view you couldn't see where a session
  was running. Unified all three views on one `locTag` helper; the 📍 chip now sits right after the window title
  in the big view, and falls back to the full cwd when a session runs at the project root.

## 0.21.33 -- 2026-06-24
- FIX/FEATURE (session titles clearer + show WHERE they run): resumed sessions whose tmux name embedded a slug
  of the opening message (e.g. `hp-r-i-need-you-to-review-a-media-l`) now display a de-slugified readable title
  (and the conversation label is stored at resume time), instead of the raw code. Agent self-named titles
  ([[CC_TITLE]]) still win. Every session row/tile now shows a 📍 location chip = the path under the project it
  was launched from, so you can tell a '7th avenue' session from an 'Avenlur' one at a glance.

## 0.21.32 -- 2026-06-24
- FIX (History times were all identical): the displayed time used the transcript FILE mtime, which the history
  re-align had clobbered (rewriting cwd touched every file), so all conversations showed the same time and
  couldn't be ordered. Now the time + sort use the LAST MESSAGE's timestamp from inside the transcript -- the
  true 'last activity', immune to file rewrites.

## 0.21.31 -- 2026-06-24
- FIX (History lens layout was cramped): the lens rendered its header + card list as cells inside the 330px
  card grid, so the header sat in a narrow left cell and cards were squeezed into one column. Header + list now
  span the full width; the list is its own wide-card grid (min 520px/card) that fills big monitors. The
  conversation preview shows more (last ~30 lines, taller pane, softer fade).

## 0.21.30 -- 2026-06-24
- FEATURE (History lens: mini-terminal preview per conversation): each past conversation now shows a small
  terminal-styled peek of its last ~15 message lines (user turns + assistant text + `⏵ tool` markers), so you
  can recognize a conversation at a glance without resuming. `scan_projects.py` extracts the tail cheaply (reads
  only the final chunk of each transcript); search now also matches preview text.

## 0.21.29 -- 2026-06-24
- FIX (portability: History lens showed another deployment's machines): the History lens hardcoded the HP
  Tuners fleet tabs (studio/T490/T480), so EVERY deployment (e.g. AFP) showed James's Windows dev/RE boxes --
  meaningless + unreachable for a tenant node. Tabs now come from THIS node's machine registry
  (_machines.json), so a node shows only its own machine(s). hptuners still shows its three.

## 0.21.28 -- 2026-06-24
- FIX (History lens broken on fresh/external nodes): `command-center/scan_projects.py` -- which powers the
  History lens + per-client "past conversations" (it scans ~/.claude/projects) -- was NOT in framework_paths,
  so cc-update never shipped it. Any node installed without it (e.g. AFP) silently got an empty History (the
  server ran a missing script). Added to framework_paths so every node has it and it survives updates.

## 0.21.27 -- 2026-06-24
- PORTABILITY (self-contained installs — deliverables travel with the bundle): a ClaudeFather install is now a
  relocatable unit — its deliverables default to `<install>/deliverables` (under CC_HOME), so the whole folder
  can be moved to a dedicated drive / new server and the files it makes go with it. The system saves
  deliverables into ONE clean consolidated branch (each module's `deliverables/` is a symlink into the store),
  not scattered — so the Files lens shows real deliverable files cleanly. Precedence: explicit
  `deliverables_root` (point it at a dedicated drive) > legacy iCloud tiered mode (storage_mode includes icloud
  + no root) > self-contained `<install>/deliverables`. `cc-init` now creates `deliverables/` and prints where
  output lands. The Studio nodes (control-plane on internal, project on SSD) set `deliverables_root` to an SSD
  path OUTSIDE their project tree — same clean branch, honoring the disk-full rule + avoiding a store/module
  self-reference. We push dedicated drives as the recommended (not required) model: totally portable, files
  where they belong, easy to move.
- account_wallet added to superadmin set_config allowlist so Mission Control can enable the Claude Accounts
  lens on a node (e.g. AFP) remotely.

## 0.21.25 -- 2026-06-24
- REBUILD (Claude Accounts — now switches the GLOBAL login, live across all sessions): the previous version
  used per-session env tokens (wrong model — switching only affected NEW sessions and fought the native
  /login). Replaced with keychain snapshot/swap: "Save this account" captures the current login (macOS keychain
  OAuth blob + ~/.claude.json identity) into a 0600 wallet; "switch" writes a saved one back -> EVERY session
  picks it up on its next request, no restart — exactly like /login but one click from saved accounts. Verified
  the keychain round-trip is safe (login intact after write-back). Removed the env-token injection entirely.

## 0.21.24 -- 2026-06-24
- FIX (Claude Accounts login: pasted code vanished before you could submit): the login modal re-rendered on
  every 2s status poll, wiping the code input. The URL+code form now renders ONCE and the poll leaves your
  typed code alone (still polls to detect completion after you Submit). Submit shows a "finishing…" hint.

## 0.21.23 -- 2026-06-24
- FIX (Claude Accounts login: "Invalid OAuth Request: Missing state parameter"): the setup-token OAuth URL is
  ~346 chars and wrapped across lines in the capture pane, so we grabbed only the first ~80 chars — dropping
  the `state`/`code_challenge` params. Now captured with `capture-pane -J` (join wrapped lines) in a wide (900)
  pane, so the full URL (with state) is surfaced. Login authorizes correctly now.

## 0.21.22 -- 2026-06-24
- RELIABILITY (access recovery / break-glass): new `cc-recover.sh` — run in any terminal to print every node's
  login PIN (auth_token), port, tailnet URL, and recent credential-change log, even when the web UI is down.
  You can always get back in. Plus a boot **credential watch**: any change to auth_token/mesh_token since last
  boot is logged loudly to the console + ~/.cc-credential-changes.log (hashes only) so a silent rotation can
  never quietly lock you out. Recovery checklist (Tailscale-first, since off-Tailscale looks like a lockout)
  in docs/ACCESS_RECOVERY.md.

## 0.21.21 -- 2026-06-24
- NEW (Claude Accounts lens — remote login wallet): authorize each Claude subscription account ONCE via
  `claude setup-token` driven from the dashboard (click the link → authorize in your browser → paste the code
  back), yielding a ~1yr OAuth token stored 0600. Sessions then launch headless with that token — no per-session
  browser dance. **One-click switch** between stored accounts (new sessions use it immediately). Per-account
  **/usage** view: 5-hour + weekly (all models / Sonnet) bars with reset times, scraped from the official
  `/usage` command (no reverse-engineered endpoint). Gated per-node by cc.config `account_wallet` (ON for the
  local nodes to shake out bugs; OFF/untouched on AFP until tonight). Token export is spliced into launches only
  when the wallet is enabled AND an active token exists, so legacy/keychain nodes are unaffected. Design:
  docs/REMOTE_LOGIN_DESIGN.md.
- POLISH (Projects): a module with no one-line summary no longer shows an alarming RED "no description"
  warning — it's now a muted, italic hint. Lacking a summary isn't an error.

## 0.21.20 -- 2026-06-24  *** deliverables off iCloud, onto the SSD ***
- The real fix for the whole download saga: a new `deliverables_root` config makes deliverables live on a
  plain LOCAL/SSD path, NOT the evictable iCloud container. When set it overrides iCloud entirely -- downloads
  then always work because the bytes are simply local (never evicted, no headless-fetch needed). The operator
  gets a file onto iCloud by downloading it here -> it lands on their Mac -> they keep it in iCloud if they
  want. On boot the node copies any still-local files off the old iCloud container to the SSD and re-points
  every module's deliverables/ symlink to the SSD, so new agent writes land there too. Allowlisted for
  superadmin set_config so Mission Control can flip a node remotely.

## 0.21.19 -- 2026-06-24
- FIX (evicted file "preparing… pulling… but never downloads"): `brctl download` does NOT materialize an
  iCloud-evicted file in the Studio's headless login-session context. The reliable mechanism is the READ
  itself -- opening a dataless file makes macOS fault it in. We now read in a bounded daemon thread (instant
  for local files; for evicted, the read pulls it down from iCloud), with `brctl` only as a non-blocking
  nudge. If it doesn't finish in ~22s we return 503 and the Download button retries (the orphan read keeps
  downloading, so a retry finds it local). This is the actual fetch-from-iCloud fix.

## 0.21.18 -- 2026-06-24
- FIX (502 on download): a MISSING file spent 10s running brctl before answering (it conflated 'absent' with
  'evicted'), and that delay -- plus the brief server-restart window -- made Tailscale serve return 502.
  Files are now classified local / evicted / absent: absent = instant 404, evicted = bounded ~9s materialize
  then 503 (the Download button auto-retries), local = instant 200. The Download button also retries through
  transient 502/504 gateway blips. Verified through the real Tailscale serve path: absent=404 in 17ms,
  fresh=200 in 20ms.

## 0.21.17 -- 2026-06-24  *** the actual download fix ***
- ROOT CAUSE (download "site wasn't available"): NOT the proxy and NOT the URL -- both were verified working
  (HTTP 200 in ~40ms through the real Tailscale serve path). The file was iCloud-EVICTED on the headless
  Studio. `os.path.getsize()` reports the logical size even for an evicted dataless file, so the old code
  thought the bytes were local, then `open().read()` BLOCKED forever faulting the file in from iCloud -> the
  request never returned -> the browser timed out as "site wasn't available".
- FIX: detect eviction by `st_blocks==0` (the truth), materialize the bytes via `brctl download` BEFORE
  reading (bounded ~10s, never hang), and if it can't be pulled in time return a fast 503 instead of hanging.
  The Download button is now a blob fetch that AUTO-RETRIES on 503 ("Pulling it down from iCloud…") so the
  user just sees "preparing" then the file -- never an error page.
- Removed the dead "Reveal in Finder / Find this file" buttons from file rows: the Studio is headless and
  accessed only remotely, so opening Finder on it is meaningless. Download is the path.

## 0.21.16 -- 2026-06-24
- FIX (shipped fixes didn't take effect without a manual hard-refresh): the dashboard HTML (with inline JS)
  had no Cache-Control, so browsers served a stale cached page -- e.g. still building the old `?path=` download
  URL with parens. All HTML pages now send `Cache-Control: no-store`, so a normal reload always gets the
  current code. (This is why an already-created file still showed the `(` URL: cached page, not the fix.)
  NOTE: already-created files DO work with the b64 fix -- the clean URL is built when the page renders, not
  when the file was made.

## 0.21.15 -- 2026-06-24
- FIX (download "site wasn't available" through the proxy): download URLs carried the raw rel path, so a
  filename with spaces + parens (e.g. "... (Action Sheet).xlsx") became a query full of %20/%28/%29 -- which
  some tunnels/proxies reject before the request reaches the server. Downloads now use a clean base64url
  token (`?b64=`), pure ASCII. Verified end-to-end: a messy-named file downloads HTTP 200 with correct bytes
  over a clean URL. The server accepts both ?b64= and legacy ?path=.
- LOCK (Chief of Staff session): its label is now ALWAYS "Chief of Staff" -- a canonical name that an
  agent-declared title can never override -- and it remains a protected singleton that cannot be ended/killed
  from the dashboard.

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
