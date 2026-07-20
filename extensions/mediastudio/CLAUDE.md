# mediastudio — the Video Studio feature (working scope + full map)

<!-- LATEST-HANDOFF -->
**>> Resume here:** read `_handoffs/20260718-1531__mediastudio.md` first -- it is the latest handoff.
<!-- /LATEST-HANDOFF -->

<!-- CC:NOTES append-only; agents file learnings that belong to THIS module here -->
## Learnings (filed by agents; append-only)
- Video Studio feature fully mapped in mediastudio/CLAUDE.md: engine=extensions/ai-video-studio/engine (9 modules studio/beats/autocut/edl/project/music/capcut/providers/generate); backend+10.8k-line STUDIO_PAGE SPA live in command-center/server.py (~L16115 backend, ~L17242 routes, ~L18319 page); analytical beat-cutter (no generative model, works on real footage/kids); shared PROJECT JSON is the currency; state on SSD (_studio, _studio_media); bins auto-install to bin/.
- Video Studio LANDSCAPE shipped v0.99.204 (2026-07-17): engine was portrait-hardcoded — the real trap was _impact_fx/apply_flashes cropping to 1080:1920, so a landscape canvas got re-cropped back. Fix: autocut.canvas_for(aspect,clips) + w,h threaded through build/build_project/_impact_fx/apply_flashes/project.emit+manual/studio.py --aspect; edl.render passes canvas into FX. UI Shape toggle auto-detects from clip dims (in-browser), aspect flows via /api/studio/{render,build-project,new-manual}. RULE: any canvas-varying ffmpeg effect must take w,h, never hardcode dims. NOTE this session: server.p
- Video Studio audio-as-clip shipped v0.99.205 (2026-07-17): music/voice track is now a draggable+trimmable .ablock on the trkM music lane (was a static full-length waveform). Model: audio clip {source,in,out,start,volume} now honored as a real clip. Magnetic snap (snapEdge/snapMove, 9px threshold) locks edges to every video clip start/end + 0 + video-end, green .snapline shows lock. reflow() auto-covers audio UNTIL clip._user=true (set on first drag/trim) then leaves it alone. edl.py audio render = atrim in:out + adelay start + APAD so a short/offset track never truncates the video (-shortest c
<!-- /CC:NOTES -->

This folder is the **working scope** for the ClaudeFather **Video Studio** feature. It holds no code — the
feature lives in two places (below). Work on Studio from here; file learnings with `cc-note`.

**Parent:** `../CLAUDE.md` -> read up-tree (extensions catalog, then the root master).

## What Video Studio IS
A built-in, in-dashboard **video editor**. Drop in phone clips (video OR photos), bring music (upload a track
or paste a YouTube link), and it either **auto-builds** a beat-synced hype cut in one tap OR opens a full
**multi-track timeline editor** (trim, split, crop, color, speed/slow-mo, PiP overlay, titles, impact
flashes/zoom, audio) that renders to MP4 or exports a **CapCut** bundle. Opens as a dedicated `/studio` page
(mobile + desktop) and as a native **Studio** lens embedded in the dashboard.

Core value: pro-looking montages **without CapCut hand-trimming** and **without uploading anyone's face to a
generative model** — the auto-cutter is **analytical** (motion/beat detection, no pixels regenerated), so it
works on **real family footage incl. children** with no policy block. Runs entirely on a bundled static
**ffmpeg** — no API key required. (See memory [[ai-video-studio-extension]].)

## Where the code lives (TWO homes)
1. **`extensions/ai-video-studio/`** — the extension: catalog card + the render **engine** (`engine/*.py`).
   This is FRAMEWORK (ships via `cc-update`; author at Mission Control, never edit on a tenant).
   - `extension.json` — catalog card + `lens:{id:"studio"}` (surfaces the nav tab); `category:integration`,
     `default_category:Team`, `provides:["lens:studio"]`, keyless (`requires:[]`).
   - `AGENT.md` — **how an agent builds a finished video from the CLI** (read this to drive Studio headless).
   - `SETUP.md` — the guided-setup script (keyless; a Studio tab just appears under Team).
2. **`command-center/server.py`** — the backend + the entire frontend:
   - Backend (~L16115–16585): upload streaming, job workers (threads), project CRUD, bin bootstrap, providers.
   - Route dispatch (~L16926 `/studio` page; ~L17242–17310 `/api/studio/*`).
   - `STUDIO_PAGE` (~L18319–29140, **~10.8k lines**) — the whole single-page timeline-editor SPA (inline
     HTML/CSS/JS). `loadStudio()` (~L20831) fetches `/studio?embed=1`, scopes its CSS under `#studioHost`, and
     runs its JS in an IIFE so it renders as a native full-width lens without colliding with the dashboard.
   - **Server edits need `claudesole-restart`** + hard-refresh (see root CLAUDE.md hard rule).

## The engine (`extensions/ai-video-studio/engine/`) — 9 stdlib+ffmpeg modules, no numpy/librosa/AI-API
- **`studio.py`** — top-level CLI orchestrator (the one entry point): resolve music -> autocut -> MP4. Prints
  `{ok,output,duration,...}`. Flags: `--music --section mm:ss-mm:ss --pace {frantic|punchy|cinematic} --out`,
  `--clips-only` (CapCut segments), `--timecode` (burn a running timer), `--flash-at/--big-flash-at` (impacts
  at exact OUTPUT secs), `--mode ai --plan plan.json` (a vision/Claude shot plan chosen by MEANING).
- **`beats.py`** — beat detection ("the edit follows the sound"). Decode->onset envelope->autocorrelation tempo
  (with **octave correction** to avoid the 150->75 half-time trap)->beat grid + `hit_beats` (the drops).
- **`autocut.py`** — the core cutter. `motion_peaks()` (frame-diff YAVG = "money moments"), lays moments onto
  the beat grid (every cut lands on a beat), places the biggest motion as a **slow-mo finisher** ~2/3 through,
  fires **impact FX** (white flash + screen shake + afterglow) on the exact detected land frame. `build()`
  renders directly; `build_project()` emits the shared PROJECT JSON. `apply_flashes()` = pixel-precise impacts.
- **`edl.py`** — the **renderer**: compiles one PROJECT JSON (single source of truth) -> MP4. Tracks:
  `video` (trim/speed/color/fit cover|contain), `overlay` (PiP), `text` (drawtext titles), `effects`
  (impact flashes + zoom punches), `audio` (a REAL clip: `atrim in:out` + `adelay start` + **`apad`** so a
  trimmed/offset track never truncates the video — `-shortest` clamps to video length, silence fills gaps;
  v0.99.205). `--proxy` = fast 480p preview.
- **`project.py`** — the timeline data layer + media cache: `emit` (auto-build a SAVED editable project +
  filmstrip sprites + waveform JSON), `manual` (clips full-length, no beat-cut), `resolve`/`addclip`/`thumbs`.
- **`music.py`** — resolve a song: local file OR YouTube/URL (yt-dlp `-x` mp3, range-fetch fast path + robust
  full-download fallback for YouTube 403s) OR direct http; `--section` slices the drop.
- **`capcut.py`** — export a CapCut bundle zip: RELIABLE layer (`clips/clip_NN.mp4` + `music.mp3` +
  `EDIT_PLAN.txt`) + EXPERIMENTAL `draft_content.json` (pyJianYingDraft schema; may need CapCut-version tweaks).
- **`providers.py`** — API-agnostic provider registry. Reads only vault key **names** (never values); resolves
  per-capability (understand/plan/image/video/tts/autoedit) which provider is available. `builtin` engine is
  always on (keyless). Two AI families: **generative** (Veo/Runway/Imagen — rebuild pixels -> **REFUSE real
  people/children**) vs **content-aware editors** (OpusClip/VEED — watch real footage, cut, don't regenerate).
- **`generate.py`** — optional generative video via BYO key (Gemini->Veo): text->video or image->video, polls
  the long-running op, downloads the MP4. Key passed via `STUDIO_GEN_KEY` env (never argv/ps). Provider policy
  **filters real people/children** (`raiMediaFilteredReasons`) — products/pets/scenery/synthetic/b-roll ONLY.
- **`timecode.py`** — burn a big running timestamp so the user reads the exact land ms, then feeds it back
  `--flash-at` (exact=True) for a dead-on flash (no motion-guessing).

## The shared PROJECT JSON (the currency)
One document is written by auto-build (`build_project`), READ/edited by the timeline, RENDERED by `edl.render`,
and mapped by the CapCut exporter. All times = **seconds on the OUTPUT timeline**. `speed` is a FACTOR:
`<1` = slow-mo (output longer). Shape: `{canvas:{w,h,fps}, duration, sources:{id:{kind,path}}, tracks:[video,
overlay, effects, text, audio]}`. See `edl.py` header + `AGENT.md` for the full schema.

## Orientation — landscape OR portrait (v0.99.204)
The `canvas` drives the output shape: **portrait 9:16 = 1080x1920**, **landscape 16:9 = 1920x1080**. The whole
engine is canvas-agnostic: `autocut.canvas_for(aspect, clips)` resolves `16:9`|`9:16`|`auto`; `build`/
`build_project`/`_impact_fx`/`apply_flashes`/`project.emit`/`project.manual`/`studio.py --aspect` all take the
canvas, and `edl.render` passes it into the FX pass. **The gotcha that made it portrait-only:** the impact
flash/shake FX (`_impact_fx`, `apply_flashes`) hard-cropped to `1080:1920`, so a landscape canvas got re-cropped
back to portrait — any new canvas-varying effect MUST take `w,h`, never hard-code dims. UI: the builder **Shape**
toggle auto-detects from the imported clips' dimensions (in-browser), always overridable; `aspect` flows through
`/api/studio/{render,build-project,new-manual}`. Default is `auto` (CLI/agent) / portrait fallback on a tie.

## Server plumbing / state (per-deployment, gitignored, on the SSD)
- `_studio/projects/<pid>.json` (editable EDLs), `_studio/cache/<pid>/` (filmstrips, music, proxies),
  `_studio_media/` (uploaded + generated clips) — all under `DELIV_LOCAL_ROOT` (SSD). Renders land in
  `command-center/deliverables/` -> show in the **Files** lens.
- `bin/` (node-local) holds static **ffmpeg/ffprobe/yt-dlp**; `_studio_ensure_bins()` **auto-downloads** them
  once on any node that lacks them (macOS), so Studio renders fleet-wide, not just the build Mac.
- Uploads stream to disk (8GB cap, `cc.config studio_upload_mb`). All renders/exports run in **background
  threads** with a job-poll API so the page never blocks. Delete-project + cleanup-uploads free disk (never
  touch finished renders in Files).

## `/api/studio/*` routes (all POST unless noted)
`upload` (streaming), `build-project` (auto-build -> editable project), `new-manual`, `render` (one-shot
auto-build->MP4), `render-project` (edited EDL->MP4, `proxy:1`=preview), `export-capcut`, `generate` (AI clip),
`add-clip`, `add-audio`, `project-save`, `delete-project`, `cleanup-uploads`; GET: `job?id=`, `project?id=`,
`projects`, `tools` (bins present + generative availability), `media?path=` (Range/206 serve for `<video>`).

## Driving it as an AGENT (headless)
The fastest path is the CLI (`AGENT.md`): `cd extensions/ai-video-studio/engine && python3 studio.py --music
"<file|YouTube URL>" --out /abs/out.mp4 --pace punchy clip1.mov clip2.mov photo.jpg`. Deliver the MP4 with
`cc-deliver`. Full control = build/edit the PROJECT JSON and `python3 edl.py proj.json out.mp4`.

## Rules / gotchas
- **Analytical only for real people.** NEVER route real footage of people (esp. children) through a generative
  model — it's policy-blocked and a line we don't cross. Real family footage -> the beat-cut/timeline editor.
- Needs `bin/` ffmpeg+ffprobe+yt-dlp (auto-installed on first render). Default big outputs to the **SSD**.
- FRAMEWORK change: build/sign at Mission Control, ship via `cc-update`; on a tenant node route via a CCR.
- Shipped v0.99.155 (2026-07-05, P1 auto-build) through P2 timeline / P3 titles+zoom / P4 CapCut / P5 bin
  bootstrap / direct-drag+PiP / native lens / v0.99.170 images+split / v0.99.171 8GB uploads / v0.99.172 AI
  generate. Installed in `command-center/_extensions.json`.
