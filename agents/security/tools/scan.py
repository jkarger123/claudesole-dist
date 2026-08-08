#!/usr/bin/env python3
# Security posture scan for the control center. Read-only. Stdlib only.
# Writes reports/latest.json (+ a dated copy) that the Security lens renders.
# Degrades gracefully: if a scanner (gitleaks/trufflehog/osv-scanner/...) is not installed,
# the check reports 'info' with an install hint instead of failing.
import json, os, re, shutil, subprocess, sys, time

HOME = os.path.expanduser("~")
DEFAULT_REPO = ""   # neutral last-resort; _project_root() prefers cc.config project_root / env
HERE = os.path.dirname(os.path.abspath(__file__))
AGENT_DIR = os.path.dirname(HERE)
REPORTS = os.path.join(AGENT_DIR, "reports")
# framework layout: <CC_HOME>/agents/security/tools/scan.py ; <CC_HOME>/bin holds the scanners.
CC_HOME = os.path.dirname(os.path.dirname(AGENT_DIR))
os.environ["PATH"] = os.path.join(CC_HOME, "bin") + os.pathsep + os.environ.get("PATH", "")

def _project_root():
    """Portable: the target project comes from cc.config.json / env / --repo, never hardcoded."""
    cfg = os.path.join(CC_HOME, "cc.config.json")
    if os.path.isfile(cfg):
        try:
            r = json.load(open(cfg)).get("project_root")
            if r: return os.path.expanduser(r)
        except Exception: pass
    return os.environ.get("CC_PROJECT_ROOT", DEFAULT_REPO)

def run(cmd, timeout=60):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, "not found"
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except Exception as e:
        return 1, str(e)

def have(b): return shutil.which(b) is not None

CHECKS = []
def add(dim, cid, sev, title, detail, evidence=""):
    CHECKS.append({"dim": dim, "id": cid, "sev": sev, "title": title,
                   "detail": detail, "evidence": evidence[:600]})

def git(repo, *a, timeout=30):
    return run(["git", "-C", repo] + list(a), timeout=timeout)

# ---------------- Secrets ----------------
def scan_secrets(repo):
    if have("gitleaks"):
        rc, out = run(["gitleaks", "git", repo, "--no-banner", "--redact"], timeout=180)
        if rc == 0:   add("Secrets", "A1-gitleaks", "ok", "gitleaks: no secrets in history", "Working tree + git history clean.", out[-300:])
        elif rc == 1: add("Secrets", "A1-gitleaks", "err", "gitleaks: secrets found", "gitleaks matched credential patterns in the repo/history. Rotate, then scrub history.", out[-500:])
        else:         add("Secrets", "A1-gitleaks", "warn", "gitleaks: scan error", "gitleaks ran but errored.", out[-300:])
    else:
        add("Secrets", "A1-gitleaks", "info", "gitleaks not installed", "Install for history secret-scanning: brew install gitleaks", "")
    if have("trufflehog"):
        rc, out = run(["trufflehog", "git", "file://" + repo, "--only-verified", "--no-update", "--fail"], timeout=240)
        if rc == 0:    add("Secrets", "A2-trufflehog", "ok", "trufflehog: no LIVE secrets", "No verified/live credentials detected.", out[-200:])
        elif rc == 183:add("Secrets", "A2-trufflehog", "err", "trufflehog: LIVE secret(s)", "A credential that STILL WORKS is in the repo. Revoke at the provider NOW.", out[-400:])
        else:          add("Secrets", "A2-trufflehog", "warn", "trufflehog: inconclusive", "Ran but did not cleanly verify (network needed to validate).", out[-200:])
    else:
        add("Secrets", "A2-trufflehog", "info", "trufflehog not installed", "Install to verify whether leaked keys are still LIVE: brew install trufflehog", "")
    # .env hygiene
    envp = os.path.join(repo, ".env")
    if os.path.exists(envp):
        tracked = git(repo, "ls-files", "--error-unmatch", ".env")[0] == 0
        ignored = git(repo, "check-ignore", ".env")[0] == 0
        try: mode = oct(os.stat(envp).st_mode & 0o777)[-3:]
        except Exception: mode = "?"
        if tracked: add("Secrets", "A4-env", "err", ".env is tracked by git", "The .env file is committed -- remove from the index and rotate anything in it.", "tracked=yes")
        elif not ignored: add("Secrets", "A4-env", "warn", ".env not gitignored", "Add .env to .gitignore so it can never be committed.", "ignored=no")
        elif mode not in ("600", "400"): add("Secrets", "A4-env", "warn", ".env is over-permissive (%s)" % mode, "Tighten: chmod 600 .env", "mode=%s" % mode)
        else: add("Secrets", "A4-env", "ok", ".env hygiene", "Ignored, untracked, mode %s." % mode, "")
    # commit gate
    hook = os.path.join(repo, ".git", "hooks", "pre-commit")
    if os.path.exists(hook):
        body = open(hook, "r", errors="ignore").read()
        if "gitleaks" in body or "secret" in body.lower(): add("Secrets", "A3-gate", "ok", "pre-commit secret gate present", "A pre-commit hook references secret scanning.", "")
        else: add("Secrets", "A3-gate", "warn", "pre-commit hook present but no secret gate", "Add gitleaks to the pre-commit hook.", "")
    else:
        add("Secrets", "A3-gate", "warn", "no pre-commit secret gate", "Install a gitleaks pre-commit + pre-push hook so secrets can't be committed.", "")
    # rotation ledger
    led = os.path.join(AGENT_DIR, "rotation_ledger.json")
    if os.path.exists(led):
        try: rows = json.load(open(led))
        except Exception: rows = []
        pend = [r for r in rows if not r.get("revoked")]
        if pend: add("Secrets", "A2b-rotate", "err", "%d leaked key(s) not yet rotated" % len(pend), "Known-leaked credentials still need revoking at the provider.", ", ".join(r.get("id","?") for r in pend))
        elif rows: add("Secrets", "A2b-rotate", "ok", "all known leaks rotated", "Rotation ledger shows every known leak revoked.", "")
    else:
        add("Secrets", "A2b-rotate", "info", "no rotation ledger", "Known deferred item: rotate Anthropic key + bridge secret + Cloudflare token, log them in rotation_ledger.json.", "")
    # plaintext key backup lingering on disk -- cf-key-backup.sh writes PAPER-BACKUP.txt = the super-creator
    # Ed25519 PRIVATE keys in CLEARTEXT (the print-to-a-safe layer). Sitting un-printed on disk is a finding;
    # it self-clears once printed + the plaintext is removed (the keys are also in the encrypted .cfkeys.enc).
    cand = [os.path.join(HOME, "cf-key-backup"), os.path.join(CC_HOME, "cf-key-backup")]
    try:
        for n in os.listdir(HOME):
            if "cf-key-backup" in n:
                p = os.path.join(HOME, n)
                if os.path.isdir(p) and p not in cand: cand.append(p)
    except Exception: pass
    paper_hits = [os.path.join(d, "PAPER-BACKUP.txt") for d in cand if os.path.isfile(os.path.join(d, "PAPER-BACKUP.txt"))]
    if paper_hits:
        add("Secrets", "A5-keybackup", "warn", "plaintext key backup on disk -- print + remove",
            "A super-creator PAPER-BACKUP.txt (Ed25519 PRIVATE keys in CLEARTEXT) is on disk. Print it to a "
            "safe, then delete the plaintext -- the same keys are in the encrypted .cfkeys.enc bundle, so "
            "nothing is lost. Self-clears once the plaintext file is gone.", ", ".join(paper_hits))
    else:
        add("Secrets", "A5-keybackup", "ok", "no plaintext key backup lingering", "No cleartext PAPER-BACKUP.txt key file found on disk.", "")

# ---------------- Access & privilege ----------------
def scan_access():
    sp = os.path.join(HOME, ".claude", "settings.json")
    cfg = {}
    if os.path.exists(sp):
        try: cfg = json.load(open(sp))
        except Exception: cfg = {}
    perms = (cfg.get("permissions") or {})
    deny = perms.get("deny") or []
    # reward a sound conservative deny-list (secret-read paths + catastrophic commands).
    # Deliberately NOT requiring curl/.env denies -- those would break legit deploys + agents that read .env.
    want = ["rm -rf", "git push --force", ".ssh", ".aws"]
    covered = sum(1 for w in want if any(w in str(x) for x in deny))
    if covered >= 4: add("Access", "B2-deny", "ok", "Claude permission deny-list present", "Deny rules block secret-file reads (~/.ssh, ~/.aws) and catastrophic commands (rm -rf, force-push).", "denies=%d" % len(deny))
    elif deny: add("Access", "B2-deny", "warn", "deny-list thin", "Add deny rules for rm -rf, force-push, Read(~/.ssh/**), Read(~/.aws/**).", "denies=%d" % len(deny))
    else: add("Access", "B2-deny", "err", "no Claude permission deny-list", "~/.claude/settings.json has no deny rules -- the only injection-proof control is missing.", "")
    sandbox = cfg.get("sandbox")
    if isinstance(sandbox, dict) and sandbox.get("enabled"): add("Access", "B4-sandbox", "ok", "Claude OS sandbox enabled", "Seatbelt sandbox on.", "")
    else: add("Access", "B4-sandbox", "warn", "Claude OS sandbox off", "Enable sandbox (filesystem + network isolation) -- survives prompt injection when deny-rules don't.", "")
    # the CC itself launches with --dangerously-skip-permissions
    add("Access", "B2b-skip", "info", "sessions run with permissions skipped (accepted by design)",
        "Deliberate, kept on purpose for autonomous operation. Mitigated by the deny-list above; the right way to harden further is the OS sandbox, NOT changing this setting.", "")

# ---------------- Dashboard / network ----------------
def scan_network(port=8799):
    rc, out = run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"], timeout=15)
    if rc == 0:
        exposed = [l for l in out.splitlines() if re.search(r"(\*|0\.0\.0\.0):", l)]
        if exposed:
            names = sorted(set(l.split()[0] for l in exposed))
            add("Network", "E1-ports", "warn", "%d listener(s) on 0.0.0.0/*" % len(exposed), "Services reachable on all interfaces (bind loopback/tailnet instead): " + ", ".join(names), "\n".join(exposed[:8]))
        else:
            add("Network", "E1-ports", "ok", "no 0.0.0.0 listeners", "All listening sockets are loopback/tailnet-scoped.", "")
    # macOS firewall
    fw = "/usr/libexec/ApplicationFirewall/socketfilterfw"
    if os.path.exists(fw):
        _, st = run([fw, "--getglobalstate"], timeout=10)
        _, stl = run([fw, "--getstealthmode"], timeout=10)
        on = "enabled" in st.lower()
        add("Network", "E2-fw", "ok" if on else "warn", "macOS firewall " + ("on" if on else "off"),
            ("Stealth " + ("on" if "enabled" in stl.lower() else "off")) if on else "Enable: socketfilterfw --setglobalstate on", st.strip()[:120])

def scan_protections():
    rc, out = run(["csrutil", "status"], timeout=8)
    if rc == 0: add("Audit", "F2-sip", "ok" if "enabled" in out.lower() else "warn", "SIP " + ("enabled" if "enabled" in out.lower() else "disabled"), out.strip()[:120], "")
    rc, out = run(["spctl", "--status"], timeout=8)
    if rc == 0: add("Audit", "F2-gk", "ok" if "enabled" in out.lower() else "warn", "Gatekeeper " + ("enabled" if "enabled" in out.lower() else "disabled"), out.strip()[:120], "")
    add("Audit", "D5-telemetry", "ok" if os.environ.get("CLAUDE_CODE_ENABLE_TELEMETRY") else "info",
        "agent audit telemetry " + ("on" if os.environ.get("CLAUDE_CODE_ENABLE_TELEMETRY") else "off"),
        "Set CLAUDE_CODE_ENABLE_TELEMETRY=1 to log every agent tool call/command off-box for an audit trail.", "")

# ---------------- Code & deps ----------------
def scan_deps(repo):
    if have("osv-scanner"):
        rc, out = run(["osv-scanner", "scan", "-r", repo], timeout=200)
        if rc == 0: add("Deps", "C1-osv", "ok", "osv-scanner: no known CVEs", "No known-vulnerable dependencies.", "")
        else: add("Deps", "C1-osv", "warn", "osv-scanner: vulnerabilities found", "Known CVEs in dependencies -- review and bump.", out[-500:])
    else:
        add("Deps", "C1-osv", "info", "osv-scanner not installed", "Install for polyglot CVE scanning: brew install osv-scanner", "")

# ---------------- AI-agent safety (Ralph loops) ----------------
def scan_loops():
    rdir = os.path.join(CC_HOME, "data", "ralph")
    if not os.path.isdir(rdir): return
    uncapped = []
    for n in os.listdir(rdir):
        cfgp = os.path.join(rdir, n, "loop.json")
        if not os.path.isfile(cfgp): continue
        try: c = json.load(open(cfgp))
        except Exception: continue
        if not (c.get("max_iters") or c.get("timeout_sec") or c.get("max_turns")):
            uncapped.append(n)
    if uncapped: add("AI-safety", "D4-loops", "warn", "%d Ralph loop(s) without caps" % len(uncapped), "Loops should set max_iters/max_turns/timeout_sec + a verify gate.", ", ".join(uncapped[:8]))
    else: add("AI-safety", "D4-loops", "ok", "Ralph loops have caps", "All loop configs declare iteration/turn/timeout caps.", "")

def main():
    args = sys.argv[1:]
    repo = args[args.index("--repo") + 1] if "--repo" in args else _project_root()
    os.makedirs(REPORTS, exist_ok=True)
    if os.path.isdir(repo):
        scan_secrets(repo); scan_deps(repo)
    scan_access(); scan_network(); scan_protections(); scan_loops()
    order = {"err": 0, "warn": 1, "info": 2, "ok": 3}
    CHECKS.sort(key=lambda c: (order.get(c["sev"], 9), c["dim"]))
    counts = {k: sum(1 for c in CHECKS if c["sev"] == k) for k in ("err", "warn", "info", "ok")}
    overall = "err" if counts["err"] else ("warn" if counts["warn"] else "ok")
    report = {"ts": time.time(), "repo": repo, "overall": overall, "counts": counts, "checks": CHECKS}
    open(os.path.join(REPORTS, "latest.json"), "w").write(json.dumps(report, indent=2))
    open(os.path.join(REPORTS, time.strftime("%Y%m%d_%H%M%S") + ".json"), "w").write(json.dumps(report, indent=2))
    print("security scan: %s (err=%d warn=%d info=%d ok=%d) -> %s/latest.json" %
          (overall, counts["err"], counts["warn"], counts["info"], counts["ok"], REPORTS))

if __name__ == "__main__":
    main()
