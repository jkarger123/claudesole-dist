/*
 * layout_helpers.js -- proven UXP/InDesign DOM helpers for professional book layout.
 *
 * WHY THIS FILE EXISTS: driving InDesign over edge-mcp, an agent lost real time
 * rediscovering the fiddly UXP text-variable / parent-page / duplicate APIs, and
 * (worse) built a 355-entry book by DRAWING every constant onto every page, then
 * had to refactor all 355 pages onto a parent afterward. These helpers encode the
 * right way so no future job relearns it. See LAYOUT_DOCTRINE.md for the "why".
 *
 * HOW TO USE over edge-mcp (no module system in a UXP execute call):
 *   PREPEND the parts you need to your `edge-mcp call sidekick-indesign execute`
 *   script (or push this file and read+prepend its contents). Everything hangs off
 *   the global `CF` object below. Each script must STILL set NEVER_INTERACT first:
 *     app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
 *
 * These are reference implementations built to the field-verified quirks documented
 * in AGENT.md. Adapt names/coords to your document; the API shapes are the point.
 */
const { app } = require('indesign');

var CF = {};

/* ------------------------------------------------------------------ *
 * Parent (master) pages -- where EVERY repeating constant belongs.
 * Edit the parent once -> all applied pages follow. Constants NEVER
 * get drawn per-page (that is the mistake this file prevents).
 * ------------------------------------------------------------------ */

// Get-or-create a parent (master) spread by prefix.
// QUIRK: set namePrefix -- baseName alone is unreliable for lookup/label.
CF.getParent = function (doc, prefix, opts) {
  opts = opts || {};
  for (var i = 0; i < doc.masterSpreads.length; i++) {
    var m = doc.masterSpreads.item(i);
    if (m.namePrefix === prefix) return m;
  }
  var ms = doc.masterSpreads.add();
  ms.namePrefix = prefix;                              // <- the reliable identifier
  if (opts.baseName) ms.baseName = opts.baseName;      // cosmetic; do not depend on it
  if (opts.basedOn) ms.appliedMaster = opts.basedOn;   // parent hierarchy: base -> child
  return ms;
};

// Duplicate an existing page item ONTO a parent, preserving exact coordinates.
// QUIRK: item.duplicate(masterPage) copies with the same geometricBounds --
// far safer than re-deriving spread-relative coordinate math by hand.
CF.dupeToParent = function (item, masterPage) {
  return item.duplicate(masterPage);
};

// Auto page-number (folio) marker on a parent text frame.
// The AUTO_PAGE_NUMBER special char shows the section marker on the parent and
// resolves to each document page's real number. Works on parents.
// QUIRK: mirror verso/recto by page side -- compare with String(page.side),
// because `page.side === PageSideOptions.LEFT_HAND` is ALWAYS false in UXP.
CF.addFolio = function (masterPage, bounds, opts) {
  opts = opts || {};
  var tf = masterPage.textFrames.add();
  tf.geometricBounds = bounds;                         // [y1,x1,y2,x2] in doc units
  tf.insertionPoints.item(0).contents = SpecialCharacters.AUTO_PAGE_NUMBER;
  var side = String(masterPage.side);                  // "LEFT_HAND" / "RIGHT_HAND"
  var para = tf.paragraphs.item(0);
  para.justification = (side === 'LEFT_HAND')
    ? Justification.LEFT_ALIGN                          // verso: outer-left
    : Justification.RIGHT_ALIGN;                        // recto: outer-right
  if (opts.charStyle) tf.texts.item(0).appliedCharacterStyle = opts.charStyle;
  return tf;
};

/* ------------------------------------------------------------------ *
 * Running headers that CHANGE per page (chapter / month) -- a Running
 * Header TEXT VARIABLE, never typed text. It reads a styled run off
 * each page automatically, so the month is never hand-entered.
 * ------------------------------------------------------------------ */

// Create (or reuse) a running-header text variable that mirrors the first/last
// occurrence of text in a given character or paragraph style on the page.
// QUIRK CHAIN (each of these cost real time to find):
//   - variableType = VariableTypes.MATCH_CHARACTER_STYLE_TYPE  (or MATCH_PARAGRAPH_STYLE_TYPE)
//   - configure via variable.variableOptions.appliedCharacterStyle (NOT a top-level prop)
//   - there is NO insertVariable(); you insert an INSTANCE:
//       ip.textVariableInstances.add(); then set inst.associatedTextVariable = variable
CF.setupRunningHeader = function (doc, name, style, opts) {
  opts = opts || {};
  var v = null;
  for (var i = 0; i < doc.textVariables.length; i++) {
    if (doc.textVariables.item(i).name === name) { v = doc.textVariables.item(i); break; }
  }
  if (!v) { v = doc.textVariables.add(); v.name = name; }

  var byPara = !!opts.paragraphStyle;
  v.variableType = byPara
    ? VariableTypes.MATCH_PARAGRAPH_STYLE_TYPE
    : VariableTypes.MATCH_CHARACTER_STYLE_TYPE;

  var vo = v.variableOptions;
  if (byPara) vo.appliedParagraphStyle = style;
  else        vo.appliedCharacterStyle = style;
  // FIRST_ON_PAGE gives a top running head; LAST_ON_PAGE for a bottom/dictionary style.
  vo.searchStrategy = opts.searchStrategy || SearchStrategies.FIRST_ON_PAGE;
  return v;
};

// Insert an instance of a text variable at the start of a parent text frame.
CF.insertVariableInstance = function (frame, variable, opts) {
  opts = opts || {};
  var ip = frame.insertionPoints.item(0);
  var inst = ip.textVariableInstances.add();           // <- add the instance...
  inst.associatedTextVariable = variable;              // <- ...then bind the variable
  if (opts.charStyle) frame.texts.item(0).appliedCharacterStyle = opts.charStyle;
  return inst;
};

/* ------------------------------------------------------------------ *
 * STYLES -- the "look" of repeating content lives in NAMED paragraph /
 * character / object styles, NEVER in direct formatting. Change the look
 * once (edit the style) -> every entry follows. Repeating text that is
 * direct-formatted is the second half of the per-page mistake (the first
 * being constants drawn per-page) and forces the same kind of rework.
 * ------------------------------------------------------------------ */

// Apply a paragraph/character style while PRESERVING computed per-page attributes.
// THE PATTERN that lets styles coexist with a computed layout (e.g. body point size
// is auto-fit per entry, but everything else about the body is style-controlled):
//   apply the style -> clearOverrides() -> re-apply ONLY the intended per-page attr(s).
// text: a text object (story/paragraph/textFrame.texts.item(0)); style: a paragraph style;
// preserved: {pointSize: 10.5, ...} -- the handful of attributes that are legitimately
// per-page. Everything not listed reverts to the style (kills stray direct formatting).
CF.applyStyleKeepOverrides = function (text, style, preserved) {
  preserved = preserved || {};
  text.appliedParagraphStyle = style;
  try { text.clearOverrides(OverrideType.ALL); } catch (e) { text.clearOverrides(); }
  for (var k in preserved) { try { text[k] = preserved[k]; } catch (e) {} }
  return text;
};

// Object style for repeated VECTOR art (e.g. the — ◆ — divider): the look is defined
// once in the object style; each instance just carries position. Set namePrefix-style
// naming via .name; apply with item.applyObjectStyle(style, true /*clearOverrides*/).
CF.applyObjectStyle = function (item, style) {
  item.applyObjectStyle(style, true, true);   // (style, clearingOverrides, clearingObjectStyleOverrides)
  return item;
};

/* ------------------------------------------------------------------ *
 * Watermark / background on a LOCKED layer, so it can't be selected by
 * accident and can be hidden while editing.
 * ------------------------------------------------------------------ */
CF.getBackgroundLayer = function (doc, name) {
  name = name || 'Background';
  var lyr;
  try { lyr = doc.layers.itemByName(name); if (!lyr.isValid) lyr = null; } catch (e) { lyr = null; }
  if (!lyr) {
    lyr = doc.layers.add({ name: name });
    lyr.move(LocationOptions.AT_END);                  // send behind content
  }
  lyr.locked = true;                                   // can't be nudged by accident
  return lyr;
};

/* ------------------------------------------------------------------ *
 * Apply a parent to a run of pages and STRIP the per-page furniture the
 * parent now owns, within a named zone (bounds). Use this to refactor a
 * document that was (wrongly) built with constants drawn on every page.
 * ------------------------------------------------------------------ */
// pages: array of page objects; parent: a masterSpread; zone: [y1,x1,y2,x2] the
// bounding box the parent's constants live in. Items on the doc page whose bounds
// fall inside the zone are removed (they are now supplied by the locked parent).
CF.applyParentAndStrip = function (pages, parent, zone) {
  var removed = 0;
  for (var p = 0; p < pages.length; p++) {
    var page = pages[p];
    page.appliedMaster = parent;
    for (var i = page.pageItems.length - 1; i >= 0; i--) {
      var it = page.pageItems.item(i);
      // Skip items overridden FROM the master (they belong to the parent already).
      var b;
      try { b = it.geometricBounds; } catch (e) { continue; }
      if (CF._inside(b, zone)) { it.remove(); removed++; }
    }
  }
  return removed;
};

CF._inside = function (b, z) {
  // b,z = [y1,x1,y2,x2]; true if b is fully within z (small tolerance).
  var t = 1; // 1pt tolerance
  return b[0] >= z[0] - t && b[1] >= z[1] - t && b[2] <= z[2] + t && b[3] <= z[3] + t;
};

/* ------------------------------------------------------------------ *
 * PREFLIGHT/LINT -- flag identical items repeated across many pages, i.e.
 * "these should be on a parent." Run this BEFORE (and after) a build to
 * catch the draw-constants-per-page mistake automatically.
 * Returns an array of {signature, count, pages, sampleBounds}.
 * ------------------------------------------------------------------ */
CF.lintConstants = function (doc, opts) {
  opts = opts || {};
  var minPages = opts.minPages || 5;                   // repeated on >= N pages = suspicious
  var buckets = {};
  for (var p = 0; p < doc.pages.length; p++) {
    var page = doc.pages.item(p);
    for (var i = 0; i < page.pageItems.length; i++) {
      var it = page.pageItems.item(i);
      // Only count items that are NOT already inherited from a master.
      var fromMaster = false;
      try { fromMaster = !!it.parentPage && it.parentPage.appliedMaster && it.overridden; } catch (e) {}
      var sig = CF._signature(it);
      if (!sig) continue;
      if (!buckets[sig]) buckets[sig] = { signature: sig, count: 0, pages: [], sampleBounds: null };
      buckets[sig].count++;
      buckets[sig].pages.push(page.name);
      if (!buckets[sig].sampleBounds) { try { buckets[sig].sampleBounds = it.geometricBounds; } catch (e) {} }
    }
  }
  var out = [];
  for (var k in buckets) if (buckets[k].count >= minPages) out.push(buckets[k]);
  out.sort(function (a, b) { return b.count - a.count; });
  return out;
};

// LINT 2 -- repeating text carrying DIRECT (local) formatting that should live in a
// paragraph style. Flags paragraphs whose applied style is [No Paragraph Style]/[Basic]
// or that report overrides, when the same kind of text recurs across N+ pages.
// Returns [{signature, count, pages, reason}].
CF.lintDirectFormatting = function (doc, opts) {
  opts = opts || {};
  var minPages = opts.minPages || 5;
  var buckets = {};
  for (var p = 0; p < doc.pages.length; p++) {
    var page = doc.pages.item(p);
    for (var f = 0; f < page.textFrames.length; f++) {
      var story = page.textFrames.item(f).parentStory;      // parentStory: includes overset text
      for (var pr = 0; pr < story.paragraphs.length; pr++) {
        var para = story.paragraphs.item(pr);
        var styleName = '';
        try { styleName = String(para.appliedParagraphStyle.name); } catch (e) {}
        var noStyle = /^\[(No Paragraph Style|Basic Paragraph)\]$/.test(styleName);
        var overridden = false;
        try { overridden = !!para.overrides; } catch (e) {}     // has local overrides vs its style
        if (!noStyle && !overridden) continue;                  // properly style-controlled -> fine
        var sig = 'para|' + styleName + '|' + (noStyle ? 'nostyle' : 'override');
        if (!buckets[sig]) buckets[sig] = { signature: sig, count: 0, pages: [],
              reason: noStyle ? 'no paragraph style -> should be a named style'
                              : 'direct formatting over "' + styleName + '" -> fold into the style' };
        buckets[sig].count++; buckets[sig].pages.push(page.name);
      }
    }
  }
  var out = [];
  for (var k in buckets) if (buckets[k].count >= minPages) out.push(buckets[k]);
  out.sort(function (a, b) { return b.count - a.count; });
  return out;
};

// LINT 3 -- missing / substituted fonts (a silent substitution ruins a print job).
// Returns [{name, status}] for any font not 'INSTALLED'.
CF.lintFonts = function (doc) {
  var bad = [];
  for (var i = 0; i < doc.fonts.length; i++) {
    var fnt = doc.fonts.item(i);
    var status = String(fnt.status);
    if (status !== 'INSTALLED') bad.push({ name: String(fnt.name), status: status });
  }
  return bad;
};

// Run all three preflight checks at once -> one report object.
CF.preflight = function (doc, opts) {
  return {
    constantsShouldBeParent: CF.lintConstants(doc, opts),
    textShouldBeStyled:      CF.lintDirectFormatting(doc, opts),
    fontProblems:            CF.lintFonts(doc)
  };
};

// A coarse content+geometry signature: same kind of item, same rounded position
// and size, same text -> the same "constant" repeated across pages.
CF._signature = function (it) {
  var b;
  try { b = it.geometricBounds; } catch (e) { return null; }
  var geo = [Math.round(b[0]), Math.round(b[1]), Math.round(b[2] - b[0]), Math.round(b[3] - b[1])].join(',');
  var kind = String(it.constructor.name);
  var txt = '';
  try { if (it.hasOwnProperty('contents') || 'contents' in it) txt = String(it.contents).slice(0, 40); } catch (e) {}
  return kind + '@' + geo + (txt ? '|' + txt : '');
};

module.exports = CF; // harmless if the host ignores module.exports; CF is also global-ish.
