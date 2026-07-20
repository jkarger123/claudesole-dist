# ClaudeFather Dashboard — Design System (the ONE way to build UI)

The dashboard has **one** visual language. Every lens, feature, and extension is built from the shared
primitives below — never one-off markup. This is **enforced**: `command-center/ui_lint.py` runs in the
preship gate (`command-center/preship.py`), so a ship that hand-rolls a dialog, color, badge, or chrome emoji
**fails before it reaches the fleet**. Build with these and you never get re-swept.

> Goal: sleek, modern, enterprise (think Linear / Vercel / Stripe). Gold-on-dark is the DEFAULT brand (the **Dark**
> theme), but the dashboard is **multi-theme** now — build with tokens, never fixed colors (see `docs/THEMING.md`).
> **Not** cartoony, not overly friendly, no 20 variants of the same thing.

## The 6 hard rules (the linter fails the ship on these)

1. **No native pop-ups.** Never `confirm()` / `prompt()` / `alert()`. Use the promise-based dialogs:
   `await confirmM(msg, {danger:true, ok:'Delete'})` · `await promptM(label, def)` (returns value or `null`) ·
   `await alertM(msg)`. They stack above any open modal, Esc/backdrop-cancel, Enter-confirm. (The embedded
   terminal/Ralph pages have their own self-contained `confirmM` + `#tdlg` for the same reason.)
2. **No off-palette colors.** Never hardcode GitHub-palette hexes (`#161b22 #238636 #1f6feb #388bfd #21262d`,
   etc.) in inline `style="..."`. Use **design tokens** — surfaces `var(--bg) --bg2 --bg-warm --card --card2 --el1
   --el2 --el3`, text `--ink --near --mut --dim`, lines `--line --hair --hair2`, accent `--accent(-rgb)
   --accent-light(-rgb) --accent-dark --grad --glow --tint --ring`, status `--ok --warn --err --info` (+ their
   `-rgb` for alpha tints). Raw hexes belong ONLY in the theme-definition blocks. **The dashboard is multi-theme**
   (Dark/Light/High-Contrast/Slate/Midnight/Paper): a token resolves to a *different value per theme*, so a
   hardcoded hex silently breaks every non-Dark theme. Full system → **`docs/THEMING.md`**.
3. **No inline-colored badges.** Never `<span class="badge" style="background:#x22;color:#x">`. Use a palette
   class: `<span class="badge bdg-amber">` (bdg-amber/violet/green/ok/red/cyan/blue/blue2/azure/gray/slate/
   gold/lilac/teal/ink/dim/plain). A *runtime-computed* color (`style="background:'+c+'22;color:'+c+'"`) is OK.
4. **No decorative chrome emoji.** No emoji at the START of a header/title/section-label/labeled-button/option.
   Headings and buttons are text. (FUNCTIONAL status emoji INSIDE data rows/badges are fine — 🟢/⚪ state,
   ⚠ warnings, ⏳ running, source/type icons. Icon-ONLY controls may keep a single glyph: 📎 ⏰ 🗑 ☰ 🔍.)
5. **Every tab has help.** Any lens the dashboard renders (a `LENS=="x"` branch) MUST have an entry in the
   `HELP` registry — `x:{t:'Title', sub:'one-liner', h:'<p>deep what/why/how</p>'}`. The persistent per-tab
   help header (`paintLensHelp`, the slim bar under the title) reads it, and the deep `h` is the "ⓘ Learn"
   inline panel + the topbar "?" modal. Add or rename a tab without its help and the ship FAILS. Extension tabs
   supply theirs via `extension.json` `lens.help` ({sub,h} or a string). Keep `sub`/`h` accurate when a tab
   changes — that's the whole point.
6. **Icon-only buttons carry a tooltip.** A button whose visible label is a glyph or ≤2 letters MUST have a
   `title=` (or `aria-label=`). Text buttons ("Save", "Run now") are self-describing and exempt. So a new
   mystery-glyph control can't ship without a hover explanation.

## The components (use these, don't reinvent)

**Lens header** — `cc-head`: slim title bar.
```
<div class="cc-head"><span class="cc-h-t">Tasks</span><span class="cc-h-sub">subtitle</span>
  <span class="cc-chip"><b>3</b> open</span>
  <span class="cc-h-act"><button class="mini go" onclick="...">＋ Add</button></span></div>
```
**Action list** — `cc-list` + `cc-item` (dense rows: leading `cc-ic`, `cc-main` with `cc-ti`/`cc-mt`/`cc-dt`,
trailing `cc-acts`). `cc-item.accent` = left accent rail. Section labels: `cc-sec` (`.warn`/`.good`) + `cc-n` count.
**Tile grid** — `cc-grid` + `cc-tile` (equal-height: `cc-t-h` header, `cc-tag` pills, `cc-t-sum` flex body,
`cc-t-foot` pinned footer). `cc-tile.on` = active/installed ring. Tag pills: `cc-tag cat|paid|ok|lock`.
**Panel** — `cc-panel` (forms/config: `cc-p-h` header, `cc-p-note` prose, `cc-row-in` field row).
**Inputs** — `cc-in` on every input/select/textarea (tokened bg/border + focus ring). Search bar: `cc-searchbar`.
**Buttons** — `mini` / `mini go` (primary) / `mini danger` (destructive) · `btn` / `btn go` / `btn danger` (modal).
**Badges** — `badge` + a `bdg-*` color · status lifecycle pill `cc-pill` · count `cc-chip`.
**Feedback** — `toast(html, ms)` (transient) · `busyOn(msg, sub)` / `busyOff()` (blocking spinner) ·
`showM(html)` / `closeM()` (a generic modal; put `.row`/`.btns` inside).

## Adding a new lens / feature / extension
Build the body from `cc-head` + (`cc-list`/`cc-grid`/`cc-panel`). Reuse `cc-in`, `mini`/`btn`, `badge bdg-*`,
`confirmM/promptM/alertM`, `toast`. **Add a `HELP` entry for the tab** (`t`/`sub`/`h`) — rule 5, enforced.
Then run `python3 command-center/ui_lint.py` — green means it'll ship.
If you genuinely need a new primitive, ADD it to the shared CSS + this doc (so the next feature reuses it),
don't inline a one-off. Always verify headless before shipping (see docs + the screenshot tooling).
