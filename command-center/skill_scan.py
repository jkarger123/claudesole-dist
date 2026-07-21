#!/usr/bin/env python3
"""skill_scan -- mine Claude Code session transcripts for REPEATED PROCEDURES ripe to become a Skill.

The idea: if agents keep doing the same distinctive multi-tool procedure by hand across many sessions, that
procedure should be a `/skill` -- captured once, discoverable, consistent. This scanner reads the real
transcripts (~/.claude/projects/<slug>/*.jsonl) and extracts, per Bash call, a normalized ACTION signature.

What makes the signal good (v2):
  - Inline script bodies are OPAQUE. `python3 -c "..."`, heredocs (`<<EOF`), `bash -c '...'`, `node -e` etc.
    collapse to a single `<lang>-inline` token -- we never split the script's contents into fake "steps".
  - Actions carry their DISTINCTIVENESS: multiplexer tools keep their subcommand (`git-push`, `tmux-kill-
    session`, `gh-pr`, `launchctl-kickstart`), curl/ssh keep their target (`curl:/api/superadmin-send`,
    `ssh:build-box`), scripts keep their basename (`py:deploy.py`, `sh:release.sh`).
  - A candidate must contain >= 2 DISTINCT *specific* actions -- so shell idioms (`tail|grep`, `for;do;done`,
    a lone `python3`) never qualify. Only real, named, multi-tool procedures do.
  - Ranked by distinct-session recurrence (a habit across many sessions), lightly boosted by cross-project
    spread and specificity.

Only ACTION signatures leave this tool -- never raw command text, args, or paths -- so no secrets/paths leak
into the candidate list.

Usage:
  skill_scan.py [--days N] [--min-sessions K] [--project SLUG] [--all] [--intents]
                [--json] [--out FILE] [--ai] [--top N]
Defaults: --days 45  --min-sessions 3  --top 12
"""
import argparse, json, os, re, subprocess, sys, time, collections

HOME = os.path.expanduser("~")
PROJECTS = os.path.join(HOME, ".claude", "projects")
USER_SKILLS = os.path.join(HOME, ".claude", "skills")

# multiplexer tools whose FIRST subcommand is the meaningful action (git push, tmux kill-session, ...)
MUX = {"git", "gh", "docker", "tmux", "systemctl", "launchctl", "kubectl", "npm", "yarn", "pnpm", "brew",
       "cargo", "pip", "pip3", "apt", "apt-get", "terraform", "ansible", "aws", "gcloud", "wrangler"}
# strong action tools -- specific even without a subcommand
SIGNAL_STRONG = MUX | {"gitleaks", "ssh", "rsync", "scp", "make", "psql", "mysql", "sqlite3", "ffmpeg",
                       "rclone", "pg_dump", "openssl", "cc-update.sh"}
# generic shell/inspection verbs -- never specific on their own
GENERIC = {"tail", "grep", "sed", "awk", "find", "wc", "sort", "uniq", "tr", "cut", "xargs", "jq", "diff",
           "comm", "paste", "tee", "rev", "column", "fold", "nl", "tac", "less", "more", "realpath",
           "dirname", "basename", "date", "stat", "du", "df", "free", "ps", "kill", "watch", "read", "cp",
           "mv", "mkdir", "rm", "touch", "chmod", "chown", "ln", "gunzip", "gzip", "tar", "unzip", "zip",
           "sleep", "for", "while", "do", "done", "if", "then", "fi", "case", "esac", "curl", "wget"}
# pure navigation/noise -- dropped entirely
NOISE = {"cd", "echo", "pwd", "true", "false", ":", "export", "printf", "clear", "which", "ls", "cat",
         "head", "test", "[", "env", "set", "source", ".", "sudo", "time", "nohup", "exec", "command"}


def _basename(tok):
    tok = tok.strip().strip('"').strip("'")
    return os.path.basename(tok) if "/" in tok else tok


def _strip_inline(cmd):
    """Remove heredoc bodies and mask quoted spans so operators inside them don't create fake steps.
    Also flags whether the command embeds an inline script (python -c / node -e / bash -c / heredoc)."""
    inline_langs = []
    # heredocs: <<EOF ... \n EOF  (also <<-'EOF')
    def _heredoc(m):
        inline_langs.append("heredoc")
        delim = m.group("d")
        return " __INLINE__ "  # body removed below by delimiter cut
    # collapse everything from a heredoc intro to its closing delimiter line
    hd = re.search(r"<<-?\s*['\"]?(?P<d>[A-Za-z_][A-Za-z0-9_]*)['\"]?", cmd)
    if hd:
        delim = hd.group("d")
        end = re.search(r"\n\s*" + re.escape(delim) + r"\s*(\n|$)", cmd[hd.end():])
        if end:
            cmd = cmd[:hd.start()] + " __INLINE__ " + cmd[hd.end() + end.end():]
        else:
            cmd = cmd[:hd.start()] + " __INLINE__ "
        inline_langs.append("heredoc")
    # inline -c / -e scripts: replace `python3 -c '...'` with a token
    for prog, lang in ((r"python3?", "python"), (r"node", "node"), (r"bash", "bash"), (r"sh", "sh"),
                       (r"perl", "perl"), (r"ruby", "ruby"), (r"zsh", "zsh")):
        pat = re.compile(r"\b" + prog + r"\s+-([ce])\b")
        if pat.search(cmd):
            inline_langs.append(lang)
    # mask quoted spans (so their contents can't be split)
    cmd = re.sub(r"'[^']*'", " __STR__ ", cmd)
    cmd = re.sub(r'"[^"]*"', " __STR__ ", cmd)
    return cmd, inline_langs


def _action(seg):
    """One pipeline/command segment -> a normalized action token, or None to drop."""
    toks = seg.strip().split()
    while toks and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]) or toks[0] in ("sudo", "time", "nohup",
                                                                                  "exec", "command", "\\")):
        toks.pop(0)
    if not toks:
        return None
    p = _basename(toks[0])
    if p.startswith("-") or not re.match(r"^[A-Za-z0-9_.][A-Za-z0-9_.-]*$", p) or p in NOISE \
            or p in ("__INLINE__", "__STR__"):
        return None
    # inline interpreter invoked as `python3 -c` etc -> opaque
    if p in ("python", "python3", "node", "bash", "sh", "zsh", "perl", "ruby") and len(toks) > 1:
        if toks[1] in ("-c", "-e"):
            return p.replace("python3", "python") + "-inline"
        # running a script file: keep its basename as the action target
        for t in toks[1:]:
            if t.startswith("-") or t in ("__STR__", "__INLINE__"):
                continue
            b = _basename(t)
            if b.endswith((".py", ".sh", ".js", ".ts")):
                return {"python": "py", "python3": "py", "node": "js", "bash": "sh", "sh": "sh"}.get(p, p) + ":" + b
            break
    # curl/wget -> keep the URL PATH (first two segments), never host/creds/query
    if p in ("curl", "wget", "http", "https"):
        m = re.search(r"https?://[^/\s'\"]+(/[^\s'\"?]+)", seg)
        if m:
            path = "/".join(m.group(1).split("/")[:3])
            return "curl:" + path
        return None  # bare curl is generic
    # ssh/scp/rsync -> keep the host alias
    if p in ("ssh", "scp"):
        for t in toks[1:]:
            if not t.startswith("-") and t not in ("__STR__",) and re.match(r"^[A-Za-z][\w.-]*$", t):
                return "ssh:" + t.split("@")[-1].split(":")[0]
        return "ssh"
    # multiplexer -> program-subcommand
    if p in MUX:
        for t in toks[1:]:
            if t.startswith("-") or t in ("__STR__", "__INLINE__"):
                continue
            sub = _basename(t)
            if re.match(r"^[A-Za-z][\w-]*$", sub):
                return p + "-" + sub
        return p
    return p


# self-traffic / non-actionable targets to ignore (Claude's own API calls, health polls)
TARGET_BLOCK = {"curl:/v1/messages", "curl:/v1/complete", "curl:/v1", "curl:/api/health"}


def _is_specific(action):
    """A DISTINCTIVE tool action worth building a skill around. An opaque inline one-liner (python-inline,
    bash-inline, ...) is NOT specific -- it tells us nothing about the procedure."""
    if not action or action.endswith("-inline") or action in TARGET_BLOCK:
        return False
    if "-" in action or ":" in action:
        return True
    base = action.split(":")[0].split("-")[0]
    return base in SIGNAL_STRONG


def _base_tokens(action):
    return set(re.split(r"[-:./]", action)) - {"", "inline"}


def _sig(cmd):
    """A (possibly compound) bash command -> ordered, de-duped tuple of action tokens."""
    cleaned, _ = _strip_inline(cmd)
    actions = []
    for seg in re.split(r"&&|\|\||[|;\n]", cleaned):
        a = _action(seg)
        if a and (not actions or actions[-1] != a):
            actions.append(a)
    return tuple(actions)


def _iter_events(path):
    try:
        for line in open(path, encoding="utf-8", errors="replace"):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue
    except Exception:
        return


def _session_data(path):
    """Return (list-of-bash-sigs, first-human-text) for one session transcript."""
    sigs = []
    first_human = None
    for e in _iter_events(path):
        msg = e.get("message")
        if not isinstance(msg, dict):
            continue
        cont = msg.get("content")
        if e.get("type") == "user" and first_human is None:
            text = cont if isinstance(cont, str) else (
                " ".join(b.get("text", "") for b in cont if isinstance(b, dict) and b.get("type") == "text")
                if isinstance(cont, list) else "")
            text = (text or "").strip()
            if text and not _looks_injected(text):
                first_human = text[:200]
        if isinstance(cont, list):
            for b in cont:
                if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Bash":
                    s = _sig((b.get("input") or {}).get("command", ""))
                    if s:
                        sigs.append(s)
    return sigs, first_human


def _looks_injected(text):
    t = text.lstrip()
    if t[:1] in ("[", "<"):
        return True
    low = t.lower()
    return any(k in low for k in ("ralph loop", "you are my chief", "you are the ", "system-reminder",
                                  "warm transfer", "handoff received", "autonomous-loop", "[request interrupted"))


def _existing_skill_terms():
    terms = set()
    try:
        names = os.listdir(USER_SKILLS)
    except Exception:
        names = []
    for n in names:
        if n.startswith((".", "_")):
            continue
        terms.update(n.split("-"))
        try:
            txt = open(os.path.join(USER_SKILLS, n, "SKILL.md"), encoding="utf-8", errors="replace").read()[:2000].lower()
            terms.update(re.findall(r"[a-z]{3,}", txt))
        except Exception:
            pass
    return terms


def _name_of(action):
    """The most distinctive human-ish name inside one action token."""
    if action.startswith(("py:", "js:", "sh:")):
        return re.sub(r"\.(py|js|ts|sh)$", "", action.split(":", 1)[1])
    if action.startswith("curl:"):
        segs = [s for s in action.split(":", 1)[1].split("/") if s]
        return segs[-1] if segs else "curl"
    if action.startswith("ssh:"):
        return action.split(":", 1)[1]
    return action  # e.g. git-status, tmux-kill-session


def _slug_for(actions):
    # rank distinctive tools first (scripts / api targets / hosts beat bare git-status), then build a kebab slug
    ranked = sorted(actions, key=lambda a: (0 if a.startswith(("py:", "js:", "sh:", "curl:", "ssh:")) else 1))
    parts = []
    for a in ranked:
        n = re.sub(r"[^a-z0-9]+", "-", _name_of(a).lower()).strip("-")
        for chunk in [n]:
            if chunk and chunk not in parts:
                parts.append(chunk[:24])
        if len(parts) >= 2:
            break
    slug = "-".join(parts[:2]) or "procedure"
    return slug[:48].strip("-")


def scan(days=45, min_sessions=3, project=None, scan_all=False, top=12):
    cutoff = time.time() - days * 86400
    files = []
    try:
        slugs = os.listdir(PROJECTS)
    except Exception:
        slugs = []
    for slug in slugs:
        if project and slug != project:
            continue
        d = os.path.join(PROJECTS, slug)
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if not f.endswith(".jsonl"):
                continue
            p = os.path.join(d, f)
            try:
                if scan_all or os.path.getmtime(p) >= cutoff:
                    files.append(p)
            except Exception:
                continue

    existing = _existing_skill_terms()

    def _covered(actions):
        toks = set()
        for a in actions:
            toks |= _base_tokens(a)
        return toks and toks.issubset(existing)

    # A candidate is keyed by its distinctive-tool IDENTITY (frozenset of specific actions), so single-command
    # and two-step variants that share the same tools collapse into ONE candidate. Generic tails (grep/tail),
    # inline one-liners, and ordering differences no longer fragment it.
    agg = collections.defaultdict(lambda: {"sessions": set(), "projects": set(), "count": 0,
                                           "forms": collections.Counter()})
    n_sessions = 0
    for p in files:
        sigs, _ = _session_data(p)
        if not sigs:
            continue
        n_sessions += 1
        sid = os.path.basename(p)[:8]
        slug = _project_slug(p)
        seen_here = set()
        # units = each command's actions, plus each consecutive pair's combined actions
        units = [list(s) for s in sigs]
        for a, b in zip(sigs, sigs[1:]):
            if a != b:
                units.append(list(dict.fromkeys(a + b)))
        for actions in units:
            spec = [a for a in dict.fromkeys(actions) if _is_specific(a)]
            if len(spec) < 2 or _covered(spec):
                continue
            ident = frozenset(spec)
            d = agg[ident]
            d["sessions"].add(sid); d["projects"].add(slug); d["count"] += 1
            d["forms"][" → ".join(actions)] += 1

    cands = []
    for ident, d in agg.items():
        ns = len(d["sessions"])
        if ns < min_sessions:
            continue
        rep = d["forms"].most_common(1)[0][0]
        spec = sorted(ident)
        cands.append({"identity": spec, "steps": rep, "sessions": ns,
                      "projects": sorted(d["projects"])[:6], "occurrences": d["count"],
                      "scope_hint": "project" if len(d["projects"]) == 1 else "node",
                      "suggested_slug": _slug_for(spec),
                      "score": ns * (1 + 0.35 * len(spec)) * (1.15 if len(d["projects"]) > 1 else 1.0)})
    cands.sort(key=lambda c: c["score"], reverse=True)
    return {"scanned_sessions": n_sessions, "scanned_files": len(files), "days": days,
            "min_sessions": min_sessions, "candidates": cands[:top]}


def _project_slug(path):
    return os.path.basename(os.path.dirname(path))


def _ai_enrich(cands):
    from shutil import which
    if not cands or not which("claude"):
        return cands
    payload = [{"tools": c["identity"], "seen_as": c["steps"], "sessions": c["sessions"],
                "projects": c["projects"]} for c in cands]
    prompt = ("You are triaging candidate Claude Code SKILLS discovered from repeated command procedures "
              "(actions are normalized tool signatures, e.g. git-push, curl:/api/x, tmux-kill-session). For "
              "EACH item propose a kebab-case skill slug and a one-sentence `description` saying WHAT it does "
              "and WHEN to use it (that description is the model's only trigger). Return ONLY a JSON array of "
              "{slug, description} in the same order. Items:\n" + json.dumps(payload))
    try:
        r = subprocess.run(["claude", "-p", prompt, "--output-format", "text"],
                           capture_output=True, text=True, timeout=150)
        m = re.search(r"\[.*\]", r.stdout, re.S)
        if m:
            for c, a in zip(cands, json.loads(m.group(0))):
                if isinstance(a, dict):
                    c["suggested_slug"] = a.get("slug") or c["suggested_slug"]
                    c["suggested_description"] = a.get("description", "")
    except Exception:
        pass
    return cands


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--min-sessions", type=int, default=3)
    ap.add_argument("--project", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--ai", action="store_true", help="name + draft candidates with a headless claude -p")
    a = ap.parse_args()

    res = scan(days=a.days, min_sessions=a.min_sessions, project=a.project, scan_all=a.all, top=a.top)
    if a.ai:
        res["candidates"] = _ai_enrich(res["candidates"])
    res["generated_at"] = int(time.time())

    if a.out:
        try:
            os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
            json.dump(res, open(a.out, "w"), indent=2)
        except Exception as e:
            print("could not write --out: %s" % e, file=sys.stderr)

    if a.json:
        print(json.dumps(res, indent=2)); return 0

    print("Scanned %d session(s) across %d transcript file(s), last %d day(s)."
          % (res["scanned_sessions"], res["scanned_files"], res["days"]))
    c = res["candidates"]
    if not c:
        print("No distinctive repeated procedures crossed the threshold (>= %d sessions, >= 2 specific "
              "actions). Loosen: --min-sessions 2 --all." % res["min_sessions"])
    else:
        print("\nRepeated procedures ripe for a /skill (most repeated first):\n")
        for i, x in enumerate(c, 1):
            print("%2d. /%-22s %d sessions · %s scope" % (i, x["suggested_slug"], x["sessions"], x["scope_hint"]))
            print("      tools: %s" % "  +  ".join(x["identity"]))
            print("      seen as: %s" % x["steps"])
            if x.get("suggested_description"):
                print("      → " + x["suggested_description"])
    if c:
        print("\nBuild one:  cc-skill new <slug> --scope <node|project> --desc \"...\"   "
              "(or /skill-builder to draft it)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
