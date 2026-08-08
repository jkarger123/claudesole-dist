#!/usr/bin/env python3
"""Deploy agent -- read-only readiness assessor. Writes reports/latest.json in the common schema.
Brand/project-agnostic: all project knowledge comes from ../config.json. ASCII-only."""
import json, os, time, subprocess, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
SLUG = os.path.basename(AGENT)


def load_config():
    try:
        return json.load(open(os.path.join(os.environ.get("CC_AGENT_STATE") or AGENT, "config.json")))
    except Exception:
        return None


def write_report(title, overall, summary, items):
    counts = {"ok": 0, "warn": 0, "err": 0}
    for it in items:
        if it.get("status") in counts:
            counts[it["status"]] += 1
    rep = {"slug": SLUG, "title": title, "overall": overall, "summary": summary,
           "counts": counts, "items": items, "ts": time.time()}
    rd = os.path.join(os.environ.get("CC_AGENT_STATE") or AGENT, "reports")
    os.makedirs(rd, exist_ok=True)
    json.dump(rep, open(os.path.join(rd, "latest.json"), "w"), indent=2)
    json.dump(rep, open(os.path.join(rd, time.strftime("%Y%m%d_%H%M%S") + ".json"), "w"), indent=2)
    return rep


def rollup(items):
    sev = [it.get("status") for it in items]
    if "err" in sev:
        return "err"
    if "warn" in sev:
        return "warn"
    return "ok" if items else "unknown"


def check_health(url, expect):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "claudesole-deploy-agent"})
        with urllib.request.urlopen(req, timeout=6) as r:
            code = r.getcode()
            body = r.read(2048).decode("utf-8", "replace")
        if code // 100 != 2:
            return "err", "HTTP %d" % code
        if expect and expect not in body:
            return "warn", "HTTP %d but missing expect=%r" % (code, expect)
        return "ok", "HTTP %d" % code
    except Exception as e:
        return "err", "unreachable: %s" % e


def git_dirty(d):
    try:
        out = subprocess.run(["git", "-C", d, "status", "--porcelain"],
                             capture_output=True, text=True, timeout=15).stdout
        n = len([x for x in out.splitlines() if x.strip()])
        return n
    except Exception:
        return None


def main():
    cfg = load_config()
    if not cfg or not cfg.get("targets"):
        write_report("Deploy", "unknown", "Not configured for this project.",
                     [{"name": "config", "status": "warn",
                       "detail": "No config.json -- copy config.example.json and set deploy targets.",
                       "evidence": os.path.join(AGENT, "config.json")}])
        print("deploy: unconfigured")
        return
    items = []
    for t in cfg["targets"]:
        name = t.get("name", "?")
        parts, status = [], "ok"
        if t.get("health_url"):
            s, d = check_health(t["health_url"], t.get("expect"))
            parts.append("health=%s (%s)" % (s, d))
            if s == "err":
                status = "err"
            elif s == "warn" and status == "ok":
                status = "warn"
        if t.get("git_dir"):
            n = git_dirty(t["git_dir"])
            if n is None:
                parts.append("git=unknown")
            elif n > 0:
                parts.append("git=%d uncommitted" % n)
                if status == "ok":
                    status = "warn"
            else:
                parts.append("git=clean")
        items.append({"name": name, "status": status, "detail": "; ".join(parts) or "no checks configured",
                      "evidence": t.get("deploy_cmd", "(no deploy_cmd)")})
    rep = write_report("Deploy", rollup(items),
                       "%d target(s); run tools/deploy.py --target <name> --yes to ship (gated)." % len(items),
                       items)
    print("deploy:", rep["overall"], rep["counts"])


if __name__ == "__main__":
    main()
