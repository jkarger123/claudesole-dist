#!/usr/bin/env python3
"""Scan a Claude Code projects dir (~/.claude/projects) -> JSON list of past conversations, newest first.
Fast: stat+sort all transcripts by mtime, then parse the HEAD of only the most-recent `limit` files
(cwd = the launch dir, sessionId = resume id, first user message = label, gitBranch).
Usage: scan_projects.py <projects_base_dir> [limit]   -- prints a JSON array.
Runs identically on macOS (Studio) and Windows (T490/T480) under python3."""
import json, os, sys, glob

base = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.claude/projects")
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 150

# 1) cheap pass: every transcript file + its mtime (skip subagent transcripts)
files = []
if os.path.isdir(base):
    for slug in os.listdir(base):
        d = os.path.join(base, slug)
        if not os.path.isdir(d):
            continue
        for f in glob.glob(os.path.join(d, "*.jsonl")):
            if "subagent" in os.path.basename(f).lower():
                continue
            try:
                files.append((os.path.getmtime(f), f, slug))
            except Exception:
                pass
files.sort(key=lambda t: -t[0])

# 2) parse the head of only the most-recent `limit` files
out = []
for mt, f, slug in files[:limit]:
    cwd = sid = label = branch = None
    try:
        with open(f, "r", encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i > 80:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                cwd = cwd or o.get("cwd")
                sid = sid or o.get("sessionId")
                branch = branch or o.get("gitBranch")
                if label is None:
                    m = o.get("message", {}) or {}
                    if m.get("role") == "user":
                        c = m.get("content")
                        if isinstance(c, list):
                            c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                        c = str(c or "").strip()
                        if c and not c.startswith("<") and not c.startswith("Caveat") and not c.startswith("[Request"):
                            label = c[:100]
                if cwd and sid and label:
                    break
    except Exception:
        continue
    out.append({
        "id": sid or os.path.basename(f)[:-6],
        "cwd": cwd or slug.replace("-", "/"),
        "label": label or "(no opening message)",
        "mtime": mt,
        "branch": branch or "",
    })
print(json.dumps(out))
