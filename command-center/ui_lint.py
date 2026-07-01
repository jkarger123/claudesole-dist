#!/usr/bin/env python3
"""ui_lint.py -- the DESIGN-SYSTEM ENFORCER for the dashboard frontend (the PAGE/TERM_PAGE/RALPH_PAGE/LOGIN_PAGE
strings in server.py). Runs in the preship gate, so any NEW feature/extension that introduces a one-off UI
primitive FAILS the ship instead of silently drifting. Lock-in, not just documentation. See docs/DESIGN_SYSTEM.md.

Catches:
  1. NATIVE DIALOGS  -- bare confirm()/prompt()/alert()  -> use confirmM()/promptM()/alertM()
  2. OFF-PALETTE     -- hardcoded GitHub-palette hexes    -> use design tokens (var(--...)) / theme hexes
  3. INLINE BADGES   -- <span class="badge" style="background:#..."> with a LITERAL color -> use .badge.bdg-*
                        (runtime-computed colors  style="background:'+x+'..."  are allowed)
  4. CHROME EMOJI    -- decorative emoji at the START of a header/title/label/button/option/section
                        -> drop it (functional status emoji inside data rows/badges are fine)

Run: python3 command-center/ui_lint.py   (exit 0 = clean, 1 = violations)
"""
import re, sys, os

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")

# ---- emoji classification (mirrors deemoji.py) -------------------------------------------------
KEEP = set("✓✔✕✗＋▶◀▸▾▴→←↑↓•·○●★☆⟳↻↺⌫⏎♦◆")   # monochrome UI glyphs kept even at a label start
def is_emoji(c):
    o = ord(c)
    if c in KEEP: return False
    return (0x1F000 <= o <= 0x1FAFF or 0x2600 <= o <= 0x26FF or 0x2700 <= o <= 0x27BF or
            0x2B00 <= o <= 0x2BFF or 0x1F1E6 <= o <= 0x1F1FF or 0x23E0 <= o <= 0x23FF or
            o in (0x2049, 0x203C, 0x2139, 0x24C2, 0x2934, 0x2935, 0x3030, 0x303D, 0x3297, 0x3299, 0xFE0F, 0x20E3))

# label-start anchors: an emoji right after one of these is decorative chrome
LABEL_ANCHORS = [
    r'<b>', r'<button\b[^>]*>', r'<option\b[^>]*>', r'<h2\b[^>]*>',
    r'<h3\b[^>]*>(?:<span[^>]*>)?', r'<label\b[^>]*>', r'<summary\b[^>]*>',
    r'class="cc-h-ic">', r"sec\(\s*['\"]",
]
ANCHOR_RE = re.compile('(?:' + '|'.join(LABEL_ANCHORS) + r')\s*')

# off-palette GitHub hexes that should never appear (we are a gold-on-dark theme)
GH_HEXES = ['#161b22', '#238636', '#1f6feb', '#388bfd', '#21262d', '#0d1117', '#30363d', '#e6edf3']
# #0d1117 is allowed ONLY as a dark code-block background; flag the rest hard.
GH_HARD = ['#161b22', '#238636', '#1f6feb', '#388bfd', '#21262d']

def lineno(src, idx): return src.count('\n', 0, idx) + 1

def lint(src):
    v = []  # (line, kind, detail)
    # only lint inside the page template strings
    spans = []
    for nm in ['LOGIN_PAGE', 'TERM_PAGE', 'RALPH_PAGE', 'PAGE']:
        m = re.search(r'^' + nm + r' = (?:r)?"""', src, re.M)   # ^ anchor: 'PAGE' must not match 'TERM_PAGE'
        if not m: continue
        start = m.end()
        end = src.find('"""', start)
        spans.append((nm, start, end if end > 0 else len(src)))

    for nm, s, e in spans:
        seg = src[s:e]
        base = s
        # 1. native dialogs
        for m in re.finditer(r'(?<![\w.])(confirm|prompt|alert)\(', seg):
            v.append((lineno(src, base + m.start()), 'native-dialog',
                      f'{m.group(1)}() -> use {m.group(1)}M()'))
        # 3. inline static badges (literal color)
        for m in re.finditer(r'class="badge"\s+style="background:#[0-9a-fA-F]', seg):
            v.append((lineno(src, base + m.start()), 'inline-badge',
                      'literal-color badge -> use .badge.bdg-*'))
        for m in re.finditer(r'style="background:#[0-9a-fA-F][^"]*"\s+class="badge"', seg):
            v.append((lineno(src, base + m.start()), 'inline-badge',
                      'literal-color badge -> use .badge.bdg-*'))
        # 2. off-palette hard hexes -- only inside INLINE style="..." (the centralized CSS palette/tokens may
        #    legitimately hold raw hexes; what we forbid is hand-rolling GitHub colors in markup).
        for sm in re.finditer(r'style="([^"]*)"', seg):
            for hx in GH_HARD:
                if hx in sm.group(1):
                    v.append((lineno(src, base + sm.start()), 'off-palette',
                              f'{hx} (GitHub palette) in inline style -> use a theme token'))
        # 4. chrome emoji at a label start -- EXEMPT icon-only controls (emoji is the whole label, e.g. a 📎/🗑
        #    button); those are functional affordances. We forbid DECORATIVE emoji that precede real text.
        for m in ANCHOR_RE.finditer(seg):
            j = m.end()
            if j < len(seg) and is_emoji(seg[j]):
                run = ''; k = j
                while k < len(seg) and (is_emoji(seg[k]) or seg[k] == ' '):
                    if is_emoji(seg[k]): run += seg[k]
                    k += 1
                rest = seg[k:k+1]
                if rest == '<' or rest == '':          # icon-only control -> allowed
                    continue
                v.append((lineno(src, base + j), 'chrome-emoji',
                          f'decorative emoji {run!r} before text -> drop it (icon-only controls may keep a glyph)'))

    # 5. HELP COVERAGE -- every built-in lens the dashboard can render MUST have an entry in the HELP registry, so
    #    the persistent per-tab help header (paintLensHelp) is never blank. This is the discipline that keeps help
    #    in lockstep with the tabs: add or rename a lens without adding its help and the ship FAILS here.
    page = ''
    for nm, s, e in spans:
        if nm == 'PAGE': page = src[s:e]; break
    if page:
        hm = re.search(r'var HELP=\{', page)
        help_keys = set()
        if hm:
            # keys look like `  ralph:{...` / `notes:{...` at an entry start (after { or , or newline)
            hb = page[hm.end():]
            depth = 1; i = 0
            while i < len(hb) and depth > 0:      # walk to the matching close of the HELP object
                c = hb[i]
                if c == '{': depth += 1
                elif c == '}': depth -= 1
                i += 1
            help_body = hb[:i]
            help_keys = set(re.findall(r'(?:^|[,{\n])\s*([a-z][a-z0-9_]*)\s*:\s*\{', help_body))
        # the lenses render() actually dispatches (LENS=="x" or LENS="x")
        dispatched = set(re.findall(r'LENS\s*==?\s*"([a-z][a-z0-9_]*)"', page))
        EXEMPT = {'correspondence'}   # sub-views that aren't a nav tab of their own
        missing = sorted(dispatched - help_keys - EXEMPT)
        for lens in missing:
            v.append((0, 'missing-help', f'lens "{lens}" is rendered but has no HELP entry -> add HELP.{lens} = {{t,sub,h}}'))

        # 6. TOOLTIP COVERAGE -- an ICON-ONLY button (its visible label is a glyph / <=2 letters) must carry a
        #    title= (or aria-label). Text buttons ("Save", "Run now") are self-describing and exempt. This bakes
        #    in "every control worth hovering has a tooltip" so a new mystery-glyph button fails the ship.
        for bm in re.finditer(r'<button\b([^>]*)>(.*?)</button>', page, re.S):
            attrs, label = bm.group(1), bm.group(2)
            if 'title=' in attrs or 'aria-label=' in attrs:
                continue
            txt = re.sub(r'<[^>]+>', '', label)
            txt = re.sub(r"'\+[^+]+\+'", '', txt).replace('&amp;', '&').strip()
            letters = sum(ch.isalnum() for ch in txt)
            if txt and letters <= 2 and len(txt) <= 6:
                v.append((lineno(src, s + bm.start()), 'no-tooltip',
                          f'icon-only button {txt!r} has no title= -> add a hover tooltip (docs/DESIGN_SYSTEM.md)'))
    return v

def main():
    src = open(PATH, encoding='utf-8').read()
    v = lint(src)
    if not v:
        print("UI-LINT OK: dashboard uses the design system (no native dialogs / off-palette / inline badges / chrome emoji)")
        return 0
    by = {}
    for ln, kind, det in v:
        by.setdefault(kind, []).append((ln, det))
    print("UI-LINT FAILED: %d design-system violation(s). Build it with the shared classes (docs/DESIGN_SYSTEM.md):\n" % len(v))
    for kind in sorted(by):
        rows = by[kind]
        print(f"  [{kind}] {len(rows)}:")
        for ln, det in rows[:25]:
            print(f"     server.py:{ln}  {det}")
        if len(rows) > 25:
            print(f"     ... +{len(rows)-25} more")
    return 1

if __name__ == "__main__":
    sys.exit(main())
