# Figma -- setup walkthrough

Brief for the setup agent. ASCII only. Confirm exact endpoint/command at https://github.com/atlassian/atlassian-mcp-server (search context) + Figma docs -- Unconfirmed; verify at setup.

## What it does
Read Figma files, components, and frames so an agent can reference real designs for design-to-code work.

## Why use it
Closes the design-to-code gap for portal/UX work -- agents stop guessing at layout/spacing and use the real design.

## How it works
Figma's Dev Mode MCP server exposes file + document data over MCP. IMPORTANT: the exact official endpoint and plan requirements are UNCONFIRMED -- this extension does NOT auto-wire a server on install; the setup agent confirms the current endpoint and writes the `.mcp.json` entry then.

## Prerequisites
- A Figma account (Dev Mode MCP may require a paid seat -- confirm at setup) + auth.

## Setup steps
1. Confirm the current Figma Dev Mode MCP endpoint + plan requirement (this is the Unconfirmed bit).
2. Authorize the server; confirm file access.
3. Write the confirmed server into `.mcp.json`; restart sessions.

## Verify
Read one frame's structure and confirm real data returns.

## Usage
- "What's the spacing/colors on the <frame> design?"
- "Generate the component matching this Figma frame."

## Best practices / Safety
- Read-only (designs are source of truth, don't mutate); least-privilege file access; CONFIRM plan/endpoint before depending on it (Unconfirmed flag).
