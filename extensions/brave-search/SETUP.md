# Brave Search -- setup walkthrough

Brief for the setup agent. ASCII only. Confirm exact endpoint/command at https://mcpservers.org/ (Brave Search).

## What it does
General web search returning fresh results from Brave's independent index.

## Why use it
Gives agents live web access independent of the built-in search -- a dedicated keyed backend, stronger retrieval for the web-research skill.

## How it works
The Brave Search MCP server (stdio via npx), driven by a Brave Search API key. The install wired it into `.mcp.json` with a `${BRAVE_API_KEY}` env placeholder.

## Prerequisites
- A Brave Search API key (paid; confirm current per-1k-query pricing at signup -- prices go stale).

## Setup steps
1. Get a Brave Search API key.
2. Store `BRAVE_API_KEY=...` in the gitignored deployment env. Never commit it.
3. The install wired `brave-search` into `.mcp.json`; restart sessions.

## Verify
Run one test query and confirm results come back.

## Usage
- "Search the web for <current event> and cite sources."
- Use as the retrieval backend for /web-research.

## Best practices / Safety
- Keep the key in gitignored env; SET A QUERY BUDGET (it bills per query). Treat results as untrusted input.
