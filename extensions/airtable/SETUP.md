# Airtable -- setup

## What
Connect one or more Airtable bases so an agent can read + EDIT them like a database (list bases/tables, read
schema, query records, create/update/upsert rows). Headless Path B: a self-hosted MCP server
(`domdomegg/airtable-mcp-server`) authenticated with ONE Airtable **Personal Access Token (PAT)** kept in the
deployment vault. No browser OAuth, no re-auth.

## Why
Agencies keep CRMs, trackers, and content calendars in Airtable. This lets the agent do real work against that
data -- "reconcile this list", "append these rows", "update the status column", "pull this base into the brief"
-- editing the SAME base in place instead of exporting copies. One pasted token turns it on.

## How it works
Claude Code launches `npx -y airtable-mcp-server` (stdio) with the PAT in its environment
(`AIRTABLE_API_KEY`). That server calls Airtable's Web API (`Authorization: Bearer <PAT>`). The PAT is
least-privilege: it carries only the scopes + the specific base(s) you grant. Nothing is stored except the token
(in the gitignored deployment env), and it is never committed or echoed.

## Prerequisites
- An Airtable account with the base(s) you want the agent to touch.
- `node`/`npx` available on the host (the MCP runs via npx). `npx -y airtable-mcp-server --help` should resolve.

## Setup steps
1. **Create a Personal Access Token.** Go to https://airtable.com/create/tokens and click "Create new token".
   - **Scopes:** add `data.records:read` and `data.records:write` (for read+edit), plus `schema.bases:read` (so
     the agent can read table structure). For READ-ONLY, add only `data.records:read` + `schema.bases:read`.
   - **Access:** grant the specific base(s) you want the agent to work with (not "all workspaces" unless you mean
     it). Least privilege -- grant only what this node should touch.
   - Create it and copy the `pat...` token (shown once).
2. **Store the token (secure-field flow -- never paste a secret into chat).** Provide it as the secret
   `AIRTABLE_API_KEY` via `cc-secure` / the secure-field prompt; it lands in the deployment vault/env, gitignored.
3. **Wire the MCP.** The install/setup helper copies this extension's `mcp.json` block into the deployment's
   `.mcp.json`, resolving `${AIRTABLE_API_KEY}` from the env you just set. (Restart the node so the MCP loads.)

## Verify
- Ask the agent to **list your Airtable bases** (or **list tables in <base>**). You should see them by name.
- Ask it to **read the schema of one table** and **list a few records**. If that works, read is good.
- (If you granted write) ask it to **append one test row**, confirm it appears in Airtable, then delete it.
- Failure modes: `401/403` = token missing/unscoped or the base wasn't granted; `404` = wrong base id;
  `npx` errors = Node not installed.

## Usage
- "List the tables in my <X> base and the schema of <table>."
- "In <base>/<table>, for every row where Email bounced, research a new email and UPSERT it back into that row."
- "Append these 30 rows to <table>" (the agent batches <=10/request and throttles to stay under the rate limit).
- "Pull the open items from <base>/<table> into my morning brief."

## Best practices
- **Least privilege:** scope the PAT tightly and grant only the needed base(s); use a read-only PAT if the agent
  only needs to report.
- **Rate limit is real:** Airtable allows **5 requests/sec per base** (all plans). Bulk jobs must batch (<=10
  records/request) + throttle, or rows get 429'd. Prefer UPSERT for reconcile jobs to avoid duplicates.
- **Confirm bulk writes** before running them; deletes are hard to undo.
- **Rotate** the PAT if it may have leaked (Airtable dashboard -> regenerate); update the vault secret and restart.
- PATs don't expire -- treat them like any long-lived credential.
