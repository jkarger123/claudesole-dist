# Linear -- setup walkthrough

Brief for the setup agent. ASCII only. Confirm the exact MCP endpoint/command at https://linear.app/docs/mcp.

## What it does
Lets agents read, create, and update Linear issues, and see project + cycle status.

## Why use it
For teams on Linear, this is where work is tracked; an agent that files and updates issues automatically turns plans into tracked tasks.

## How it works
Linear's official hosted remote MCP server, authorized with OAuth. The install wired the `linear` remote server into `.mcp.json`; you authorize in the browser. Data flow: agent -> MCP tool -> Linear API -> back.

## Prerequisites
- A Linear workspace you can authorize.
- Browser OAuth.

## Setup steps
1. The install wired `linear` into `.mcp.json`. Authorize in the browser when prompted; confirm the right workspace/team.
2. Restart sessions to load it. (Confirm the current endpoint at the source URL if it fails.)

## Verify
Ask the agent to list the current cycle's open issues. Real issues = connected.

## Usage
- "What's open in this cycle?"
- "File a bug: <desc> in team X." (after you enable write + approve)
- "Move issue ABC-123 to In Progress."

## Best practices / Safety
- Read-first; require approval before creating/closing issues. Scope to the intended team; never auto-reassign. Uninstall removes wiring.
