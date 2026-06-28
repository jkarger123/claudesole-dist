#!/usr/bin/env python3
"""Slack -> the CONTEXT LAYER. Read-only ingest of recent Slack messages into the context store
(command-center/context.py) so chat becomes provenance-stamped, retrievable context like email/calls/email.

Design (matches granola.py / context.py): stdlib ONLY (urllib/json/os/time/re/threading -- no Slack SDK,
no pip deps); config-driven (everything via cc.config "slack" + a gitignored token, never hardcoded);
secret-clean (the bot token is never printed, logged, or returned); graceful when not configured
(no token -> reads are [] and ingest is a no-op, never raises). Provenance + TRUST on every event:
Slack message content is UNTRUSTED -- it is ingested as trust="contact" (data, never instructions).

server.py wires this once with slack.init({...}); then a line in _context_backfill() calls
slack.ingest(context, ...). Nothing else in the engine changes.

Token resolution order (first hit wins; all gitignored, never committed):
  1. ctx["token"]                                  (explicit, e.g. tests)
  2. cc.config "slack".token                        (discouraged -- prefer a secret file/env)
  3. <EXT_DIR>/slack/secrets/bot_token              (raw xoxb-... token, chmod 600; preferred)
  4. deploy_env("SLACK_BOT_TOKEN")                  (the .env.claudefather per-deploy secret)

Config (cc.config "slack"): {
  "channels":   ["C0123ABC", "general", "#eng"],   # channel IDs or names to read (resolved to ids)
  "dms":        false,                               # also pull recent direct messages (needs im:history)
  "client_map": {"acme": ["acme", "C0ACME", "acme.com"]},  # channel id/name/alias -> client subject
  "limit":      50,                                  # messages per channel per pull
  "permalinks": true                                 # fetch a real permalink per message (best-effort)
}

Standalone:  python3 slack.py status        (prints config + connectivity, NEVER the token)
             python3 slack.py recent [n]     (prints recent messages as JSON)
"""
import json, os, re, time, threading, urllib.request, urllib.parse

_API = "https://slack.com/api/"
_CTX = {}            # injected by server.py: CC, STATE_DIR, CC_HOME, EXT_DIR, deploy_env(optional)
_LOCK = threading.RLock()
_USERS = {}          # uid -> display name (in-process cache; avoids re-fetching users.info)
_CHANNELS = None     # resolved [{id,name,is_im,user}] (cached after first conversations.list)


# ---- init / config -------------------------------------------------------------------------------------
def init(ctx):
    """Called once by server.py (like granola.init). ctx may carry CC, STATE_DIR, CC_HOME, EXT_DIR,
    deploy_env (a callable for per-deploy secrets), and token (explicit override)."""
    global _CHANNELS, _USERS
    _CTX.update({k: v for k, v in (ctx or {}).items() if v is not None})
    _CHANNELS = None; _USERS = {}     # reset caches on (re)init
    return {"ok": True, "configured": configured()}


def _cfg():
    return (_CTX.get("CC", {}) or {}).get("slack") or {}


def _token():
    """Resolve the bot token, secret-clean. Returns the token string or None. NEVER printed/logged.
    Order: cc.config token -> the VAULT (via deploy_env, the canonical store) -> legacy secret file (retiring)."""
    t = _CTX.get("token") or _cfg().get("token")
    if t: return str(t).strip()
    # the canonical store: deploy_env resolves the per-install vault (then legacy .env). Vault is the one place.
    de = _CTX.get("deploy_env")
    if callable(de):
        try:
            v = de("SLACK_BOT_TOKEN")
            if v: return str(v).strip()
        except Exception:
            pass
    # legacy: a gitignored secret file under the extension (migrated into the vault + retired by vault_import_env)
    ext = _CTX.get("EXT_DIR") or (os.path.join(_CTX["CC_HOME"], "extensions") if _CTX.get("CC_HOME") else None)
    if ext:
        sf = _cfg().get("secret_file") or os.path.join(ext, "slack", "secrets", "bot_token")
        try:
            if os.path.isfile(sf):
                v = open(sf, encoding="utf-8", errors="replace").read().strip()
                if v: return v
        except Exception:
            pass
    v = os.environ.get("SLACK_BOT_TOKEN")
    return str(v).strip() if v else None


def configured():
    """True iff we have a token AND at least one channel/DM source to read. Graceful gate for callers."""
    c = _cfg()
    return bool(_token()) and bool(c.get("channels") or c.get("dms"))


# ---- Slack Web API (stdlib urllib; POST form-encoded with a bearer token) ------------------------------
def _api(method, params=None):
    """Call one Slack Web API method. Returns the parsed JSON dict (with ok:bool) or {ok:False,error:...}.
    Never raises and never includes the token in any returned/logged value."""
    tok = _token()
    if not tok: return {"ok": False, "error": "not_configured"}
    data = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None}).encode()
    req = urllib.request.Request(_API + method, data=data,
                                 headers={"Authorization": "Bearer " + tok,
                                          "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        # scrub: an exception string can't carry the token (it's a header, not the URL), but be explicit
        return {"ok": False, "error": str(e)[:160].replace(tok, "***")}


# ---- channel + user resolution -------------------------------------------------------------------------
def _all_conversations():
    """List + cache the workspace conversations the bot can see (public/private channels + IMs)."""
    global _CHANNELS
    if _CHANNELS is not None: return _CHANNELS
    out, cursor = [], None
    for _ in range(10):   # bounded pagination
        p = {"types": "public_channel,private_channel,im,mpim", "limit": 200, "exclude_archived": "true"}
        if cursor: p["cursor"] = cursor
        d = _api("conversations.list", p)
        if not d.get("ok"): break
        for c in d.get("channels", []):
            out.append({"id": c.get("id"), "name": c.get("name") or "", "is_im": bool(c.get("is_im")),
                        "user": c.get("user")})
        cursor = (d.get("response_metadata") or {}).get("next_cursor")
        if not cursor: break
    _CHANNELS = out
    return out


def _resolve_channels():
    """Resolve the configured channels[] (ids OR names, '#' optional) to [{id,name}]. DMs added when dms:true."""
    cfg = _cfg()
    want = [str(c).lstrip("#") for c in (cfg.get("channels") or [])]
    convos = _all_conversations()
    by_id = {c["id"]: c for c in convos}
    by_name = {c["name"].lower(): c for c in convos if c.get("name")}
    picked, seen = [], set()
    for w in want:
        c = by_id.get(w) or by_name.get(w.lower())
        if c and c["id"] not in seen:
            picked.append({"id": c["id"], "name": c.get("name") or c["id"], "is_im": c.get("is_im"), "user": c.get("user")})
            seen.add(c["id"])
        elif not c and re.match(r"^[CGD][A-Z0-9]+$", w) and w not in seen:
            picked.append({"id": w, "name": w, "is_im": False, "user": None}); seen.add(w)   # raw id we can't list
    if cfg.get("dms"):
        for c in convos:
            if c.get("is_im") and c["id"] not in seen:
                picked.append({"id": c["id"], "name": "dm:" + (c.get("user") or c["id"]), "is_im": True, "user": c.get("user")})
                seen.add(c["id"])
    return picked


def _user_name(uid):
    """Display name for a Slack user id (cached). Falls back to the id; never raises."""
    if not uid: return ""
    if uid in _USERS: return _USERS[uid]
    d = _api("users.info", {"user": uid})
    nm = uid
    if d.get("ok"):
        u = d.get("user") or {}; pr = u.get("profile") or {}
        nm = pr.get("display_name") or pr.get("real_name") or u.get("real_name") or u.get("name") or uid
    _USERS[uid] = nm
    return nm


def _permalink(channel_id, ts):
    """Best-effort real permalink for a message; falls back to a stable slack:// ref. Never raises."""
    if _cfg().get("permalinks") is False:
        return "slack://%s/%s" % (channel_id, ts)
    d = _api("chat.getPermalink", {"channel": channel_id, "message_ts": ts})
    if d.get("ok") and d.get("permalink"): return d["permalink"]
    return "slack://%s/%s" % (channel_id, ts)


# ---- map a channel to a client subject (mirrors granola's client_map) ----------------------------------
def map_subject(channel_id, channel_name):
    """Best client subject for a channel via cc.config slack.client_map ({subject: [id/name/alias,...]}).
    Returns the client subject string or None (then the event is ingested with subject=None)."""
    cmap = _cfg().get("client_map") or {}
    hay = (str(channel_id or "") + " " + str(channel_name or "")).lower()
    for subject, aliases in cmap.items():
        for a in ([subject] + list(aliases or [])):
            if a and str(a).lower() in hay:
                return subject
    return None


# ---- read (no writes; no context dependency) -----------------------------------------------------------
def read_channels(limit=None):
    """Return metadata for the configured channels/DMs we will read: [{id,name,is_im}]. [] when unconfigured."""
    if not configured(): return []
    out = []
    for c in _resolve_channels():
        out.append({"id": c["id"], "name": c["name"], "is_im": bool(c.get("is_im")),
                    "subject": map_subject(c["id"], c["name"])})
    return out


def read_recent(limit=None):
    """Pull recent messages across the configured channels/DMs. Returns a flat list of normalized messages:
    [{channel, channel_name, ts, epoch, user, user_name, text, thread_ts, is_im, subject, permalink}].
    [] when unconfigured or on any API error (graceful)."""
    if not configured(): return []
    lim = int(limit or _cfg().get("limit") or 50)
    msgs = []
    for c in _resolve_channels():
        d = _api("conversations.history", {"channel": c["id"], "limit": lim})
        if not d.get("ok"): continue
        subject = map_subject(c["id"], c["name"])
        for m in d.get("messages", []):
            if m.get("type") != "message" or m.get("subtype") in ("channel_join", "channel_leave"): continue
            text = (m.get("text") or "").strip()
            if not text: continue
            uid = m.get("user") or m.get("bot_id") or ""
            ts = m.get("ts") or ""
            msgs.append({"channel": c["id"], "channel_name": c["name"], "ts": ts,
                         "epoch": _epoch(ts), "user": uid, "user_name": _user_name(uid) if m.get("user") else uid,
                         "text": text, "thread_ts": m.get("thread_ts"), "is_im": bool(c.get("is_im")),
                         "subject": subject, "permalink": _permalink(c["id"], ts)})
    return msgs


def _epoch(ts):
    try: return float(ts)
    except Exception: return None


def _title(m):
    """Human title for an event: '#channel' or 'DM' (+ a thread tag for replies)."""
    base = ("DM" if m.get("is_im") else "#" + str(m.get("channel_name") or m.get("channel")))
    if m.get("thread_ts") and m.get("thread_ts") != m.get("ts"):
        base += " (thread)"
    return base


# ---- ingest into the context store (idempotent; trust=contact) -----------------------------------------
def ingest(context, limit=None):
    """For each recent message, write a context event. Idempotent on ext_id='<channel>:<ts>', so it can run
    on boot + every backfill cycle without duplicating. Returns the count of events written/seen.
    Slack content is UNTRUSTED -> trust='contact' (data, not instructions). Graceful no-op when unconfigured."""
    if not configured(): return 0
    n = 0
    for m in read_recent(limit):
        try:
            context.ingest_event(kind="slack", source="slack", title=_title(m), body=m["text"],
                                 ts=m.get("epoch"), actor=(m.get("user_name") or m.get("user") or None),
                                 subject=m.get("subject"), trust="contact",
                                 ext_id="%s:%s" % (m["channel"], m["ts"]),
                                 refs={"permalink": m.get("permalink"), "channel": m["channel"],
                                       "thread_ts": m.get("thread_ts")})
            n += 1
        except Exception:
            continue
    return n


def save_thread(context, channel, ts, subject=None):
    """Capture a SPECIFIC thread (channel + parent ts) to a subject: ingest the parent + every reply as
    context events (trust='contact'). Resolves the channel id from a name if needed. Returns {ok, saved}."""
    if not _token(): return {"ok": False, "error": "not_configured"}
    cid = channel
    if not re.match(r"^[CGD][A-Z0-9]+$", str(channel or "")):
        c = next((x for x in _resolve_channels() if (x.get("name") or "").lower() == str(channel).lower()), None)
        if c: cid = c["id"]
    d = _api("conversations.replies", {"channel": cid, "ts": ts, "limit": 200})
    if not d.get("ok"): return {"ok": False, "error": d.get("error", "replies_failed")}
    subj = subject or map_subject(cid, "")
    saved = 0
    for m in d.get("messages", []):
        text = (m.get("text") or "").strip()
        if not text: continue
        mts = m.get("ts") or ""
        try:
            context.ingest_event(kind="slack", source="slack", title="#%s (thread)" % cid, body=text,
                                 ts=_epoch(mts), actor=(_user_name(m.get("user")) if m.get("user") else None),
                                 subject=subj, trust="contact", ext_id="%s:%s" % (cid, mts),
                                 refs={"permalink": _permalink(cid, mts), "channel": cid, "thread_ts": ts})
            saved += 1
        except Exception:
            continue
    return {"ok": True, "saved": saved, "subject": subj}


# ---- standalone (validation / debugging; NEVER prints the token) ---------------------------------------
def _selftest():
    """Offline check: client_map mapping + title rendering work with no token/network."""
    _CTX["CC"] = {"slack": {"client_map": {"acme": ["C0ACME", "acme-team"]}}}
    assert map_subject("C0ACME", "acme-team") == "acme", "client_map id/name match"
    assert map_subject("C9ZZZ", "random") is None, "no false match"
    assert configured() is False, "no token -> not configured"
    assert read_recent() == [] and ingest(None) == 0, "graceful no-op when unconfigured"
    assert _title({"channel_name": "eng", "is_im": False}) == "#eng"
    assert _title({"is_im": True}) == "DM"
    assert _title({"channel_name": "eng", "ts": "1.2", "thread_ts": "1.0"}) == "#eng (thread)"
    print("SELFTEST OK (offline: client_map + graceful no-op + titles)")
    return True


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "selftest":
        _selftest()
    elif cmd == "status":
        # connectivity check WITHOUT ever revealing the token
        ok = bool(_token())
        info = {"has_token": ok, "configured": configured(),
                "channels": [c.get("name") for c in (read_channels() if ok else [])]}
        if ok:
            a = _api("auth.test")
            info["auth_ok"] = bool(a.get("ok")); info["team"] = a.get("team"); info["bot"] = a.get("user")
            if not a.get("ok"): info["auth_error"] = a.get("error")
        print(json.dumps(info, indent=1))
    elif cmd == "recent":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        print(json.dumps(read_recent(n), indent=1, default=str))
    else:
        print("usage: slack.py [status|recent [n]|selftest]")
