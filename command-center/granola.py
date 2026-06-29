#!/usr/bin/env python3
"""Granola -> agency tree. Transcribe agency calls (via Granola), turn each into a REVIEWED set of updates:
a dated note appended to the matched client's CLAUDE.md, plus tasks + reminders. Read-only ingest from
Granola (official REST API, or the local cache as a no-key fallback); LLM extraction runs in a headless
`claude -p` (no metered key); EVERYTHING lands as PROPOSALS in a review queue -- nothing touches a client
file or creates a task/reminder until the operator approves it in the Calls lens.

Stdlib only. server.py calls granola.init(ctx) once, then the gr_* functions behind /api/granola-*.
Config (cc.config "granola"): {
  "source": "api" | "cache",                 # default: api if api_key set, else cache
  "api_key": "grn_...",                        # Granola Settings -> Connectors -> API keys
  "cache_path": "~/Library/Application Support/Granola/cache-v3.json",
  "client_map": {"acme": ["acme.com", "Acme Corp"], ...},   # client folder -> attendee domains/aliases
  "destinations": ["cc"],                      # any of: cc, google, apple, slack  (cc = built-in)
  "slack_webhook": "https://hooks.slack.com/...",
  "apply_mode": "review"                       # review (default) | hybrid (auto-note, review tasks) | auto
}
"""
import json, os, re, subprocess, time, glob, urllib.request, urllib.error

_CTX = {}  # injected by server.py: CC, PROJECT, STATE_DIR, sh, agency_dirs, pretty_name, mesh_log(optional)


def init(ctx):
    _CTX.update(ctx)


def _cfg():
    return (_CTX.get("CC", {}) or {}).get("granola") or {}


def _api_key():
    """Resolve the Granola API key VAULT-FIRST (the platform standard: every credential lives in the per-install
    encrypted vault, scope/per-node aware), falling back to the legacy cc.config granola.api_key for nodes that
    haven't migrated. So a key added via the Vault lens / secure-field 'just works' -- no cc.config hand-edit."""
    sec = _CTX.get("secret")
    if callable(sec):
        try:
            k = sec("GRANOLA_API_KEY")
            if k: return k
        except Exception:
            pass
    return _cfg().get("api_key") or ""


def _state_path():
    return os.path.join(_CTX.get("STATE_DIR", "."), "_granola.json")


def _load_state():
    try:
        with open(_state_path()) as f: return json.load(f)
    except Exception:
        return {"proposals": [], "seen": [], "last_sync": 0}


def _save_state(s):
    with open(_state_path(), "w") as f: json.dump(s, f, indent=2)


# ---- ingest: meetings + transcripts (official API, or local cache) -------------------------------------
def _source():
    c = _cfg()
    return c.get("source") or ("api" if _api_key() else "cache")


def _api_get(path):
    key = _api_key()
    if not key:
        raise RuntimeError("no Granola API key set (cc.config granola.api_key). Create one in Granola -> "
                           "Settings -> Connectors -> API keys (needs a Business plan; the workspace must have "
                           "end-to-end encryption OFF for the public API to read notes), then add it.")
    req = urllib.request.Request("https://public-api.granola.ai/v1" + path,
                                 headers={"Authorization": "Bearer " + key, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError("Granola rejected the API key (HTTP %d). Either the key is wrong, OR your Granola "
                               "workspace has END-TO-END ENCRYPTION enabled -- which blocks the public API from "
                               "reading notes. Fix: in Granola workspace settings turn E2E encryption OFF (and "
                               "confirm your plan allows API keys), then recreate the key." % e.code)
        raise RuntimeError("Granola API HTTP %d on %s" % (e.code, path))


def _cache_file():
    p = _cfg().get("cache_path") or "~/Library/Application Support/Granola/cache-v3.json"
    return os.path.expanduser(p)


def _load_cache():
    """Granola's local cache is double-JSON-encoded: a JSON file whose top value is a JSON STRING."""
    raw = open(_cache_file()).read()
    data = json.loads(raw)
    if isinstance(data, str):
        data = json.loads(data)
    return data


def list_meetings(limit=25):
    """Return [{id, title, date, attendees:[{name,email}], summary}] newest-first, from API or cache."""
    if _source() == "api":
        try:
            d = _api_get("/notes")
            notes = d.get("notes") or d.get("data") or (d if isinstance(d, list) else [])
            out = []
            for n in notes[:limit]:
                out.append({"id": n.get("id"), "title": n.get("title") or "(untitled)",
                            "date": n.get("created_at") or n.get("date") or "",
                            "attendees": n.get("attendees") or ([n["owner"]] if n.get("owner") else []),
                            "summary": n.get("summary") or ""})
            return out
        except Exception as e:
            return [{"error": "granola api: " + str(e)[:160]}]
    # cache fallback
    try:
        c = _load_cache()
        docs = (c.get("state", {}) or {}).get("documents") or c.get("documents") or {}
        items = list(docs.values()) if isinstance(docs, dict) else list(docs)
        items.sort(key=lambda x: x.get("created_at") or x.get("updated_at") or "", reverse=True)
        out = []
        for n in items[:limit]:
            people = n.get("people") or n.get("attendees") or []
            out.append({"id": n.get("id") or n.get("document_id"), "title": n.get("title") or "(untitled)",
                        "date": n.get("created_at") or "", "attendees": people, "summary": n.get("summary") or ""})
        return out
    except Exception as e:
        return [{"error": "granola cache: " + str(e)[:160]}]


def _detail_attendees(d):
    """[{name,email}] from a note-DETAIL dict: attendees[].email + calendar_event.invitees[].email. The sparse
    /notes LIST endpoint omits these, so client-matching can't fire on the API source without them."""
    out = []
    for a in (d.get("attendees") or []):
        if isinstance(a, dict) and (a.get("email") or a.get("name")):
            out.append({"name": a.get("name") or "", "email": a.get("email") or ""})
    ce = d.get("calendar_event") or {}
    for inv in (ce.get("invitees") or []):
        if isinstance(inv, dict) and (inv.get("email") or inv.get("name")):
            out.append({"name": inv.get("name") or "", "email": inv.get("email") or ""})
    return out


def get_detail(meeting_id):
    """Return (transcript_str, attendees). The API DETAIL endpoint (/notes/{id}?include=transcript) carries BOTH
    the transcript AND attendees/invitees, while the LIST endpoint omits attendees -- so fetching detail once
    gives the emails client-matching needs (no extra request: the transcript already required this call)."""
    if _source() == "api":
        d = _api_get("/notes/" + meeting_id + "?include=transcript")
        segs = d.get("transcript") or (d.get("note") or {}).get("transcript") or []
        return _fmt_segments(segs), _detail_attendees(d)
    c = _load_cache()
    tx = (c.get("state", {}) or {}).get("transcripts") or c.get("transcripts") or {}
    segs = tx.get(meeting_id) or []
    return _fmt_segments(segs), []   # cache: attendees already populated by list_meetings()


def get_transcript(meeting_id):
    """Transcript as 'Speaker: text' lines (back-compat wrapper; also used by the drag-to-session sendable)."""
    return get_detail(meeting_id)[0]


def _fmt_segments(segs):
    lines = []
    for s in segs or []:
        sp = s.get("speaker") or {}
        who = sp.get("diarization_label") or sp.get("source") or sp.get("name") or "?"
        t = (s.get("text") or "").strip()
        if t: lines.append("%s: %s" % (who, t))
    return "\n".join(lines)


# ---- match a meeting to a client folder ----------------------------------------------------------------
def _client_dirs():
    """[(client_name, abs_path)] across Clients/ and Partners/*/clients/."""
    PROJECT = _CTX.get("PROJECT", ".")
    ad = _CTX.get("agency_dirs", lambda: {"clients": "Clients", "partners": "Partners"})()
    subf = _CTX.get("agency_subfolders")
    out = []
    cl = os.path.join(PROJECT, ad.get("clients", "Clients"))
    for nm, p in (subf(cl) if subf else []):
        out.append((nm, p))
    pr = os.path.join(PROJECT, ad.get("partners", "Partners"))
    for pnm, pp in (subf(pr) if subf else []):
        cd = os.path.join(pp, "clients")
        for nm, p in (subf(cd) if subf and os.path.isdir(cd) else []):
            out.append((nm, p))
    return out


# free-mail providers don't identify a client -- never match a client folder by these domains
_FREE_MAIL = {"gmail.com", "googlemail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com",
              "me.com", "mac.com", "aol.com", "proton.me", "protonmail.com", "live.com", "msn.com"}
_TLDISH = {"com", "net", "org", "io", "co", "ai", "app", "dev", "www", "us", "uk", "gov", "edu", "biz"}


def _meeting_domains(meeting):
    """Lower-cased attendee/invitee email domains, minus free-mail providers (they don't identify a client)."""
    doms = set()
    for a in meeting.get("attendees", []) or []:
        if not isinstance(a, dict): continue
        em = (a.get("email") or "").strip().lower()
        if "@" in em:
            dom = em.rsplit("@", 1)[1].strip()
            if dom and dom not in _FREE_MAIL:
                doms.add(dom)
    return doms


def _word_in(alias, text):
    """True if `alias` is a whole word/phrase in `text` (case-insensitive, alnum boundaries) -- so 'omm' does
    NOT match inside 'communications' and 'aldo' not inside 'ronaldo'."""
    a = (alias or "").strip().lower()
    if not a: return False
    return re.search(r"(?<![a-z0-9])" + re.escape(a) + r"(?![a-z0-9])", (text or "").lower()) is not None


def _alias_matches(alias, title, domains):
    """Precise alias match (never an unanchored substring):
    - a DOMAIN-shaped alias (has a dot, no space) matches the attendee email domains STRUCTURALLY (equal or
      subdomain, e.g. 'acme.com' matches 'mail.acme.com');
    - a bare NAME/brand alias matches the TITLE by word boundary, OR an exact email-domain LABEL (so 'acme'
      matches '@acme.com' but 'omm' does NOT match 'vlivcommunications.com')."""
    a = (alias or "").strip().lower().lstrip("@")
    if not a: return False
    if "." in a and " " not in a:
        return any(d == a or d.endswith("." + a) for d in domains)
    if _word_in(a, title):
        return True
    labels = {lab for d in domains for lab in d.split(".") if lab and lab not in _TLDISH}
    return a in labels


def match_client(meeting):
    """Best client folder for a meeting. PRECISE matching -- no unanchored substrings (which caused false
    positives like alias 'OMM' inside 'vlivcommunications.com' or 'aldo' inside 'ronaldo'):
      1) cc.config client_map: a DOMAIN alias matches attendee email domains structurally; a NAME alias
         matches the TITLE by word boundary or an exact email-domain label.
      2) fallback: the de-slugged client folder name as a whole word in the title.
    Returns (client_name, abs_path) or (None, None)."""
    cmap = _cfg().get("client_map") or {}
    dirs = _client_dirs()
    by_slug = {nm.lower(): (nm, p) for nm, p in dirs}
    title = meeting.get("title", "") or ""
    domains = _meeting_domains(meeting)
    for slug, aliases in cmap.items():
        if slug.lower() not in by_slug: continue
        for a in ([slug] + list(aliases or [])):
            if _alias_matches(a, title, domains):
                return by_slug[slug.lower()]
    for nm, p in dirs:                          # fuzzy fallback: folder name as a whole word in the title
        words = re.sub(r"[-_]+", " ", nm).strip()
        if words and _word_in(words, title):
            return (nm, p)
    return (None, None)


# ---- LLM extraction via a headless claude -p -----------------------------------------------------------
EXTRACT_PROMPT = (
    "You are an agency operations assistant. From the MEETING TRANSCRIPT below, extract ONLY what is "
    "clearly supported by the transcript -- do not invent. Return STRICT JSON (no prose, no code fence) "
    "with this exact shape:\n"
    '{"summary":"<=2 sentences","notes":["client-facing fact to remember", ...],'
    '"tasks":[{"title":"action item","owner":"who or \\"\\"","due":"YYYY-MM-DD or \\"\\""}],'
    '"reminders":[{"text":"follow-up","when":"YYYY-MM-DD or relative like \\"next Mon\\""}],'
    '"decisions":["decision made", ...]}\n'
    "Keep each list tight (omit if nothing concrete). MEETING: %s\nTRANSCRIPT:\n%s\n")


def _claude_extract(title, transcript):
    """Run extraction in a headless claude (Max subscription, no metered key). Returns the parsed dict."""
    inj = _CTX.get("extractor")          # tests inject a fake extractor
    if inj: return inj(title, transcript)
    prompt = EXTRACT_PROMPT % (title, transcript[:24000])
    try:
        r = subprocess.run(["claude", "--dangerously-skip-permissions", "-p", prompt],
                           capture_output=True, text=True, timeout=180,
                           env={**os.environ, "PATH": os.environ.get("PATH", "") + ":" + os.path.expanduser("~/.local/bin") + ":/opt/homebrew/bin"})
        out = (r.stdout or "").strip()
        m = re.search(r"\{.*\}", out, re.S)
        return json.loads(m.group(0)) if m else {}
    except Exception as e:
        return {"error": str(e)[:160]}


# ---- sync: ingest new meetings -> proposals ------------------------------------------------------------
def gr_sync(limit=15):
    """Pull recent meetings, skip already-seen, match + extract each, store as PENDING proposals.
    - Client-matching runs AFTER fetching each note's DETAIL, so attendee emails are available (the LIST
      endpoint omits them) and cc.config client_map domains match out of the box.
    - State persists INCREMENTALLY (per proposal) + exposes sync_progress, so a long multi-call run shows
      progress instead of looking hung.
    - last_sync_status/last_sync_error are recorded into state on EVERY return path, so a caller that discards
      our return value (the daemon-thread /api/granola-sync) still surfaces auth/E2E failures."""
    cfg = _cfg()
    st = _load_state()

    def _finish(res):
        st["last_sync_status"] = "ok" if res.get("ok") else "error"
        st["last_sync_error"] = "" if res.get("ok") else (res.get("error") or "")
        if isinstance(st.get("sync_progress"), dict): st["sync_progress"]["running"] = False
        try: _save_state(st)
        except Exception: pass
        return res

    if not cfg:
        return _finish({"ok": False, "error": "granola not configured (cc.config 'granola')"})
    seen = set(st.get("seen", []))
    meetings = list_meetings(limit)
    if meetings and meetings[0].get("error"):
        return _finish({"ok": False, "error": meetings[0]["error"]})
    pending_ids = [m.get("id") for m in meetings if m.get("id") and m.get("id") not in seen]
    st["sync_progress"] = {"processed": 0, "total": len(pending_ids), "running": True, "started": int(time.time())}
    _save_state(st)
    added = 0
    for m in meetings:
        mid = m.get("id")
        if not mid or mid in seen: continue
        # DETAIL first: gives transcript AND attendees -> match_client can use attendee email domains
        tx = ""
        try:
            tx, det_att = get_detail(mid)
            if det_att: m["attendees"] = (m.get("attendees") or []) + det_att
        except Exception:
            tx = ""
        client, cpath = match_client(m)
        ext = _claude_extract(m.get("title", ""), tx) if tx else {}
        prop = {"id": "g-%d-%d" % (int(time.time() * 1000), added), "meeting_id": mid,
                "title": m.get("title", ""), "date": m.get("date", ""), "ts": int(time.time()),
                "client": client, "client_path": (os.path.relpath(cpath, _CTX.get("PROJECT", ".")) if cpath else None),
                "matched": bool(client), "summary": ext.get("summary", ""), "notes": ext.get("notes", []),
                "tasks": ext.get("tasks", []), "reminders": ext.get("reminders", []),
                "decisions": ext.get("decisions", []), "status": "pending", "error": ext.get("error")}
        st["proposals"].insert(0, prop)
        seen.add(mid); added += 1
        st["seen"] = list(seen)[-500:]
        st["last_sync"] = int(time.time())
        if isinstance(st.get("sync_progress"), dict): st["sync_progress"]["processed"] = added
        _save_state(st)            # incremental: each proposal persists immediately
    return _finish({"ok": True, "added": added,
                    "pending": len([p for p in st["proposals"] if p["status"] == "pending"])})


def _gr_ready():
    """(ready, hint) -- is Granola actually able to ingest? Distinguishes 'enabled' from 'has a usable source'."""
    c = _cfg()
    if not c: return (False, "Granola isn't enabled on this node (cc.config 'granola').")
    src = _source()
    if src == "api" and not _api_key():
        return (False, "Add your Granola API key (granola.api_key). Create it in Granola -> Settings -> "
                       "Connectors -> API keys (Business plan; workspace end-to-end encryption must be OFF "
                       "for the public API to read notes).")
    if src == "cache" and not os.path.isfile(_cache_file()):
        return (False, "No Granola desktop cache on this machine (%s). Install/run Granola here, or set "
                       "source='api' with an API key." % _cache_file())
    return (True, "")


def gr_proposals():
    st = _load_state()
    ready, hint = _gr_ready()
    return {"ok": True, "proposals": st.get("proposals", [])[:80], "last_sync": st.get("last_sync", 0),
            "configured": bool(_cfg()), "ready": ready, "hint": hint, "source": _source(),
            "has_key": bool(_api_key()),
            "last_sync_status": st.get("last_sync_status", ""), "last_sync_error": st.get("last_sync_error", ""),
            "sync_progress": st.get("sync_progress"),
            "clients": [nm for nm, _ in _client_dirs()], "destinations": _cfg().get("destinations") or ["cc"]}


# ---- apply an approved proposal (review-first) ---------------------------------------------------------
def gr_apply(pid, edited=None):
    """Approve + apply a proposal. `edited` may override the proposal fields (operator edits) and may set
    `client` (manual assignment) + `pick` (which items to apply)."""
    st = _load_state()
    prop = next((p for p in st["proposals"] if p["id"] == pid), None)
    if not prop: return {"ok": False, "error": "no such proposal"}
    p = {**prop, **(edited or {})}
    PROJECT = _CTX.get("PROJECT", ".")
    # resolve client path (allow manual assignment by name)
    cpath = None
    if p.get("client"):
        for nm, ap in _client_dirs():
            if nm == p["client"] or nm.lower() == str(p["client"]).lower():
                cpath = ap; break
    if not cpath:
        return {"ok": False, "error": "no client matched -- set 'client' to one of the listed clients"}
    applied = {"note": False, "tasks": 0, "reminders": 0, "dest": []}
    # 1) append a dated call note to the client's CLAUDE.md (managed CC:CALLS region)
    if p.get("summary") or p.get("notes") or p.get("decisions"):
        _append_call_note(cpath, p)
        applied["note"] = True
    # 2) tasks + reminders -> configured destinations
    dests = _cfg().get("destinations") or ["cc"]
    tasks = p.get("tasks", []); rem = p.get("reminders", [])
    for dn in dests:
        fn = {"cc": _dest_cc, "google": _dest_google, "apple": _dest_apple, "slack": _dest_slack}.get(dn)
        if fn:
            try: fn(p["client"], cpath, tasks, rem, p); applied["dest"].append(dn)
            except Exception as e: applied.setdefault("errors", []).append("%s: %s" % (dn, str(e)[:120]))
    applied["tasks"] = len(tasks); applied["reminders"] = len(rem)
    prop["status"] = "applied"; prop["applied"] = applied; prop["applied_ts"] = int(time.time())
    if edited: prop["edited"] = {k: edited[k] for k in edited if k in ("summary", "notes", "tasks", "reminders", "client")}
    _save_state(st)
    return {"ok": True, "applied": applied}


def gr_skip(pid):
    st = _load_state()
    prop = next((p for p in st["proposals"] if p["id"] == pid), None)
    if prop: prop["status"] = "skipped"; _save_state(st)
    return {"ok": bool(prop)}


CALLS_B, CALLS_E = "<!-- CC:CALLS log (Granola; newest first) -->", "<!-- /CC:CALLS -->"


def _append_call_note(cpath, p):
    """Append a dated call entry to the client's CLAUDE.md inside a managed CC:CALLS region."""
    cm = os.path.join(cpath, "CLAUDE.md")
    entry = ["", "### %s -- %s" % ((p.get("date") or time.strftime("%Y-%m-%d")), p.get("title") or "call")]
    if p.get("summary"): entry.append(p["summary"])
    for n in p.get("notes", []): entry.append("- " + str(n))
    for dme in p.get("decisions", []): entry.append("- DECISION: " + str(dme))
    block = "\n".join(entry)
    try:
        cur = open(cm).read() if os.path.isfile(cm) else "# %s\n" % os.path.basename(cpath)
    except Exception:
        cur = "# %s\n" % os.path.basename(cpath)
    m = re.search(re.escape(CALLS_B) + r"(.*?)" + re.escape(CALLS_E), cur, re.S)
    if m:
        new = cur[:m.start(1)] + (m.group(1).rstrip() + "\n" + block + "\n") + cur[m.end(1):]
    else:
        new = cur.rstrip() + "\n\n## Call log\n" + CALLS_B + "\n" + block + "\n" + CALLS_E + "\n"
    with open(cm, "w") as f: f.write(new)


# ---- destination adapters ------------------------------------------------------------------------------
def _dest_cc(client, cpath, tasks, reminders, p):
    """Built-in: a per-client TODO.md (checkbox list) -- shows in the client's Files panel + Calls lens."""
    todo = os.path.join(cpath, "TODO.md")
    lines = []
    try:
        if os.path.isfile(todo): lines = open(todo).read().splitlines()
    except Exception:
        lines = []
    if not lines: lines = ["# %s -- TODO" % client, ""]
    for t in tasks:
        due = (" (due %s)" % t["due"]) if t.get("due") else ""
        own = (" [@%s]" % t["owner"]) if t.get("owner") else ""
        lines.append("- [ ] %s%s%s  _(from %s)_" % (t.get("title", "task"), own, due, p.get("title", "call")))
    for r in reminders:
        when = (" (%s)" % r["when"]) if r.get("when") else ""
        lines.append("- [ ] REMINDER: %s%s  _(from %s)_" % (r.get("text", ""), when, p.get("title", "call")))
    with open(todo, "w") as f: f.write("\n".join(lines) + "\n")


def _dest_slack(client, cpath, tasks, reminders, p):
    """Post a per-call action digest to a Slack incoming webhook (cc.config granola.slack_webhook)."""
    hook = _cfg().get("slack_webhook")
    if not hook: raise RuntimeError("no slack_webhook configured")
    parts = ["*%s* -- %s" % (client, p.get("title", "call"))]
    for t in tasks: parts.append("- [ ] %s%s" % (t.get("title", ""), (" (due %s)" % t["due"]) if t.get("due") else ""))
    for r in reminders: parts.append("- reminder: %s%s" % (r.get("text", ""), (" (%s)" % r["when"]) if r.get("when") else ""))
    data = json.dumps({"text": "\n".join(parts)}).encode()
    urllib.request.urlopen(urllib.request.Request(hook, data=data, headers={"Content-Type": "application/json"}), timeout=15).read()


def _dest_google(client, cpath, tasks, reminders, p):
    """Google Calendar/Tasks. The Google MCP tools are connected at the session layer, not here, so this
    adapter writes a pending request the operator's chief fulfills via the Google MCP. Kept simple +
    auditable; wired live once Sarah confirms the calendar/list."""
    out = os.path.join(_CTX.get("STATE_DIR", "."), "_granola_google_outbox.jsonl")
    rec = {"ts": int(time.time()), "client": client, "title": p.get("title"),
           "events": [{"summary": r.get("text"), "when": r.get("when")} for r in reminders],
           "tasks": [{"title": t.get("title"), "due": t.get("due")} for t in tasks]}
    with open(out, "a") as f: f.write(json.dumps(rec) + "\n")


def _dest_apple(client, cpath, tasks, reminders, p):
    """Apple Reminders via osascript (runs on Sarah's Mac). Each task/reminder -> a Reminders item."""
    items = [t.get("title", "") for t in tasks] + [("Reminder: " + r.get("text", "")) for r in reminders]
    for it in items:
        if not it: continue
        script = 'tell application "Reminders" to make new reminder with properties {name:"%s"}' % it.replace('"', "'")
        subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)
