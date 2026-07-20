# Morning Brief — scheduled, voice-read daily brief

<!-- LATEST-HANDOFF -->
**>> Resume here:** read `_handoffs/20260720-0309__morning-brief.md` first -- it is the latest handoff.
<!-- /LATEST-HANDOFF -->

Turn the operator's own data into a short spoken brief of their day, ready before they start and played in
their browser. Official extension (`id: morning-brief`, `lens:brief`, category agency).

## How it works
1. **SCHEDULE** — a routine (auto-created/updated from the Brief lens config via `brief_config_save`) runs
   `command-center/cc-brief` at `open_time - lead_minutes`. `cc-brief` POSTs `/api/brief-generate` so
   generation runs IN the node's server (which has the Google/Granola/context accessors + Full Disk Access).
2. **GATHER** — `morning_brief.py` has an EXTENSIBLE source registry (`@source(name,label)`): calendar +
   gmail (live Google accessors), tasks (`_tasks.json`), granola + slack (the context layer's cited events).
   Add a source = add one function. Each item keeps its provenance.
3. **SYNTHESIZE** — a headless `claude -p` (subscription, no metered key) writes 2-3 spoken paragraphs
   (today's shape / coming up / prep), in the operator's **VoiceMatch** style (`voice_profile_get`).
4. **VOICE** — `_tts()` renders an audio file, provider order = chosen → elevenlabs → openai → `say`
   (file-only fallback). Keys resolve VAULT-FIRST. **Audio is a FILE the lens plays in the operator's
   browser — generation never makes sound on the server.**
5. **SURFACE** — stored in `_morning_brief.json`; the **Brief lens** shows today's brief + an `<audio>`
   player (best-effort autoplay; browsers need one click) + history + config.

## Key files / endpoints
- `command-center/morning_brief.py` — the engine (stdlib). `server.py` injects ctx in `morning_brief.init(...)`
  (CC, accessors, `voice_profile` lazily, `secret`=`_deploy_env`). NOTE: `voice_profile_get` is defined later
  in server.py than the init call, so it's passed as `lambda: voice_profile_get()` (forward-ref).
- `command-center/cc-brief` — the routine's trigger (resolves port+token from cc.config, POSTs generate).
- Routes: `/api/brief` (state), `/api/brief-generate` (POST, background), `/api/brief-config` (POST, writes
  cc.config `morning_brief` live + upserts the routine), `/api/brief-audio?f=` (streams the mp3).
- State (per-deployment): `<STATE_DIR>/_morning_brief.json` + `brief_audio/`.
- Config (`cc.config morning_brief`): open_time, lead_minutes, days, horizon_days, length, tone, sources[],
  voice{enabled,provider,voice_id,autoplay}.

## Hard rules / gotchas
- **Read-only.** Summarize only — never send mail / edit calendar / complete a task.
- **Browser playback only.** The server writes an audio file; it must never play audio on the host (the operator is
  on a different machine than the node). Keep `say` as a file-writer fallback (`-o`), never live playback.
- **Per-project.** Each console briefs its own day from its own data/config.
- **VAULT-FIRST keys.** OpenAI/ElevenLabs keys come from the vault; never echo them.
- The routine is owned by the brief config (upsert), so it runs even on a node with
  `extension_routine_host:false` (the brief must run where its operator is).
