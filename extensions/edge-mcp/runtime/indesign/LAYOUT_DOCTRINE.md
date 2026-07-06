# Professional Layout Doctrine (InDesign via Edge MCP)

Field-proven rules for building a professional multi-page document (book, magazine,
devotional) by driving InDesign over `edge-mcp`. Read this BEFORE you place a single
repeating element. It exists because an agent built a 355-entry book by drawing every
constant onto every page, then had to refactor all 355 pages onto a parent afterward.
Doing it right the first time is the whole point.

The proven helpers that implement all of this live next to this file:
`layout_helpers.js` (getParent / dupeToParent / addFolio / setupRunningHeader /
insertVariableInstance / applyStyleKeepOverrides / applyObjectStyle /
getBackgroundLayer / applyParentAndStrip / preflight = lintConstants +
lintDirectFormatting + lintFonts).

## Classify EVERY element before you build

The rework this doctrine prevents came from building with everything drawn per-page and
direct-formatted. Two independent axes: WHERE a thing lives (constant → parent, content →
page) and HOW its look is defined (styles, never direct formatting). Classify each element:

| Element | Classification | Goes to |
|---|---|---|
| Fixed-position constant (folio, running head, rule, watermark) | constant | **parent page** |
| Running head that CHANGES (chapter/month) | constant, dynamic | **Running Header text variable** |
| Watermark / background | constant | **locked layer** |
| Changing content, consistent look (date, verse, body, divider) | content + look | **document page, but formatted by named paragraph/character/object STYLES — never direct-format repeating text** |
| Page numbering | constant | **current-page-number marker + Numbering/Section Options** |
| The actual words of each entry | content | **document page, left directly editable** |

The two governing rules: **constants → parent; look → styles; content → page.** If the
template enforces those three up front, this whole class of rework disappears.

Quick test per element: *"If I change this, does it change on one page or all of them?"*
All → constant → parent. Only this one → per-page content (but its LOOK still comes from a
style). *"Am I typing/formatting this the same way on every page?"* → it's a style, not
direct formatting.

Worked example (a daily devotional, 355 entries):
- **Constant (parent):** page number / folio, running heads, hairline rule, watermark.
- **Per-page CONTENT, but STYLE-controlled look:** date, reference, verse, divider glyph,
  body, NOTES. Their vertical positions vary with entry length, so they sit on the page —
  but their look is entirely paragraph/character/object styles.
- **The ONLY per-page direct value:** the body **point size** — it auto-fits each entry to
  one page. Everything else about the body except its size is style-controlled. That single
  computed override is applied with the clearOverrides pattern below.

## The five mandates

1. **Parent pages for every repeating element** — folios, running heads, rules,
   watermarks. Use a **parent hierarchy** (base → child) when there are multiple page
   types (e.g. a base parent with the rule+folio, child parents per section). In
   `layout_helpers.js`: `getParent(doc, prefix, {basedOn})`, `dupeToParent(item, page)`.

2. **Running heads that CHANGE (chapter/month) = a Running Header text variable**, not
   manual text. The variable reads a styled run off each page automatically, so the
   month is never typed and never wrong. `setupRunningHeader(doc, name, style)` +
   `insertVariableInstance(frame, variable)`. See the UXP quirk chain below.

3. **Page numbers = the auto current-page-number marker** (`SpecialCharacters.AUTO_PAGE_NUMBER`
   on a parent text frame). Front-matter vs body page numbering is handled with
   **Numbering & Section Options** (`doc.sections`), not by typing numbers. Mirror
   verso/recto by page side — compare with `String(page.side)`. `addFolio(page, bounds)`.

4. **Watermarks / backgrounds on a LOCKED layer** ("Background"), sent behind content,
   so they can't be selected by accident and can be hidden while editing.
   `getBackgroundLayer(doc)`. NB: a reduced-opacity PLACED image renders as an uneven
   wash — bake watermarks to flat opaque art (see AGENT.md).

5. **Look = named STYLES, never direct formatting on repeating text.** Every recurring
   run (date, reference, verse, body, NOTES) gets a paragraph and/or character style;
   repeated vector art (the divider) gets an **object style**. Edit the style once → every
   entry follows. The pattern that lets styles coexist with a computed per-page value:
   **apply style → `clearOverrides()` → re-apply only the one intended per-page attribute**
   (e.g. the auto-fit body point size). `applyStyleKeepOverrides(text, style, {pointSize})`;
   `applyObjectStyle(item, style)`. This is what makes "everything about the body except its
   size is style-controlled" true.

6. **Run the full preflight before AND after building** — the three-check test (below)
   verifies you actually got constants→parent, look→styles, and fonts clean.

## The UXP quirks that cost real time (encoded in layout_helpers.js)

- **Running-header variable:** `variableType = VariableTypes.MATCH_CHARACTER_STYLE_TYPE`
  (or `MATCH_PARAGRAPH_STYLE_TYPE`); configure via `variable.variableOptions.appliedCharacterStyle`.
  There is **no `insertVariable()`** — insert an instance:
  `ip.textVariableInstances.add()` then set `inst.associatedTextVariable = variable`.
- **Parent naming:** set `masterSpread.namePrefix` — `baseName` is unreliable for lookup.
- **Build parent furniture with `item.duplicate(masterPage)`** — it preserves exact
  coordinates, so you avoid spread-relative coordinate math.
- **Auto page-number special character works on parents.**
- **Enum identity fails:** `page.side === PageSideOptions.LEFT_HAND` is ALWAYS false —
  use `String(page.side)` (`"LEFT_HAND"` / `"RIGHT_HAND"`).

## Preflight / lint — catch the mistake automatically

`preflight(doc, {minPages: 5})` runs three checks and returns one report:
- **`constantsShouldBeParent`** (`lintConstants`) — items identical (same kind, rounded
  position/size, text) on N+ pages → "these should be on a parent." Refactor with
  `applyParentAndStrip(pages, parent, zone)`.
- **`textShouldBeStyled`** (`lintDirectFormatting`) — repeating paragraphs with no
  paragraph style or with local overrides → "this should be a paragraph style." Fix with
  `applyStyleKeepOverrides`.
- **`fontProblems`** (`lintFonts`) — any font whose status isn't `INSTALLED`
  (missing/substituted) → a silent substitution ruins a print job.

Run it **before a build** on the template (confirm parents own constants + styles own the
look) and **after a build** as a gate — a non-empty result is your automatic signal that
you drew a constant per-page or direct-formatted repeating text and should refactor.

## Refactoring a document already built the wrong way

If constants were already drawn on every page: build the parent
(`getParent` + `dupeToParent` one page's furniture up), then
`applyParentAndStrip(pages, parent, zone)` applies the parent to each page and removes
the now-duplicated furniture inside the constant zone. Verify with `lintConstants`.
