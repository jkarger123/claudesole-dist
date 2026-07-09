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

# modules pulled in via `import x`, `from x import ...`, `_opt_import("x")`, or `__import__("x")`
mods = set(re.findall(r'^\s*import\s+([a-zA-Z0-9_]+)', src, re.M))
mods |= set(re.findall(r'^\s*from\s+([a-zA-Z0-9_]+)\s+import', src, re.M))   # `from localmod import y` also crash-loops
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

# MANIFEST-COMPLETENESS gate (deep-audit 2026-07-09 finding 0.5): the import check above catches Python modules,
# but server.py ALSO references command-center helper FILES by path -- `os.path.join(BASE, "ralph_live.py")`,
# `..."cc-advise")`, etc. If such a file isn't in framework_paths it never propagates, so the feature that spawns
# it (a tmux tab, a subprocess, the break-glass console) runs a NONEXISTENT file on every tenant. This is the same
# class as the import gap; we found ralph_live.py + cc-lifeline missing this way. Scan the single-arg BASE joins
# and require each referenced command-center file to be covered by framework_paths.
_KNOWN_UNSHIPPED = {"deliverables"}        # STUDIO_OUT_DIR: a runtime OUTPUT dir, not a shipped file
                                           # (P2-11 CLOSED: platform_map.json now ships relative-path + is in the manifest)
_refs = set(re.findall(r'os\.path\.join\(\s*BASE\s*,\s*["\']([^"\'/]+)["\']\s*\)', src))
def _covered(n):
    if n in _KNOWN_UNSHIPPED: return True
    if ("command-center/%s" % n) in fw: return True                 # exact file OR a dir entry (e.g. static)
    return any(p == "command-center/%s" % n or p.startswith("command-center/%s/" % n) for p in fw)
_uncovered = sorted(n for n in _refs if not _covered(n))
if _uncovered:
    print("PRESHIP FAIL: server.py references command-center file(s) via os.path.join(BASE, ...) that are MISSING "
          "from framework_paths -> the feature runs a nonexistent file on every tenant (same class as the import "
          "gap). Add them to claudesole.manifest.json (or, if genuinely runtime-only, to preship's "
          "_KNOWN_UNSHIPPED allowlist with a reason):", _uncovered)
    sys.exit(1)

# Footgun gate (the 2026-06-28 self-DoS class): `tmux kill-server` nukes the SHARED brain tmux server -> every
# node + every chief + the operator's live terminals die at once. It must NEVER live in a shipped/automatable
# script (the incident was a one-shot kill-server script registered with launchd KeepAlive -> infinite kill
# loop). Restart a SINGLE node session instead. Allowed ONLY with an explicit '# preship-allow: kill-server'
# marker on a clearly interactive, operator-confirmed break-glass tool.
import glob
ksp = []
for shp in glob.glob(os.path.join(ROOT, "**", "*.sh"), recursive=True):
    if any(seg in shp for seg in ("/_archive/", "/data/", "/scratch/", "/.git/", "/node_modules/")):
        continue
    try:
        body = open(shp, errors="ignore").read()
    except Exception:
        continue
    if "kill-server" in body and "preship-allow: kill-server" not in body:
        ksp.append(os.path.relpath(shp, ROOT))
if ksp:
    print("PRESHIP FAIL: `tmux kill-server` found in shipped script(s) -- it nukes the SHARED brain tmux "
          "server (every node + every chief + the operator's terminals at once). Restart a SINGLE node "
          "session instead; if it is a deliberate interactive break-glass tool, mark it "
          "'# preship-allow: kill-server'. Offending:", ksp)
    sys.exit(1)

# DESIGN-SYSTEM gate: the dashboard must be built with the shared UI primitives, not one-off markup. Any NEW
# feature/extension that hand-rolls a native dialog, an off-palette color, an inline-colored badge, or a
# decorative chrome emoji FAILS HERE -- so the unified look stays locked in without periodic manual re-sweeps.
# Full standard: docs/DESIGN_SYSTEM.md.  Linter: command-center/ui_lint.py.
try:
    import ui_lint
    _viol = ui_lint.lint(src)
except Exception as _e:
    print("PRESHIP FAIL: could not run the UI design-system linter:", _e); sys.exit(1)
if _viol:
    print("PRESHIP FAIL: %d design-system violation(s) in the dashboard -- build with the shared classes "
          "(docs/DESIGN_SYSTEM.md). Run `python3 command-center/ui_lint.py` for the full list:" % len(_viol))
    _by = {}
    for ln, kind, det in _viol: _by.setdefault(kind, []).append((ln, det))
    for kind in sorted(_by):
        print("  [%s] %d (e.g. server.py:%d %s)" % (kind, len(_by[kind]), _by[kind][0][0], _by[kind][0][1]))
    sys.exit(1)

# CLEAN-CORE gate: a framework file must not gain NEW tenant residue (hptuners/text2tune/carsearch/Sarah/...).
# Ratchets down toward 0 -- see command-center/residue_lint.py. Fails the ship on any regression vs the baseline.
try:
    import residue_lint
except Exception as _e:
    print("PRESHIP FAIL: could not load the residue linter:", _e); sys.exit(1)
_cur = residue_lint.scan(); _base = {}
try:
    import json as _json
    _base = _json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".residue_baseline.json")))
except Exception: pass
_reg = [(rel, _base.get(rel, 0), n) for rel, n in _cur.items() if n > _base.get(rel, 0)]
if _reg:
    print("PRESHIP FAIL: tenant residue INCREASED in %d framework file(s) (clean-core gate) -- keep the core "
          "tenant-neutral (config-drive it) or re-baseline if intentional:" % len(_reg))
    for rel, was, now in sorted(_reg): print("  %s: %d -> %d (+%d)" % (rel, was, now, now - was))
    print("  Re-baseline (only if intentional): python3 command-center/residue_lint.py --baseline")
    sys.exit(1)

# PAGE-JS SYNTAX GATE: the dashboard is one big inline <script>; a single JS syntax error (e.g. an unescaped
# apostrophe in a string) breaks the WHOLE script, so the SPA never boots and NO lens/Sessions load. Python +
# ui_lint don't catch it. node --check every inline <script> in PAGE. This is exactly the class that broke v0.99.144.
import subprocess as _sp, tempfile as _tf, shutil as _sh
_jsnote = "PAGE JS parses"
if _sh.which("node"):
    # AST-extract EVERY module-level HTML string constant that has inline JS (PAGE + TERM_PAGE + any others) --
    # a regex on r\"\"\"...\"\"\" truncates, and checking only PAGE misses the terminal page. node --check them all.
    import ast as _ast
    _blocks = []
    try:
        for _n in _ast.walk(_ast.parse(src)):
            if isinstance(_n, _ast.Assign) and isinstance(_n.value, _ast.Constant) and isinstance(_n.value.value, str) \
               and "<script>" in _n.value.value:
                _blocks += re.findall(r'<script>(.*?)</script>', _n.value.value, re.S)
    except Exception: pass
    _bad = None
    for _b in _blocks:
        if not _b.strip(): continue
        _t = _tf.NamedTemporaryFile("w", suffix=".js", delete=False); _t.write(_b); _t.close()
        _r = _sp.run(["node", "--check", _t.name], capture_output=True, text=True); os.unlink(_t.name)
        if _r.returncode != 0: _bad = _r.stderr.strip(); break
    if _bad is not None:
        print("PRESHIP FAIL: the dashboard PAGE JavaScript has a SYNTAX ERROR -- one bad char (e.g. an unescaped "
              "apostrophe in a JS string) breaks the ENTIRE inline script, so NO lens/Sessions load (this is exactly "
              "what broke v0.99.144). Fix it before shipping:")
        for _ln in _bad.splitlines()[-4:]: print("  " + _ln[:200])
        sys.exit(1)
else:
    _jsnote = "PAGE-JS gate SKIPPED (node not found)"

# BEHAVIORAL gate (deep-audit 2026-07-09 finding 0.2): run the unit suites (imports server.py by path, no network,
# ~2s). These existed but were NEVER in the ship path, so a logic regression in mesh auth / CCR / deliverables /
# save-load could ship fleet-wide unseen. 6 pre-existing DRIFT failures are quarantined with @unittest.skip + an
# un-skip TODO in each; any NEW failure fails the ship. (_sp = subprocess, imported in the PAGE-JS gate above.)
_tests = "tests.test_framework tests.test_cognition"
_tr = _sp.run([sys.executable, "-m", "unittest", "-q"] + _tests.split(), cwd=ROOT, capture_output=True, text=True)
if _tr.returncode != 0:
    print("PRESHIP FAIL: behavioral unit tests did not pass -- a logic regression would ship to the whole fleet. "
          "Run `python3 -m unittest %s` for detail. Tail:" % _tests)
    for _ln in (_tr.stderr or _tr.stdout or "").strip().splitlines()[-10:]: print("  " + _ln[:200])
    sys.exit(1)
_tsumm = (_tr.stderr or "").strip().splitlines()[-1] if (_tr.stderr or "").strip() else "ran"

print("PRESHIP OK: all %d local engine modules imported by server.py are in framework_paths (%s); no "
      "kill-server footgun; UI design-system clean; %s; no new tenant residue (clean-core: %d hits, ratcheting to 0); "
      "unit tests %s"
      % (len(local), ", ".join(local), _jsnote, sum(_cur.values()), _tsumm))
