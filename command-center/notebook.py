#!/usr/bin/env python3
"""Notebook -- speak or write a note naturally; on finish it's structured into actionable items.

Capture (type, or dictate -> the browser records + uploads audio -> server transcribes via Deepgram, key
VAULT-FIRST, so it works from ANY device Sarah opens the dashboard on, never the server's mic). On save a
headless `claude -p` (Max subscription, NO metered key) structures the raw note into {title, summary,
tasks[], decisions[], reminders[], tags[]}. REVIEW-FIRST: nothing auto-commits -- the note's tasks land as
SUGGESTIONS in the Tasks list when approved; the note becomes a context-layer event (so it feeds retrieval
AND the Morning Brief); and it's draggable into any session. Stdlib only. server.py calls notebook.init(ctx).
"""
import json, os, re, subprocess, time, base64, urllib.request, urllib.error

_CTX = {}   # injected by server.py: CC, STATE_DIR, secret, context_ingest, task_add, extractor(test)


def init(ctx): _CTX.update(ctx)


def _state_path(): return os.path.join(_CTX.get("STATE_DIR", "."), "_notebook.json")
def _load():
    try:
        with open(_state_path()) as f: return json.load(f)
    except Exception: return {"notes": []}
def _save(s):
    try:
        with open(_state_path(), "w") as f: json.dump(s, f, indent=2)
    except Exception: pass


def _secret(k):
    f = _CTX.get("secret")
    try: return f(k) if callable(f) else ""
    except Exception: return ""


# ---- voice: Deepgram pre-recorded transcription (server-side; key from the vault) ---------------------
def nb_transcribe(audio_b64, mime="audio/webm"):
    """Transcribe a recorded audio blob (base64) via Deepgram. The browser records + uploads, so this works
    from the operator's own device; the key stays server-side (never exposed to the browser)."""
    key = _secret("DEEPGRAM_API_KEY")
    if not key:
        return {"ok": False, "error": "voice not enabled yet -- add DEEPGRAM_API_KEY to the vault (Vault lens)."}
    try: audio = base64.b64decode(audio_b64 or "")
    except Exception: return {"ok": False, "error": "bad audio"}
    if not audio: return {"ok": False, "error": "no audio"}
    try:
        req = urllib.request.Request(
            "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true&punctuate=true",
            data=audio, headers={"Authorization": "Token " + key, "Content-Type": mime or "audio/webm"})
        with urllib.request.urlopen(req, timeout=120) as r: res = json.loads(r.read().decode())
        ch = ((res.get("results") or {}).get("channels") or [{}])
        alt = (ch[0].get("alternatives") or [{}]) if ch else [{}]
        return {"ok": True, "text": (alt[0].get("transcript") or "").strip()}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": "Deepgram HTTP %d: %s" % (e.code, (e.read().decode() or "")[:140])}
    except Exception as e:
        return {"ok": False, "error": str(e)[:140]}


# ---- structure a raw note into actionable items (headless claude -p, no metered key) ------------------
STRUCT_PROMPT = (
    "You turn a raw, free-form personal note (typed or dictated, possibly rambling) into structured, "
    "actionable output. Return STRICT JSON only (no prose, no code fence) with this exact shape:\n"
    '{"title":"<=8 words","summary":"1-2 sentences of what this note is about",'
    '"tasks":[{"title":"clear action item","owner":"who or \\"\\"","due":"YYYY-MM-DD or \\"\\""}],'
    '"reminders":[{"text":"follow-up","when":"YYYY-MM-DD or relative like \\"next Mon\\""}],'
    '"decisions":["a decision stated"],"tags":["short-topic", ...]}\n'
    "Extract ONLY what the note actually supports -- do not invent. Tasks = concrete next actions the writer "
    "intends. Keep every list tight; omit (empty list) if there is nothing concrete. NOTE:\n%s\n")


def _structure(text):
    inj = _CTX.get("extractor")
    if inj: return inj(text)
    try:
        r = subprocess.run(["claude", "--dangerously-skip-permissions", "-p", STRUCT_PROMPT % text[:16000]],
                           capture_output=True, text=True, timeout=150,
                           env={**os.environ, "PATH": os.environ.get("PATH", "") + ":" +
                                os.path.expanduser("~/.local/bin") + ":/opt/homebrew/bin"})
        out = (r.stdout or "").strip()
        m = re.search(r"\{.*\}", out, re.S)
        return json.loads(m.group(0)) if m else {}
    except Exception as e:
        return {"error": str(e)[:140]}


def nb_save(text, structure=True):
    """Save a finished note: store the raw text, structure it into actionable items, and file it into the
    ecosystem as a CITED context event (feeds retrieval + the Morning Brief). Tasks are NOT auto-added --
    review-first; the lens approves them into Tasks. Returns the structured note for review."""
    text = (text or "").strip()
    st = _load()
    s = _structure(text) if (structure and text) else {}
    if not isinstance(s, dict): s = {}
    note = {"id": "nb-%d" % int(time.time() * 1000), "ts": int(time.time()),
            "date": time.strftime("%Y-%m-%d"), "text": text,
            "title": (s.get("title") or (text[:60] + ("…" if len(text) > 60 else "")) or "Note"),
            "summary": s.get("summary", ""), "tasks": s.get("tasks", []) or [],
            "decisions": s.get("decisions", []) or [], "reminders": s.get("reminders", []) or [],
            "tags": s.get("tags", []) or [], "struct_error": s.get("error"), "applied": False}
    st["notes"].insert(0, note); st["notes"] = st["notes"][:300]; _save(st)
    ing = _CTX.get("context_ingest")
    if callable(ing):
        try: ing("note", "notebook", note["title"], (note["summary"] or text)[:1500],
                 ts=note["ts"], trust=3, ext_id=note["id"])
        except Exception: pass
    return {"ok": True, "note": note}


def nb_apply(note_id, picks=None):
    """Approve the note's extracted tasks -> push them into the Tasks list (as suggestions; review-first there
    too). picks = list of task indexes to add (None = all)."""
    st = _load(); note = next((n for n in st.get("notes", []) if n["id"] == note_id), None)
    if not note: return {"ok": False, "error": "no such note"}
    add = _CTX.get("task_add"); added = 0
    for i, t in enumerate(note.get("tasks", [])):
        if picks is not None and i not in picks: continue
        if callable(add):
            try:
                add(t.get("title", ""), detail=("from note: " + note.get("title", "")),
                    due=(t.get("due") or None), source="notebook", source_ref=note_id)
                added += 1
            except Exception: pass
    note["applied"] = True; _save(st)
    return {"ok": True, "added": added}


def nb_delete(note_id):
    st = _load(); n0 = len(st.get("notes", []))
    st["notes"] = [n for n in st.get("notes", []) if n["id"] != note_id]; _save(st)
    return {"ok": True, "deleted": n0 - len(st["notes"])}


def nb_get(note_id):
    return next((n for n in _load().get("notes", []) if n["id"] == note_id), None)


def nb_list():
    return {"ok": True, "notes": _load().get("notes", [])[:120], "has_voice": bool(_secret("DEEPGRAM_API_KEY"))}


def recent_notes(limit=12):
    """For the Morning Brief 'notes' source: [{label,text,ts}] of recent notes."""
    out = []
    for n in _load().get("notes", [])[:limit]:
        out.append({"label": n.get("title", "")[:80],
                    "text": (n.get("title", "") + " -- " + (n.get("summary") or n.get("text", "")))[:260],
                    "ts": n.get("ts", "")})
    return out
