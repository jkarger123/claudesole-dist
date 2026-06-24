#!/usr/bin/env python3
"""Incidents agent -- read-only open-incident posture. Writes reports/latest.json in the common schema.
Brand/project-agnostic: all project knowledge comes from ../config.json. ASCII-only."""
import json, os, time, glob

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
SLUG = os.path.basename(AGENT)
DEFAULT_OPEN = ["OPEN", "UNRESOLVED", "INCIDENT", "FAIL", "ERROR"]
DEFAULT_CRIT = ["CRITICAL", "SEV1", "P0", "BRICK"]


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


def scan_text(path, openp, critp):
    try:
        lines = open(path, "r", errors="replace").read().splitlines()
    except Exception as e:
        return {"status": "warn", "detail": "unreadable: %s" % e}
    op = [l for l in lines if any(p in l.upper() for p in openp)]
    cp = [l for l in lines if any(p in l.upper() for p in critp)]
    age_d = (time.time() - os.path.getmtime(path)) / 86400.0
    newest = (cp or op)[-1].strip()[:160] if (cp or op) else ""
    status = "err" if cp else ("warn" if op else "ok")
    detail = "%d open, %d critical; mtime %.1fd ago" % (len(op), len(cp), age_d)
    if newest:
        detail += " | latest: " + newest
    return {"status": status, "detail": detail}


def scan_dir(path, recent_days):
    try:
        files = [f for f in glob.glob(os.path.join(path, "*")) if os.path.isfile(f)]
    except Exception as e:
        return {"status": "warn", "detail": "unreadable: %s" % e}
    if not files:
        return {"status": "warn", "detail": "empty / no files"}
    cutoff = time.time() - recent_days * 86400.0
    recent = [f for f in files if os.path.getmtime(f) >= cutoff]
    newest = max(files, key=os.path.getmtime)
    age_d = (time.time() - os.path.getmtime(newest)) / 86400.0
    status = "ok" if recent else "warn"
    return {"status": status, "detail": "%d files, %d in last %dd; newest %s (%.1fd ago)" %
            (len(files), len(recent), recent_days, os.path.basename(newest), age_d)}


def main():
    cfg = load_config()
    if not cfg or not cfg.get("sources"):
        write_report("Incidents", "unknown", "Not configured for this project.",
                     [{"name": "config", "status": "warn",
                       "detail": "No config.json -- copy config.example.json and set log sources.",
                       "evidence": os.path.join(AGENT, "config.json")}])
        print("incidents: unconfigured")
        return
    openp = [p.upper() for p in cfg.get("open_patterns", DEFAULT_OPEN)]
    critp = [p.upper() for p in cfg.get("critical_patterns", DEFAULT_CRIT)]
    items = []
    for s in cfg["sources"]:
        name = s.get("name", "?")
        path = s.get("path", "")
        if not path or not os.path.exists(path):
            items.append({"name": name, "status": "warn", "detail": "path missing: %s" % path, "evidence": path})
            continue
        if s.get("type") == "dir":
            r = scan_dir(path, int(s.get("recent_days", 7)))
        else:
            r = scan_text(path, openp, critp)
        r.update({"name": name, "evidence": path})
        items.append(r)
    rep = write_report("Incidents", rollup(items),
                       "%d source(s) scanned." % len(items), items)
    print("incidents:", rep["overall"], rep["counts"])


if __name__ == "__main__":
    main()
