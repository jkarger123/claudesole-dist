# Edge MCP Host (agent)

Drive MCP servers that run on a user's OWN computer -- GUI apps (Adobe InDesign/Photoshop, Blender),
their real logged-in browser, local files/devices -- over the mesh, with every call logged transparently.
Use the `edge-mcp` CLI (on PATH). Registered hosts+servers live in a registry; credentials in the vault.

WANT TO DRIVE A USER'S REAL LOGGED-IN CHROME (scraping, portal pulls)? ONE command does the whole setup --
do NOT hand-build it (register host, provision key, install Node, register server are all automatic):
    edge-mcp setup-browser <host-id> <user@tailnet-addr>   # e.g. work-laptop  jo@100.x.y.z
It registers the host (reusing an already-authorized SSH key if one exists, else prints a one-line snippet the
user pastes), preflights + auto-installs Node/checks Chrome on the host, and registers the browser server. Then:
    edge-mcp start <server>            # opens Chrome (isolated debug profile) on the user's machine
    -> the user LOGS IN once in that window; that becomes the session. Then drive it:
    edge-mcp call <server> navigate_page '{"url":"..."}'   # + take_snapshot, list_pages, click, fill_form
    edge-mcp accounts <server>         # which sites it can reach   |   edge-mcp revoke <server>  # cut access + wipe profile
If anything looks wrong, `edge-mcp doctor` shows WHICH node this CLI targets (wrong node = the #1 gotcha).

    edge-mcp hosts | servers            # what's registered (reachable? warm?)
    edge-mcp status <server>            # {warm, ready, reachable, recipe, calls, profile}
    edge-mcp call <server> <tool> '<json-args>'    # invoke a tool, JSON back
    edge-mcp run  <server> <file.js> [desc]        # run a JS file on the server (big scripts)
    edge-mcp sh   <host> '<cmd>'                    # shell ON the host (ssh, or local) -- you HAVE real shell
    edge-mcp pull <host> <remote> <local>          # scp a file BACK from the host (pull an export to inspect)
    edge-mcp push <host> <local> <remote>          # scp a file UP to the host (push an asset)
    edge-mcp host-key <host>                        # print the host's ssh key path + user@addr (for manual scp/ssh)

Reality checks:
- A host that's a LAPTOP may be ASLEEP -> status shows reachable:false; ask the user to wake it. Don't retry-hammer.
- `plugin-app` servers need the app OPEN with its plugin loaded; a call before the plugin handshakes says
  "not ready" -- `edge-mcp status` shows ready:true once connected (warm session keeps it connected).
- Transport timeout is generous (600s) -- BUT a `plugin-app` (Sidekick/InDesign) has its OWN ~30s response cap:
  a long script returns "Plugin response timeout" yet KEEPS RUNNING in the app. For any long op (a big build,
  a PDF/JPEG export) do NOT wait on the return -- FIRE it, then POLL for a completion marker you write yourself
  (a flag file you `edge-mcp pull`, or re-query a known variable/state). Only genuinely-fast calls can trust the
  direct return.

INDESIGN (server `sidekick-indesign`, recipe plugin-app) -- tools: `execute` (UXP JS), `snapshot`
(page/spread -> JPEG), get_layout, get_font_metrics, get_health. The design loop: write UXP JS -> run it ->
SNAPSHOT to SEE the result -> iterate. HARD-WON RULES (don't relearn these the slow way):
- **`snapshot` is LOW-RES (~72dpi -- a 7x10 page renders ~504x720px). Trust it for rough layout/composition ONLY.**
  It physically CANNOT resolve color, opacity, image edges, watermark fades, or "does this artifact print." For
  anything fine, export a REAL raster: `app.jpegExportPreferences.exportResolution = 200; doc.exportFile(
  ExportFormat.JPG, "<plain-string path>", false)`. The path MUST be a plain string into a real user folder
  (e.g. an expanded "~/Downloads/x.jpg") -- a UXP File object, an InDesign File object, and /tmp all FAIL (UXP
  sandbox). Then `edge-mcp pull <host> <remote> <local>` and Read the file to actually verify.
- **`snapshot` renders `app.activeDocument`.** Set `app.activeDocument = d` FIRST, or you snapshot the wrong open doc.
- **Every script MUST start with** `app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;`
  -- a modal (missing font, an export warning) freezes the whole script engine and forces an InDesign force-quit.
- **You CANNOT see the user's screen.** `screencapture` over ssh returns only the desktop wallpaper (macOS TCC
  blocks window contents for non-GUI sessions). To see what the user sees, ASK them to screenshot.
- You have real shell + scp to the host (`edge-mcp sh|pull|push`) -- use it to pull exports back and push assets up.
  Far better than base64-chunking binaries through a plugin tool (that double-JSON-encodes and is fragile).
UXP quirks: `const {app}=require('indesign')`; `doc.pages.item(0)` not `[0]`; compare objects with `.equals()`;
ENUM identity FAILS -- `page.side === PageSideOptions.LEFT_HAND` is ALWAYS false, use `String(page.side)`; units are
strings ("11pt","0.5in"); paragraph break `\r`; when text oversets read `frame.parentStory.paragraphs`
(frame.paragraphs omits overset ones); a reduced-opacity placed image renders as an uneven wash -- bake watermarks
to FLAT OPAQUE art instead. `snapshot` args: {target:"page"|"spread", index:<0-based>}.

LAYOUT DOCTRINE (building a multi-page book/magazine/devotional -- read this BEFORE placing repeating elements):
- **THE THREE RULES: constants -> PARENT pages; look -> named STYLES; content -> document pages.** Never draw a
  repeating element per-page, and never direct-format repeating text. Edit the parent (or the style) once -> every page
  follows. Both halves of the mistake -- furniture drawn per-page AND repeating text direct-formatted -- force a full
  refactor of hundreds of pages later (that exact rework is why this exists).
- Classify EVERY element before building: fixed-position constant (folio/running-head/rule/watermark) -> **parent**;
  changing-content-consistent-look (date/verse/body/divider) -> **document page but formatted by paragraph/character/
  object STYLES**; running head that CHANGES (chapter/month) -> **Running Header text variable**; watermark/background
  -> **locked layer**; page numbering -> **AUTO_PAGE_NUMBER marker + Numbering/Section Options**; the words -> **page,
  editable**. Test: "change it -> one page or all?" all=constant; "same formatting every page?" -> it's a style.
- **Styles coexist with a computed per-page value** via: apply style -> `clearOverrides()` -> re-apply ONLY the one
  intended per-page attribute (e.g. the body's auto-fit point size -- the ONE thing that stays per-page; everything else
  about the body is style-controlled). Helper `applyStyleKeepOverrides(text, style, {pointSize})`. Repeated vector art
  (dividers) = **object styles** (`applyObjectStyle`).
- UXP quirks (each cost real time): running-header var -> `variableType = VariableTypes.MATCH_CHARACTER_STYLE_TYPE`,
  set `variable.variableOptions.appliedCharacterStyle`, **no `insertVariable()`** (do `ip.textVariableInstances.add()`
  then set `inst.associatedTextVariable`). Parent lookup: set `namePrefix` (`baseName` unreliable). Build parent
  furniture with `item.duplicate(masterPage)` (preserves exact coords). Verso/recto: `String(page.side)` (enum === fails).
- **Proven helpers + full doctrine ship with this extension** -- don't rediscover the UXP APIs:
  `runtime/indesign/layout_helpers.js` (getParent, dupeToParent, addFolio, setupRunningHeader, insertVariableInstance,
  applyStyleKeepOverrides, applyObjectStyle, getBackgroundLayer, applyParentAndStrip, **preflight**) and
  `runtime/indesign/LAYOUT_DOCTRINE.md`. Prepend the helpers you need to your `execute` script (no module system in a
  UXP call). Run `CF.preflight(doc)` before AND after building -- it flags constants duplicated per-page ("should be a
  parent"), repeating text with direct formatting ("should be a paragraph style"), and missing/substituted fonts.

BROWSER (recipe browser-attach) -- attaches to the user's real Chrome (chrome-devtools-mcp): navigate_page,
take_screenshot, take_snapshot, click, fill_form, list_pages, etc. Gives the user's real logged-in sessions.
- **Set it up with `edge-mcp setup-browser <host> <user@addr>` (above)** -- it does host+key+Node+Chrome+server in
  one shot. The operator can also click **Connect a browser** in the Edge MCP lens (same primitive, one button).
- LOGINS ARE REMEMBERED: the browser uses a DURABLE profile ($HOME/.edge-mcp/profiles/<name>, NOT ~/.cache). The
  user signs into a site ONCE and every future session returns already logged in. Chrome 136+ blocks remote-debug
  on the user's DEFAULT profile, so this is a SEPARATE profile -- their existing tabs/logins aren't in it at first.
  Reliability: "remember-me"/persistent-cookie logins (Facebook, most sites) persist across full restarts; session-
  only logins last while the warm browser stays up. To start already logged into their existing sites, run
  `edge-mcp import-logins <server>` (best-effort copy of their real Chrome logins; Chrome must be QUIT, same user).
  `edge-mcp accounts <server>` shows remembered sites; `edge-mcp revoke <server>` forgets them (wipes the profile).
- `env: node: No such file or directory` at start = Node missing/not on the host PATH -> `edge-mcp preflight <server>`
  (setup-browser already fixes this: it installs Node and the recipe launches with an absolute PATH).
- WRONG-NODE gotcha: a bare `edge-mcp` on a co-located node can target the primary install's vault (401 on key
  provisioning, split registry). Fixed -- launched sessions export CC_HOME/CC_CONFIG -- but if you ever see a 401
  or a "not provisioned" key, run `edge-mcp doctor` to confirm the node, or set CC_CONFIG=<node>/cc.config.json.

To register a DIFFERENT kind of server by hand: `edge-mcp add-host <id> <user@addr>` then
`edge-mcp add-server <id> <host> --recipe <plugin-app|browser-attach>`.
