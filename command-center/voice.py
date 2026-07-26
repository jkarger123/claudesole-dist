#!/usr/bin/env python3
"""Voice I/O for sessions -- talk to a running Claude session and hear its replies.

Two directions, both reusing production-proven engines (no new integrations):
  * HEAR (text->speech): render the agent's last message to audio. Provider chain
    ElevenLabs (eleven_turbo_v2_5) -> OpenAI (tts-1-hd) -> macOS `say`; keys VAULT-FIRST
    (ELEVENLABS_API_KEY / OPENAI_API_KEY). Audio lands in <STATE_DIR>/voice_audio/ and is
    streamed to the browser (the host never makes sound). Same provider set the Morning
    Brief uses -- kept independent here because core must not import an extension module.
  * TALK (speech->text): the browser records mic audio; transcription runs through the
    SAME Deepgram path the Notebook uses (injected as ctx['stt'] -> notebook.nb_transcribe,
    key DEEPGRAM_API_KEY). One Deepgram code path, one key.

"Read the last message" is SMART: short messages are read verbatim; long ones are first
distilled to a 1-3 sentence, TTS-friendly TL;DR by a headless `claude -p` (Max subscription,
NO metered key). Config in <STATE_DIR>/_voice.json. server.py owns transcript parsing, session
injection (_mesh_deliver) and busy/idle detection; this module is the audio brain. Stdlib only.
server.py calls voice.init(ctx).

NOTE: distinct from VoiceMatch (the /api/voice/profile writing-tone engine) -- that decides how
replies are WORDED; this is literal audio in and out.
"""
import json, os, re, subprocess, time, urllib.request, urllib.error

_CTX = {}   # injected by server.py: CC, STATE_DIR, secret, stt(audio_b64, mime)

DEFAULTS = {"provider": "elevenlabs", "voice_id": "", "read_mode": "smart", "summarize_threshold": 600,
            "announce_node": True}   # prefix each readback with the node name so multiple open instances are distinguishable
_ALLOWED_PROVIDERS = ("elevenlabs", "openai", "say")


def init(ctx): _CTX.update(ctx)


def _secret(k):
    f = _CTX.get("secret")
    try: return f(k) if callable(f) else ""
    except Exception: return ""


def _audio_dir():
    d = os.path.join(_CTX.get("STATE_DIR", "."), "voice_audio")
    try: os.makedirs(d, exist_ok=True)
    except Exception: pass
    return d


# ---- config (the settings popover reads/writes this) -------------------------------------------------
def _cfg_path(): return os.path.join(_CTX.get("STATE_DIR", "."), "_voice.json")


def cfg_get():
    c = dict(DEFAULTS)
    try:
        with open(_cfg_path()) as f: c.update(json.load(f) or {})
    except Exception: pass
    if c.get("provider") not in _ALLOWED_PROVIDERS: c["provider"] = DEFAULTS["provider"]
    try: c["summarize_threshold"] = max(120, int(c.get("summarize_threshold") or 600))
    except Exception: c["summarize_threshold"] = 600
    c["announce_node"] = bool(c.get("announce_node"))
    c["node_label"] = (_CTX.get("node_label") or "").strip()   # the node's spoken name (read-only; from server config)
    # surface which keys are present so the UI can explain what's on/off (never the values)
    c["has_deepgram"] = bool(_secret("DEEPGRAM_API_KEY"))
    c["has_elevenlabs"] = bool(_secret("ELEVENLABS_API_KEY"))
    c["has_openai"] = bool(_secret("OPENAI_API_KEY"))
    return c


def cfg_set(patch):
    c = dict(DEFAULTS)
    try:
        with open(_cfg_path()) as f: c.update(json.load(f) or {})
    except Exception: pass
    for k in ("provider", "voice_id", "read_mode", "summarize_threshold", "announce_node"):
        if isinstance(patch, dict) and k in patch: c[k] = patch[k]
    c["announce_node"] = bool(c.get("announce_node"))
    if c.get("provider") not in _ALLOWED_PROVIDERS: c["provider"] = DEFAULTS["provider"]
    if c.get("read_mode") not in ("smart", "verbatim", "summarize"): c["read_mode"] = "smart"
    try: c["summarize_threshold"] = max(120, int(c.get("summarize_threshold") or 600))
    except Exception: c["summarize_threshold"] = 600
    try:
        with open(_cfg_path(), "w") as f: json.dump(c, f, indent=2)
    except Exception: pass
    return cfg_get()


# ---- speech -> text (reuse the Notebook's single Deepgram path) --------------------------------------
def _transcripts_file(): return os.path.join(_CTX.get("STATE_DIR", "."), "_voice_transcripts.jsonl")
def _log_transcript(text, dur=None, session=""):
    """DURABLE SAFETY NET: every successful transcription is written to disk the instant Deepgram returns it --
    BEFORE the text leaves this function -- so a spoken message can NEVER silently evaporate if the browser then
    fails to deliver it (voice-mode flipped, target session rotated, network blip). A long dictation is expensive
    to redo; losing it is unacceptable. Bounded to the newest ~300 lines. Read it back via vc_transcripts()."""
    text = (text or "").strip()
    if not text: return
    try:
        f = _transcripts_file()
        rec = {"ts": int(time.time()), "chars": len(text), "dur": dur, "session": session or "", "text": text}
        with open(f, "a", encoding="utf-8") as fh: fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        try:                                             # cap growth without a full rewrite each call
            lines = open(f, encoding="utf-8").read().splitlines()
            if len(lines) > 360:
                with open(f, "w", encoding="utf-8") as fh: fh.write("\n".join(lines[-300:]) + "\n")
        except Exception: pass
    except Exception: pass
def vc_transcripts(n=30):
    """Recent successful transcriptions, newest first -- the recovery view for a dictation the client dropped."""
    try:
        lines = open(_transcripts_file(), encoding="utf-8").read().splitlines()
        out = []
        for l in lines[-max(1, int(n)):][::-1]:
            try: out.append(json.loads(l))
            except Exception: pass
        return {"ok": True, "items": out}
    except Exception: return {"ok": True, "items": []}

def vc_stt(audio_b64, mime="audio/webm", session=""):
    stt = _CTX.get("stt")
    if not callable(stt):
        return {"ok": False, "error": "voice not enabled yet -- add DEEPGRAM_API_KEY to the vault (Vault lens)."}
    try:
        r = stt(audio_b64 or "", mime or "audio/webm")
        if isinstance(r, dict) and r.get("ok"):
            _meter({"stt_sec": float(r.get("dur") or 0), "stt_calls": 1})   # dur = Deepgram-reported audio seconds
            _log_transcript(r.get("text") or "", r.get("dur"), session)     # persist BEFORE returning -- never lose a spoken message
        return r
    except Exception as e: return {"ok": False, "error": str(e)[:140]}


# ---- text -> speech (provider chain; keys VAULT-FIRST) -----------------------------------------------
def _prune(keep=40):
    """Cap growth: keep only the newest `keep` rendered clips (STATE_DIR is SSD-backed)."""
    try:
        d = _audio_dir()
        fs = sorted((os.path.join(d, x) for x in os.listdir(d) if x.startswith("sess-")),
                    key=os.path.getmtime, reverse=True)
        for old in fs[keep:]:
            try: os.remove(old)
            except Exception: pass
    except Exception: pass


def _speakable(text):
    """Strip markdown/code noise so TTS reads clean prose, not backticks and asterisks."""
    t = text or ""
    t = re.sub(r"```.*?```", " (code block omitted) ", t, flags=re.S)   # fenced code -> a spoken marker
    t = re.sub(r"`([^`]*)`", r"\1", t)                                   # inline code ticks
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)                  # heading hashes
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t); t = re.sub(r"(?<!\*)\*(?!\*)([^*]+)\*", r"\1", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)                       # [label](url) -> label
    t = re.sub(r"^\s*[-*]\s+", "", t, flags=re.M)                        # bullet dashes
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


def vc_tts(text, cfg=None):
    """Render text -> an audio file under voice_audio/. Returns {ok, file, provider} or {ok:False, error}.
    Tries the configured provider first, then falls back (elevenlabs -> openai -> local `say`)."""
    text = _speakable(text)
    if not text: return {"ok": False, "error": "nothing to read"}
    cfg = cfg or cfg_get()
    prov = cfg.get("provider") or "elevenlabs"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    order = [prov] + [p for p in _ALLOWED_PROVIDERS if p != prov]
    reasons = []
    for p in order:
        try:
            if p == "elevenlabs":
                key = _secret("ELEVENLABS_API_KEY")
                if not key: reasons.append("elevenlabs: no ELEVENLABS_API_KEY in vault"); continue
                vid = cfg.get("voice_id") or "EXAVITQu4vr4xnSDxMaL"   # default ElevenLabs voice
                body = json.dumps({"text": text[:5000], "model_id": "eleven_turbo_v2_5"}).encode()
                req = urllib.request.Request(
                    "https://api.elevenlabs.io/v1/text-to-speech/" + vid, data=body,
                    headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
                with urllib.request.urlopen(req, timeout=60) as r: audio = r.read()
                fn = "sess-%s-11l.mp3" % stamp
                open(os.path.join(_audio_dir(), fn), "wb").write(audio); _prune(); return {"ok": True, "file": fn, "provider": "elevenlabs"}
            if p == "openai":
                key = _secret("OPENAI_API_KEY")
                if not key: reasons.append("openai: no OPENAI_API_KEY in vault"); continue
                # tts-1 (standard), NOT tts-1-hd: same voices, ~2x faster to first byte + half the price. The HD
                # model's extra fidelity is inaudible for a short spoken summary but roughly doubles render latency.
                body = json.dumps({"model": (cfg.get("openai_model") or "tts-1"), "voice": (cfg.get("voice_id") or "nova"),
                                   "input": text[:4000]}).encode()
                req = urllib.request.Request(
                    "https://api.openai.com/v1/audio/speech", data=body,
                    headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=90) as r: audio = r.read()
                fn = "sess-%s-oai.mp3" % stamp
                open(os.path.join(_audio_dir(), fn), "wb").write(audio); _prune(); return {"ok": True, "file": fn, "provider": "openai"}
            if p == "say":
                fn = "sess-%s-say.aiff" % stamp
                rc = subprocess.run(["say", "-o", os.path.join(_audio_dir(), fn), text[:6000]],
                                    capture_output=True, timeout=60).returncode
                if rc == 0: _prune(); return {"ok": True, "file": fn, "provider": "say", "fallback": "; ".join(reasons[:3])}
                reasons.append("say: rc=%s" % rc)
        except Exception as e:
            reasons.append("%s: %s" % (p, str(e)[:110]))
            continue
    return {"ok": False, "error": "voice failed -- " + "; ".join(reasons[:4])}


# ---- distill a long message into a spoken TL;DR (headless claude -p, no metered key) ------------------
_SUMM_PROMPT = (
    "You are turning an AI coding-agent's chat message into something read ALOUD by text-to-speech. "
    "Summarize it in 1 to 3 short, natural spoken sentences: what was done, what it says, and any question "
    "or next step for the listener. Plain conversational English -- NO markdown, NO bullet points, NO code, "
    "NO file paths unless essential, NO emoji. Output ONLY the spoken summary, nothing else.\n\nMESSAGE:\n%s\n")


def _summarizer_cwd():
    """The headless `claude -p` summarizer WRITES a transcript into ~/.claude/projects/<slug-of-its-cwd>/.
    If it runs inside a real session's directory (e.g. the CC root, where the Chief of Staff lives), that fresh
    transcript becomes the NEWEST .jsonl there -- and voice's 'newest jsonl in the cwd' resolver then reads the
    SUMMARIZER'S transcript as if it were the session's last reply (the 'Chief read a summary about double-escapes'
    bug). Pin the summarizer to an ISOLATED dir so its transcripts never collide with any real session's."""
    d = os.path.join(_CTX.get("STATE_DIR", "/tmp"), "_voice_summarizer_cwd")
    try: os.makedirs(d, exist_ok=True); return d
    except Exception: return "/tmp"

def vc_summarize(text):
    inj = _CTX.get("summarizer")   # tests may inject
    if callable(inj):
        try: return (inj(text) or "").strip()
        except Exception: pass
    env = {**os.environ, "PATH": os.environ.get("PATH", "") + ":" + os.path.expanduser("~/.local/bin") + ":/opt/homebrew/bin"}
    try:
        # --strict-mcp-config (with no --mcp-config) loads ZERO MCP servers -> cuts the biggest, most variable part
        # of `claude -p` cold-start. This is a one-shot text summarize; it needs no tools/MCP/project context.
        # --model haiku: a 1-3 sentence TL;DR does NOT need a frontier model; Haiku renders in ~2-4s vs 5-13s+ on
        # the account default, which was blowing the readback timeout ("reading is slow — never reads"). Big latency win.
        r = subprocess.run(["claude", "--dangerously-skip-permissions", "--strict-mcp-config",
                            "--model", "haiku",
                            "-p", _SUMM_PROMPT % (text or "")[:6000]],   # a spoken 1-3 sentence TL;DR needs the gist, not 16k chars -> smaller input = faster Haiku render (keeps readback under the timeout)
                           capture_output=True, text=True, timeout=90, env=env, cwd=_summarizer_cwd())
        out = (r.stdout or "").strip()
        return out or ""
    except Exception:
        return ""


_META_RX = re.compile(
    r"(appears? to be (completely |entirely )?(empty|blank)"
    r"|nothing to summariz|cannot summariz|can't summariz|unable to summariz"
    r"|no (message|content|text) (was |is )?(provided|given|included|attached)"
    r"|there('s| is) no (message|content|text)"
    r"|i don'?t see (a|any) (message|content|text)"
    r"|please (provide|share) (the|a) message)", re.I)

def _summary_usable(s, orig):
    """A summary is usable only if it's real prose ABOUT the message -- never the summarizer talking about
    its own inability to summarize. Meta/refusal shapes are short; only screen short outputs so a genuine
    (long) summary that merely mentions the word 'empty' is never wrongly rejected."""
    s = (s or "").strip()
    if not s: return False
    if len(s) < 600 and _META_RX.search(s): return False       # meta/refusal, not a summary
    if len(s) > max(len(orig or ""), 800): return False        # "summary" longer than the source = broken
    return True


def vc_speak_last(text, cfg=None, announce=""):
    """Smart read of an agent's last message: verbatim when short, distilled when long. `announce` is an
    optional spoken preamble (who + where, built by the server) so you know which instance is talking.
    Returns {ok, file, provider, spoken_text, summarized} -- or {ok:False, empty:True} when there is no
    speakable content (the caller treats empty as a first-class silent-skip, NOT a retryable error)."""
    text = (text or "").strip()
    if not text: return {"ok": False, "empty": True, "error": "no message to read"}
    if not _speakable(text): return {"ok": False, "empty": True, "error": "message has no speakable text"}
    cfg = cfg or cfg_get()
    mode = cfg.get("read_mode") or "smart"
    thr = int(cfg.get("summarize_threshold") or 600)
    do_sum = (mode == "summarize") or (mode == "smart" and len(_speakable(text)) >= thr)
    spoken, summarized = text, False
    if do_sum:
        s = vc_summarize(text)
        if _summary_usable(s, text): spoken, summarized = s, True
        # unusable/meta summary (e.g. "the message appears to be completely empty") -> fall back to reading
        # the real text verbatim; NEVER speak the summarizer's meta-commentary aloud
    announce = (announce or "").strip()
    if announce: spoken = announce.rstrip(". ") + ". " + spoken   # e.g. "Mission Control here, working in the command center, voice folder. <reply>"
    res = vc_tts(spoken, cfg)
    if res.get("ok"):
        res["spoken_text"] = _speakable(spoken)[:1200]
        res["summarized"] = summarized
        prov = res.get("provider") or "openai"
        _meter({"tts_chars": len(_speakable(spoken)), "tts_calls": 1,
                ("tts_chars_" + ("elevenlabs" if prov == "elevenlabs" else ("say" if prov == "say" else "openai"))): len(_speakable(spoken))})
    return res

def vc_render(text, cfg=None, announce=""):
    """Speak EXACTLY the given text (verbatim, never summarized) -- for reading a pending question + its options
    aloud. Same provider chain + metering as vc_speak_last."""
    text = (text or "").strip()
    if not text: return {"ok": False, "empty": True}
    cfg = cfg or cfg_get()
    announce = (announce or "").strip()
    spoken = (announce.rstrip(". ") + ". " + text) if announce else text
    res = vc_tts(spoken, cfg)
    if res.get("ok"):
        res["spoken_text"] = _speakable(spoken)[:1200]
        prov = res.get("provider") or "openai"
        _meter({"tts_chars": len(_speakable(spoken)), "tts_calls": 1,
                ("tts_chars_" + ("elevenlabs" if prov == "elevenlabs" else ("say" if prov == "say" else "openai"))): len(_speakable(spoken))})
    return res


# ---- usage metering (so voice cost is VISIBLE, not guessed) ------------------------------------------
# Deepgram prerecorded ~$0.0043/min; OpenAI tts-1-hd $30/1M chars, tts-1 $15/1M; ElevenLabs ~ $0.30/1k (est);
# macOS `say` = free. We meter TTS chars (by provider) + STT seconds, roll up per month, and estimate $.
_RATE = {"stt_per_sec": 0.0043 / 60.0, "openai": 15e-6, "openai_hd": 30e-6, "elevenlabs": 300e-6, "say": 0.0}   # openai now tts-1 ($15/1M chars); tts-1-hd was $30/1M
def _usage_file(): return os.path.join(_CTX.get("STATE_DIR", "."), "_voice_usage.json")
def _meter(patch):
    try:
        try:
            with open(_usage_file()) as f: d = json.load(f)
        except Exception: d = {}
        mk = time.strftime("%Y-%m"); m = d.setdefault(mk, {})
        for k, v in patch.items(): m[k] = round(m.get(k, 0) + v, 4)
        with open(_usage_file(), "w") as f: json.dump(d, f, indent=2)
    except Exception: pass
def usage_summary():
    try:
        with open(_usage_file()) as f: d = json.load(f)
    except Exception: d = {}
    mk = time.strftime("%Y-%m"); m = d.get(mk, {})
    tts_chars = m.get("tts_chars", 0); stt_sec = m.get("stt_sec", 0)
    # cost the TTS chars by the provider they were rendered with (tracked separately); default OpenAI-HD
    est = stt_sec * _RATE["stt_per_sec"]
    est += m.get("tts_chars_openai", 0) * _RATE["openai"]
    est += m.get("tts_chars_elevenlabs", 0) * _RATE["elevenlabs"]
    return {"ok": True, "month": mk, "tts_chars": tts_chars, "stt_sec": round(stt_sec, 1),
            "stt_min": round(stt_sec / 60.0, 1), "tts_calls": m.get("tts_calls", 0),
            "stt_calls": m.get("stt_calls", 0), "est_usd": round(est, 3)}


# ---- path-traversal-guarded resolve for the /api/voice/audio streamer --------------------------------
def audio_path(fn):
    fn = os.path.basename(fn or "")
    if not fn or not fn.endswith((".mp3", ".aiff")): return None
    p = os.path.join(_audio_dir(), fn)
    return p if os.path.isfile(p) else None
