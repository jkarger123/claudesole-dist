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


def tail_preview(path, maxlines=15, maxbytes=24000):
    """A terminal-style tail of a conversation: the most recent user/assistant text turns (+ tool-use
    markers), flattened to lines, last `maxlines`. Cheap: reads only the final chunk of the transcript."""
    try:
        sz = os.path.getsize(path)
        with open(path, "rb") as fh:
            if sz > maxbytes:
                fh.seek(sz - maxbytes)
            chunk = fh.read().decode("utf-8", "replace")
    except Exception:
        return []
    lines = []
    for ln in chunk.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            o = json.loads(ln)          # a chunk-truncated first line just fails json -> skipped
        except Exception:
            continue
        m = o.get("message", {}) or {}
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        c = m.get("content")
        parts = []
        if isinstance(c, str):
            parts.append(c)
        elif isinstance(c, list):
            for x in c:
                if not isinstance(x, dict):
                    continue
                t = x.get("type")
                if t == "text":
                    parts.append(x.get("text", ""))
                elif t == "tool_use":
                    parts.append("⏵ " + str(x.get("name", "tool")))
                # tool_result content is large/noisy -> omit from the peek
        txt = "\n".join(p for p in parts if p and p.strip())
        if not txt.strip():
            continue
        pfx = "> " if role == "user" else ""
        for sub in txt.splitlines():
            sub = sub.rstrip()
            if not sub:
                continue
            lines.append((pfx + sub)[:160])
            pfx = ""
    return lines[-maxlines:]


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
        "preview": "\n".join(tail_preview(f)),
    })
print(json.dumps(out))
