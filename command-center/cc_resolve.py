#!/usr/bin/env python3
"""cc_resolve -- decide WHICH co-located ClaudeFather node a cc-* command belongs to.

THE PROBLEM this removes: several instances on one box SHARE this command-center dir (and therefore the cc-*
CLIs on PATH). A CLI can't tell its node from its own location, so the old fallback (`$HERE/../cc.config.json`)
silently sent EVERY stray command -- deliverables, notifications, notes -- to the ROOT/default node. On a
multi-node box that made the root node a catch-all sink for other nodes' work (a real, confusing leak).

RESOLUTION ORDER (never silently sinks to a default):
  1. explicit --node <id>            -- hard override
  2. $CC_CONFIG (a real file)        -- a dashboard-launched session carries its own; explicit intent wins
  3. cwd inside a node's project_root-- the node that OWNS this working dir (fixes bare shells / admin / `!`)
  4. the ONLY instance on the box    -- a standalone install is never ambiguous
  5. FAIL LOUD                        -- multi-node + can't tell -> actionable error, exit 3 (no silent leak)

Instances are discovered from (a) the self-registered runtime registry each server writes on boot
(`<command-center>/_colocated_nodes.json`) UNIONed with (b) a filesystem scan of the co-located configs
(`<CC_HOME>/cc.config.json` + `<CC_HOME>/instances/*/cc.config.json`). Either alone suffices; together they
cover any layout, present or future.

CLI use:   cc.config path -> stdout (exit 0), or an actionable error -> stderr (exit 3).
  python:  from cc_resolve import resolve_config_path; p, err = resolve_config_path()
  bash:    CFG="$(python3 "$HERE/cc_resolve.py")" || { echo "$CFG"; exit 3; }   # $CFG holds the error on failure
"""
import json, os, glob, sys, time

def _load(p):
    try: return json.load(open(p))
    except Exception: return None

def _cc_home():
    # this file lives at <CC_HOME>/command-center/cc_resolve.py
    return os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

def _registry_path():
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), "_colocated_nodes.json")

def register(instance_id, project_root, home, config_path, port):
    """Called by the server on boot: record this instance so any cc-* CLI (in any shell) can route to it.
    Best-effort + self-pruning (drops entries whose config file has vanished). Never raises."""
    try:
        path = _registry_path()
        reg = _load(path) or {}
        if not isinstance(reg, dict): reg = {}
        key = os.path.realpath(config_path)
        reg[key] = {"id": instance_id, "project_root": project_root, "home": home,
                    "config_path": config_path, "port": port, "ts": int(time.time())}
        # prune: config file gone
        for k in list(reg.keys()):
            cp = (reg.get(k) or {}).get("config_path")
            if cp and not os.path.isfile(cp): reg.pop(k, None)
        tmp = path + ".tmp"
        with open(tmp, "w") as f: json.dump(reg, f)
        os.replace(tmp, path)
    except Exception:
        pass

def _instances(cc_home):
    """Every co-located instance config: registry entries UNION a filesystem scan. Deduped by realpath."""
    seen = {}; out = []
    def _add(p, c=None):
        if not p: return
        rp = os.path.realpath(p)
        if rp in seen or not os.path.isfile(p): return
        c = c if isinstance(c, dict) else _load(p)
        if isinstance(c, dict) and (c.get("port") or c.get("auth_token") or c.get("instance_id")):
            seen[rp] = 1; out.append((p, c))
    # (a) self-registered runtime registry (any layout)
    reg = _load(_registry_path()) or {}
    if isinstance(reg, dict):
        for e in reg.values():
            if isinstance(e, dict): _add(e.get("config_path"))
    # (b) filesystem scan of the conventional co-located layout
    _add(os.path.join(cc_home, "cc.config.json"))
    for p in sorted(glob.glob(os.path.join(cc_home, "instances", "*", "cc.config.json"))): _add(p)
    return out

def resolve_config_path(cc_home=None, node=None, cwd=None):
    """-> (config_path, None) on success | (None, error_message) when it must fail loud."""
    cc_home = cc_home or _cc_home()
    insts = _instances(cc_home)
    ids = ", ".join((c.get("instance_id") or "?") for _, c in insts) or "(none)"
    # 1. explicit --node
    if node:
        for p, c in insts:
            if (c.get("instance_id") or "") == node: return p, None
        return None, "cc-node: unknown --node '%s' (co-located here: %s)" % (node, ids)
    # 2. explicit env (a launched session carries its own CC_CONFIG)
    env = os.environ.get("CC_CONFIG")
    if env and os.path.isfile(env): return os.path.realpath(env), None
    # 3. cwd ownership -- the node whose project_root contains this shell (fixes bare shells with no env)
    here = os.path.realpath(cwd or os.getcwd())
    best = None; blen = -1
    for p, c in insts:
        r = c.get("project_root")
        if not r: continue
        r = os.path.realpath(os.path.expanduser(r))
        if (here == r or here.startswith(r + os.sep)) and len(r) > blen:
            best, blen = p, len(r)
    if best: return best, None
    # 4. exactly one instance on the box -> unambiguous (the standalone-install case)
    if len(insts) == 1: return insts[0][0], None
    # nothing discovered at all (unexpected/old layout) -> legacy default, so a standalone box never breaks
    if not insts:
        d = os.path.join(cc_home, "cc.config.json")
        if os.path.isfile(d): return os.path.realpath(d), None
    # 5. multi-node and genuinely ambiguous -> FAIL LOUD (never silently sink into the default node)
    return None, ("cc-node: can't tell which node this command is for -- %d ClaudeFather instances share this box "
                  "and the working dir (%s) is not inside any node's project. Fix: set CC_CONFIG, pass --node <id>, "
                  "or run from inside the node's project tree. Co-located here: %s" % (len(insts), here, ids))

def main(argv):
    node = None; args = argv[1:]
    if "--node" in args:
        i = args.index("--node"); node = args[i + 1] if i + 1 < len(args) else None
    p, err = resolve_config_path(node=node)
    if err:
        sys.stderr.write(err + "\n"); return 3
    sys.stdout.write(p + "\n"); return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
