# Edge MCP Host

Core `integration` extension that runs MCP servers which must live on a user's OWN computer (GUI apps like
Adobe InDesign, local files, devices) and drives them over the Tailscale mesh -- no remote desktop -- wrapped
in a transparency proxy that logs every tool call + latency.

- `extension.json` -- catalog entry (category integration; lens edge-mcp; vault key EDGE_SSH_KEY).
- `SETUP.md` -- guided setup: register an edge host + an edge MCP server; authorize a vault SSH key.
- `AGENT.md` -- agent-facing usage (auto-injected where installed); includes InDesign/Sidekick UXP quirks.
- `config.example.json` -- host + server registry schema (real state per-install; secrets are vault refs).
- `runtime/` -- the graduated runtime (built + tested):
  - `edge_registry.py` -- host/server registry + transport resolver (ssh-reach AND node-local modes) + key
    resolution (vault ref -> 0600 temp file, or direct path) + reachability probe.
  - `edge_mcpd.py` -- generic warm daemon + CLI (`edge-mcp hosts|servers|start|status|call|probe|stop`);
    one warm session per `mode:warm` server, reachability-aware backoff, generic `tool_call`.
  - `edge_setup.py` -- vault wiring + easy two-sided install: `add-host` mints/imports the SSH key into the
    VAULT (via /api/vault-set), registers the host, prints the user's ONE-command authorize snippet
    (macOS Terminal AND Windows PowerShell); `add-server` (explicit launch | `--autodetect sidekick` | `--recipe <id>`).
  - `edge_recipes.py` -- first-class RECIPES (patterns) so a popular MCP is a registry entry, not a build.
    Each recipe: default_config, mode_default, resolve_launch(), pre_launch() health gate, setup_steps.
    Shipped: `browser-attach` (attach chrome-devtools-mcp/playwright to the user's Chrome; pre_launch starts
    Chrome w/ a debug port). Next: `plugin-app` (Sidekick/Adobe/Blender), `os-automation`, `session-pairing`, `stdio-bridge`.
  - `mcp_proxy_log.py` -- byte-exact transparency proxy (tees every JSON-RPC frame + latency to jsonl).
  - `view_activity.py` -- timeline viewer (terminal precursor to the lens).
  - `indesign/` -- app-specific layout know-how shipped so no InDesign job relearns it:
    - `LAYOUT_DOCTRINE.md` -- the Template Architecture doctrine (three rules: constants -> parent pages; look ->
      named styles; content -> document pages). Running-header text variables; auto folios; locked watermark layer;
      the element-classification table; the clearOverrides pattern (style + one computed per-page value); 3-check preflight.
    - `layout_helpers.js` -- proven UXP snippet library (getParent, dupeToParent, addFolio, setupRunningHeader,
      insertVariableInstance, applyStyleKeepOverrides, applyObjectStyle, getBackgroundLayer, applyParentAndStrip,
      preflight = lintConstants + lintDirectFormatting + lintFonts). Prepend into an `execute` call.

**Design + rationale:** `../../mcp/EDGE_MCP_DESIGN.md` (the forward-looking blueprint) and the proven PoC in
`../../mcp/proxy/`. Sidekick/InDesign is the first reference instance of the general capability.

**Status:** v0.1.0. Runtime graduated + tested; VAULT wiring DONE (key stored + read back bit-identical, 0600
temp materialization, `.secrets` retired); easy two-sided install DONE (`add-host` + Mac/Windows snippets).
**FINALIZED (v1.0.0) -- Studio-side complete + battle-tested.** Proven at scale: built a 356-page InDesign book
through the stack (hundreds of execute/snapshot calls, a 12k-char script). Done:
- Runtime: registry (ssh + node-local transport, vault keys), warm daemon, transparency proxy.
- Recipes: **plugin-app** (Sidekick/Adobe/Blender/Figma/DAWs -- warm + plugin-handshake gate) + **browser-attach**
  (attach the user's real Chrome). Both proven live.
- **`edge-mcp` CLI on PATH** (hosts/servers/start/status/call/run/probe/stop + add-host/add-server); AGENT.md refreshed.
- Two-sided install (vault-minted SSH key + Mac/Windows authorize snippets).
- Hardening from the InDesign work: transport timeout 90s->600s; Sidekick = plugin-app instance. NOTE: the
  plugin app ITSELF still caps responses at ~30s -> long ops must fire-and-poll a completion marker (see AGENT.md).
- Driving lessons baked into AGENT.md (so no install relearns them): snapshot is ~72dpi (rough layout only ->
  export a 200dpi raster + `edge-mcp pull` to verify detail); every script sets NEVER_INTERACT or a modal freezes
  the engine; snapshot renders `app.activeDocument`; no remote screen capture (TCC); real shell+scp via
  `edge-mcp sh|pull|push`; UXP enum-identity + reduced-opacity-image gotchas.
- **Template Architecture doctrine shipped** (from a live 355-entry-book job): three rules -- constants -> PARENT
  pages (never per-page); look -> named paragraph/character/object STYLES (never direct-format repeating text);
  content -> document pages. Running heads that change = Running Header text variables; auto folios; watermark on a
  locked layer; the clearOverrides pattern (a style + one computed per-page value, e.g. auto-fit body size); a 3-check
  `preflight` (constants-should-be-parent, text-should-be-styled, missing/substituted fonts). Doctrine block in
  AGENT.md + full `runtime/indesign/LAYOUT_DOCTRINE.md` + proven `runtime/indesign/layout_helpers.js` snippet library.

PENDING (fleet ship, gated): edge-mcp **lens** (hosts/servers/live activity -- server.py+PAGE, needs restart) +
Design Canvas; `--mcp-config` on spawn for native in-session tools; then **sign + converge** (Mission Control ceremony).

**Parent:** `../CLAUDE.md`
