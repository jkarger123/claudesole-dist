# PagerDuty -- setup walkthrough

Brief for the setup agent. ASCII only. Confirm the exact MCP endpoint/command at https://support.pagerduty.com/main/docs/pagerduty-mcp-server-integration-guide.

## What it does
Retrieve incidents and on-call schedules, and (with approval) create/ack/resolve incidents.

## Why use it
Pairs with incident-scanner to give a real, write-capable incident surface -- the control center can both report and respond.

## How it works
PagerDuty's official MCP server. PagerDuty-hosted at https://mcp.pagerduty.com/mcp (OAuth) or a self-hosted build (API token). The install wired the hosted form into `.mcp.json`. Data flow: agent -> MCP tool -> PagerDuty API -> back.

## Prerequisites
- A PagerDuty account + auth (hosted OAuth, or a self-hosted API token).

## Setup steps
1. The install wired `pagerduty` into `.mcp.json`. Choose hosted (OAuth) or self-hosted.
2. Self-hosted: store the API token in the gitignored env; never echo/commit it.
3. Restart sessions.

## Verify
List open incidents + the current on-call. Real data = connected.

## Usage
- "What incidents are open and who's on call?"
- "Details on incident X."
- "Ack incident X." (only with explicit approval -- this pages people)

## Best practices / Safety
- Read-first; ack/resolve ONLY with explicit approval (these page real humans); never auto-resolve. Scope the token; never echo it.
