#!/usr/bin/env python3
"""Zoom meeting transcripts -> agency tree. A SELF-CONTAINED intake module that feeds Zoom recordings/
transcripts into the SAME propose->approve->apply pipeline Granola calls use: transcript -> REVIEWED
proposals (a dated note in the matched client's CLAUDE.md CC:CALLS region + tasks/reminders).

Design / reuse (the lowest-friction choice -- justified):
  Zoom is just a SECOND SOURCE of the existing Granola proposal queue. zoom_sync() builds the exact same
  proposal dict granola.gr_sync() produces and inserts it into Granola's shared state (_granola.json), so
  the EXISTING Calls lens, /api/granola-apply, and /api/granola-skip review+apply it with ZERO new apply
  code or UI. We REUSE granola._claude_extract (headless `claude -p`, no metered key) and
  granola._client_dirs (folder scan) directly. We ALSO ingest each transcript into the context store with
  its OWN provenance (source="zoom", trust="owner") so the substrate keeps Zoom distinct from Granola.
  Net: only the INTAKE (3 paths to a normalized transcript) is Zoom-specific; the whole propose->apply
  spine is reused unchanged.

Three intake paths to a normalized transcript:
  (a) a local recording/transcript file  -> parse_transcript_file(path)  (Zoom .vtt or .txt drop-in)
  (b) the Zoom Cloud Recording API       -> list_recordings(limit) + get_transcript(meeting_id)
  (c) a generic in-memory transcript     -> ingest_transcript(text, title, ts, client=None)

Stdlib only (urllib). Secret-clean: Server-to-Server OAuth creds come from a gitignored secret/.env
(ZOOM_ACCOUNT_ID / ZOOM_CLIENT_ID / ZOOM_CLIENT_SECRET via the injected `secret` reader or os.environ) --
NEVER from code and NEVER from cc.config. Graceful no-op when not configured. Review-first: nothing
touches a client CLAUDE.md until the operator approves the proposal in the Calls lens.

server.py wires this exactly like granola: zoom.init({...}) once, then the zoom_* functions behind
/api/zoom-sync and /api/zoom-drop.

Config (cc.config "zoom") -- NON-secret only: {
  "client_map": {"acme": ["acme.com", "Acme Corp"], ...},   # client folder -> attendee domains/aliases
  "user": "me",                                              # Zoom user id/email to list recordings for
  "drop_dir": "~/Downloads"                                  # default dir for /api/zoom-drop bare filenames
}
Secrets (gitignored .env.claudefather or env) -- the S2S app credentials:
  ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET
"""
import json, os, re, time, base64, urllib.request, urllib.parse

import granola   # REUSE the propose->apply spine: shared proposal queue + extractor + client-dir scan

# context layer is optional (graceful if unavailable); imported lazily in _ctx_ingest
_CTX = {}        # injected by server.py: CC, PROJECT, STATE_DIR, secret(callable), mesh_log(optional)
_TOKEN = {"access_token": None, "exp": 0}


def init(ctx):
    """Called once by server.py (mirrors granola.init). ctx may carry CC, PROJECT, STATE_DIR, and a
    `secret` callable (server's _deploy_env) used to read S2S creds from the gitignored .env.claudefather."""
    _CTX.update(ctx or {})
    return {"ok": True, "configured": is_configured()}


def _cfg():
    return (_CTX.get("CC", {}) or {}).get("zoom") or {}


def _secret(key, default=None):
    """Resolve an S2S credential: os.environ -> injected secret reader (.env.claudefather) -> default.
    NEVER reads from cc.config (secrets stay out of config). Never logged/printed."""
    v = os.environ.get(key)
    if v: return v
    fn = _CTX.get("secret")
    if callable(fn):
        try:
            v = fn(key)
            if v: return v
        except Exception:
            pass
    return default


def is_configured():
    """True when EITHER the cloud API creds are present OR a client_map exists (drop-file path still works
    with no creds). Cloud sync specifically needs the three S2S secrets."""
    return bool(_cloud_creds()[0] or _cfg())


def _cloud_creds():
    return (_secret("ZOOM_ACCOUNT_ID"), _secret("ZOOM_CLIENT_ID"), _secret("ZOOM_CLIENT_SECRET"))


# ---- (a) LOCAL FILE intake: parse a Zoom .vtt / .txt transcript --------------------------------------
def parse_vtt_text(text):
    """Parse a WebVTT (.vtt) transcript STRING -> {text:'Speaker: line\\n...', speakers:[...]}.
    Handles Zoom's two speaker encodings: a `<v Speaker Name>line` voice tag, or a `Speaker: line` prefix.
    Skips the WEBVTT header, NOTE blocks, numeric cue indexes, and `-->` timestamp lines. Collapses
    consecutive lines from the same speaker. Pure-stdlib + standalone-testable on a string."""
    lines, speakers = [], []
    last_sp = None
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.upper().startswith("WEBVTT") or s.startswith("NOTE"):
            continue
        if "-->" in s:                      # timestamp cue line
            continue
        if re.match(r"^\d+$", s):           # numeric cue index
            continue
        sp, body = None, s
        mv = re.match(r"^<v\s+([^>]+)>(.*)$", s)        # <v Speaker Name>text
        if mv:
            sp = mv.group(1).strip()
            body = re.sub(r"</v>$", "", mv.group(2)).strip()
        else:
            mn = re.match(r"^([A-Za-z0-9 ._'\-]{1,48}):\s+(.*)$", s)   # Speaker: text
            if mn:
                sp = mn.group(1).strip()
                body = mn.group(2).strip()
        body = re.sub(r"<[^>]+>", "", body).strip()      # strip any leftover inline tags
        if not body:
            continue
        if sp and sp not in speakers:
            speakers.append(sp)
        if sp:
            if sp == last_sp and lines:                  # same speaker -> append to their last line
                lines[-1] += " " + body
            else:
                lines.append("%s: %s" % (sp, body))
            last_sp = sp
        else:
            if last_sp and lines:
                lines[-1] += " " + body
            else:
                lines.append(body)
    return {"text": "\n".join(lines), "speakers": speakers}


def parse_txt_text(text):
    """Parse a plain .txt transcript STRING. Keeps `Speaker: line` prefixes; collects speaker names."""
    speakers = []
    for raw in (text or "").splitlines():
        m = re.match(r"^([A-Za-z0-9 ._'\-]{1,48}):\s+\S", raw.strip())
        if m and m.group(1).strip() not in speakers:
            speakers.append(m.group(1).strip())
    return {"text": (text or "").strip(), "speakers": speakers}


def parse_transcript_file(path):
    """Drop-in parse of a local Zoom transcript file (.vtt or .txt) -> {text, speakers, title, source}.
    `title` defaults to the filename stem (operator can rename on the proposal)."""
    p = os.path.expanduser(path)
    with open(p, encoding="utf-8", errors="replace") as f:
        raw = f.read()
    ext = os.path.splitext(p)[1].lower()
    parsed = parse_vtt_text(raw) if (ext == ".vtt" or raw.lstrip().upper().startswith("WEBVTT")) else parse_txt_text(raw)
    parsed["title"] = os.path.splitext(os.path.basename(p))[0]
    parsed["source_path"] = p
    return parsed


# ---- (b) ZOOM CLOUD RECORDING API (Server-to-Server OAuth) -------------------------------------------
def _s2s_token():
    """Mint/refresh a Server-to-Server OAuth access token. Creds come from the gitignored secret/.env
    (never code/cc.config). Cached until ~1 min before expiry. Returns None when not configured."""
    acct, cid, csec = _cloud_creds()
    if not (acct and cid and csec):
        return None
    if _TOKEN["access_token"] and time.time() < _TOKEN["exp"] - 60:
        return _TOKEN["access_token"]
    qs = urllib.parse.urlencode({"grant_type": "account_credentials", "account_id": acct})
    basic = base64.b64encode(("%s:%s" % (cid, csec)).encode()).decode()
    req = urllib.request.Request("https://zoom.us/oauth/token?" + qs, data=b"",
                                 headers={"Authorization": "Basic " + basic,
                                          "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read().decode())
    _TOKEN["access_token"] = d.get("access_token")
    _TOKEN["exp"] = time.time() + int(d.get("expires_in") or 3500)
    return _TOKEN["access_token"]


def _api_get(path):
    tok = _s2s_token()
    if not tok:
        raise RuntimeError("zoom S2S not configured (ZOOM_ACCOUNT_ID/CLIENT_ID/CLIENT_SECRET)")
    req = urllib.request.Request("https://api.zoom.us/v2" + path,
                                 headers={"Authorization": "Bearer " + tok, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def list_recordings(limit=25):
    """Return recent cloud recordings as [{id, uuid, title, date, attendees, summary, _files}], newest-first.
    `id` is the meeting id get_transcript() expects. Graceful: returns [{error:...}] on failure/no-config."""
    if not _cloud_creds()[0]:
        return [{"error": "zoom cloud not configured"}]
    user = _cfg().get("user") or "me"
    try:
        d = _api_get("/users/%s/recordings?page_size=%d" % (urllib.parse.quote(str(user)), min(int(limit), 300)))
    except Exception as e:
        return [{"error": "zoom api: " + str(e)[:160]}]
    out = []
    for m in (d.get("meetings") or [])[:limit]:
        files = m.get("recording_files") or []
        out.append({"id": str(m.get("id") or m.get("uuid")), "uuid": m.get("uuid"),
                    "title": m.get("topic") or "(untitled)", "date": m.get("start_time") or "",
                    "attendees": [], "summary": "",
                    "_files": [{"type": f.get("file_type"), "url": f.get("download_url"),
                                "ext": f.get("file_extension")} for f in files]})
    return out


def zoom_meetings(limit=25):
    """SAME shape as granola.list_meetings -> [{id,title,date,attendees,summary}]. Lets the existing Calls
    machinery treat Zoom meetings identically. (Cloud-only; for files use parse_transcript_file/ingest.)"""
    return [{k: m[k] for k in ("id", "title", "date", "attendees", "summary")} for m in list_recordings(limit)
            if not m.get("error")] or list_recordings(limit)


def _download(url):
    tok = _s2s_token()
    u = url + (("&" if "?" in url else "?") + "access_token=" + tok) if tok else url
    req = urllib.request.Request(u, headers={"Authorization": "Bearer " + (tok or "")})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


def get_transcript(meeting_id):
    """Download + parse the VTT transcript of a cloud recording -> 'Speaker: text' lines (granola shape)."""
    for m in list_recordings(100):
        if m.get("error"):
            return ""
        if str(m.get("id")) == str(meeting_id) or m.get("uuid") == meeting_id:
            tfile = next((f for f in m.get("_files", []) if (f.get("type") or "").upper() == "TRANSCRIPT"), None)
            if not tfile and not any((f.get("type") or "").upper() == "TRANSCRIPT" for f in m.get("_files", [])):
                # some accounts label it CC/closed-caption; fall back to any .vtt file
                tfile = next((f for f in m.get("_files", []) if (f.get("ext") or "").lower() == "vtt"), None)
            if not tfile or not tfile.get("url"):
                return ""
            return parse_vtt_text(_download(tfile["url"]))["text"]
    return ""


# ---- client matching (cc.config zoom.client_map; reuses granola's folder scan) ------------------------
def match_client(meeting):
    """Best client folder for a meeting via cc.config zoom.client_map (domains/aliases) then a fuzzy title
    match. Mirrors granola.match_client but keyed on the ZOOM config. Returns (name, abs_path) or (None,None)."""
    cmap = _cfg().get("client_map") or {}
    dirs = granola._client_dirs()
    by_slug = {nm.lower(): (nm, p) for nm, p in dirs}
    emails = " ".join((a.get("email") or "") for a in meeting.get("attendees", []) if isinstance(a, dict)).lower()
    hay = (meeting.get("title", "") + " " + emails).lower()
    for slug, aliases in cmap.items():
        for a in ([slug] + list(aliases or [])):
            if a and a.lower() in hay and slug.lower() in by_slug:
                return by_slug[slug.lower()]
    for nm, p in dirs:
        words = re.sub(r"[-_]+", " ", nm).lower()
        if words and words in meeting.get("title", "").lower():
            return (nm, p)
    return (None, None)


# ---- the shared core: a normalized transcript -> a REVIEWED proposal in the Granola queue -------------
def _ctx_ingest(title, transcript, ts, client, meeting_id):
    """Best-effort: record the raw call in the context store with ZOOM provenance (source='zoom', owner
    trust). Idempotent on ext_id. Never raises (the proposal path must not depend on the store)."""
    try:
        import context
        context.ingest_event(kind="call", source="zoom", title=(title or "call"), body=(transcript or ""),
                             ts=ts, subject=(client or None), trust="owner",
                             ext_id=("zoom:" + str(meeting_id)), refs={"meeting_id": meeting_id})
    except Exception:
        pass


def ingest_transcript(text, title="(Zoom call)", ts=None, client=None, meeting_id=None):
    """(c) Generic intake: a normalized transcript STRING -> a PENDING proposal in the SHARED Granola queue
    (so the existing Calls lens / gr_apply / gr_skip review+apply it) + a context event with zoom provenance.
    Reuses granola._claude_extract for the LLM pass. Review-first: NOTHING is applied to a client file here.
    Returns the proposal dict."""
    ts = int(ts or time.time())
    meeting_id = meeting_id or ("file-%d" % ts)
    meeting = {"id": meeting_id, "title": title, "date": time.strftime("%Y-%m-%d", time.localtime(ts)), "attendees": []}
    cname, cpath = (None, None)
    if client:                                  # explicit client wins (drop-file / API hint)
        for nm, ap in granola._client_dirs():
            if nm == client or nm.lower() == str(client).lower():
                cname, cpath = nm, ap; break
    if not cname:
        cname, cpath = match_client(meeting)
    ext = granola._claude_extract(title, text) if text else {}
    PROJECT = _CTX.get("PROJECT", ".")
    prop = {"id": "z-%d-%d" % (int(time.time() * 1000), ts % 1000), "meeting_id": meeting_id,
            "source": "zoom", "title": title, "date": meeting["date"], "ts": ts,
            "client": cname, "client_path": (os.path.relpath(cpath, PROJECT) if cpath else None),
            "matched": bool(cname), "summary": ext.get("summary", ""), "notes": ext.get("notes", []),
            "tasks": ext.get("tasks", []), "reminders": ext.get("reminders", []),
            "decisions": ext.get("decisions", []), "status": "pending", "error": ext.get("error")}
    _queue_insert(prop, meeting_id)
    _ctx_ingest(title, text, ts, cname, meeting_id)
    return prop


def _queue_insert(prop, meeting_id):
    """Insert a proposal into the SHARED Granola state (_granola.json) so the existing review/apply UI + API
    operate on it unchanged. Records meeting_id in `seen` for idempotent cloud sync."""
    st = granola._load_state()
    st.setdefault("proposals", []).insert(0, prop)
    seen = set(st.get("seen", []))
    if meeting_id:
        seen.add("zoom:" + str(meeting_id))
    st["seen"] = list(seen)[-500:]
    granola._save_state(st)


# ---- (b) cloud SYNC: pull new recordings -> proposals (mirrors granola.gr_sync) -----------------------
def zoom_sync(limit=15):
    """Pull recent cloud recordings, skip already-seen, download+extract each, store PENDING proposals in the
    SHARED Granola queue. Mirrors granola.gr_sync. Graceful no-op when cloud creds are absent."""
    if not _cloud_creds()[0]:
        return {"ok": False, "error": "zoom cloud not configured (ZOOM_ACCOUNT_ID/CLIENT_ID/CLIENT_SECRET in .env)"}
    meetings = list_recordings(limit)
    if meetings and meetings[0].get("error"):
        return {"ok": False, "error": meetings[0]["error"]}
    seen = set(granola._load_state().get("seen", []))
    added = 0
    for m in meetings:
        mid = m.get("id")
        if not mid or ("zoom:" + str(mid)) in seen:
            continue
        try:
            tx = get_transcript(mid)
        except Exception:
            tx = ""
        if not tx:
            continue   # no transcript yet (still processing) -> skip; a later sync picks it up
        ts = granola_epoch(m.get("date"))
        ingest_transcript(tx, title=m.get("title") or "(Zoom call)", ts=ts, meeting_id=mid)
        added += 1
    pend = len([p for p in granola._load_state().get("proposals", []) if p.get("status") == "pending"])
    return {"ok": True, "added": added, "pending": pend}


def zoom_drop(path, client=None):
    """(a) Intake a DROPPED local transcript file -> a PENDING proposal. `path` may be absolute or a bare
    filename resolved against cc.config zoom.drop_dir (default ~/Downloads). Returns the proposal."""
    p = os.path.expanduser(path)
    if not os.path.isabs(p) and not os.path.isfile(p):
        base = os.path.expanduser(_cfg().get("drop_dir") or "~/Downloads")
        p = os.path.join(base, path)
    if not os.path.isfile(p):
        return {"ok": False, "error": "no such file: " + p}
    parsed = parse_transcript_file(p)
    if not parsed["text"].strip():
        return {"ok": False, "error": "empty/unparseable transcript: " + p}
    ts = int(os.path.getmtime(p))
    prop = ingest_transcript(parsed["text"], title=parsed["title"], ts=ts, client=client,
                             meeting_id="file:" + os.path.basename(p))
    return {"ok": True, "proposal_id": prop["id"], "client": prop["client"], "matched": prop["matched"]}


def granola_epoch(s):
    """Parse a Zoom ISO8601 start_time (e.g. 2026-06-25T18:00:00Z) to epoch seconds; falls back to now."""
    if not s:
        return int(time.time())
    try:
        from datetime import datetime
        return int(datetime.strptime(s.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z").timestamp())
    except Exception:
        return int(time.time())


# ---- standalone self-test (no network, no creds) -----------------------------------------------------
def _selftest():
    sample = (
        "WEBVTT\n\n"
        "1\n00:00:01.000 --> 00:00:04.000\n<v James>Hey, thanks for hopping on.\n\n"
        "2\n00:00:04.000 --> 00:00:07.500\n<v James>Wanted to talk about the 6.7 tune.\n\n"
        "3\n00:00:08.000 --> 00:00:12.000\nDana Lee: Sure, what are the EGT concerns?\n\n"
    )
    out = parse_vtt_text(sample)
    assert "James:" in out["text"] and "Dana Lee:" in out["text"], out
    assert "James" in out["speakers"] and "Dana Lee" in out["speakers"], out["speakers"]
    # consecutive same-speaker cues collapse onto one line
    assert out["text"].count("James:") == 1, out["text"]
    txt = parse_txt_text("James: hello there\nDana: hi back")
    assert txt["speakers"] == ["James", "Dana"], txt
    print("SELFTEST OK ->\n" + out["text"])
    print("speakers:", out["speakers"])
    return True


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    if cmd == "selftest":
        _selftest()
    elif cmd == "parse" and len(sys.argv) > 2:
        print(json.dumps(parse_transcript_file(sys.argv[2]), indent=2))
    else:
        print("usage: zoom.py [selftest | parse <file.vtt>]")
