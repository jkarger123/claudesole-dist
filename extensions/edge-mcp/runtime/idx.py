#!/usr/bin/env python3
"""idx.py -- run a JS file (or a tool call) against a warm edge MCP server, no shell escaping.
  idx.py <server> exec <file.js> [description]
  idx.py <server> call <tool> '<json-args>'
"""
import sys, json
import edge_mcpd as M

sid = sys.argv[1]; op = sys.argv[2]
if op == "exec":
    code = open(sys.argv[3]).read()
    desc = (sys.argv[4] if len(sys.argv) > 4 else "ClaudeFather build") + "\nManual: n/a"
    r = M._client(sid, {"op": "call", "tool": "execute", "args": {"code": code, "description": desc}}, timeout=600)
else:
    tool = sys.argv[3]; args = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
    r = M._client(sid, {"op": "call", "tool": tool, "args": args}, timeout=600)
print(r.get("text") if isinstance(r, dict) and r.get("text") else json.dumps(r, indent=2))
