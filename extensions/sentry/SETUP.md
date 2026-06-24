# Sentry -- setup walkthrough

Brief for the setup agent: connect Sentry read-only, verify by listing one recent issue. ASCII only.
Confirm the exact package/remote endpoint at https://github.com/getsentry/sentry-mcp.

## What it does
Lists and inspects Sentry issues/errors (with details) for your project's apps, from inside the control center.

## Why use it
"Is it healthy?" is the control center's core question. Sentry is the ground truth for runtime errors, so
this grounds the incident posture in production reality instead of just local logs. Pairs with incident-scanner.

## How it works
Sentry's official MCP server. Two mechanisms:
- Hosted remote (recommended): authorize via OAuth; no token stored locally.
- Self-hosted (stdio): run the server via npx with a `SENTRY_AUTH_TOKEN` (+ `SENTRY_HOST`). The install wired
  this form into `.mcp.json` with env placeholders.
Data flow: agent -> MCP tool -> Sentry API (your org/projects) -> issues back.

## Prerequisites
- A Sentry account/org. Remote: ability to OAuth. Self-hosted: an auth token scoped to the needed org/projects.

## Setup steps
1. Choose hosted remote (OAuth) or self-hosted (token).
2. Self-hosted: create an auth token (least-privilege, read scopes); store `SENTRY_AUTH_TOKEN=...` and
   `SENTRY_HOST=...` in the gitignored deployment env. Never echo or commit the token.
3. The install merged the `sentry` server into `.mcp.json`; restart sessions. (Switch to the hosted remote
   URL form if you prefer OAuth -- confirm the current endpoint at the source URL above.)

## Verify
Have the agent list the most recent unresolved issue in one project. A real issue = connected.

## Usage
- "What are the top unresolved errors in <app> this week?"
- "Show details + stack for issue X."
- Feed findings into the Incidents lens rather than auto-acting.

## Best practices / Safety
- Read-only by default; enable resolve/assign only with explicit approval.
- Scope the token to the needed org/projects; never echo it.
- Uninstall removes the `.mcp.json` wiring.
