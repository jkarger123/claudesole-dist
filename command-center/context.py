"""
ClaudeFather -- the CONTEXT LAYER (the substrate behind "perfect context, every time").

The thesis (see docs/VISION.md): completeness lives in a STORE; the working window an agent sees is a
small, curated SLICE assembled on demand (because of "context rot" -- more context makes models worse, not
better). This module is that store + the router that assembles slices.

Design constraints (hard): stdlib ONLY (sqlite3/json/time/re/math/hashlib/threading -- all stdlib), no pip
deps; config-driven (paths via init()/env, never hardcoded); secret-clean; portable; everything carries
PROVENANCE + a TRUST label (source + how-much-to-believe-it) so the router and the (future) capability plane
can reason about where context came from. Single-writer-on-one-Mac model -> SQLite WAL is plenty.

Two layers, one DB:
  - EVENTS   = the episodic timeline (what happened): email, calendar, call transcripts, sessions,
               deliverables, web, notes ... append-mostly, full fidelity, FTS-indexed.
  - ENTITIES + EDGES = the semantic graph (people / projects / clients / threads / files and how they relate).
The router (assemble) retrieves across both, ranks by relevance x recency x trust, dedups, budgets to a small
window, places the highest-signal items at the EDGES (lost-in-the-middle), and returns a CITED bundle.

Standalone-testable:  python3 context.py selftest   /   python3 context.py stats
"""
import os, json, time, re, math, hashlib, threading, sqlite3

# ---- config (resolved at init or from env; never hardcoded) -------------------------------------------
_CTX = {"PROJECT": "default"}
_DB_PATH = None
_CONN = None
_LOCK = threading.RLock()
_FTS = False   # whether FTS5 is available (graceful fallback to LIKE if not)

# Trust levels: how much the router/capability-plane should believe a source. Higher = more trusted.
TRUST = {"owner": 3, "internal": 2, "contact": 1, "external": 0}   # e.g. your own notes=owner; an inbound email=external

def _default_db_path():
    # Prefer the SSD data dir (data/ is symlinked to the SSD); fall back to alongside this file.
    env = os.environ.get("CF_CONTEXT_DB")
    if env: return env
    home = _CTX.get("CC_HOME") or os.environ.get("CC_HOME")
    base = _CTX.get("DATA_DIR") or (os.path.join(home, "data") if home else None) or os.path.dirname(os.path.abspath(__file__))
    d = os.path.join(base, "context")
    try: os.makedirs(d, exist_ok=True)
    except Exception: d = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(d, "context.db")

def init(ctx=None):
    """Called once by server.py (like granola.init). ctx may carry PROJECT, CC_HOME, DATA_DIR, db_path."""
    global _DB_PATH
    if ctx: _CTX.update({k: v for k, v in ctx.items() if v is not None})
    _DB_PATH = _CTX.get("db_path") or _default_db_path()
    _connect(); _migrate()
    return {"ok": True, "db": _DB_PATH, "fts": _FTS}

def _connect():
    global _CONN
    if _CONN is not None: return _CONN
    if _DB_PATH is None: init()
    _CONN = sqlite3.connect(_DB_PATH, check_same_thread=False)
    _CONN.row_factory = sqlite3.Row
    try: _CONN.execute("PRAGMA journal_mode=WAL"); _CONN.execute("PRAGMA synchronous=NORMAL")
    except Exception: pass
    return _CONN

def _migrate():
    global _FTS
    c = _connect()
    with _LOCK:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS events(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts REAL NOT NULL,            -- when it OCCURRED (valid-time)
          ingested REAL NOT NULL,      -- when WE learned it (ingestion-time) -> bi-temporal
          kind TEXT NOT NULL,          -- email|calendar|call|session|deliverable|web|note|...
          source TEXT NOT NULL,        -- the producing surface/integration (provenance)
          trust INTEGER NOT NULL DEFAULT 1,
          actor TEXT,                  -- who (from/owner)
          subject TEXT,                -- the entity key this is "about" (client/project/thread)
          title TEXT,
          body TEXT,
          refs TEXT,                   -- json: links/paths/ids
          meta TEXT,                   -- json
          ext_id TEXT,                 -- natural id from the source (for idempotent ingest)
          UNIQUE(source, ext_id)
        );
        CREATE INDEX IF NOT EXISTS ix_events_ts ON events(ts);
        CREATE INDEX IF NOT EXISTS ix_events_kind ON events(kind);
        CREATE INDEX IF NOT EXISTS ix_events_subject ON events(subject);
        CREATE TABLE IF NOT EXISTS entities(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          type TEXT NOT NULL,          -- person|project|client|thread|file|org|topic
          name TEXT NOT NULL,
          nkey TEXT NOT NULL,          -- normalized key for dedup
          keys TEXT,                   -- json: aliases/emails/ids
          meta TEXT,
          updated REAL NOT NULL,
          UNIQUE(type, nkey)
        );
        CREATE TABLE IF NOT EXISTS edges(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          src INTEGER NOT NULL, dst INTEGER NOT NULL, rel TEXT NOT NULL,
          ts REAL NOT NULL, provenance TEXT, meta TEXT,
          UNIQUE(src, dst, rel)
        );
        """)
        try:
            c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(title, body, subject, content='events', content_rowid='id')")
            # keep FTS in sync
            c.executescript("""
            CREATE TRIGGER IF NOT EXISTS events_ai AFTER INSERT ON events BEGIN
              INSERT INTO events_fts(rowid,title,body,subject) VALUES (new.id,new.title,new.body,new.subject); END;
            CREATE TRIGGER IF NOT EXISTS events_ad AFTER DELETE ON events BEGIN
              INSERT INTO events_fts(events_fts,rowid,title,body,subject) VALUES('delete',old.id,old.title,old.body,old.subject); END;
            CREATE TRIGGER IF NOT EXISTS events_au AFTER UPDATE ON events BEGIN
              INSERT INTO events_fts(events_fts,rowid,title,body,subject) VALUES('delete',old.id,old.title,old.body,old.subject);
              INSERT INTO events_fts(rowid,title,body,subject) VALUES (new.id,new.title,new.body,new.subject); END;
            """)
            _FTS = True
        except Exception:
            _FTS = False
        c.commit()

# ---- write path -------------------------------------------------------------------------------------
def _norm(s): return re.sub(r"\s+", " ", (s or "").strip().lower())
def _trust(v):
    if isinstance(v, str): return int(TRUST.get(v, 1))
    try: return max(0, min(3, int(v)))
    except Exception: return 1

def ingest_event(kind, source, title="", body="", ts=None, ingested=None, actor=None, subject=None,
                 trust=1, refs=None, meta=None, ext_id=None):
    """Add one event. Idempotent on (source, ext_id) when ext_id is given (so backfills don't duplicate).
    Returns the row id (existing id if it was a dup). Everything carries source+trust = provenance."""
    c = _connect(); now = time.time()
    row = (float(ts if ts is not None else now), float(ingested if ingested is not None else now),
           str(kind), str(source), _trust(trust), actor, subject, (title or "")[:2000], (body or ""),
           json.dumps(refs or {}), json.dumps(meta or {}), ext_id)
    with _LOCK:
        try:
            cur = c.execute("""INSERT INTO events(ts,ingested,kind,source,trust,actor,subject,title,body,refs,meta,ext_id)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", row)
            c.commit(); eid = cur.lastrowid
        except sqlite3.IntegrityError:
            r = c.execute("SELECT id FROM events WHERE source=? AND ext_id=?", (source, ext_id)).fetchone()
            eid = r["id"] if r else None
    _index_entities(actor, subject)   # seed the graph on BOTH insert AND dup (idempotent upsert) so a
    return eid                         # re-backfill of already-known events still populates people/subjects

def _index_entities(actor, subject):
    """Deterministic, cheap entity seeding (no LLM): a person from the actor (keyed by email so the same
    person across sources resolves to one), and a subject/project entity. Turns the flat log into a graph."""
    try:
        if actor:
            em = re.search(r"[\w.+-]+@[\w.-]+\.\w+", actor)
            name = re.sub(r"<[^>]*>", "", actor).strip().strip('"').strip() or (em.group(0) if em else actor)
            upsert_entity("person", name[:80], keys=([em.group(0).lower()] if em else []))
        if subject:
            upsert_entity("subject", str(subject)[:80])
    except Exception: pass

def upsert_entity(etype, name, keys=None, meta=None):
    c = _connect(); nkey = _norm(name); now = time.time()
    with _LOCK:
        r = c.execute("SELECT id,keys,meta FROM entities WHERE type=? AND nkey=?", (etype, nkey)).fetchone()
        if r:
            ek = set(json.loads(r["keys"] or "[]")) | set(keys or [])
            em = json.loads(r["meta"] or "{}"); em.update(meta or {})
            c.execute("UPDATE entities SET keys=?,meta=?,updated=? WHERE id=?",
                      (json.dumps(sorted(ek)), json.dumps(em), now, r["id"])); c.commit(); return r["id"]
        cur = c.execute("INSERT INTO entities(type,name,nkey,keys,meta,updated) VALUES(?,?,?,?,?,?)",
                        (etype, name, nkey, json.dumps(keys or []), json.dumps(meta or {}), now))
        c.commit(); return cur.lastrowid

def link(src_id, dst_id, rel, provenance=None, meta=None):
    c = _connect()
    with _LOCK:
        try:
            c.execute("INSERT OR IGNORE INTO edges(src,dst,rel,ts,provenance,meta) VALUES(?,?,?,?,?,?)",
                      (src_id, dst_id, rel, time.time(), provenance, json.dumps(meta or {}))); c.commit()
        except Exception: pass

# ---- retrieval --------------------------------------------------------------------------------------
def _search_ids(query, limit=80):
    """Lexical candidate retrieval. FTS5 (bm25) when available, else a LIKE fallback. Returns [(id, relevance)]."""
    c = _connect(); q = (query or "").strip()
    if not q: return []
    if _FTS:
        # turn a free-text query into a tolerant FTS OR-match of its word tokens
        toks = [t for t in re.findall(r"[A-Za-z0-9_]+", q) if len(t) > 1][:12]
        if not toks: return []
        match = " OR ".join(toks)
        try:
            rows = c.execute("""SELECT e.id AS id, bm25(events_fts) AS score FROM events_fts
                                JOIN events e ON e.id=events_fts.rowid
                                WHERE events_fts MATCH ? ORDER BY score LIMIT ?""", (match, limit)).fetchall()
            # bm25: lower is better -> convert to 0..1 relevance
            if rows:
                worst = max(r["score"] for r in rows) or 1.0
                return [(r["id"], 1.0 - (r["score"] / (worst + 1e-9))) for r in rows]
        except Exception: pass
    like = "%" + q[:60] + "%"
    rows = c.execute("SELECT id FROM events WHERE title LIKE ? OR body LIKE ? OR subject LIKE ? ORDER BY ts DESC LIMIT ?",
                     (like, like, like, limit)).fetchall()
    return [(r["id"], 0.5) for r in rows]

def _recent_ids(limit=40, kinds=None, subject=None):
    c = _connect(); where, args = [], []
    if kinds: where.append("kind IN (%s)" % ",".join("?" * len(kinds))); args += list(kinds)
    if subject: where.append("subject=?"); args.append(subject)
    sql = "SELECT id FROM events" + ((" WHERE " + " AND ".join(where)) if where else "") + " ORDER BY ts DESC LIMIT ?"
    args.append(limit)
    return [r["id"] for r in c.execute(sql, args).fetchall()]

def _fetch(ids):
    if not ids: return []
    c = _connect()
    rows = c.execute("SELECT * FROM events WHERE id IN (%s)" % ",".join("?" * len(ids)), list(ids)).fetchall()
    return {r["id"]: dict(r) for r in rows}

def _est_tokens(s): return max(1, len(s or "") // 4)

# ---- THE ROUTER: assemble a perfect-as-possible slice ----------------------------------------------
def assemble(query=None, subject=None, budget_tokens=3500, kinds=None, half_life_hours=72.0,
             w_rel=0.55, w_rec=0.30, w_trust=0.15, now=None):
    """Assemble the working-context slice for a task/subject. Pipeline:
       retrieve (lexical query + recent + subject) -> score (relevance x recency x trust) -> dedup ->
       budget to the window -> EDGE-PLACE the highest-signal items -> return a CITED bundle.
    Returns {ok, items:[{id,kind,source,ts,trust,score,title,snippet,refs}], text, citations, budget, used}."""
    now = now or time.time()
    cand = {}                                   # id -> relevance (max over retrieval routes)
    for i, rel in _search_ids(query, 80): cand[i] = max(cand.get(i, 0.0), rel)
    if subject:
        for i, rel in _search_ids(subject, 40): cand[i] = max(cand.get(i, 0.0), rel * 0.8)
    for i in _recent_ids(40, kinds, subject): cand.setdefault(i, 0.15)   # recency floor even w/o a query
    rows = _fetch(list(cand.keys()))
    scored = []
    seen_hashes = set()
    for i, rel in cand.items():
        r = rows.get(i)
        if not r: continue
        if kinds and r["kind"] not in kinds: continue
        age_h = max(0.0, (now - r["ts"]) / 3600.0)
        recency = math.exp(-age_h / max(1.0, half_life_hours))      # 0..1, decays over the half-life
        trust = r["trust"] / 3.0
        score = w_rel * rel + w_rec * recency + w_trust * trust
        # near-duplicate suppression (same source item / repeated content)
        h = hashlib.sha1((str(r["source"]) + "|" + _norm(r["title"]) + "|" + _norm((r["body"] or "")[:200])).encode()).hexdigest()
        if h in seen_hashes: continue
        seen_hashes.add(h)
        scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)

    # budget greedily by score
    chosen, used = [], 0
    for score, r in scored:
        snippet = (r["body"] or r["title"] or "").strip().replace("\n", " ")
        snippet = snippet[:600]
        cost = _est_tokens((r["title"] or "") + snippet) + 12
        if used + cost > budget_tokens and chosen: break
        used += cost
        chosen.append({"id": r["id"], "kind": r["kind"], "source": r["source"], "ts": r["ts"],
                       "trust": r["trust"], "score": round(score, 4), "title": r["title"],
                       "snippet": snippet, "refs": json.loads(r["refs"] or "{}")})
        if used >= budget_tokens: break

    # EDGE-PLACEMENT: highest-signal at the start AND end, weaker in the middle (lost-in-the-middle).
    ordered = _edge_place(chosen)
    text = _render(ordered, subject, query)
    citations = [{"id": x["id"], "source": x["source"], "kind": x["kind"],
                  "ts": x["ts"], "trust": x["trust"]} for x in ordered]
    return {"ok": True, "subject": subject, "query": query, "budget": budget_tokens, "used": used,
            "count": len(ordered), "items": ordered, "text": text, "citations": citations}

def _edge_place(items):
    # items are sorted by score desc; render order = [0,2,4,...,5,3,1] -> #1 first, #2 last.
    front, back = [], []
    for idx, it in enumerate(items):
        (front if idx % 2 == 0 else back).append(it)
    return front + back[::-1]

def _render(items, subject, query):
    def ago(ts):
        s = max(0, int(time.time() - ts));
        return (str(s)+"s") if s < 60 else (str(s//60)+"m") if s < 3600 else (str(s//3600)+"h") if s < 86400 else (str(s//86400)+"d")
    lines = ["# Context" + (" — " + subject if subject else "") + (" (re: %s)" % query if query else "")]
    for it in items:
        tag = "[%s · %s · %s ago · trust %d]" % (it["kind"], it["source"], ago(it["ts"]), it["trust"])
        head = (it["title"] or "").strip()
        lines.append("\n## %s %s" % (head or it["kind"], tag))
        if it["snippet"]: lines.append(it["snippet"])
    return "\n".join(lines)

# ---- introspection (for the Context lens) -----------------------------------------------------------
def stats():
    c = _connect()
    out = {"db": _DB_PATH, "fts": _FTS}
    out["events"] = c.execute("SELECT COUNT(*) n FROM events").fetchone()["n"]
    out["entities"] = c.execute("SELECT COUNT(*) n FROM entities").fetchone()["n"]
    out["by_kind"] = {r["kind"]: r["n"] for r in c.execute("SELECT kind,COUNT(*) n FROM events GROUP BY kind ORDER BY n DESC").fetchall()}
    out["by_source"] = {r["source"]: r["n"] for r in c.execute("SELECT source,COUNT(*) n FROM events GROUP BY source ORDER BY n DESC").fetchall()}
    r = c.execute("SELECT MIN(ts) a, MAX(ts) b FROM events").fetchone()
    out["span"] = {"oldest": r["a"], "newest": r["b"]}
    return out

def search(q, limit=30):
    rows = _fetch([i for i, _ in _search_ids(q, limit)])
    items = sorted(rows.values(), key=lambda r: r["ts"], reverse=True)
    return [{"id": r["id"], "kind": r["kind"], "source": r["source"], "ts": r["ts"], "trust": r["trust"],
             "title": r["title"], "snippet": (r["body"] or "")[:200]} for r in items]

# ---- self test --------------------------------------------------------------------------------------
def selftest():
    import tempfile
    global _DB_PATH, _CONN
    _CONN = None; _DB_PATH = os.path.join(tempfile.mkdtemp(), "ctx_test.db")
    init({"db_path": _DB_PATH})
    now = time.time()
    ingest_event("email", "gmail", "Tune request for the 6.7 Cummins", "Customer wants more low-end torque, towing setup, EGT concerns.", ts=now-3600, actor="cust@x.com", subject="acme-diesel", trust="external", ext_id="m1")
    ingest_event("call", "granola", "Call with Acme Diesel", "Discussed turbo sizing and a safe timing map. James to send a draft tune.", ts=now-7200, subject="acme-diesel", trust="owner", ext_id="c1")
    ingest_event("deliverable", "files", "acme_v3.hpt", "Draft calibration v3 for Acme.", ts=now-1800, subject="acme-diesel", trust="owner", ext_id="d1")
    ingest_event("email", "gmail", "Unrelated newsletter", "Big sale on parts this week.", ts=now-600, trust="external", ext_id="m2")
    ingest_event("email", "gmail", "Tune request for the 6.7 Cummins", "Customer wants more low-end torque, towing setup, EGT concerns.", ts=now-3600, actor="cust@x.com", subject="acme-diesel", trust="external", ext_id="m1")  # dup ext_id -> ignored
    b = assemble(query="cummins towing torque tune", subject="acme-diesel", budget_tokens=800)
    assert b["count"] >= 2, b
    titles = [i["title"] for i in b["items"]]
    assert any("Cummins" in (t or "") for t in titles), titles
    assert all("newsletter" not in (i["title"] or "").lower() for i in b["items"][:2]), "noise ranked too high"
    s = stats(); assert s["events"] == 4, s   # the dup did not create a 5th
    print("SELFTEST OK -> events=%d count=%d used=%d fts=%s" % (s["events"], b["count"], b["used"], _FTS))
    print("--- assembled bundle (edge-placed, cited) ---"); print(b["text"][:700])
    return True

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "selftest": selftest()
    elif cmd == "stats": init(); print(json.dumps(stats(), indent=1, default=str))
    elif cmd == "assemble": init(); print(assemble(query=" ".join(sys.argv[2:]) or None)["text"])
    else: print("usage: context.py [selftest|stats|assemble <query>]")
