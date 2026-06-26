#!/usr/bin/env python3
"""Capture SPINE: Capture -> Triage -> Apply (review-first). Mirrors granola.py's propose->approve->apply.

A CLIP is anything captured from where you work -- a web selection, a screenshot, a note, a link -- saved
from the browser extension / desktop sidebar / a paste. Each clip lands as PENDING in _clips.json AND is
ingested into the context store (provenance: source + trust=external, ext_id = url-or-uuid) so the router
sees it immediately. The TRIAGE AGENT (a headless `claude -p`, no metered key -- exactly granola's pattern)
clusters the pending clips per subject, dedups, summarizes, and extracts tasks/decisions/contacts/links, and
PROPOSES: (a) a dated digest for that subject's CLAUDE.md in a managed CC:CLIPS region (mirrors CC:CALLS),
(b) tasks, (c) which clips to file into deliverables. NOTHING touches a CLAUDE.md or creates a task until
clips_apply() (review-first). Every applied line CITES its source clip ("[from <url>, saved <date>]").

Stdlib only. server.py calls clips.init(ctx) once, then clip_*/clips_* behind /api/clip*. ctx injects the
context-store + task + deliverable + agency helpers so this module stays engine-only (no server imports).
"""
import json, os, re, subprocess, time, uuid, hashlib

_CTX = {}  # injected by server.py: CC, PROJECT, STATE_DIR, ingest_event, assemble, subjects, task_add,
           # write_clip_image, subject_dir, pretty_name, client_list, (optional) extractor, mesh_log


def init(ctx):
    _CTX.update(ctx)


def _cfg():
    return (_CTX.get("CC", {}) or {}).get("clips") or {}


def _state_path():
    return os.path.join(_CTX.get("STATE_DIR", "."), "_clips.json")


def _load_state():
    try:
        with open(_state_path()) as f:
            s = json.load(f)
    except Exception:
        s = {}
    s.setdefault("clips", [])
    s.setdefault("proposals", [])
    return s


def _save_state(s):
    with open(_state_path(), "w") as f:
        json.dump(s, f, indent=2)


# ---- secret-clean: never capture an obvious auth/secret URL --------------------------------------------
_SECRET_URL = re.compile(
    r"(access_token=|id_token=|refresh_token=|[?&](api[_-]?key|apikey|secret|password|passwd|pwd|"
    r"client_secret|auth|token|sig|signature|session)=|//[^/@:]+:[^/@]+@)", re.I)
_TEXT_CAP = 8000     # bound the stored clip body
_NOTE_CAP = 1000


def _url_ok(url):
    """A URL is safe to keep verbatim unless it looks like it carries a credential/token."""
    return not (url and _SECRET_URL.search(url))


# ---- 1) CAPTURE: save a pending clip + ingest into the context store -----------------------------------
def clip_save(subject="", kind="web", url="", title="", text="", note="", image_b64=None, source="web"):
    """Save a PENDING clip. If image_b64 (data: URL or raw base64 PNG) is given, write it to the subject's
    deliverables/ (clips/) via the injected writer and store image_rel. ALSO ingest_event() so the router
    sees it now. Secret-clean (drops credential-bearing URLs). Returns {ok, id}."""
    subject = (subject or "").strip()
    kind = (kind or "web").strip() or "web"
    url = (url or "").strip()
    title = (title or "").strip()
    text = (text or "")[:_TEXT_CAP]
    note = (note or "")[:_NOTE_CAP]
    source = (source or "web").strip() or "web"
    if url and not _url_ok(url):
        url = ""                                          # drop a credential-bearing URL; keep the rest
    if not (text or title or url or image_b64):
        return {"ok": False, "error": "empty clip"}

    image_rel = None
    if image_b64:
        wci = _CTX.get("write_clip_image")
        try:
            image_rel = wci(subject, (title or "clip"), image_b64) if wci else None
        except Exception:
            image_rel = None

    cid = "clip-%d-%s" % (int(time.time() * 1000), uuid.uuid4().hex[:6])
    ts = int(time.time())
    clip = {"id": cid, "subject": subject, "kind": kind, "url": url, "title": title,
            "text": text, "note": note, "image_rel": image_rel, "ts": ts,
            "status": "pending", "source": source}

    st = _load_state()
    st["clips"].insert(0, clip)
    st["clips"] = st["clips"][:2000]
    _save_state(st)

    # ingest into the context store (provenance + trust). ext_id = url (idempotent on re-clip) else uuid.
    ing = _CTX.get("ingest_event")
    if ing:
        try:
            ing(kind="clip", source=source, title=(title or url or (text[:60] if text else "clip")),
                body=text, ts=ts, subject=(subject or None), trust="external",
                ext_id=(url or cid), refs={"url": url, "note": note, "image_rel": image_rel, "clip_kind": kind})
        except Exception:
            pass
    return {"ok": True, "id": cid}


# ---- 2) read: list clips -------------------------------------------------------------------------------
def clips_list(subject=None, status=None):
    st = _load_state()
    out = st.get("clips", [])
    if subject:
        out = [c for c in out if (c.get("subject") or "").lower() == str(subject).lower()]
    if status:
        out = [c for c in out if c.get("status") == status]
    pend = [c for c in st.get("clips", []) if c.get("status") == "pending"]
    by_subject = {}
    for c in pend:
        by_subject[c.get("subject") or ""] = by_subject.get(c.get("subject") or "", 0) + 1
    return {"ok": True, "clips": out[:500], "pending": len(pend),
            "by_subject": by_subject, "configured": True,
            "proposals": [p for p in st.get("proposals", []) if p.get("status") == "pending"][:80],
            "clients": (_CTX.get("client_list") or (lambda: []))()}


# ---- 3) TRIAGE: cluster pending clips per subject + extract proposals (headless claude -p) -------------
EXTRACT_PROMPT = (
    "You are a capture-triage assistant. Below are CLIPS the user saved while working (web selections, "
    "notes, screenshots, links) -- all about the SUBJECT '%s'. Cluster + dedup them, then extract ONLY what "
    "is clearly supported -- do not invent. Return STRICT JSON (no prose, no code fence) with this exact "
    "shape:\n"
    '{"summary":"<=2 sentences of what these clips are about",'
    '"digest":["durable fact worth remembering about this subject", ...],'
    '"tasks":[{"title":"action item","owner":"who or \\"\\"","due":"YYYY-MM-DD or \\"\\""}],'
    '"decisions":["decision/conclusion", ...],'
    '"contacts":[{"name":"person","handle":"email or @handle or \\"\\""}],'
    '"links":[{"url":"a link worth keeping","why":"why it matters"}],'
    '"file":[<index of any clip whose screenshot/text should be filed as a deliverable>]}\n'
    "Keep each list tight (omit if nothing concrete). CLIPS (index. kind | title | url):\n%s\n")


def _claude_extract(subject, clips):
    """Run triage in a headless claude (Max subscription, no metered key). Returns the parsed dict.
    Tests inject a fake via ctx['extractor']."""
    inj = _CTX.get("extractor")
    if inj:
        return inj(subject, clips)
    lines = []
    for i, c in enumerate(clips):
        body = (c.get("text") or "")[:1200]
        lines.append("%d. [%s] %s | %s\n%s" % (i, c.get("kind", ""), (c.get("title") or "(untitled)"),
                                               (c.get("url") or ""), body))
    prompt = EXTRACT_PROMPT % (subject or "(unsorted)", "\n\n".join(lines)[:24000])
    try:
        r = subprocess.run(["claude", "--dangerously-skip-permissions", "-p", prompt],
                           capture_output=True, text=True, timeout=180,
                           env={**os.environ, "PATH": os.environ.get("PATH", "") + ":" +
                                os.path.expanduser("~/.local/bin") + ":/opt/homebrew/bin"})
        out = (r.stdout or "").strip()
        m = re.search(r"\{.*\}", out, re.S)
        return json.loads(m.group(0)) if m else {}
    except Exception as e:
        return {"error": str(e)[:160]}


def clips_process(subject=None):
    """The TRIAGE step: cluster the PENDING clips (by subject), run the extractor, and store PENDING
    PROPOSALS (one per subject). Returns {ok, proposals}. Does NOT apply anything (review-first)."""
    st = _load_state()
    pend = [c for c in st.get("clips", []) if c.get("status") == "pending"]
    if subject:
        pend = [c for c in pend if (c.get("subject") or "").lower() == str(subject).lower()]
    if not pend:
        return {"ok": True, "proposals": [], "note": "no pending clips"}

    groups = {}
    for c in pend:
        groups.setdefault(c.get("subject") or "", []).append(c)

    made = []
    for subj, clips in groups.items():
        ext = _claude_extract(subj, clips)
        prop = {"id": "clp-%d-%s" % (int(time.time() * 1000), uuid.uuid4().hex[:4]),
                "subject": subj, "ts": int(time.time()), "status": "pending",
                "clip_ids": [c["id"] for c in clips],
                "summary": ext.get("summary", ""), "digest": ext.get("digest", []),
                "tasks": ext.get("tasks", []), "decisions": ext.get("decisions", []),
                "contacts": ext.get("contacts", []), "links": ext.get("links", []),
                "file": [clips[i]["id"] for i in (ext.get("file") or []) if isinstance(i, int) and 0 <= i < len(clips)],
                "error": ext.get("error")}
        # cite-able source index for the UI / applier: clip id -> {url, ts}
        prop["sources"] = {c["id"]: {"url": c.get("url"), "ts": c.get("ts"),
                                     "title": c.get("title"), "image_rel": c.get("image_rel")} for c in clips}
        st["proposals"].insert(0, prop)
        made.append(prop)
    st["proposals"] = st["proposals"][:200]
    _save_state(st)
    return {"ok": True, "proposals": made}


# ---- 4) APPLY (review-first): splice CC:CLIPS, create tasks, file deliverables -------------------------
CLIPS_B, CLIPS_E = "<!-- CC:CLIPS log (Capture; newest first) -->", "<!-- /CC:CLIPS -->"


def _cite(src):
    """A provenance footnote for an applied line: '[from <url>, saved <date>]'."""
    if not src:
        return ""
    when = time.strftime("%Y-%m-%d", time.localtime(src.get("ts") or time.time()))
    where = src.get("url") or src.get("title") or "clip"
    return "  _[from %s, saved %s]_" % (where, when)


def _append_clips_note(cpath, prop):
    """Append a dated capture digest to the subject CLAUDE.md inside a managed CC:CLIPS region (mirrors
    granola's CC:CALLS). Each line cites its source clip."""
    cm = os.path.join(cpath, "CLAUDE.md")
    srcs = prop.get("sources") or {}
    # one representative source for the citation: prefer the newest clip that actually has a URL, else newest
    head_src = None
    if srcs:
        withurl = [s for s in srcs.values() if s.get("url")]
        head_src = max((withurl or list(srcs.values())), key=lambda s: (s.get("ts") or 0))
    entry = ["", "### %s -- captured notes" % time.strftime("%Y-%m-%d")]
    if prop.get("summary"):
        entry.append(prop["summary"])
    for d in prop.get("digest", []):
        entry.append("- " + str(d) + (_cite(head_src) if head_src else ""))
    for dec in prop.get("decisions", []):
        entry.append("- DECISION: " + str(dec) + (_cite(head_src) if head_src else ""))
    for ln in prop.get("links", []):
        if isinstance(ln, dict) and ln.get("url"):
            entry.append("- LINK: %s%s" % (ln["url"], (" -- " + ln["why"]) if ln.get("why") else ""))
    for ct in prop.get("contacts", []):
        if isinstance(ct, dict) and ct.get("name"):
            entry.append("- CONTACT: %s%s" % (ct["name"], (" <" + ct["handle"] + ">") if ct.get("handle") else ""))
    block = "\n".join(entry)
    try:
        cur = open(cm).read() if os.path.isfile(cm) else "# %s\n" % os.path.basename(cpath)
    except Exception:
        cur = "# %s\n" % os.path.basename(cpath)
    m = re.search(re.escape(CLIPS_B) + r"(.*?)" + re.escape(CLIPS_E), cur, re.S)
    if m:
        new = cur[:m.start(1)] + (m.group(1).rstrip() + "\n" + block + "\n") + cur[m.end(1):]
    else:
        new = cur.rstrip() + "\n\n## Capture log\n" + CLIPS_B + "\n" + block + "\n" + CLIPS_E + "\n"
    with open(cm, "w") as f:
        f.write(new)


def clips_apply(pid, edited=None):
    """Approve + apply a PROPOSAL. `edited` may override fields (operator edits) and may set `subject`
    (manual assignment). Splices CC:CLIPS into the subject CLAUDE.md, creates tasks, files deliverables,
    marks the proposal + its clips applied. Returns {ok, applied}."""
    st = _load_state()
    prop = next((p for p in st["proposals"] if p["id"] == pid), None)
    if not prop:
        return {"ok": False, "error": "no such proposal"}
    p = {**prop, **(edited or {})}
    subj = (p.get("subject") or "").strip()
    if not subj:
        return {"ok": False, "error": "no subject -- set 'subject' to one of the listed clients"}

    applied = {"note": False, "tasks": 0, "filed": 0, "errors": []}

    # 1) dated digest -> subject CLAUDE.md (only if it resolves to a real folder in the tree)
    cpath = None
    sd = _CTX.get("subject_dir")
    try:
        cpath = sd(subj) if sd else None
    except Exception:
        cpath = None
    if cpath and (p.get("summary") or p.get("digest") or p.get("decisions") or p.get("links") or p.get("contacts")):
        try:
            _append_clips_note(cpath, p)
            applied["note"] = True
        except Exception as e:
            applied["errors"].append("note: " + str(e)[:120])

    # 2) tasks -> the Tasks lens (review-first creation happens HERE, not at capture)
    ta = _CTX.get("task_add")
    if ta:
        for t in (p.get("tasks") or []):
            try:
                ta((t.get("title") or "task"), detail=("from capture: " + subj),
                   due=(t.get("due") or None), client=(os.path.relpath(cpath, _CTX["PROJECT"]) if cpath else ""),
                   source="clip", source_ref=pid, status="open")
                applied["tasks"] += 1
            except Exception as e:
                applied["errors"].append("task: " + str(e)[:120])

    # 3) file chosen clips into deliverables (images already live there; text clips -> a .md note)
    fc = _CTX.get("file_clip")
    for cid in (p.get("file") or []):
        clip = next((c for c in st["clips"] if c["id"] == cid), None)
        if not clip:
            continue
        if clip.get("image_rel"):
            applied["filed"] += 1                  # already filed at capture time
            continue
        if fc and clip.get("text"):
            try:
                if fc(subj, clip):
                    applied["filed"] += 1
            except Exception as e:
                applied["errors"].append("file: " + str(e)[:120])

    # 4) mark clips + proposal applied
    capplied = set(prop.get("clip_ids") or [])
    for c in st["clips"]:
        if c["id"] in capplied:
            c["status"] = "applied"
    prop["status"] = "applied"
    prop["applied"] = applied
    prop["applied_ts"] = int(time.time())
    if edited:
        prop["edited"] = {k: edited[k] for k in edited if k in
                          ("summary", "digest", "tasks", "decisions", "contacts", "links", "subject", "file")}
    if not applied["errors"]:
        applied.pop("errors")
    _save_state(st)
    return {"ok": True, "applied": applied}


def clips_skip(pid):
    """Skip a PROPOSAL (and its clips) or a single CLIP, by id."""
    st = _load_state()
    prop = next((p for p in st["proposals"] if p["id"] == pid), None)
    if prop:
        prop["status"] = "skipped"
        for c in st["clips"]:
            if c["id"] in (prop.get("clip_ids") or []) and c["status"] == "pending":
                c["status"] = "skipped"
        _save_state(st)
        return {"ok": True, "kind": "proposal"}
    clip = next((c for c in st["clips"] if c["id"] == pid), None)
    if clip:
        clip["status"] = "skipped"
        _save_state(st)
        return {"ok": True, "kind": "clip"}
    return {"ok": False, "error": "no such clip/proposal"}


# ---- 5) AI co-reading sidebar: what do we ALREADY know relevant to this page (read-only) ---------------
def page_intel(url="", title="", text="", subject=None):
    """For the desktop 'AI co-reading' sidebar: use the router (context.assemble) to surface what we already
    know that's relevant to the page in front of you. READ-ONLY -- never writes, never proposes."""
    asm = _CTX.get("assemble")
    if not asm:
        return {"ok": True, "related": [], "flags": []}
    q = " ".join(x for x in [title, (text or "")[:400]] if x).strip()
    try:
        b = asm(query=(q or None), subject=(subject or None), budget_tokens=1500)
    except Exception as e:
        return {"ok": False, "error": str(e)[:120], "related": [], "flags": []}
    items = b.get("items") or []
    related = []
    for it in items[:6]:
        related.append({"title": (it.get("title") or it.get("kind") or "item"),
                        "source": it.get("source"), "kind": it.get("kind"),
                        "why": "%s from %s" % (it.get("kind"), it.get("source"))})
    flags = []
    now = time.time()
    for it in items:
        if it.get("kind") == "calendar" and (it.get("ts") or 0) >= now:
            flags.append("ties to upcoming: %s" % ((it.get("title") or "an event"))[:60])
    if subject and items:
        flags.insert(0, "%d things known about %s" % (len(items), subject))
    return {"ok": True, "related": related, "flags": flags[:4], "subject": subject,
            "considered": (b.get("pipeline") or {}).get("considered", len(items))}


# ---- self test ----------------------------------------------------------------------------------------
def selftest():
    import tempfile
    _CTX.clear()
    sd = tempfile.mkdtemp()
    proj = tempfile.mkdtemp()
    os.makedirs(os.path.join(proj, "Acme"))
    ingested = []
    init({"CC": {}, "PROJECT": proj, "STATE_DIR": sd,
          "ingest_event": (lambda **k: ingested.append(k)),
          "assemble": (lambda **k: {"items": [{"title": "Acme call", "source": "granola", "kind": "call", "ts": time.time()}], "pipeline": {"considered": 1}}),
          "task_add": (lambda title, **k: {"ok": True, "id": "t1"}),
          "subject_dir": (lambda s: os.path.join(proj, "Acme") if s == "Acme" else None),
          "client_list": (lambda: ["Acme"]),
          "write_clip_image": (lambda subj, fn, b64: "Acme/deliverables/clips/x.png"),
          "extractor": (lambda subj, clips: {"summary": "Acme wants a quote.", "digest": ["Acme prefers email"],
                                             "tasks": [{"title": "Send Acme a quote", "owner": "", "due": ""}],
                                             "decisions": ["Go with plan B"], "contacts": [], "links": [], "file": []})})
    r = clip_save(subject="Acme", kind="web", url="https://acme.com/pricing", title="Acme pricing", text="They want a quote by Friday.")
    assert r["ok"], r
    assert len(ingested) == 1 and ingested[0]["kind"] == "clip", ingested
    # secret URL is dropped
    r2 = clip_save(subject="Acme", url="https://x.com/cb?access_token=SECRET", text="login page")
    saved = clips_list(subject="Acme")["clips"]
    assert any(c.get("url") == "" for c in saved), "secret url not dropped"
    proc = clips_process(subject="Acme")
    assert proc["proposals"] and proc["proposals"][0]["subject"] == "Acme", proc
    pid = proc["proposals"][0]["id"]
    ap = clips_apply(pid)
    assert ap["ok"] and ap["applied"]["note"] and ap["applied"]["tasks"] == 1, ap
    cm = open(os.path.join(proj, "Acme", "CLAUDE.md")).read()
    assert CLIPS_B in cm and "Acme prefers email" in cm and "[from https://acme.com/pricing" in cm, cm
    assert all(c["status"] == "applied" for c in clips_list(subject="Acme", status="applied")["clips"])
    pi = page_intel(title="Acme pricing", subject="Acme")
    assert pi["ok"] and pi["related"], pi
    print("SELFTEST OK -> clips=%d proposal applied, CC:CLIPS spliced, tasks=%d, page-intel related=%d"
          % (len(saved), ap["applied"]["tasks"], len(pi["related"])))
    return True


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    if cmd == "selftest":
        selftest()
    else:
        print("usage: clips.py [selftest]")
