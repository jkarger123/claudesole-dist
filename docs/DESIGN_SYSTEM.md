# ClaudeFather Dashboard — Design System (the ONE way to build UI)

The dashboard has **one** visual language. Every lens, feature, and extension is built from the shared
primitives below — never one-off markup. This is **enforced**: `command-center/ui_lint.py` runs in the
preship gate (`command-center/preship.py`), so a ship that hand-rolls a dialog, color, badge, or chrome emoji
**fails before it reaches the fleet**. Build with these and you never get re-swept.

> Goal: sleek, modern, enterprise (think Linear / Vercel / Stripe), on a gold-on-dark brand. **Not** cartoony,
> not overly friendly, no 20 variants of the same thing.

## The 4 hard rules (the linter fails the ship on these)

1. **No native pop-ups.** Never `confirm()` / `prompt()` / `alert()`. Use the promise-based dialogs:
   `await confirmM(msg, {danger:true, ok:'Delete'})` · `await promptM(label, def)` (returns value or `null`) ·
   `await alertM(msg)`. They stack above any open modal, Esc/backdrop-cancel, Enter-confirm. (The embedded
   terminal/Ralph pages have their own self-contained `confirmM` + `#tdlg` for the same reason.)
2. **No off-palette colors.** Never hardcode GitHub-palette hexes (`#161b22 #238636 #1f6feb #388bfd #21262d`,
   etc.) in inline `style="..."`. Use design tokens: `var(--bg) --card --card2 --line --ink --mut --dim
   --accent --accent-rgb --grad --glow --ok --warn --err`. Raw hexes belong only in the central CSS palette.
3. **No inline-colored badges.** Never `<span class="badge" style="background:#x22;color:#x">`. Use a palette
   class: `<span class="badge bdg-amber">` (bdg-amber/violet/green/ok/red/cyan/blue/blue2/azure/gray/slate/
   gold/lilac/teal/ink/dim/plain). A *runtime-computed* color (`style="background:'+c+'22;color:'+c+'"`) is OK.
4. **No decorative chrome emoji.** No emoji at the START of a header/title/section-label/labeled-button/option.
   Headings and buttons are text. (FUNCTIONAL status emoji INSIDE data rows/badges are fine — 🟢/⚪ state,
   ⚠ warnings, ⏳ running, source/type icons. Icon-ONLY controls may keep a single glyph: 📎 ⏰ 🗑 ☰ 🔍.)

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
`confirmM/promptM/alertM`, `toast`. Then run `python3 command-center/ui_lint.py` — green means it'll ship.
If you genuinely need a new primitive, ADD it to the shared CSS + this doc (so the next feature reuses it),
don't inline a one-off. Always verify headless before shipping (see docs + the screenshot tooling).
