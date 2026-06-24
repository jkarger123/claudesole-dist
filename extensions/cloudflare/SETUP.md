# Cloudflare -- setup walkthrough

Brief for the setup agent. ASCII only. Confirm the exact MCP endpoint/command at https://github.com/cloudflare/mcp.

## What it does
Query and manage Cloudflare resources -- Workers, DNS, KV/R2, Pages, analytics.

## Why use it
This project ships on Cloudflare; an agent that can check Worker status, read analytics, and inspect config closes the loop on deploy + ops.

## How it works
Cloudflare's official MCP server, connectable by URL (https://mcp.cloudflare.com/mcp) with OAuth + permission selection. The install wired it into `.mcp.json`. Data flow: agent -> MCP tool -> Cloudflare API -> back.

## Prerequisites
- A Cloudflare account + OAuth (account + zone access).

## Setup steps
1. The install wired `cloudflare` into `.mcp.json`. Connect via OAuth, select the narrowest permissions.
2. Confirm the right account/zone. Restart sessions.

## Verify
List Workers or read one zone's DNS. Real data = connected.

## Usage
- "Is the text2tune Worker healthy? Show recent analytics."
- "What DNS records are on <zone>?"
- "Deploy/update a Worker." (after approval)

## Best practices / Safety
- Read-first (analytics + config) before any mutation; least-privilege at OAuth time; require approval before DNS/Worker changes (prod). Never expose API tokens. (Unrelated to the HP Tuners-cloud rule -- this is Cloudflare ops.)
