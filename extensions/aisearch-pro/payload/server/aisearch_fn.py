#!/usr/bin/env python3
"""
AISearch Pro -- ClaudeFather server-function entry script.

Faithful Python (stdlib-only) port of the `analyze` and `compare` logic from the
Cloudflare Worker (`_worker.js`). Runs as a subprocess for the ClaudeFather
server-function runtime.

Contract
--------
  * Input  : JSON object on stdin -> {"brand": "...", "query": "...", "competitor": "..."}
             (competitor is only used by `compare`).
  * Action : os.environ["CF_FN"] -> "analyze" | "compare".
  * Keys   : read from os.environ (BYOK, injected by the runtime):
                OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_AI_API_KEY, PERPLEXITY_API_KEY
             A provider is only called when its key is present (mirrors the worker).
             If NO provider key at all is present -> {"ok": false, "error": "missing_api_keys"}.
  * Output : JSON object on stdout (see assemble_* below).
  * Log    : best-effort INSERT into aisearch_requests at os.environ["CF_STORE_DB"].

Stdlib only: urllib, json, os, sys, sqlite3, time, uuid, re, concurrent.futures.

Fidelity notes (see module docstring tail / final report):
  * The simple (non-grounded) provider calls are ported verbatim from the worker's
    queryOpenAI / queryAnthropic / queryGoogle. The worker's `compare` actually uses
    web-search-GROUNDED variants + query expansion + source scraping + journalist
    enrichment; those are explicitly out of scope (and not stdlib-portable), so
    `compare` here reuses the same simple provider calls and ports the faithful
    brand-mention/position/winner analysis (analyzeBrandMentions) from handleCompare.
"""

import os
import re
import sys
import json
import time
import uuid
import sqlite3
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor

# ---------------------------------------------------------------------------
# Constants ported verbatim from the worker
# ---------------------------------------------------------------------------

# _worker.js line 19
SYSTEM_PROMPT = (
    "You are a helpful assistant providing product and brand recommendations. "
    "Give specific, actionable recommendations with brand names when asked about "
    "products or services. Be thorough but concise. Always cite your sources."
)

# Already validated against live keys (per task spec)
OPENAI_MODEL = "gpt-4o"
ANTHROPIC_MODEL = "claude-sonnet-4-5"
GEMINI_MODEL = "gemini-2.5-flash"

HTTP_TIMEOUT = 30  # seconds, per-provider call


# ---------------------------------------------------------------------------
# Small HTTP helper (stdlib urllib)
# ---------------------------------------------------------------------------

def _http_post_json(url, headers, body, timeout=HTTP_TIMEOUT):
    """POST a JSON body, return parsed JSON dict. Raises on transport error.

    On an HTTP error status we still try to parse the JSON body (so we can read
    the provider's {"error": {...}} payload, exactly like the worker does with
    `await response.json()` even on non-2xx).
    """
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8", "replace")
        except Exception:
            raise
    try:
        return json.loads(raw)
    except Exception:
        return {"error": {"message": "non-JSON response: " + raw[:200]}}


def get_api_key(key_string):
    """Port of getApiKey (_worker.js line 22): supports a comma-separated list,
    picks the first non-empty entry (worker picks a random one; first is fine
    and deterministic). Returns None if absent/empty."""
    if not key_string:
        return None
    keys = [k.strip() for k in key_string.split(",") if k.strip()]
    return keys[0] if keys else None


# ---------------------------------------------------------------------------
# Simple per-provider calls (ported from queryOpenAI / queryAnthropic / queryGoogle)
# Each returns: {provider, name, success, text?, error?}
# ---------------------------------------------------------------------------

def query_openai(prompt, api_key):
    name, provider = "GPT-4o", "openai"
    if not api_key:
        return {"provider": provider, "name": name, "success": False, "error": "No API key"}
    try:
        data = _http_post_json(
            "https://api.openai.com/v1/chat/completions",
            {"Content-Type": "application/json",
             "Authorization": "Bearer " + api_key},
            {
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 2000,
                "temperature": 0,
            },
        )
        if data.get("error"):
            return {"provider": provider, "name": name, "success": False,
                    "error": data["error"].get("message") if isinstance(data["error"], dict) else str(data["error"])}
        choices = data.get("choices") or []
        text = ""
        if choices:
            text = (choices[0].get("message") or {}).get("content") or ""
        return {"provider": provider, "name": name, "text": text, "success": True}
    except Exception as e:
        return {"provider": provider, "name": name, "success": False, "error": str(e)}


def query_anthropic(prompt, api_key):
    name, provider = "Claude Sonnet 4", "anthropic"
    if not api_key:
        return {"provider": provider, "name": name, "success": False, "error": "No API key"}
    try:
        data = _http_post_json(
            "https://api.anthropic.com/v1/messages",
            {"Content-Type": "application/json",
             "x-api-key": api_key,
             "anthropic-version": "2023-06-01"},
            {
                "model": ANTHROPIC_MODEL,
                "max_tokens": 2000,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        if data.get("error"):
            return {"provider": provider, "name": name, "success": False,
                    "error": data["error"].get("message") if isinstance(data["error"], dict) else str(data["error"])}
        content = data.get("content") or []
        text = ""
        if content:
            text = content[0].get("text") or ""
        return {"provider": provider, "name": name, "text": text, "success": True}
    except Exception as e:
        return {"provider": provider, "name": name, "success": False, "error": str(e)}


def query_google(prompt, api_key):
    name, provider = "Gemini 2.0", "google"
    if not api_key:
        return {"provider": provider, "name": name, "success": False, "error": "No API key"}
    try:
        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               + GEMINI_MODEL + ":generateContent?key=" + api_key)
        data = _http_post_json(
            url,
            {"Content-Type": "application/json"},
            {
                "contents": [{"parts": [{"text": prompt}]}],
                "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "generationConfig": {"maxOutputTokens": 2000, "temperature": 0},
            },
        )
        if data.get("error"):
            return {"provider": provider, "name": name, "success": False,
                    "error": data["error"].get("message") if isinstance(data["error"], dict) else str(data["error"])}
        text = ""
        cands = data.get("candidates") or []
        if cands:
            parts = ((cands[0].get("content") or {}).get("parts")) or []
            if parts:
                text = parts[0].get("text") or ""
        return {"provider": provider, "name": name, "text": text, "success": True}
    except Exception as e:
        return {"provider": provider, "name": name, "success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Mention analysis
# ---------------------------------------------------------------------------

_LIST_RE = re.compile(r"^\s*(\d+)[.):\-]\s*(.+)", re.MULTILINE)
_BOLD_RE = re.compile(r"\*\*([^*]{3,25})\*\*")


def analyze_mentions(text, brand):
    """Port of analyzeMentions (_worker.js ~2894) -- used by ANALYZE.

    Returns {mentioned, position, competitors[<=5]}.
    position format: "N/M" (1-indexed list position out of total list items).
    """
    brand_lower = brand.lower()
    text_lower = text.lower()
    mentioned = brand_lower in text_lower

    position = None
    list_matches = list(_LIST_RE.finditer(text))
    if len(list_matches) >= 3:
        for i, m in enumerate(list_matches):
            if brand_lower in m.group(2).lower():
                position = "%d/%d" % (i + 1, len(list_matches))
                break

    competitors = []
    seen = set()
    for m in _BOLD_RE.finditer(text):
        nm = m.group(1).strip()
        nl = nm.lower()
        if (nl not in seen
                and brand_lower not in nl
                and re.match(r"[A-Z]", nm)):
            seen.add(nl)
            competitors.append(nm)

    return {"mentioned": mentioned, "position": position, "competitors": competitors[:5]}


def analyze_brand_mentions(text, brand_name):
    """Port of handleCompare's inner analyzeBrandMentions (_worker.js ~3019) -- used by COMPARE.

    Returns {mentioned, position, positionNum, mentionCount, context}.
    position format: "#N of M".
    """
    text_lower = text.lower()
    brand_lower = brand_name.lower()
    mentioned = brand_lower in text_lower

    position = None
    position_num = None
    list_matches = list(_LIST_RE.finditer(text))
    if len(list_matches) >= 3:
        for i, m in enumerate(list_matches):
            if brand_lower in m.group(2).lower():
                position = "#%d of %d" % (i + 1, len(list_matches))
                position_num = i + 1
                break

    mention_count = len(re.findall(re.escape(brand_lower), text_lower))

    context = None
    if mentioned:
        idx = text_lower.find(brand_lower)
        start = max(0, idx - 50)
        end = min(len(text), idx + len(brand_name) + 100)
        context = (("..." if start > 0 else "")
                   + text[start:end].strip()
                   + ("..." if end < len(text) else ""))

    return {
        "mentioned": mentioned,
        "position": position,
        "positionNum": position_num,
        "mentionCount": mention_count,
        "context": context,
    }


# ---------------------------------------------------------------------------
# Provider fan-out helpers (parallel via ThreadPoolExecutor -- mirrors the
# worker's Promise.all concurrency)
# ---------------------------------------------------------------------------

def _present_providers(env):
    """Which simple providers have a key. Returns list of (provider_id, callable, key)."""
    out = []
    okey = env.get("OPENAI_API_KEY")
    akey = env.get("ANTHROPIC_API_KEY")
    gkey = get_api_key(env.get("GOOGLE_AI_API_KEY"))
    if okey:
        out.append(("openai", query_openai, okey))
    if akey:
        out.append(("anthropic", query_anthropic, akey))
    if gkey:
        out.append(("google", query_google, gkey))
    return out


def _any_provider_key(env):
    """The 'no provider key at all' gate. Perplexity counts as a provider key
    (per contract) even though analyze/compare do not call it (faithful to the
    worker, whose simple calls never invoke Perplexity)."""
    return any(env.get(k) for k in (
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_AI_API_KEY", "PERPLEXITY_API_KEY"
    ))


def _run_providers(env, query):
    """Call every present simple provider once, concurrently. Returns list of
    provider result dicts in the canonical order openai, anthropic, google
    (matching the worker's Promise.all ordering)."""
    providers = _present_providers(env)
    if not providers:
        return []
    with ThreadPoolExecutor(max_workers=len(providers)) as ex:
        futures = [(pid, ex.submit(fn, query, key)) for pid, fn, key in providers]
        return [f.result() for _pid, f in futures]


# ---------------------------------------------------------------------------
# ANALYZE
# ---------------------------------------------------------------------------

def do_analyze(env, payload):
    brand = payload.get("brand") or None
    query = payload.get("query")
    if not query:
        return {"ok": False, "error": "Query is required"}, []

    tracking_brand = brand or None
    results = _run_providers(env, query)

    models = []
    all_brands = {}
    mention_count = 0

    for result in results:
        if result.get("success") and tracking_brand:
            analysis = analyze_mentions(result.get("text") or "", tracking_brand)
        else:
            analysis = {"mentioned": False, "position": None, "competitors": []}

        if analysis["mentioned"]:
            mention_count += 1

        for comp in analysis["competitors"]:
            all_brands[comp] = all_brands.get(comp, 0) + 1

        models.append({
            "name": result.get("name"),
            "provider": result.get("provider"),
            "mentioned": analysis["mentioned"] if tracking_brand else None,
            "position": analysis["position"] or ("Mentioned" if analysis["mentioned"] else "Not found"),
            "success": result.get("success", False),
            "error": result.get("error") or None,
            "top_brands": analysis["competitors"][:3],
        })

    success_count = sum(1 for r in results if r.get("success"))
    competitors = [
        {"name": nm, "count": cnt, "total": success_count}
        for nm, cnt in sorted(all_brands.items(), key=lambda kv: kv[1], reverse=True)[:10]
    ]

    out = {
        "brand": tracking_brand,
        "query": query,
        "mode": "track" if tracking_brand else "scan",
        "mention_rate": (mention_count / success_count) if (tracking_brand and success_count > 0) else None,
        "models": models,
        "competitors": competitors,
    }
    providers_used = [r.get("provider") for r in results]
    return out, providers_used


# ---------------------------------------------------------------------------
# COMPARE
# ---------------------------------------------------------------------------

# worker compare provider label map: the simple call returns provider "google",
# but handleCompare buckets Gemini under "gemini".
_COMPARE_PROVIDER_LABEL = {"openai": "openai", "anthropic": "anthropic", "google": "gemini"}


def _winner(brand_a, comp_a):
    """Port of the per-provider winner logic in handleCompare (_worker.js ~3197)."""
    b_m, c_m = brand_a["mentioned"], comp_a["mentioned"]
    if not b_m and not c_m:
        return "neither"
    if b_m and not c_m:
        return "brand"
    if not b_m and c_m:
        return "competitor"
    # both mentioned
    b_pos, c_pos = brand_a["positionNum"], comp_a["positionNum"]
    if b_pos and c_pos:
        if b_pos < c_pos:
            return "brand"
        if b_pos > c_pos:
            return "competitor"
        return "tie"
    if brand_a["mentionCount"] > comp_a["mentionCount"]:
        return "brand"
    if brand_a["mentionCount"] < comp_a["mentionCount"]:
        return "competitor"
    return "tie"


def do_compare(env, payload):
    brand = payload.get("brand")
    competitor = payload.get("competitor")
    query = payload.get("query")
    if not query:
        return {"ok": False, "error": "Query is required"}, []
    if not brand or not competitor:
        return {"ok": False, "error": "Both brand and competitor are required"}, []

    results = _run_providers(env, query)

    provider_analysis = []   # faithful handleCompare per-provider shape
    models = []              # analyze-style array for lens convenience (brand-centric)

    for result in results:
        plabel = _COMPARE_PROVIDER_LABEL.get(result.get("provider"), result.get("provider"))
        if result.get("success"):
            text = result.get("text") or ""
            brand_a = analyze_brand_mentions(text, brand)
            comp_a = analyze_brand_mentions(text, competitor)
            win = _winner(brand_a, comp_a)
            provider_analysis.append({
                "provider": plabel,
                "name": result.get("name"),
                "success": True,
                "brand": {
                    "mentioned": brand_a["mentioned"],
                    "position": brand_a["position"],
                    "positionNum": brand_a["positionNum"],
                    "mentionCount": brand_a["mentionCount"],
                    "context": brand_a["context"],
                },
                "competitor": {
                    "mentioned": comp_a["mentioned"],
                    "position": comp_a["position"],
                    "positionNum": comp_a["positionNum"],
                    "mentionCount": comp_a["mentionCount"],
                    "context": comp_a["context"],
                },
                "winner": win,
                "response_text": text,
                "response_length": len(text),
            })
            models.append({
                "name": result.get("name"),
                "provider": result.get("provider"),
                "mentioned": brand_a["mentioned"],
                "position": brand_a["position"] or ("Mentioned" if brand_a["mentioned"] else "Not found"),
                "success": True,
                "error": None,
                "top_brands": [],
            })
        else:
            provider_analysis.append({
                "provider": plabel,
                "name": result.get("name"),
                "success": False,
                "error": result.get("error") or "No responses received",
            })
            models.append({
                "name": result.get("name"),
                "provider": result.get("provider"),
                "mentioned": None,
                "position": "Not found",
                "success": False,
                "error": result.get("error") or None,
                "top_brands": [],
            })

    # Summary stats (port of _worker.js ~3499-3508 + verdict)
    brand_wins = sum(1 for p in provider_analysis if p.get("winner") == "brand")
    competitor_wins = sum(1 for p in provider_analysis if p.get("winner") == "competitor")
    ties = sum(1 for p in provider_analysis if p.get("winner") == "tie")
    successful = sum(1 for p in provider_analysis if p.get("success"))

    brand_rate = (sum(1 for p in provider_analysis if p.get("success") and p["brand"]["mentioned"]) / successful) if successful > 0 else 0
    comp_rate = (sum(1 for p in provider_analysis if p.get("success") and p["competitor"]["mentioned"]) / successful) if successful > 0 else 0

    if brand_wins > competitor_wins:
        verdict = "%s leads" % brand
    elif competitor_wins > brand_wins:
        verdict = "%s leads" % competitor
    else:
        verdict = "Even match"

    out = {
        "brand": brand,
        "competitor": competitor,
        "query": query,
        # top-level float, per the runtime contract
        "mention_rate": brand_rate,
        "competitor_mention_rate": comp_rate,
        # analyze-style array (brand-centric) for the lens
        "models": models,
        # faithful handleCompare shapes
        "providers": provider_analysis,
        "summary": {
            "brand_mention_rate": str(round(brand_rate * 100)) + "%",
            "competitor_mention_rate": str(round(comp_rate * 100)) + "%",
            "brand_wins": brand_wins,
            "competitor_wins": competitor_wins,
            "ties": ties,
            "verdict": verdict,
        },
    }
    providers_used = [r.get("provider") for r in results]
    return out, providers_used


# ---------------------------------------------------------------------------
# Request log (best-effort)
# ---------------------------------------------------------------------------

def log_request(endpoint, payload, providers_used, latency_ms, success):
    db_path = os.environ.get("CF_STORE_DB")
    if not db_path:
        return
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            conn.execute(
                "INSERT INTO aisearch_requests "
                "(id, created_at, endpoint, brand, competitor, query, "
                " providers_used, cost_total, latency_ms, sources_found, success) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    uuid.uuid4().hex,
                    time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z",
                    endpoint,
                    payload.get("brand"),
                    payload.get("competitor"),
                    payload.get("query"),
                    json.dumps(providers_used or []),
                    0,
                    int(latency_ms),
                    0,
                    1 if success else 0,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        # best-effort: never let a store failure break the response
        pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    start = time.time()
    env = os.environ

    try:
        raw = sys.stdin.read() or "{}"
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    action = (env.get("CF_FN") or "").strip().lower()

    # Gate: no provider key at all
    if not _any_provider_key(env):
        sys.stdout.write(json.dumps({"ok": False, "error": "missing_api_keys"}))
        return

    if action == "compare":
        endpoint = "/api/compare"
        out, providers_used = do_compare(env, payload)
    elif action == "analyze":
        endpoint = "/api/analyze"
        out, providers_used = do_analyze(env, payload)
    else:
        sys.stdout.write(json.dumps({"ok": False, "error": "unknown_action: " + repr(action)}))
        return

    latency_ms = (time.time() - start) * 1000.0
    success = not (isinstance(out, dict) and out.get("ok") is False)

    log_request(endpoint, payload, providers_used, latency_ms, success)

    # echo latency for observability (does not conflict with the worker shape)
    if isinstance(out, dict) and "ok" not in out:
        out.setdefault("latency_ms", int(latency_ms))

    sys.stdout.write(json.dumps(out))


if __name__ == "__main__":
    main()
