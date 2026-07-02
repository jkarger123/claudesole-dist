#!/usr/bin/env python3
"""email_archive -- index + full-text search over a (large) Gmail Takeout mbox. Stdlib only (mailbox, email,
sqlite3). Backs the 'email-archive' EXTENSION: a searchable UI over an operator's exported old-work email.

One-time build -> a SQLite FTS5 index; queries are then instant with ranked, highlighted snippets. server.py
calls email_archive.init(ctx) once; the mb_* fns read the CONFIGURED paths (cc.config: email_archive_mbox,
email_archive_db). Node-local + portable; no pip deps. ASCII-safe.

CLI (also used by the extension's index-build routine):
  python3 email_archive.py index  <mbox> <db> [limit]
  python3 email_archive.py search <db> "<query>" [limit]
  python3 email_archive.py stats  <db>
"""
import sys, os, re, sqlite3, mailbox, time
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime, getaddresses

_CTX = {}
def init(ctx): _CTX.update(ctx)

def _cc(): return _CTX.get("CC", {}) or {}
def _mbox_path():
    return os.path.expanduser(_cc().get("email_archive_mbox") or "")
def _db_path():
    p = _cc().get("email_archive_db")
    if p: return os.path.expanduser(p)
    return os.path.join(_CTX.get("STATE_DIR", "."), "ext_stores", "email-archive.sqlite")

# ---- parsing helpers ----------------------------------------------------------------------------------------
def _dh(v):
    if not v: return ""
    try: return str(make_header(decode_header(v)))
    except Exception:
        try: return str(v)
        except Exception: return ""

def _addrs(v):
    v = _dh(v)
    try:
        out = [(name + " " + addr).strip() for name, addr in getaddresses([v])]
        return ", ".join(x for x in out if x) or v
    except Exception:
        return v

def _body_text(msg):
    parts = []
    for p in (msg.walk() if msg.is_multipart() else [msg]):
        if p.get_content_type() != "text/plain": continue
        if "attachment" in str(p.get("Content-Disposition", "")).lower(): continue
        try:
            pay = p.get_payload(decode=True)
            if pay: parts.append(pay.decode(p.get_content_charset() or "utf-8", "replace"))
        except Exception: pass
    text = "\n".join(parts).strip()
    if not text:
        for p in (msg.walk() if msg.is_multipart() else [msg]):
            if p.get_content_type() == "text/html":
                try:
                    h = (p.get_payload(decode=True) or b"").decode(p.get_content_charset() or "utf-8", "replace")
                    h = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", h)
                    text = re.sub(r"<[^>]+>", " ", h); text = re.sub(r"&nbsp;?", " ", text); text = re.sub(r"[ \t]+", " ", text); break
                except Exception: pass
    return text[:100000]

def _ts(datehdr):
    try:
        dt = parsedate_to_datetime(datehdr)
        return int(dt.timestamp()), dt.strftime("%a %b %d, %Y %-I:%M%p").replace("AM", "am").replace("PM", "pm")
    except Exception:
        return 0, (datehdr or "")[:40]

def _from_parts(v):
    """From header -> (display_name, lowercased email). For contact faceting + rollups."""
    v = _dh(v)
    try:
        addrs = getaddresses([v])
        if addrs:
            name, addr = addrs[0]
            return (name or "").strip(), (addr or "").strip().lower()
    except Exception:
        pass
    return "", v.strip().lower()

SCHEMA = ("CREATE VIRTUAL TABLE IF NOT EXISTS messages USING fts5("
          "subject, sender, recipients, labels, body, "
          "date_str UNINDEXED, date_ts UNINDEXED, msgid UNINDEXED, "
          "thread_id UNINDEXED, from_addr UNINDEXED, from_name UNINDEXED, tokenize='porter unicode61')")

# ---- index build --------------------------------------------------------------------------------------------
def build_index(mbox_path=None, db_path=None, limit=None, log=print):
    mbox_path = mbox_path or _mbox_path(); db_path = db_path or _db_path()
    if not mbox_path or not os.path.isfile(mbox_path):
        log("[email_archive] no mbox at %r" % mbox_path); return 0
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    tmp = db_path + ".building"
    if os.path.exists(tmp): os.remove(tmp)
    con = sqlite3.connect(tmp); cur = con.cursor()
    cur.execute("PRAGMA journal_mode=WAL"); cur.execute("PRAGMA synchronous=NORMAL"); cur.execute(SCHEMA)
    mb = mailbox.mbox(mbox_path); t0 = time.time(); n = 0; batch = []
    ins = ("INSERT INTO messages(subject,sender,recipients,labels,body,date_str,date_ts,msgid,"
           "thread_id,from_addr,from_name) VALUES(?,?,?,?,?,?,?,?,?,?,?)")
    for key in mb.keys():
        try: msg = mb.get_message(key)
        except Exception: continue
        ts, dstr = _ts(msg.get("Date", ""))
        fname, faddr = _from_parts(msg.get("From", ""))
        batch.append((_dh(msg.get("Subject", "")), _addrs(msg.get("From", "")),
                      (_addrs(msg.get("To", "")) + " " + _addrs(msg.get("Cc", ""))).strip(),
                      _dh(msg.get("X-Gmail-Labels", "")), _body_text(msg), dstr, ts, (msg.get("Message-ID", "") or "")[:200],
                      (msg.get("X-GM-THRID", "") or "").strip(), faddr, fname))
        n += 1
        if len(batch) >= 500:
            cur.executemany(ins, batch); con.commit(); batch = []; log("  indexed %d (%.0fs)" % (n, time.time() - t0))
        if limit and n >= int(limit): break
    if batch: cur.executemany(ins, batch); con.commit()
    cur.execute("INSERT INTO messages(messages) VALUES('optimize')"); con.commit(); con.close()
    os.replace(tmp, db_path)                       # atomic swap so queries never see a half-built index
    log("[email_archive] indexed %d messages in %.0fs -> %s" % (n, time.time() - t0, db_path))
    return n

# ---- query (server-facing) ----------------------------------------------------------------------------------
def _conn():
    db = _db_path()
    if not os.path.isfile(db): return None
    con = sqlite3.connect(db); con.row_factory = sqlite3.Row; return con

def mb_stats():
    con = _conn()
    if not con: return {"ok": False, "ready": False, "error": "index not built yet"}
    try:
        cur = con.cursor()
        n = cur.execute("SELECT count(*) FROM messages").fetchone()[0]
        lo = cur.execute("SELECT min(date_ts) FROM messages WHERE date_ts>0").fetchone()[0]
        hi = cur.execute("SELECT max(date_ts) FROM messages WHERE date_ts>0").fetchone()[0]
        try: threads = cur.execute("SELECT count(DISTINCT thread_id) FROM messages WHERE thread_id<>''").fetchone()[0]
        except Exception: threads = 0
        try: contacts = cur.execute("SELECT count(DISTINCT from_addr) FROM messages WHERE from_addr<>''").fetchone()[0]
        except Exception: contacts = 0
        return {"ok": True, "ready": True, "count": n, "threads": threads, "contacts": contacts,
                "oldest_ts": lo, "newest_ts": hi, "mbox": os.path.basename(_mbox_path() or "")}
    finally: con.close()

_STOP = set(("the a an and or of to in on for with at by from is are was were be do did what when who "
             "how why where which that this it me my we our i you your they their about did any all "
             "email emails mail find show tell give get list did last first").split())
def _kw_from_question(q):
    ws = re.findall(r"[A-Za-z0-9][A-Za-z0-9'@.\-]{1,}", (q or "").lower())
    kw = [w for w in ws if w not in _STOP and len(w) > 2]
    return " ".join(kw[:8]) or (q or "").strip()

_COLS = ("rowid, subject, sender, from_addr, from_name, recipients, date_str, date_ts, thread_id, labels")
def _apply_facets(sel, params, contact, since, until, label, thread):
    if contact:
        sel += " AND (from_addr LIKE ? OR recipients LIKE ? OR sender LIKE ?)"; c = "%" + contact.lower() + "%"; params += [c, c, c]
    if since: sel += " AND date_ts >= ?"; params.append(int(since))
    if until: sel += " AND date_ts <= ?"; params.append(int(until))
    if label:  sel += " AND labels LIKE ?"; params.append("%" + label + "%")
    if thread: sel += " AND thread_id = ?"; params.append(str(thread))
    return sel

def mb_search(query, limit=50, contact=None, since=None, until=None, label=None, thread=None):
    """Faceted full-text search. `query` = FTS5 text (optional); facets (contact/since/until/label/thread) narrow
    the result deterministically. With no query, browse by facet ordered newest-first."""
    con = _conn()
    if not con: return {"ok": False, "ready": False, "results": [], "error": "index not built yet"}
    q = (query or "").strip()
    try:
        params = []
        if q:
            sel = ("SELECT " + _COLS + ", snippet(messages,4,'CCHLA','CCHLB',' ... ',16) AS snip "
                   "FROM messages WHERE messages MATCH ?"); params.append(q)
        else:
            sel = "SELECT " + _COLS + ", '' AS snip FROM messages WHERE 1=1"
        sel = _apply_facets(sel, params, contact, since, until, label, thread)
        sel += " ORDER BY " + ("rank" if q else "date_ts DESC") + " LIMIT ?"; params.append(min(int(limit), 200))
        try: rows = con.execute(sel, params).fetchall()
        except sqlite3.OperationalError:
            if not q: raise
            params[0] = '"' + q.replace('"', "") + '"'; rows = con.execute(sel, params).fetchall()   # phrase-fallback for punctuation
        return {"ok": True, "ready": True, "q": q, "results": [dict(r) for r in rows]}
    except Exception as e:
        return {"ok": False, "ready": True, "results": [], "error": str(e)[:140]}
    finally: con.close()

def mb_get(rowid):
    con = _conn()
    if not con: return {"ok": False, "error": "index not built yet"}
    try:
        r = con.execute("SELECT subject,sender,recipients,labels,body,date_str,date_ts,thread_id,from_addr FROM messages WHERE rowid=?",
                        (int(rowid),)).fetchone()
        return {"ok": True, "message": dict(r)} if r else {"ok": False, "error": "not found"}
    finally: con.close()

def mb_thread(thread_id, limit=100):
    """All messages in one Gmail conversation (thread), oldest-first, with a short body preview each."""
    con = _conn()
    if not con: return {"ok": False, "error": "index not built yet"}
    try:
        rows = con.execute("SELECT rowid, subject, sender, from_name, date_str, date_ts, substr(body,1,600) AS preview "
                           "FROM messages WHERE thread_id=? ORDER BY date_ts ASC LIMIT ?",
                           (str(thread_id), int(limit))).fetchall()
        if not rows: return {"ok": False, "error": "thread not found"}
        return {"ok": True, "thread_id": str(thread_id), "messages": [dict(r) for r in rows]}
    finally: con.close()

def mb_contacts(limit=40, query=None):
    """Top correspondents by message count -- for the facet sidebar / 'who do I email most'."""
    con = _conn()
    if not con: return {"ok": False, "ready": False, "contacts": []}
    try:
        rows = con.execute("SELECT from_addr AS addr, max(from_name) AS name, count(*) AS n, max(date_ts) AS last "
                           "FROM messages WHERE from_addr<>'' GROUP BY from_addr ORDER BY n DESC LIMIT ?",
                           (int(limit),)).fetchall()
        return {"ok": True, "ready": True, "contacts": [dict(r) for r in rows]}
    finally: con.close()

def mb_facets(query=None, contact=None, since=None, until=None, label=None):
    """For the CURRENT search, the top contacts / years / labels among the matches -- so the UI can offer
    'narrow by' without any AI. Bounded, deterministic, cheap."""
    con = _conn()
    if not con: return {"ok": False, "contacts": [], "years": [], "labels": []}
    q = (query or "").strip()
    def _grp(expr, extra=""):
        params = []
        base = ("FROM messages WHERE messages MATCH ?" if q else "FROM messages WHERE 1=1")
        if q: params.append(q)
        base = _apply_facets(base, params, contact, since, until, label, None)
        sql = "SELECT %s AS k, count(*) AS n %s AND %s GROUP BY k ORDER BY n DESC LIMIT 12" % (expr, base, extra or "k IS NOT NULL")
        try: return [dict(r) for r in con.execute(sql, params).fetchall() if r["k"] not in (None, "")]
        except sqlite3.OperationalError:
            if q: params[0] = '"' + q.replace('"', "") + '"'
            try: return [dict(r) for r in con.execute(sql, params).fetchall() if r["k"] not in (None, "")]
            except Exception: return []
        except Exception: return []
    try:
        contacts = _grp("from_addr", "from_addr<>''")
        years = _grp("strftime('%Y', date_ts, 'unixepoch')", "date_ts>0")
        return {"ok": True, "contacts": contacts, "years": years}
    finally: con.close()

# ---- the AI "ask" loop (token-bounded): plan -> retrieve (free) -> synthesize over a tiny slice -------------
def _date_to_ts(s):
    if not s: return None
    try:
        import datetime as _dt
        return int(_dt.datetime.strptime(str(s)[:10], "%Y-%m-%d").timestamp())
    except Exception:
        return None

def _parse_plan(raw):
    if not raw: return {}
    try:
        m = re.search(r"\{.*\}", raw, re.S)
        return json.loads(m.group(0)) if m else {}
    except Exception:
        return {}

def _ask_plan_prompt(question, today):
    return ("You convert an email-search question into a compact JSON query for a full-text email archive. "
            "Today is %s. Output ONLY minified JSON with keys: keywords (space-separated search terms, no "
            "operators), contact (an email/name to filter by, or null), since (YYYY-MM-DD or null), until "
            "(YYYY-MM-DD or null). Keep keywords few and specific.\nQuestion: %s\nJSON:" % (today or "unknown", question))

def _synth_prompt(question, ctx):
    return ("Answer the question using ONLY the emails below. Cite the emails you use as [#n]. Be concise and "
            "factual; if the emails don't answer it, say so plainly. Do not invent details.\n\nEMAILS:\n%s\n\n"
            "QUESTION: %s\nAnswer (with [#n] citations):" % (ctx, question))

def _format_ctx(rows, maxchars=550):
    con = _conn(); bodies = {}
    if con:
        try:
            ids = [int(r["rowid"]) for r in rows]
            qmarks = ",".join("?" * len(ids))
            for rr in con.execute("SELECT rowid, substr(body,1,%d) AS b FROM messages WHERE rowid IN (%s)" % (maxchars, qmarks), ids):
                bodies[rr["rowid"]] = rr["b"]
        except Exception: pass
        finally: con.close()
    out = []
    for i, r in enumerate(rows, 1):
        body = (bodies.get(r["rowid"]) or r.get("snip") or "").replace("CCHLA", "").replace("CCHLB", "").strip()
        out.append("[#%d] (id=%s) %s | From %s | Subject: %s\n%s" %
                   (i, r["rowid"], r.get("date_str", ""), (r.get("sender") or "")[:50],
                    (r.get("subject") or "")[:90], re.sub(r"\s+", " ", body)[:maxchars]))
    return "\n\n".join(out)

def mb_ask(question, ask_llm=None, today=None, k=12):
    """Bounded 'ask your email': (1) an optional cheap LLM plans the query, (2) DETERMINISTIC faceted retrieval
    does the heavy lifting for free, (3) an optional cheap LLM synthesizes an answer over only the top-k snippets
    -- never the corpus. ask_llm(prompt)->text is injected (server: Haiku on the subscription; CLI: `claude -p`).
    With ask_llm=None it degrades to pure retrieval (no tokens spent)."""
    question = (question or "").strip()
    if not question: return {"ok": False, "error": "no question"}
    if not os.path.isfile(_db_path()): return {"ok": False, "ready": False, "error": "index not built yet"}
    plan = {}
    if ask_llm:
        try: plan = _parse_plan(ask_llm(_ask_plan_prompt(question, today)))
        except Exception: plan = {}
    kw = (plan.get("keywords") or "").strip() or _kw_from_question(question)
    since, until = _date_to_ts(plan.get("since")), _date_to_ts(plan.get("until"))
    contact = (plan.get("contact") or None)
    # OR the terms so recall stays high (FTS ranks by relevance -> docs matching more terms float up); a single
    # noisy keyword can't zero the result the way an implicit AND does.
    fts = " OR ".join(w for w in kw.split() if w) or kw
    res = mb_search(fts, limit=max(k * 3, 30), contact=contact, since=since, until=until)
    hits = res.get("results", [])
    if not hits and (contact or since or until):                      # relax facets if they zeroed it out
        res = mb_search(fts, limit=max(k * 3, 30)); hits = res.get("results", [])
    if not hits:                                                      # last resort: the question's own keywords, OR'd
        alt = " OR ".join(w for w in _kw_from_question(question).split() if w)
        res = mb_search(alt, limit=max(k * 3, 30)); hits = res.get("results", [])
    top = hits[:k]
    answer = None; est = 0
    if ask_llm and top:
        ctx = _format_ctx(top)
        est = (len(ctx) + 200) // 4                                   # rough token estimate (in), for the UI
        try: answer = ask_llm(_synth_prompt(question, ctx))
        except Exception: answer = None
    return {"ok": True, "ready": True, "question": question, "plan": {"keywords": kw, "contact": contact,
            "since": plan.get("since"), "until": plan.get("until")}, "answer": answer,
            "sources": top, "n_considered": len(hits), "tokens_in_est": est, "synthesized": bool(answer)}

# ---- CLI ----------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "index":
        build_index(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    elif cmd == "search":
        _CTX["CC"] = {"email_archive_db": sys.argv[2]}
        for r in mb_search(sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else 20).get("results", []):
            print("[%d] %s | %s | %s" % (r["rowid"], (r["subject"] or "(no subj)")[:60], r["sender"][:36], r["date_str"]))
    elif cmd == "stats":
        _CTX["CC"] = {"email_archive_db": sys.argv[2]}; print(mb_stats())
    else:
        print(__doc__)
