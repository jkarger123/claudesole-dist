# Postgres / Supabase -- setup walkthrough

Brief for the setup agent: connect the project DB READ-ONLY, verify with a harmless read. ASCII only.
Sources: https://supabase.com/docs/guides/ai-tools/mcp + https://github.com/modelcontextprotocol/servers.
The read-only guardrail is the most important thing here -- do not skip it.

## What it does
Lets agents run SQL (read-only by default) against your Postgres/Supabase DB to answer real questions
(row counts, revenue, recent signups, error rows) and inspect the schema.

## Why use it
The truth about a project is in its data. Grounded answers from the live DB beat guesses, and let the
control center report on real state (users, money, health).

## How it works
Two options, pick by what the project uses:
- Supabase: the official Supabase MCP server, run with `--read-only` + your project ref + access token.
  The install wired this into `.mcp.json` with `${SUPABASE_ACCESS_TOKEN}` + `${SUPABASE_PROJECT_REF}`.
- Plain Postgres: the official Postgres reference MCP server, pointed at a READ-ONLY connection string.
Data flow: agent -> MCP SQL tool -> DB (read-only role) -> rows back.

## Prerequisites
- Supabase mode: a Supabase access token + the project ref.
- Postgres mode: a connection string for a READ-ONLY database role (create one; never use a superuser).

## Setup steps
1. Create the least-privilege access: a Supabase token, OR a dedicated read-only Postgres role.
2. Store in the gitignored deployment env: `SUPABASE_ACCESS_TOKEN=...` + `SUPABASE_PROJECT_REF=...`
   (or `DATABASE_URL=postgres://readonly:...`). Never log or commit a full connection string/token.
3. The install merged the read-only server into `.mcp.json`; restart sessions. (For plain Postgres, switch
   the `.mcp.json` entry to the Postgres reference server pointed at your read-only `DATABASE_URL`.)

## Verify
Have the agent run `SELECT 1`, then one real read (e.g. row count of a known table). Confirm real values.

## Usage
- "How many users signed up this week?"
- "Show the schema of the orders table."
- "Top 10 rows in the errors table from today."

## Best practices / Safety
- READ-ONLY role by default -- this is the single most important guardrail. Never wire a superuser.
- Any write capability needs a separate role + explicit, logged approval.
- Never log full connection strings/tokens. Uninstall removes the `.mcp.json` wiring.
