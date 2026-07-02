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

SCHEMA = ("CREATE VIRTUAL TABLE IF NOT EXISTS messages USING fts5("
          "subject, sender, recipients, labels, body, "
          "date_str UNINDEXED, date_ts UNINDEXED, msgid UNINDEXED, tokenize='porter unicode61')")

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
    ins = "INSERT INTO messages(subject,sender,recipients,labels,body,date_str,date_ts,msgid) VALUES(?,?,?,?,?,?,?,?)"
    for key in mb.keys():
        try: msg = mb.get_message(key)
        except Exception: continue
        ts, dstr = _ts(msg.get("Date", ""))
        batch.append((_dh(msg.get("Subject", "")), _addrs(msg.get("From", "")),
                      (_addrs(msg.get("To", "")) + " " + _addrs(msg.get("Cc", ""))).strip(),
                      _dh(msg.get("X-Gmail-Labels", "")), _body_text(msg), dstr, ts, (msg.get("Message-ID", "") or "")[:200]))
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
        return {"ok": True, "ready": True, "count": n, "oldest_ts": lo, "newest_ts": hi,
                "mbox": os.path.basename(_mbox_path() or "")}
    finally: con.close()

def mb_search(query, limit=50):
    con = _conn()
    if not con: return {"ok": False, "ready": False, "results": [], "error": "index not built yet"}
    q = (query or "").strip()
    if not q: return {"ok": True, "ready": True, "results": []}
    sel = ("SELECT rowid, subject, sender, recipients, date_str, date_ts, "
           "snippet(messages, 4, 'CCHLA', 'CCHLB', ' ... ', 16) AS snip "     # ASCII markers -> <mark> on the client (no control chars, no collision)
           "FROM messages WHERE messages MATCH ? ORDER BY rank LIMIT ?")
    try:
        try: rows = con.execute(sel, (q, min(int(limit), 200))).fetchall()
        except sqlite3.OperationalError:
            rows = con.execute(sel, ('"' + q.replace('"', "") + '"', min(int(limit), 200))).fetchall()   # phrase-fallback for punctuation
        return {"ok": True, "ready": True, "q": q, "results": [dict(r) for r in rows]}
    except Exception as e:
        return {"ok": False, "ready": True, "results": [], "error": str(e)[:140]}
    finally: con.close()

def mb_get(rowid):
    con = _conn()
    if not con: return {"ok": False, "error": "index not built yet"}
    try:
        r = con.execute("SELECT subject,sender,recipients,labels,body,date_str FROM messages WHERE rowid=?",
                        (int(rowid),)).fetchone()
        return {"ok": True, "message": dict(r)} if r else {"ok": False, "error": "not found"}
    finally: con.close()

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
