#!/usr/bin/env python3
"""ClaudeFather per-action POLICY ENGINE (ALLOW / DENY / ASK) -- the mechanism that replaces prose HARD RULEs.

Deep-audit 2026-07-09 graft G1 (from OmniAgent's fail-closed policy engine). Pure stdlib, NO server import --
so the Claude Code PreToolUse hook (policy_hook.py) AND the server can both use it, and it is unit-testable in
isolation. This module is the ENGINE only; wiring (the hook settings, /api/policy-evaluate, making the
auto-approve loop policy-aware) is a later increment.

Model: a policy is a function (tool, tool_input, ctx) -> Verdict | None. `None` = no opinion. evaluate() runs
every applicable policy and takes the STRICTEST result -- any DENY short-circuits the action; else any ASK
parks it for a human; else ALLOW. FAIL-CLOSED: an exception inside a policy is treated as ASK, never a silent
ALLOW. Only builtins registered in POLICY_REGISTRY run (an allowlist -- a compromised extension can't inject a
policy that weakens the gate).
"""
import re, json, sys

ALLOW, DENY, ASK = "allow", "deny", "ask"
_RANK = {ALLOW: 0, ASK: 1, DENY: 2}


class Verdict:
    def __init__(self, decision, rule, reason):
        self.decision, self.rule, self.reason = decision, rule, reason
    def as_dict(self):
        return {"decision": self.decision, "rule": self.rule, "reason": self.reason}


def _bash_cmd(tool, inp):
    return ((inp.get("command") if (tool == "Bash" and isinstance(inp, dict)) else "") or "")


# ---- BUILTINS -------------------------------------------------------------------------------------------
# Each returns a Verdict to object, or None to abstain. Keep them narrow + evidence-based; false DENYs erode trust.

_BLAST = [
    (r"\bgit\s+push\b[^\n]*(--force\b|--force-with-lease\b|\s-f\b)", "force-push (rewrites shared history)"),
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard (discards the working tree -- the dirty-tree guardrail)"),
    (r"\bgit\s+clean\b[^\n]*-[a-zA-Z]*f", "git clean -f (deletes untracked files)"),
    (r"\bgit\s+add\s+(-A\b|--all\b|\.\s*(&&|;|\||$))", "git add -A/. on the dirty tree (guardrail: stage explicit paths)"),
    (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f?[a-zA-Z]*\s+(/|~|\$HOME|\*)(\s|/|$)", "rm -rf of a root/home/glob path"),
    (r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "fork bomb"),
    (r"\bmkfs\b|\bdd\s+[^\n]*of=/dev/", "disk-destroying command"),
    (r"\btmux\s+kill-server\b", "tmux kill-server (nukes the shared brain tmux -> every node + chief at once)"),
]
def blast_radius(tool, inp, ctx):
    cmd = _bash_cmd(tool, inp)
    for pat, why in _BLAST:
        if re.search(pat, cmd):
            return Verdict(DENY, "blast_radius", "blocked destructive op: " + why)
    return None


_CRED_PAT = re.compile(r"auth_token|mesh_token|superadmin|\.vault\b|vault[_-]?set|cc_auth|/api/(config|vault-set|core-sign|superadmin)", re.I)
def credential_guard(tool, inp, ctx):
    """Any action that could change a credential / the signing surface -> human ASK. The PIN/auth-token rule
    ('never change auth_token/mesh_token without confirming') enforced as a MECHANISM, not a paragraph."""
    blob = _bash_cmd(tool, inp)
    if tool in ("Edit", "Write") and isinstance(inp, dict):
        blob += " " + str(inp.get("file_path", "")) + " " + str(inp.get("new_string", "")) + " " + str(inp.get("content", ""))
    if _CRED_PAT.search(blob):
        return Verdict(ASK, "credential_guard", "touches a credential / signing surface -- needs operator confirmation")
    return None


_MUTATE = re.compile(r"(^|[\s;&|])(rm|mv|cp|mkdir|touch|tee|chmod|chown|sed\s+-i|git\s+(commit|push|add|reset|rm|checkout))\b|>>?\s*\S")
def read_only_os(tool, inp, ctx):
    """Agents flagged read_only (reviewers/auditors/scouts) may READ but never mutate the filesystem/repo."""
    if not ctx.get("read_only"):
        return None
    if tool in ("Write", "Edit", "NotebookEdit"):
        return Verdict(DENY, "read_only_os", "read-only agent may not edit files")
    cmd = _bash_cmd(tool, inp)
    if cmd and _MUTATE.search(cmd):
        return Verdict(DENY, "read_only_os", "read-only agent may not run a mutating shell command")
    return None


_OS_TOOLS = re.compile(r"(^|[\s;&|])(sudo|launchctl|systemctl|defaults\s+write|pmset|scutil|networksetup|killall|kextload|csrutil|spctl)\b")
def ask_on_os_tools(tool, inp, ctx):
    """System-level OS changes -> ASK (unless the agent is explicitly trusted for them via ctx.trust_os)."""
    if ctx.get("trust_os"):
        return None
    cmd = _bash_cmd(tool, inp)
    if cmd and _OS_TOOLS.search(cmd):
        return Verdict(ASK, "ask_on_os_tools", "system-level command -- confirm before running")
    return None


def spawn_bounds(tool, inp, ctx):
    """Cap runaway agent fan-out (borrowed from OmniAgent's spawn_bounds). Uses ctx.spawn_count/spawn_cap the
    caller supplies, plus a heuristic for a single command launching many headless agents."""
    cap = int(ctx.get("spawn_cap", 12))
    if int(ctx.get("spawn_count", 0)) >= cap:
        return Verdict(DENY, "spawn_bounds", "agent spawn cap reached (%d live)" % cap)
    cmd = _bash_cmd(tool, inp)
    if cmd and len(re.findall(r"\bclaude\b[^\n]*--dangerously-skip-permissions", cmd)) >= 3:
        return Verdict(ASK, "spawn_bounds", "command launches several agent sessions at once")
    return None


POLICY_REGISTRY = {
    "blast_radius": blast_radius,
    "credential_guard": credential_guard,
    "read_only_os": read_only_os,
    "ask_on_os_tools": ask_on_os_tools,
    "spawn_bounds": spawn_bounds,
}
DEFAULT_POLICIES = list(POLICY_REGISTRY.keys())


def evaluate(tool, tool_input, ctx=None, policies=None):
    """Run the applicable policies and return the STRICTEST verdict as a dict {decision, rule, reason}.
    policies=None -> the full default set; pass a subset (stricter-only stacking is the caller's job)."""
    ctx = ctx or {}
    names = policies if policies is not None else DEFAULT_POLICIES
    verdicts = []
    for name in names:
        fn = POLICY_REGISTRY.get(name)
        if not fn:
            continue
        try:
            v = fn(tool, tool_input or {}, ctx)
        except Exception as e:
            v = Verdict(ASK, name, "policy error (fail-closed to ASK): " + str(e)[:80])
        if v:
            verdicts.append(v)
    if not verdicts:
        return Verdict(ALLOW, "default", "no policy objected").as_dict()
    best = max(verdicts, key=lambda v: _RANK[v.decision])
    return best.as_dict()


if __name__ == "__main__":
    # `cc_policy.py --selftest` -> run the assertions; else read a PreToolUse-shaped JSON on stdin and print a verdict.
    if "--selftest" in sys.argv:
        C = lambda **k: k
        cases = [
            # (tool, input, ctx, expected_decision, label)
            ("Bash", {"command": "git push --force origin main"}, {}, DENY, "force-push"),
            ("Bash", {"command": "git push -f"}, {}, DENY, "force-push short"),
            ("Bash", {"command": "git add -A"}, {}, DENY, "git add -A"),
            ("Bash", {"command": "git add . && git commit"}, {}, DENY, "git add . chained"),
            ("Bash", {"command": "git add command-center/server.py"}, {}, ALLOW, "explicit git add is fine"),
            ("Bash", {"command": "rm -rf ~/stuff"}, {}, DENY, "rm -rf home"),
            ("Bash", {"command": "rm -rf ./build"}, {}, ALLOW, "rm -rf a local dir is fine"),
            ("Bash", {"command": "tmux kill-server"}, {}, DENY, "kill-server"),
            ("Edit", {"file_path": "cc.config.json", "new_string": "\"auth_token\": \"9999\""}, {}, ASK, "auth_token edit"),
            ("Bash", {"command": "curl -X POST /api/vault-set -d ..."}, {}, ASK, "vault-set"),
            ("Bash", {"command": "sudo launchctl kickstart -k system/foo"}, {}, ASK, "sudo/launchctl"),
            ("Write", {"file_path": "x.py", "content": "print(1)"}, {"read_only": True}, DENY, "read-only agent writes"),
            ("Bash", {"command": "rm notes.txt"}, {"read_only": True}, DENY, "read-only agent mutates"),
            ("Bash", {"command": "grep -r foo ."}, {"read_only": True}, ALLOW, "read-only agent reads"),
            ("Read", {"file_path": "a.py"}, {}, ALLOW, "plain read"),
            ("Bash", {"command": "ls -la"}, {}, ALLOW, "benign command"),
            ("Bash", {"command": "echo hi"}, {"spawn_count": 20, "spawn_cap": 12}, DENY, "spawn cap"),
        ]
        ok = 0
        for tool, inp, ctx, exp, label in cases:
            v = evaluate(tool, inp, ctx)
            status = "ok " if v["decision"] == exp else "FAIL"
            if v["decision"] == exp: ok += 1
            print("  [%s] %-28s -> %-5s (%s)%s" % (status, label, v["decision"], v["rule"],
                  "" if v["decision"] == exp else "  EXPECTED " + exp))
        print("\n%d/%d passed" % (ok, len(cases)))
        sys.exit(0 if ok == len(cases) else 1)
    else:
        try:
            payload = json.loads(sys.stdin.read() or "{}")
        except Exception:
            payload = {}
        print(json.dumps(evaluate(payload.get("tool") or payload.get("tool_name", ""),
                                  payload.get("input") or payload.get("tool_input", {}),
                                  payload.get("ctx", {}))))
