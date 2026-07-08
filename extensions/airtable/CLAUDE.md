# Airtable extension -- headless Airtable bases via a PAT-authed self-hosted MCP

<!-- LATEST-HANDOFF -->
**>> Resume here:** read `_handoffs/20260708-1825__airtable.md` first -- it is the latest handoff.
<!-- /LATEST-HANDOFF -->

A ClaudeFather **integration extension** (`extension.json` id `airtable`) that lets an agent read + EDIT Airtable
bases in place (list bases/tables, read schema, query records, create/update/upsert rows). Path B / headless:
`domdomegg/airtable-mcp-server` (`npx -y airtable-mcp-server`, stdio) authed with ONE Airtable Personal Access
Token stored in the deployment vault as `AIRTABLE_API_KEY` (referenced as `${AIRTABLE_API_KEY}` in `mcp.json`;
never committed/echoed).

## Key files
- `extension.json` -- catalog manifest (`provides: mcp:airtable`; `setup_agent: true`; `default_category: Integrations`).
- `mcp.json` -- TEMPLATE (never the live config): the `npx airtable-mcp-server` block + `${AIRTABLE_API_KEY}` env.
- `SETUP.md` -- authoritative setup walkthrough (create a PAT, scope it, grant the base, paste it, verify).
- `AGENT.md` -- agent rules: base->table->record->field model, EDIT-IN-PLACE, read schema first, and the hard
  **5 req/s per base** rate limit (batch <=10 records/request, throttle bulk jobs, prefer UPSERT for reconcile).

## Hard rules
- **Least privilege in the PAT** (Airtable side): `data.records:read/write` + `schema.bases:read`, granted only
  to the specific base(s). Read-only = drop `data.records:write`.
- Secret lives ONLY in the gitignored deployment env/vault; never in `mcp.json`/`SETUP.md`/git; never echoed.
- Core change, not local: new/edited extensions are authored at Mission Control + shipped via dist (CCR on a node).
- Needs `node`/`npx` on the host.
