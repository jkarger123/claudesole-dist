#!/usr/bin/env python3
"""Pre-ship invariant (run before every cc-update/ship). Catches the 0.43.0 incident class: server.py
imported clips.py, but clips.py wasn't in framework_paths, so cc-update never propagated it and remote nodes
crash-looped on the missing import. Rule: EVERY local command-center/<x>.py that server.py imports (directly
or via _opt_import) MUST be listed in claudesole.manifest.json framework_paths. Exit 1 if any is missing.

Usage: python3 command-center/preship.py
"""
import re, json, os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
src = open(os.path.join(BASE, "server.py")).read()

# modules pulled in via `import x`, `_opt_import("x")`, or `__import__("x")`
mods = set(re.findall(r'^\s*import\s+([a-zA-Z0-9_]+)', src, re.M))
mods |= set(re.findall(r'_opt_import\(\s*["\']([a-zA-Z0-9_]+)["\']', src))
mods |= set(re.findall(r'__import__\(\s*["\']([a-zA-Z0-9_]+)["\']', src))

# only the ones that are LOCAL files in this dir (skip stdlib/3rd-party)
local = sorted(m for m in mods if os.path.isfile(os.path.join(BASE, m + ".py")))

fw = set(json.load(open(os.path.join(ROOT, "claudesole.manifest.json"))).get("framework_paths", []))
missing = [m for m in local if ("command-center/%s.py" % m) not in fw]

if missing:
    print("PRESHIP FAIL: local modules imported by server.py but MISSING from framework_paths -> remote nodes "
          "would crash-loop on cc-update:", missing)
    sys.exit(1)
print("PRESHIP OK: all %d local engine modules imported by server.py are in framework_paths (%s)"
      % (len(local), ", ".join(local)))
