#!/usr/bin/env python3
"""residue_lint -- the CLEAN-CORE gate: fail the ship if a FRAMEWORK file carries tenant residue.

The framework surface (manifest framework_paths) is what ships to every node. It must be tenant-NEUTRAL --
no hptuners/text2tune/carsearch/Sarah identifiers baked into shipped code/docs. This lints exactly those
paths for a set of tenant fingerprints.

RATCHET model (like retrofitting a linter onto a dirty tree): a baseline (.residue_baseline.json) records the
current per-file hit counts. The gate FAILS only when a file EXCEEDS its baseline (new residue creeps in) or a
brand-new file has residue. As we scrub, we lower the baseline -- the number only ever ratchets DOWN toward 0.

  python3 residue_lint.py             # lint against the baseline (exit 1 on regression) -- used by preship
  python3 residue_lint.py --report    # full current inventory by file (no pass/fail)
  python3 residue_lint.py --baseline  # snapshot current counts AS the new baseline (after a scrub pass)
"""
import os, re, json, sys, glob

BASE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.dirname(BASE)
MANIFEST = os.path.join(HOME, "claudesole.manifest.json")
BASELINE = os.path.join(BASE, ".residue_baseline.json")

# Tenant FINGERPRINTS -- identifiers that must never ship in a framework file. Deliberately specific (real
# tenant names/paths/ids), not generic words, to avoid false positives.
MARKERS = re.compile(r"""(
    hptuner | carsearch | text2tune | t2tbridge | t2tcrons |
    sarahkarger | Sarah\ Karger | \bSarah\b | avenlur | getcalibrated |
    Samsung990PRO | app58zxrnoAKrn92s | api\.text2tune\.com | 7th\ Ave
)""", re.IGNORECASE | re.VERBOSE)

TEXT_EXT = (".py", ".js", ".json", ".md", ".sh", ".txt", ".html", ".css")
SKIP = {"command-center/residue_lint.py", "command-center/preship.py",   # NAME the markers by design (linter + gate)
        "docs/CHANGELOG.md"}   # narrates tenant work EVERY ship by design -> can't gate on it; product-changelog strategy is Phase 4


def _framework_files():
    """Expand manifest framework_paths (files, dirs, globs) into the set of shippable TEXT files, repo-relative."""
    try:
        fps = json.load(open(MANIFEST))["framework_paths"]
    except Exception as e:
        print("residue_lint: cannot read manifest: %s" % e); sys.exit(2)
    files = set()
    for p in fps:
        for m in glob.glob(os.path.join(HOME, p)):
            if os.path.isfile(m):
                if m.endswith(TEXT_EXT): files.add(os.path.relpath(m, HOME))
            elif os.path.isdir(m):
                for root, _dirs, fs in os.walk(m):
                    if "secrets" in root.split(os.sep) or "/.git" in root: continue
                    for f in fs:
                        if f.endswith(TEXT_EXT): files.add(os.path.relpath(os.path.join(root, f), HOME))
    return sorted(files)


def scan():
    """{relpath: hit_count} for every framework file with >=1 tenant marker."""
    out = {}
    for rel in _framework_files():
        if rel in SKIP: continue
        try:
            txt = open(os.path.join(HOME, rel), encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        n = len(MARKERS.findall(txt))
        if n: out[rel] = n
    return out


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    cur = scan()
    total = sum(cur.values())
    if arg == "--baseline":
        json.dump(cur, open(BASELINE, "w"), indent=2, sort_keys=True)
        print("residue baseline written: %d files, %d total hits" % (len(cur), total))
        return 0
    if arg == "--report":
        print("TENANT RESIDUE in framework files: %d hits across %d files" % (total, len(cur)))
        for rel, n in sorted(cur.items(), key=lambda kv: -kv[1]):
            print("  %4d  %s" % (n, rel))
        return 0
    # gate mode: compare to baseline, fail on any regression
    base = {}
    try: base = json.load(open(BASELINE))
    except Exception: pass
    regressions = []
    for rel, n in cur.items():
        allowed = base.get(rel, 0)
        if n > allowed:
            regressions.append((rel, allowed, n))
    if regressions:
        print("RESIDUE-LINT FAIL: tenant residue INCREASED in framework files (clean-core gate):")
        for rel, allowed, n in sorted(regressions):
            print("  %s: %d -> %d (+%d) tenant refs. Make it config-driven/neutral, or re-baseline if intentional." % (rel, allowed, n, n - allowed))
        print("Baseline total was %d; scrub the file(s) above (see docs -- clean-core). Re-baseline: python3 command-center/residue_lint.py --baseline" % sum(base.values()))
        return 1
    baseline_total = sum(base.values())
    print("RESIDUE-LINT OK: no new tenant residue in framework files (%d hits vs baseline %d; ratcheting to 0)." % (total, baseline_total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
