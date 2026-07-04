#!/usr/bin/env python3
"""Render an MCP activity JSONL (produced by mcp_proxy_log.py) as a human timeline.
This is the terminal precursor to the dashboard "MCP Activity" lens. Usage:
    python3 view_activity.py <path-to-.jsonl>
"""
import sys, json

path = sys.argv[1]
rows = [json.loads(l) for l in open(path) if l.strip()]

C = {"req": "→", "resp": "←", "notify": "•", "stderr": "…", "life": "⚙", "raw": "?"}
print("time         dir  what")
print("-" * 78)
for r in rows:
    ev = r.get("ev")
    t = (r.get("t") or "")[11:23]
    if ev == "life":
        print("%s  %s  [proxy %s] %s" % (t, C[ev], r.get("msg"),
              ("rc=%s" % r.get("returncode")) if r.get("returncode") is not None else ""))
    elif ev == "stderr":
        print("%s  %s  server: %s" % (t, C[ev], (r.get("preview") or "").strip()))
    elif ev == "req":
        print("%s  %s  %s  id=%s  %s" % (t, C[ev], r.get("method"), r.get("id"),
              (r.get("preview") or "")[:60]))
    elif ev == "notify":
        print("%s  %s  %s" % (t, C[ev], r.get("method")))
    elif ev == "resp":
        tag = "ERROR" if r.get("is_error") else "ok"
        dt = ("%.0fms" % r["dt_ms"]) if r.get("dt_ms") is not None else "?"
        print("%s  %s  %-14s id=%s  %6s  %-5s %s" % (t, C[ev], (r.get("method") or ""),
              r.get("id"), dt, tag, (r.get("preview") or "")[:52]))

# quick per-method latency summary
lat = {}
for r in rows:
    if r.get("ev") == "resp" and r.get("dt_ms") is not None:
        lat.setdefault(r.get("method") or "?", []).append(r["dt_ms"])
if lat:
    print("\nlatency by method:")
    for m, xs in sorted(lat.items(), key=lambda kv: -max(kv[1])):
        print("  %-16s calls=%d  min=%.0f  max=%.0f  avg=%.0fms" % (
            m, len(xs), min(xs), max(xs), sum(xs) / len(xs)))
