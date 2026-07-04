#!/usr/bin/env python3
"""Pre-backup secret + oversize gate for the project monorepo.

Scans the files that a `git add -A` WOULD stage (modified + new, gitignore-respected) for real
secrets and for any file that would break GitHub's 100MB push limit. Exits 0 if clean, non-zero and
prints offenders if not -- so the backup engine can ABORT before staging anything.

What it treats as a REAL secret (high-signal only; the public Supabase anon key `role:anon` embedded
in the frontend is intentional/public and is NOT flagged):
  - Anthropic API keys (sk-ant-api...)
  - *_BRIDGE_SECRET / CLOUDFLARE_API_TOKEN assignments with a literal value
  - PEM private key blocks, AWS access keys, GitHub PATs, Slack tokens
  - Supabase service_role JWTs (the secret one), NOT anon
Placeholders / env-var references (REPLACE, YOUR, $env:, os.environ, ...) are ignored.

Usage: git-backup-secretscan.py [REPO_DIR]   (default: <repo dir>)
"""
import os, re, subprocess, sys

REPO = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()   # backup engine always passes the repo; cwd is a neutral fallback
MAX_BYTES = 95 * 1024 * 1024
SCAN_CONTENT_MAX = 3 * 1024 * 1024     # don't read >3MB files for content (still size-checked)

PATTERNS = {
    "anthropic_key":   re.compile(r"sk-ant-api[A-Za-z0-9_-]{24,}"),
    "bridge_secret":   re.compile(r"(?i)bridge_secret\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{16,}"),
    "cloudflare_token": re.compile(r"(?i)cloudflare_api_token\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{16,}"),
    "pem_private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "aws_access_key":  re.compile(r"AKIA[0-9A-Z]{16}"),
    "github_pat":      re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "slack_token":     re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "supabase_service_role": re.compile(r'"role"\s*:\s*"service_role"'),
}
# things that look like a secret pattern but are placeholders / env refs -> not a real secret
ALLOW = re.compile(r"\$\{?|\benv:|os\.environ|getenv|process\.env|YOUR|REPLACE|EXAMPLE|PLACEHOLDER|FILL_THIS|<[a-z]", re.I)


def would_be_committed(repo):
    out = subprocess.run(["git", "-C", repo, "status", "--porcelain", "-z"],
                         capture_output=True, text=True).stdout
    files = []
    for e in (x for x in out.split("\0") if x):
        status, path = e[:2], e[3:]
        if status.strip() == "D":            # pure deletion -> nothing to scan
            continue
        if "->" in path:                      # rename -> target
            path = path.split("->")[-1].strip()
        files.append(path)
    return files


def main():
    secret_hits = []
    big = []
    for rel in would_be_committed(REPO):
        path = os.path.join(REPO, rel)
        if not os.path.isfile(path):
            continue
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        if size > MAX_BYTES:
            big.append((rel, size))
        if size > SCAN_CONTENT_MAX:
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                data = fh.read()
        except Exception:
            continue
        for label, rx in PATTERNS.items():
            for m in rx.finditer(data):
                seg = data[max(0, m.start() - 40):m.start() + 40]
                if not ALLOW.search(seg):
                    secret_hits.append((rel, label))
                    break

    if not secret_hits and not big:
        print("secret-scan: CLEAN (no real secrets, no oversize files)")
        return 0

    if secret_hits:
        print("secret-scan: BLOCKED -- real secrets in files that would be committed:")
        for rel, label in sorted(set(secret_hits)):
            print("   [%s] %s" % (label, rel))
    if big:
        print("secret-scan: BLOCKED -- files exceed GitHub's 100MB push limit:")
        for rel, size in big:
            print("   %.1f MB  %s" % (size / 1048576, rel))
    print("Fix or .gitignore the above, then re-run the backup.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
