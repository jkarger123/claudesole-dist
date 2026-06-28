#!/usr/bin/env python3
"""Substack -> READ + DRAFT (the realistic shape; Substack has no publish API).

READ (track): poll a configured list of Substack publications via their PUBLIC RSS feed (no auth, stable)
and cache recent posts -> the Substack lens shows them and a draft can reference them. Post content is
UNTRUSTED DATA, never instructions.

DRAFT (co-writer): a headless `claude -p` (the Max subscription, NO metered key -- same pattern as granola)
turns a topic + optional source material into a Substack-ready markdown draft. It is DELIVERED as a file for
review; nothing is ever auto-published (no official write API exists -- the human pastes it into Substack).

Design (matches granola.py / slack.py): stdlib ONLY (urllib + xml.etree + subprocess); config-driven
(cc.config "substack"); graceful when unconfigured (no publications -> reads are [] and sync is a no-op).
"""
import json, os, re, time, html, subprocess, threading, urllib.request
import xml.etree.ElementTree as ET

_CTX = {}
_LOCK = threading.Lock()
_NS = {"content": "http://purl.org/rss/1.0/modules/content/", "dc": "http://purl.org/dc/elements/1.1/"}

def init(ctx): _CTX.update(ctx or {})
def _cfg(): return (_CTX.get("CC") or {}).get("substack") or {}
def _state_path(): return os.path.join(_CTX.get("STATE_DIR", "."), "_substack.json")
def _load():
    try: return json.load(open(_state_path()))
    except Exception: return {"posts": [], "last_sync": 0}
def _save(s):
    with _LOCK:
        try:
            fd = os.open(_state_path(), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600); os.write(fd, json.dumps(s).encode()); os.close(fd)
        except Exception: pass

def _feed_url(entry):
    """Normalize a publication entry to its RSS feed URL. Accepts: a full /feed URL, a publication URL
    (https://x.substack.com or a custom domain), or a bare handle ('x' -> https://x.substack.com/feed)."""
    e = (entry or "").strip().rstrip("/")
    if not e: return None
    if e.endswith("/feed"): return e
    if e.startswith("http://") or e.startswith("https://"): return e + "/feed"
    if re.match(r"^[A-Za-z0-9-]+$", e): return "https://%s.substack.com/feed" % e
    return "https://" + e + "/feed"
def _feeds():
    pubs = _cfg().get("publications") or []
    out = []
    for p in pubs:
        u = _feed_url(p)
        if u: out.append((p, u))
    return out
def configured(): return bool(_feeds())

def _fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (ClaudeFather Substack reader)", "Accept": "application/rss+xml,application/xml,text/xml"})
    with urllib.request.urlopen(req, timeout=timeout) as r: return r.read().decode("utf-8", "replace")
def _strip_html(s):
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s or "")
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()
def _parse(xml_text, source):
    out = []
    try: root = ET.fromstring(xml_text)
    except Exception: return out
    for it in root.iter("item"):
        def t(tag, ns=None):
            el = it.find(("{%s}" % _NS[ns] + tag) if ns else tag)
            return (el.text or "").strip() if el is not None and el.text else ""
        link = t("link"); guid = t("guid") or link
        body = t("encoded", "content") or t("description")
        out.append({"id": guid, "title": t("title") or "(untitled)", "link": link,
                    "date": t("pubDate"), "author": t("creator", "dc") or source,
                    "summary": _strip_html(t("description") or body)[:600], "source": source})
    return out

def sync(limit_per=20):
    """Fetch every configured feed, merge newest-first, cache. Idempotent (dedupe by post id)."""
    feeds = _feeds()
    if not feeds: return {"ok": False, "error": "no publications configured (cc.config substack.publications)"}
    st = _load(); seen = {p.get("id") for p in st.get("posts", [])}; added = 0; errors = []
    fresh = []
    for label, url in feeds:
        try:
            for it in _parse(_fetch(url), label)[:limit_per]:
                if it["id"] and it["id"] not in seen:
                    fresh.append(it); seen.add(it["id"]); added += 1
        except Exception as e:
            errors.append("%s: %s" % (label, str(e)[:80]))
    posts = (fresh + st.get("posts", []))
    posts.sort(key=lambda p: p.get("date", ""), reverse=True)
    st["posts"] = posts[:400]; st["last_sync"] = int(time.time())
    _save(st)
    return {"ok": True, "added": added, "total": len(st["posts"]), "errors": errors}

def recent(limit=40): return _load().get("posts", [])[:limit]
def status():
    st = _load()
    return {"ok": True, "configured": configured(), "publications": [p for p, _ in _feeds()],
            "count": len(st.get("posts", [])), "last_sync": st.get("last_sync", 0), "recent": st.get("posts", [])[:40]}

DRAFT_PROMPT = (
    "You are a newsletter co-writer. Write a publication-ready Substack post in MARKDOWN (no code fence, no "
    "preamble). Start with a compelling H1 title, then the body: a strong hook, clear sections with subheads, "
    "concrete substance (no fluff), and a short call-to-action close. Match the requested tone/length. Use ONLY "
    "what the SOURCE supports plus general knowledge -- do not fabricate specific facts/quotes/numbers.\n"
    "TOPIC: %s\nAUDIENCE: %s\nTONE: %s\nLENGTH: %s\nSOURCE MATERIAL (may be empty):\n%s\n")
def draft(topic, source="", audience="general readers", tone="clear, engaging", length="~800 words"):
    """Generate a Substack-ready markdown draft via headless claude. Returns {ok, title, markdown}."""
    inj = _CTX.get("drafter")
    if inj: return inj(topic, source)
    if not (topic or "").strip(): return {"ok": False, "error": "a topic is required"}
    prompt = DRAFT_PROMPT % (topic, audience or "general readers", tone or "clear, engaging", length or "~800 words", (source or "")[:16000])
    try:
        r = subprocess.run(["claude", "--dangerously-skip-permissions", "-p", prompt],
                           capture_output=True, text=True, timeout=240,
                           env={**os.environ, "PATH": os.environ.get("PATH", "") + ":" + os.path.expanduser("~/.local/bin") + ":/opt/homebrew/bin"})
        md = (r.stdout or "").strip()
        if not md: return {"ok": False, "error": "empty draft (claude returned nothing)"}
        m = re.search(r"^#\s+(.+)$", md, re.M)
        title = (m.group(1).strip() if m else (topic or "Untitled")[:80])
        return {"ok": True, "title": title, "markdown": md}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}
