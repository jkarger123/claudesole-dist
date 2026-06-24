# Filesystem -- setup walkthrough

Brief for the setup agent. ASCII only. Confirm exact endpoint/command at https://github.com/modelcontextprotocol/servers (Filesystem).

## What it does
Secure file read/write/search confined to the directory roots you configure.

## Why use it
Lets agents work over a docs/data/research folder outside the repo with explicit, scoped access controls.

## How it works
The official Filesystem reference MCP server (stdio via npx), pointed at allowed root path(s). The install wired it into `.mcp.json` with a `${FS_ROOT}` placeholder.

## Prerequisites
- Choose the allowed root path(s). Nothing else required.

## Setup steps
1. Pick the NARROWEST directory the agent needs.
2. Set `FS_ROOT=/abs/path` in the gitignored deployment env.
3. The install wired `filesystem` into `.mcp.json`; restart sessions.

## Verify
List files under the allowed root, and confirm access OUTSIDE it is denied.

## Usage
- "Summarize the docs in <research folder>."
- "Find the file that mentions X under <root>."

## Best practices / Safety
- Scope to the NARROWEST directory; read-only first; never grant the repo root or home dir. Respect the OneDrive-walk gotcha -- never point it at OneDrive paths.
