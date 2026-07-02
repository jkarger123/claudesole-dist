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
    _CONN = sqlite3.connect(_DB_PATH, check_same_thread=False, timeout=10)
    _CONN.row_factory = sqlite3.Row
    try: _CONN.execute("PRAGMA journal_mode=WAL"); _CONN.execute("PRAGMA synchronous=NORMAL")
    except Exception: pass
    try: _CONN.execute("PRAGMA busy_timeout=8000")   # wait up to 8s for a write lock instead of failing ("database is locked")
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
          valid_at REAL,               -- when this became true in the WORLD (bi-temporal: valid-time)
          invalid_at REAL,             -- when it STOPPED being true (NULL = still true). Invalidate, never delete.
          created_at REAL,             -- when WE recorded it (system-time)
          expired_at REAL              -- when WE retracted/corrected the RECORD itself (NULL = live record)
        );
        CREATE INDEX IF NOT EXISTS ix_edges_src_rel ON edges(src, rel);
        CREATE INDEX IF NOT EXISTS ix_edges_dst_rel ON edges(dst, rel);
        """)
        # BI-TEMPORAL MIGRATION (one-time): the v1 edges table had UNIQUE(src,dst,rel), which forbids
        # HISTORY (the same fact can never be re-asserted after being invalidated). Rebuild without the
        # constraint, preserving rows; v1 rows get valid_at=ts, created_at=ts (best available truth).
        try:
            cols = {r[1] for r in c.execute("PRAGMA table_info(edges)").fetchall()}
            uniq = any("sqlite_autoindex" in (r[1] or "") for r in c.execute("PRAGMA index_list(edges)").fetchall())
            if "valid_at" not in cols or uniq:
                c.executescript("""
                CREATE TABLE IF NOT EXISTS edges_v2(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  src INTEGER NOT NULL, dst INTEGER NOT NULL, rel TEXT NOT NULL,
                  ts REAL NOT NULL, provenance TEXT, meta TEXT,
                  valid_at REAL, invalid_at REAL, created_at REAL, expired_at REAL
                );
                """)
                old = "src,dst,rel,ts,provenance,meta" + (",valid_at,invalid_at,created_at,expired_at" if "valid_at" in cols else "")
                new = "src,dst,rel,ts,provenance,meta" + (",valid_at,invalid_at,created_at,expired_at" if "valid_at" in cols else ",valid_at,created_at")
                sel = old if "valid_at" in cols else old + ",ts,ts"
                c.execute("INSERT INTO edges_v2(%s) SELECT %s FROM edges" % (new, sel))
                c.executescript("DROP TABLE edges; ALTER TABLE edges_v2 RENAME TO edges;")
                c.executescript("""
                CREATE INDEX IF NOT EXISTS ix_edges_src_rel ON edges(src, rel);
                CREATE INDEX IF NOT EXISTS ix_edges_dst_rel ON edges(dst, rel);
                """)
        except Exception:
            pass
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

# ---- ENTITY RESOLUTION (VISION 3.2): the same person/thing from every surface -> ONE entity ------------
# Two-tier, deterministic-first (Fellegi-Sunter shape, no LLM): (1) high-confidence KEYS (an email address,
# a source id) match exactly -> same entity, whatever the display name; (2) no key match -> Jaro-Winkler
# name similarity >= 0.87 against same-type entities -> merge as an alias. Merges are NON-DESTRUCTIVE
# (aliases[] + merged_ids in meta; the duplicate row is tombstoned with merged_into, never deleted) so a
# wrong merge is reversible. An LLM adjudication tier can slot in later for the blocking survivors.

def _jaro_winkler(a, b):
    """Stdlib Jaro-Winkler similarity 0..1 (standard p=0.1, 4-char prefix cap)."""
    a, b = (a or ""), (b or "")
    if a == b: return 1.0
    la, lb = len(a), len(b)
    if not la or not lb: return 0.0
    window = max(la, lb) // 2 - 1
    ma = [False] * la; mb = [False] * lb; matches = 0
    for i in range(la):
        lo, hi = max(0, i - window), min(lb, i + window + 1)
        for j in range(lo, hi):
            if not mb[j] and a[i] == b[j]:
                ma[i] = mb[j] = True; matches += 1; break
    if not matches: return 0.0
    t = 0; k = 0
    for i in range(la):
        if ma[i]:
            while not mb[k]: k += 1
            if a[i] != b[k]: t += 1
            k += 1
    jaro = (matches / la + matches / lb + (matches - t / 2) / matches) / 3.0
    prefix = 0
    for i in range(min(4, la, lb)):
        if a[i] == b[i]: prefix += 1
        else: break
    return jaro + prefix * 0.1 * (1.0 - jaro)

_JW_MERGE = 0.87   # match threshold for name-only resolution (keys always win outright)

def upsert_entity(etype, name, keys=None, meta=None):
    """Upsert with RESOLUTION: (1) any provided key already held by a same-type entity -> that entity (the
    new name becomes an alias); (2) exact normalized-name match -> that entity; (3) Jaro-Winkler >= 0.87
    against same-type names/aliases -> that entity (alias merge); else a new entity."""
    c = _connect(); nkey = _norm(name); now = time.time()
    keys = [k for k in (keys or []) if k]
    def _absorb(row):
        ek = set(json.loads(row["keys"] or "[]")) | set(keys)
        em = json.loads(row["meta"] or "{}"); em.update(meta or {})
        if nkey and nkey != row["nkey"]:
            al = set(em.get("aliases") or []); al.add(name); em["aliases"] = sorted(al)
        c.execute("UPDATE entities SET keys=?,meta=?,updated=? WHERE id=?",
                  (json.dumps(sorted(ek)), json.dumps(em), now, row["id"])); c.commit(); return row["id"]
    with _LOCK:
        # tier 1: deterministic key match (email / source id) beats any name difference
        if keys:
            for row in c.execute("SELECT id,nkey,keys,meta FROM entities WHERE type=? AND keys!='[]'", (etype,)).fetchall():
                held = set(json.loads(row["keys"] or "[]"))
                if held & set(keys): return _absorb(row)
        # tier 2: exact normalized name
        r = c.execute("SELECT id,nkey,keys,meta FROM entities WHERE type=? AND nkey=?", (etype, nkey)).fetchone()
        if r: return _absorb(r)
        # tier 3: fuzzy name vs names + aliases (persons and orgs only -- subjects/threads are literal keys)
        if etype in ("person", "org", "client") and len(nkey) >= 5:
            best, best_row = 0.0, None
            for row in c.execute("SELECT id,nkey,keys,meta FROM entities WHERE type=?", (etype,)).fetchall():
                cand = [row["nkey"]] + [_norm(x) for x in (json.loads(row["meta"] or "{}").get("aliases") or [])]
                s = max((_jaro_winkler(nkey, x) for x in cand if x), default=0.0)
                if s > best: best, best_row = s, row
            if best_row is not None and best >= _JW_MERGE:
                return _absorb(best_row)
        cur = c.execute("INSERT INTO entities(type,name,nkey,keys,meta,updated) VALUES(?,?,?,?,?,?)",
                        (etype, name, nkey, json.dumps(sorted(set(keys))), json.dumps(meta or {}), now))
        c.commit(); return cur.lastrowid

def merge_entities(keep_id, dup_id):
    """Non-destructive merge: union keys, record aliases + merged_ids on the keeper, repoint the duplicate's
    edges, tombstone the duplicate (meta.merged_into; the row stays -- reversible by construction)."""
    if keep_id == dup_id: return {"ok": False, "error": "same entity"}
    c = _connect(); now = time.time()
    with _LOCK:
        k = c.execute("SELECT * FROM entities WHERE id=?", (keep_id,)).fetchone()
        d = c.execute("SELECT * FROM entities WHERE id=?", (dup_id,)).fetchone()
        if not k or not d: return {"ok": False, "error": "no such entity"}
        km = json.loads(k["meta"] or "{}"); dm = json.loads(d["meta"] or "{}")
        keys = set(json.loads(k["keys"] or "[]")) | set(json.loads(d["keys"] or "[]"))
        al = set(km.get("aliases") or []) | set(dm.get("aliases") or []) | {d["name"]}
        km["aliases"] = sorted(x for x in al if _norm(x) != k["nkey"])
        km["merged_ids"] = sorted(set(km.get("merged_ids") or []) | {dup_id})
        c.execute("UPDATE entities SET keys=?,meta=?,updated=? WHERE id=?",
                  (json.dumps(sorted(keys)), json.dumps(km), now, keep_id))
        c.execute("UPDATE edges SET src=? WHERE src=?", (keep_id, dup_id))
        c.execute("UPDATE edges SET dst=? WHERE dst=?", (keep_id, dup_id))
        dm["merged_into"] = keep_id
        c.execute("UPDATE entities SET meta=?,updated=? WHERE id=?", (json.dumps(dm), now, dup_id))
        c.commit()
    return {"ok": True, "kept": keep_id, "merged": dup_id}

# ---- BI-TEMPORAL EDGES (VISION 3.2 / Graphiti-Zep model) ----------------------------------------------
# Four timestamps per edge: valid_at/invalid_at = when it was true IN THE WORLD; created_at/expired_at =
# when WE recorded/retracted the record. Conflict rule: INVALIDATE, NEVER DELETE (the old edge's invalid_at
# is set to the new edge's valid_at), so "what was true WHEN" is always answerable and corrections never
# destroy history. Freshness is resolved in DETERMINISTIC CODE (max valid_at), never by an LLM.

def assert_edge(src_id, dst_id, rel, valid_at=None, provenance=None, meta=None, functional=False):
    """Assert a fact edge. functional=True means (src, rel) has ONE current value (e.g. project STATUS,
    person WORKS_AT): asserting a new dst invalidates any currently-valid edges to other dsts. Re-asserting
    the SAME currently-valid (src,dst,rel) is a no-op (returns the live edge id). Returns the edge id."""
    c = _connect(); now = time.time(); va = float(valid_at if valid_at is not None else now)
    with _LOCK:
        live = c.execute("""SELECT id,dst FROM edges WHERE src=? AND rel=? AND expired_at IS NULL
                            AND (invalid_at IS NULL OR invalid_at>?)""", (src_id, rel, va)).fetchall()
        for r in live:
            if r["dst"] == dst_id:
                return r["id"]                          # already true now -- nothing to change
        if functional:
            for r in live:                              # a new value supersedes the old: invalidate at the handover
                c.execute("UPDATE edges SET invalid_at=? WHERE id=? AND (invalid_at IS NULL OR invalid_at>?)",
                          (va, r["id"], va))
        cur = c.execute("""INSERT INTO edges(src,dst,rel,ts,provenance,meta,valid_at,created_at)
                           VALUES(?,?,?,?,?,?,?,?)""",
                        (src_id, dst_id, rel, now, provenance, json.dumps(meta or {}), va, now))
        c.commit(); return cur.lastrowid

def invalidate_edge(edge_id, invalid_at=None):
    """Mark an edge as no longer true in the world (correction path). The row stays -- history is sacred."""
    c = _connect()
    with _LOCK:
        c.execute("UPDATE edges SET invalid_at=? WHERE id=?", (float(invalid_at or time.time()), edge_id)); c.commit()
    return {"ok": True, "id": edge_id}

def current_edges(src=None, dst=None, rel=None, at=None):
    """THE DETERMINISTIC FRESHNESS RESOLVER: what is true at time `at` (default: now). An edge counts iff
    valid_at<=at AND (invalid_at is NULL or invalid_at>at) AND the record isn't expired. Ordered newest
    valid_at first, so callers wanting 'the' value of a functional rel take row 0 -- pure max(valid_at),
    no model involved (research: a ~50-line deterministic resolver beats every LLM memory system on
    'which fact is current')."""
    c = _connect(); at = float(at if at is not None else time.time())
    where, args = ["(valid_at IS NULL OR valid_at<=?)", "(invalid_at IS NULL OR invalid_at>?)", "expired_at IS NULL"], [at, at]
    if src is not None: where.append("src=?"); args.append(src)
    if dst is not None: where.append("dst=?"); args.append(dst)
    if rel is not None: where.append("rel=?"); args.append(rel)
    rows = c.execute("SELECT * FROM edges WHERE %s ORDER BY valid_at DESC" % " AND ".join(where), args).fetchall()
    return [dict(r) for r in rows]

def edge_history(src, rel=None):
    """The full timeline for a src (optionally one rel): every assertion with its validity window --
    'what was true when', including superseded values. Never deletes, so this is complete."""
    c = _connect(); where, args = ["src=?"], [src]
    if rel: where.append("rel=?"); args.append(rel)
    rows = c.execute("SELECT * FROM edges WHERE %s ORDER BY valid_at ASC" % " AND ".join(where), args).fetchall()
    return [dict(r) for r in rows]

def link(src_id, dst_id, rel, provenance=None, meta=None):
    """Compat wrapper (v1 API): a non-functional observation edge, valid from now."""
    try: return assert_edge(src_id, dst_id, rel, provenance=provenance, meta=meta, functional=False)
    except Exception: return None

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
    if not ids: return {}                  # dict, consistent with the populated case (search() calls rows.values())
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
    # PIPELINE: the "behind the curtain" story -- what the router actually did, for the Context X-ray.
    _TLABEL = {0: "external", 1: "contact", 2: "internal", 3: "owner"}
    src_mix, trust_mix = {}, {}
    for it in ordered:
        src_mix[it["source"]] = src_mix.get(it["source"], 0) + 1
        tl = _TLABEL.get(it["trust"], str(it["trust"]))
        trust_mix[tl] = trust_mix.get(tl, 0) + 1
    pipeline = {"considered": len(cand), "ranked": len(scored), "kept": len(ordered),
                "dropped": max(0, len(scored) - len(ordered)),
                "sources": src_mix, "trust": trust_mix, "budget": budget_tokens, "used": used,
                "signals": ["relevance", "recency", "trust"], "placement": "edges (highest-signal first & last)",
                "store_total": stats().get("events", 0)}
    return {"ok": True, "subject": subject, "query": query, "budget": budget_tokens, "used": used,
            "count": len(ordered), "items": ordered, "text": text, "citations": citations, "pipeline": pipeline}

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
    try:
        out["edges"] = c.execute("SELECT COUNT(*) n FROM edges").fetchone()["n"]
        out["edges_current"] = c.execute("SELECT COUNT(*) n FROM edges WHERE expired_at IS NULL AND (invalid_at IS NULL OR invalid_at>?)", (time.time(),)).fetchone()["n"]
    except Exception: pass
    out["by_kind"] = {r["kind"]: r["n"] for r in c.execute("SELECT kind,COUNT(*) n FROM events GROUP BY kind ORDER BY n DESC").fetchall()}
    out["by_source"] = {r["source"]: r["n"] for r in c.execute("SELECT source,COUNT(*) n FROM events GROUP BY source ORDER BY n DESC").fetchall()}
    r = c.execute("SELECT MIN(ts) a, MAX(ts) b FROM events").fetchone()
    out["span"] = {"oldest": r["a"], "newest": r["b"]}
    return out

def subjects(limit=300):
    """Known subjects/people the focus engine can match an activity signal against (graph nodes + the
    distinct subject keys seen on events). name + aliases/keys."""
    c = _connect(); out = {}
    for r in c.execute("SELECT type,name,keys,meta FROM entities WHERE type IN ('subject','project','client','person') ORDER BY updated DESC LIMIT ?", (limit,)).fetchall():
        if (json.loads(r["meta"] or "{}")).get("merged_into"): continue   # tombstoned duplicate -> its keeper carries the aliases
        out[_norm(r["name"])] = {"name": r["name"], "type": r["type"], "keys": json.loads(r["keys"] or "[]")}
    for r in c.execute("SELECT DISTINCT subject FROM events WHERE subject IS NOT NULL AND subject!='' LIMIT ?", (limit,)).fetchall():
        k = _norm(r["subject"])
        if k and k not in out: out[k] = {"name": r["subject"], "type": "subject", "keys": []}
    return list(out.values())

def search(q, limit=30):
    rows = _fetch([i for i, _ in _search_ids(q, limit)])
    items = sorted(rows.values(), key=lambda r: r["ts"], reverse=True)
    return [{"id": r["id"], "kind": r["kind"], "source": r["source"], "ts": r["ts"], "trust": r["trust"],
             "title": r["title"], "snippet": (r["body"] or "")[:200]} for r in items]

# ---- THE SCOUT: proactive "you didn't know to look" surfacing -------------------------------------
def _ago(now, ts):
    s = max(0, int((now or time.time()) - (ts or 0)))
    return (str(s)+"s") if s < 60 else (str(s//60)+"m") if s < 3600 else (str(s//3600)+"h") if s < 86400 else (str(s//86400)+"d")

def scout(subject=None, query=None, limit=6, max_age_hours=336.0, min_rel=0.18, exclude_ids=None, now=None):
    """The SCOUT -- proactive relevance surfacing (the answer to 'the email you didn't know was in the inbox').
    Return the freshest, genuinely-relevant POINTERS about a subject/query that the agent was NOT already handed
    (exclude_ids), so a cheap index pass can flag 'these N recent items may bear on what you're doing -- open if
    useful' WITHOUT dumping the whole inbox. Distinct from assemble(): assemble returns the cited BRIEF TEXT
    (the obvious subject matches); scout returns actionable, deduped, FRESHNESS-FIRST pointers. Scores
    relevance x recency (short half-life) x trust, gates on a freshness window + a relevance floor (a fresh item
    with no subject/query match survives only if it's very fresh AND carries a link -- a genuine 'new thing').
    stdlib-only, no LLM (a model re-rank can wrap this later). Returns {ok, subject, query, count, items:[
    {id,kind,source,title,ts,ago,refs,trust,actor,score,why}]}."""
    now = now or time.time()
    exclude = set(int(x) for x in (exclude_ids or []) if str(x).isdigit())
    nsubj = _norm(str(subject)) if subject else ""
    cand, matched = {}, set()   # `matched` = items that LEXICALLY matched the query/subject (membership is the
    if query:                   # relevance signal -- the bm25 magnitude is brittle: a SOLE match normalizes to ~0).
        for i, rel in _search_ids(query, 60): cand[i] = max(cand.get(i, 0.0), max(rel, 0.4)); matched.add(i)
    if subject:
        for i, rel in _search_ids(str(subject), 60): cand[i] = max(cand.get(i, 0.0), max(rel * 0.9, 0.36)); matched.add(i)
        for i in _recent_ids(60, None, str(subject)): cand[i] = max(cand.get(i, 0.0), 0.5); matched.add(i)  # subject-keyed = strong
    for i in _recent_ids(40, None, None): cand.setdefault(i, 0.0)   # the unknown-unknown net: fresh items at large
    rows = _fetch(list(cand.keys()))
    half = 96.0   # freshness-biased half-life (~4 days): the scout favors the NEW more than assemble does
    scored, seen_h = [], set()
    for i, rel in cand.items():
        if i in exclude: continue
        r = rows.get(i)
        if not r: continue
        age_h = max(0.0, (now - r["ts"]) / 3600.0)
        if age_h > max_age_hours: continue                              # freshness window
        recency = math.exp(-age_h / half)
        refs = json.loads(r["refs"] or "{}")
        has_link = bool(refs.get("url") or refs.get("link") or refs.get("rel") or refs.get("thread"))
        subj_match = bool(nsubj and _norm(r["subject"] or "") == nsubj)
        relevant = (i in matched) or subj_match                        # it matched the query/subject lexically or by key
        if not relevant:
            if not (recency > 0.5 and has_link): continue              # not relevant -> only a fresh, actionable "new thing"
        score = 0.5 * max(rel, min_rel if relevant else 0.0) + 0.4 * recency + 0.1 * (r["trust"] / 3.0)
        h = hashlib.sha1((str(r["source"]) + "|" + _norm(r["title"])).encode()).hexdigest()
        if h in seen_h: continue
        seen_h.add(h)
        actor = re.sub(r"<[^>]*>", "", (r["actor"] or "")).strip().strip('"').strip()[:40]
        why = "%s%s, %s ago%s" % (r["kind"], (" from " + actor) if actor else "", _ago(now, r["ts"]),
                                  (" -- matches '%s'" % subject) if (subject and relevant) else "")
        scored.append((score, r, refs, why))
    scored.sort(key=lambda x: x[0], reverse=True)
    items = [{"id": r["id"], "kind": r["kind"], "source": r["source"], "title": r["title"], "ts": r["ts"],
              "ago": _ago(now, r["ts"]), "refs": refs, "trust": r["trust"], "actor": r["actor"],
              "score": round(score, 4), "why": why}
             for score, r, refs, why in scored[:max(1, int(limit))]]
    return {"ok": True, "subject": subject, "query": query, "count": len(items), "items": items}

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
    # SCOUT: surfaces fresh+relevant pointers about the subject, excluding what was already handed, and never the noise.
    sc = scout(subject="acme-diesel", limit=5)
    assert sc["count"] >= 2, sc
    assert all("newsletter" not in (i["title"] or "").lower() for i in sc["items"]), "scout surfaced noise"
    scx = scout(subject="acme-diesel", limit=5, exclude_ids=[i["id"] for i in sc["items"]])
    assert scx["count"] == 0, ("scout did not honor exclude_ids", scx)
    print("SCOUT OK -> surfaced=%d why0=%s" % (sc["count"], sc["items"][0]["why"]))
    # BI-TEMPORAL EDGES: invalidate-never-delete + deterministic freshness (max valid_at, pure code).
    pa = upsert_entity("project", "acme-diesel"); st_draft = upsert_entity("topic", "status:draft")
    st_final = upsert_entity("topic", "status:final")
    e1 = assert_edge(pa, st_draft, "status", valid_at=now-5000, functional=True)
    e2 = assert_edge(pa, st_final, "status", valid_at=now-100, functional=True)
    cur_now = current_edges(src=pa, rel="status")
    assert len(cur_now) == 1 and cur_now[0]["dst"] == st_final, ("freshness resolver wrong", cur_now)
    cur_then = current_edges(src=pa, rel="status", at=now-3000)
    assert len(cur_then) == 1 and cur_then[0]["dst"] == st_draft, ("time-travel wrong", cur_then)
    hist = edge_history(pa, "status")
    assert len(hist) == 2 and hist[0]["invalid_at"] == hist[1]["valid_at"], ("invalidate-at-handover wrong", hist)
    e3 = assert_edge(pa, st_draft, "status", valid_at=now, functional=True)   # RE-assertion after supersession must work (v1 UNIQUE forbade this)
    assert e3 not in (e1, e2) and current_edges(src=pa, rel="status")[0]["dst"] == st_draft
    assert assert_edge(pa, st_draft, "status", functional=True) == e3, "re-assert same current value must be a no-op"
    print("BITEMPORAL OK -> history=%d current=draft (re-asserted)" % len(edge_history(pa, "status")))
    # ENTITY RESOLUTION: same email under two name-forms -> ONE entity; fuzzy name -> alias merge; merge is reversible.
    p1 = upsert_entity("person", "Sarah K", keys=["sarah@x.com"])
    p2 = upsert_entity("person", "Sarah Karger", keys=["sarah@x.com"])
    assert p1 == p2, "email key must resolve name variants to one entity"
    p3 = upsert_entity("person", "Jon Smithers", keys=["jon@y.com"])
    p4 = upsert_entity("person", "John Smithers")                    # no key; JW >= 0.87 vs "jon smithers"
    assert p3 == p4, ("fuzzy resolution failed", p3, p4, _jaro_winkler("jon smithers", "john smithers"))
    p5 = upsert_entity("person", "Completely Different", keys=["cd@z.com"])
    assert p5 not in (p1, p3), "distinct person wrongly merged"
    m = merge_entities(p1, p5)
    assert m["ok"], m
    c2 = _connect()
    dm = json.loads(c2.execute("SELECT meta FROM entities WHERE id=?", (p5,)).fetchone()["meta"])
    assert dm.get("merged_into") == p1, "merge must tombstone (reversible), not delete"
    assert all(_norm(s["name"]) != "completely different" for s in subjects()), "tombstoned dup leaked into subjects()"
    print("RESOLUTION OK -> email-key unify + JW fuzzy (%.3f) + reversible merge" % _jaro_winkler("jon smithers", "john smithers"))
    print("SELFTEST OK -> events=%d count=%d used=%d fts=%s" % (s["events"], b["count"], b["used"], _FTS))
    print("--- assembled bundle (edge-placed, cited) ---"); print(b["text"][:700])
    return True

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "selftest": selftest()
    elif cmd == "stats": init(); print(json.dumps(stats(), indent=1, default=str))
    elif cmd == "assemble": init(); print(assemble(query=" ".join(sys.argv[2:]) or None)["text"])
    elif cmd == "scout": init(); print(json.dumps(scout(subject=" ".join(sys.argv[2:]) or None), indent=1, default=str))
    else: print("usage: context.py [selftest|stats|assemble <query>|scout <subject>]")
