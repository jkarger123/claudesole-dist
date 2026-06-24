#!/usr/bin/env python3
"""Cost agent -- read-only spend posture from local cost artifacts. Writes reports/latest.json in the
common schema. Brand/project-agnostic: all project knowledge comes from ../config.json. ASCII-only.
NEVER calls a paid/billing API -- reads only files the pipeline already produced."""
import json, os, time

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


def dig(obj, dotted):
    cur = obj
    for k in dotted.split("."):
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return None
    return cur


def read_number(src):
    typ = src.get("type", "json")
    path = src.get("path", "")
    field = src.get("field")
    if not os.path.exists(path):
        return None, "path missing: %s" % path
    try:
        if typ == "json":
            obj = json.load(open(path))
            val = dig(obj, field) if field else obj
            return (float(val), "%s=%s" % (field, val)) if isinstance(val, (int, float)) else (None, "field %r not numeric" % field)
        if typ == "jsonl_sum":
            total = 0.0
            n = 0
            for line in open(path, errors="replace"):
                line = line.strip()
                if not line:
                    continue
                try:
                    v = dig(json.loads(line), field)
                    if isinstance(v, (int, float)):
                        total += float(v); n += 1
                except Exception:
                    pass
            return total, "sum %s over %d rows" % (field, n)
        if typ == "file":
            age_d = (time.time() - os.path.getmtime(path)) / 86400.0
            return None, "raw source; mtime %.1fd ago" % age_d
    except Exception as e:
        return None, "parse error: %s" % e
    return None, "unknown type %r" % typ


def main():
    cfg = load_config()
    if not cfg or not cfg.get("sources"):
        write_report("Cost", "unknown", "Not configured for this project.",
                     [{"name": "config", "status": "warn",
                       "detail": "No config.json -- copy config.example.json and point at cost artifacts.",
                       "evidence": os.path.join(AGENT, "config.json")}])
        print("cost: unconfigured")
        return
    cur = cfg.get("currency", "USD")
    items = []
    grand = 0.0
    for s in cfg["sources"]:
        name = s.get("name", "?")
        val, note = read_number(s)
        status = "ok"
        detail = note
        if val is not None:
            grand += val
            detail = "%.2f %s (%s)" % (val, cur, note)
            if s.get("err") is not None and val >= s["err"]:
                status = "err"
            elif s.get("warn") is not None and val >= s["warn"]:
                status = "warn"
        else:
            status = "warn" if "missing" in note or "error" in note else "ok"
        items.append({"name": name, "status": status, "detail": detail, "evidence": s.get("path", "")})
    rep = write_report("Cost", rollup(items),
                       "total read: %.2f %s across %d source(s)." % (grand, cur, len(items)), items)
    print("cost:", rep["overall"], rep["counts"], "total=%.2f" % grand)


if __name__ == "__main__":
    main()
