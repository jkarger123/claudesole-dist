# Edge MCP Host (agent)

Drive MCP servers that run on a user's OWN computer -- GUI apps (Adobe InDesign/Photoshop, Blender),
their real logged-in browser, local files/devices -- over the mesh, with every call logged transparently.
Use the `edge-mcp` CLI (on PATH). Registered hosts+servers live in a registry; credentials in the vault.

    edge-mcp hosts | servers            # what's registered (reachable? warm?)
    edge-mcp status <server>            # {warm, ready, reachable, recipe, calls}
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

BROWSER (recipe browser-attach) -- attaches to the user's real Chrome (chrome-devtools-mcp): navigate_page,
take_screenshot, take_snapshot, click, fill_form, list_pages, etc. Gives the user's real logged-in sessions.

To register a new one: `edge-mcp add-host <id> <user@addr>` (mints a vault SSH key + prints the user's
one-command authorize snippet), then `edge-mcp add-server <id> <host> --recipe <plugin-app|browser-attach>`.
