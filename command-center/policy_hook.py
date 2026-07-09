#!/usr/bin/env python3
"""Claude Code PreToolUse hook -> ClaudeFather policy engine (deep-audit graft G1).

A THIN, BULLETPROOF relay: read the tool call on stdin, ask THIS node's server (/api/policy-evaluate) for a
decision, emit Claude Code's PreToolUse permission decision. FAIL-OPEN by construction -- ANY error, timeout,
or unreachable server -> `allow`. A hook bug must NEVER block an agent (this is what makes the rollout safe:
during the default log-only phase the server always returns allow anyway, and even if it didn't, this hook
degrades to allow). Enforcement policy lives SERVER-SIDE (POLICY_ENFORCE); this hook never decides on its own.
"""
import sys, json, os, urllib.request


def _emit(decision, reason=""):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                      "permissionDecision": decision, "permissionDecisionReason": reason}}))
    sys.exit(0)


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return _emit("allow", "policy hook: unreadable input (fail-open)")
    base = (os.environ.get("CC_NOTIFY") or os.environ.get("MESH_CC") or "http://127.0.0.1:8799").rstrip("/")
    try:
        ctx = json.loads(os.environ.get("CC_POLICY_CTX") or "{}")   # per-session profile the launch set (e.g. {"read_only":true})
    except Exception:
        ctx = {}
    body = json.dumps({
        "session": data.get("session_id") or data.get("session") or "",
        "tool": data.get("tool_name") or data.get("tool") or "",
        "input": data.get("tool_input") or data.get("input") or {},
        "cwd": data.get("cwd") or "",
        "ctx": ctx,
    }).encode()
    try:
        req = urllib.request.Request(base + "/api/policy-evaluate", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            res = json.loads(r.read().decode())
    except Exception:
        return _emit("allow", "policy hook: server unreachable (fail-open)")
    decision = str(res.get("permissionDecision") or "allow").lower()
    if decision not in ("allow", "deny", "ask"):
        decision = "allow"
    return _emit(decision, res.get("reason") or "")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _emit("allow", "policy hook: unexpected error (fail-open)")
