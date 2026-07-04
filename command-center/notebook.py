#!/usr/bin/env python3
"""Notebook -- speak or write a note naturally; on finish it's structured into actionable items.

Capture (type, or dictate -> the browser records + uploads audio -> server transcribes via Deepgram, key
VAULT-FIRST, so it works from ANY device the operator opens the dashboard on, never the server's mic). On save a
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


def _parse_json(out):
    """Robustly pull a JSON object out of the summarizer's reply (tolerate code fences / trailing prose)."""
    out = (out or "").strip()
    out = re.sub(r"^```(?:json)?\s*|\s*```$", "", out, flags=re.S).strip()
    m = re.search(r"\{.*\}", out, re.S)
    if not m: return None
    blob = m.group(0)
    try: return json.loads(blob)
    except Exception:
        try: return json.loads(blob[:blob.rfind("}") + 1])   # trim trailing junk after the last brace
        except Exception: return None


def _structure(text):
    """Ask a headless claude -p to turn the raw note into the strict {title,summary,tasks,reminders,decisions,
    tags} contract. Retries once with a stricter preamble if the first reply doesn't parse, so the summary +
    action items reliably come back in a shape the lens can route into Tasks."""
    inj = _CTX.get("extractor")
    if inj: return inj(text)
    env = {**os.environ, "PATH": os.environ.get("PATH", "") + ":" + os.path.expanduser("~/.local/bin") + ":/opt/homebrew/bin"}
    last_err = ""
    for attempt in range(2):
        pre = "" if attempt == 0 else "Your last reply was not valid JSON. Output ONLY the JSON object, nothing else.\n"
        try:
            r = subprocess.run(["claude", "--dangerously-skip-permissions", "-p", pre + (STRUCT_PROMPT % text[:16000])],
                               capture_output=True, text=True, timeout=150, env=env)
            d = _parse_json(r.stdout)
            if isinstance(d, dict): return d
            last_err = "unparseable summarizer output"
        except Exception as e:
            last_err = str(e)[:140]
    return {"error": last_err or "could not structure the note"}


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
        # index BOTH the structured summary AND the verbatim raw text (+ tags) so the note is searchable in the
        # context layer by anything it contains -- not just the paraphrased summary (which can drop key words).
        body = ((note["summary"] + "\n\n") if note["summary"] else "") + text
        if note.get("tags"): body += "\n\ntags: " + " ".join(note["tags"])
        try: ing("note", "notebook", note["title"], body[:4000],
                 ts=note["ts"], trust=3, ext_id=note["id"])
        except Exception as e: note["ingest_error"] = str(e)[:200]
    else:
        note["ingest_error"] = "context_ingest not wired (callable=%s)" % (ing is not None)
    _save(st)
    return {"ok": True, "note": note}


def nb_apply(note_id, picks=None):
    """Approve the note's extracted tasks -> push them into the Tasks list (as suggestions; review-first there
    too). picks = list of task indexes to add (None = all)."""
    st = _load(); note = next((n for n in st.get("notes", []) if n["id"] == note_id), None)
    if not note: return {"ok": False, "error": "no such note"}
    add = _CTX.get("task_add"); added = 0
    _datelike = re.compile(r"^\d{4}-\d\d-\d\d$")
    for i, t in enumerate(note.get("tasks", [])):
        if picks is not None and i not in picks: continue
        if callable(add):
            try:
                add(t.get("title", ""), detail=("from note: " + note.get("title", "")),
                    due=(t.get("due") or None), source="notebook", source_ref=note_id)
                added += 1
            except Exception: pass
    if picks is None:                                  # "add all" also routes follow-up reminders into Tasks
        for r in note.get("reminders", []):
            txt = (r.get("text") or "").strip()
            if not txt: continue
            when = str(r.get("when") or "")
            if callable(add):
                try:
                    add("Follow up: " + txt, detail=("reminder from note: " + note.get("title", "")),
                        due=(when if _datelike.match(when) else None), source="notebook",
                        source_ref=note_id, kind="reminder")
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


def nb_list(q=None):
    """List notes, newest first. With `q`, full-text search across title + summary + raw text + tags + the
    extracted task/decision text (so a note is findable by anything it contains, not just its title)."""
    notes = _load().get("notes", [])
    total = len(notes)
    if q and q.strip():
        ql = q.strip().lower()
        def hay(n):
            parts = [n.get("title", ""), n.get("summary", ""), n.get("text", ""), " ".join(n.get("tags", []) or [])]
            parts += [t.get("title", "") for t in (n.get("tasks", []) or [])]
            parts += [str(x) for x in (n.get("decisions", []) or [])]
            parts += [r.get("text", "") for r in (n.get("reminders", []) or [])]
            return " ".join(parts).lower()
        notes = [n for n in notes if ql in hay(n)]
    return {"ok": True, "notes": notes[:150], "total": total, "matched": len(notes),
            "has_voice": bool(_secret("DEEPGRAM_API_KEY"))}


def recent_notes(limit=12):
    """For the Morning Brief 'notes' source: [{label,text,ts}] of recent notes."""
    out = []
    for n in _load().get("notes", [])[:limit]:
        out.append({"label": n.get("title", "")[:80],
                    "text": (n.get("title", "") + " -- " + (n.get("summary") or n.get("text", "")))[:260],
                    "ts": n.get("ts", "")})
    return out
