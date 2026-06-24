# Notion -- setup walkthrough

Brief for the setup agent. ASCII only. Confirm the exact MCP endpoint/command at https://developers.notion.com/guides/mcp/get-started-with-mcp.

## What it does
Search and read Notion pages, query databases, and (when allowed) create or update pages.

## Why use it
Specs, runbooks, and meeting notes live in Notion; this lets agents pull that context and write durable notes back.

## How it works
Notion's official hosted MCP server at https://mcp.notion.com/mcp with OAuth. The install wired it into `.mcp.json`. Data flow: agent -> MCP tool -> Notion API (only pages you shared) -> back.

## Prerequisites
- A Notion workspace + OAuth.
- Share the specific pages/databases with the integration (page-level least privilege).

## Setup steps
1. The install wired `notion` into `.mcp.json`. Connect via OAuth when prompted.
2. In Notion, share ONLY the pages/DBs the agent needs with the connection.
3. Restart sessions.

## Verify
Ask the agent to read one shared page's title + a snippet. Real content = connected.

## Usage
- "Summarize the spec page for project X."
- "Add a note to the runbook DB." (after approval)
- "Find the meeting notes from last week."

## Best practices / Safety
- Share only the pages the agent needs (page-level least privilege). Read-first; confirm before overwriting pages. Never expose private workspace content in public outputs.
