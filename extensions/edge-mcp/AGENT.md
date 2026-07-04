# Edge MCP Host (agent)

Drive MCP servers that run on a user's OWN computer -- GUI apps (Adobe InDesign/Photoshop, Blender),
their real logged-in browser, local files/devices -- over the mesh, with every call logged transparently.
Use the `edge-mcp` CLI (on PATH). Registered hosts+servers live in a registry; credentials in the vault.

    edge-mcp hosts | servers            # what's registered (reachable? warm?)
    edge-mcp status <server>            # {warm, ready, reachable, recipe, calls}
    edge-mcp call <server> <tool> '<json-args>'    # invoke a tool, JSON back
    edge-mcp run  <server> <file.js> [desc]        # run a JS file on the server (big scripts)

Reality checks:
- A host that's a LAPTOP may be ASLEEP -> status shows reachable:false; ask the user to wake it. Don't retry-hammer.
- `plugin-app` servers need the app OPEN with its plugin loaded; a call before the plugin handshakes says
  "not ready" -- `edge-mcp status` shows ready:true once connected (warm session keeps it connected).
- Long ops are fine (tool timeout is generous); no need to micro-batch.

INDESIGN (server `sidekick-indesign`, recipe plugin-app) -- tools: `execute` (UXP JS), `snapshot`
(page/spread -> JPEG), get_layout, get_font_metrics, get_health. Write UXP JS, run it, then SNAPSHOT to SEE
the result and iterate (the design loop). UXP quirks: `const {app}=require('indesign')`; `doc.pages.item(0)`
not `[0]`; compare with `.equals()`; units are strings ("11pt","0.5in"); paragraph break `\r`; when text
oversets, read paragraphs via `frame.parentStory.paragraphs` (frame.paragraphs omits overset ones).
`snapshot` args: {target:"page"|"spread", index:<0-based>}.

BROWSER (recipe browser-attach) -- attaches to the user's real Chrome (chrome-devtools-mcp): navigate_page,
take_screenshot, take_snapshot, click, fill_form, list_pages, etc. Gives the user's real logged-in sessions.

To register a new one: `edge-mcp add-host <id> <user@addr>` (mints a vault SSH key + prints the user's
one-command authorize snippet), then `edge-mcp add-server <id> <host> --recipe <plugin-app|browser-attach>`.
