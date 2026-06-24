#!/usr/bin/env python3
"""Mesh Stop hook -- the deterministic, instant inter-chief reply forwarder.

Claude Code runs this when a chief FINISHES a turn. If that turn was the chief answering a peer's mesh
message ('[message from X] ...'), we read the chief's EXACT reply from the transcript and forward it to X
over the local Command Center -- instantly, with no screen-scraping and no fixed timeout. On any other
turn (the operator talking to the chief) it is a no-op, so an operator reply is NEVER leaked to a peer.

Wiring: chief sessions launch with `--settings '{"hooks":{"Stop":[...command: mesh_stop_hook.py...]}}'`
and `MESH_CC=http://localhost:<port>` in env. Idempotent per user-message uuid. Fails silent (exit 0).
"""
import sys, os, json, re, time, urllib.request

MSG_RE = re.compile(r"^\s*\[message from ([a-z0-9_\-]+)\]\s*(.*)", re.S | re.I)
DEBUG = os.environ.get("MESH_HOOK_DEBUG")

def _dbg(msg):
    if not DEBUG: return
    try:
        with open(os.path.expanduser("~/.mesh_hook_debug.log"), "a") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def _user_text(e):
    """Return the text of a GENUINE user turn (string content, or text blocks). None for tool-results."""
    if e.get("type") != "user":
        return None
    msg = e.get("message") or {}
    c = msg.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
            return None  # a tool result, not a real user turn
        return "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return None


def _asst_text(e):
    """Return the assistant's visible text for one transcript entry (ignores thinking / tool_use)."""
    if e.get("type") != "assistant":
        return ""
    msg = e.get("message") or {}
    c = msg.get("content")
    if isinstance(c, list):
        return "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    if isinstance(c, str):
        return c
    return ""


def _reply_after(lines, i):
    """Assistant text produced after the user turn at index i, up to the NEXT genuine user turn (tool_results
    in between are part of the same reply). Robust to tool calls inside the reply."""
    parts = []
    for e in lines[i + 1:]:
        if _user_text(e) is not None:        # a genuine user turn (not a tool_result) ends this reply
            break
        t = _asst_text(e)
        if t:
            parts.append(t)
    return "\n".join(parts).strip()


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        _dbg("no payload"); return
    tp = payload.get("transcript_path") or ""
    _dbg("FIRED event=%s tp=%s cc=%s" % (payload.get("hook_event_name"), os.path.basename(tp), os.environ.get("MESH_CC")))
    if not tp or not os.path.exists(tp):
        _dbg("no transcript"); return
    statef = tp + ".meshfwd"
    cc = os.environ.get("MESH_CC") or "http://localhost:8799"

    # Scan for EVERY unforwarded '[message from X]' that now has a reply, and forward it. This does NOT rely on
    # the mesh message being the LAST turn -- so an interleaved task-notification or operator turn can't bury a
    # mesh reply. Retry the scan a few times so a just-finished reply (not yet flushed to JSONL) is caught.
    for _ in range(16):
        try:
            lines = [json.loads(l) for l in open(tp) if l.strip()]
        except Exception:
            time.sleep(0.4); continue
        try:
            done = set(x for x in open(statef).read().split("\n") if x)
        except Exception:
            done = set()
        pending_without_reply = False
        for i, e in enumerate(lines):
            ut = _user_text(e)
            if ut is None:
                continue
            m = MSG_RE.match(ut)
            if not m:
                continue                     # operator turn -> never forwarded
            uid = e.get("uuid") or ("idx%d:%s" % (i, ut[:40]))
            if uid in done:
                continue
            peer = m.group(1)
            reply = _reply_after(lines, i)
            if not reply:
                pending_without_reply = True  # mesh msg seen but reply not produced/flushed yet
                continue
            try:
                data = json.dumps({"to": peer, "text": reply}).encode()
                req = urllib.request.Request(cc + "/api/mesh-reply", data=data,
                                             headers={"Content-Type": "application/json"})
                r = urllib.request.urlopen(req, timeout=8).read()
                with open(statef, "a") as f:
                    f.write(uid + "\n")
                done.add(uid)
                _dbg("FORWARDED to %s (%r) via %s -> %s" % (peer, reply[:40], cc, r[:60]))
            except Exception as e2:
                _dbg("POST FAILED cc=%s err=%s" % (cc, e2))
        if not pending_without_reply:
            return                            # nothing left waiting on a reply
        time.sleep(0.4)
    return


if __name__ == "__main__":
    main()
