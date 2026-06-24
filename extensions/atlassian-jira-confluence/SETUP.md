# Jira + Confluence -- setup walkthrough

Brief for the setup agent. ASCII only. Confirm the exact MCP endpoint/command at https://github.com/atlassian/atlassian-mcp-server.

## What it does
Read and manage Jira issues/sprints/boards and read/search Confluence pages.

## Why use it
Enterprise teams run on Jira + Confluence; this brings that work and knowledge into the control center.

## How it works
Atlassian's official Rovo MCP server (remote, OAuth). The install wired it into `.mcp.json`. Cloud only -- Data Center needs a different server. Data flow: agent -> Rovo MCP -> Atlassian Cloud APIs -> back.

## Prerequisites
- An Atlassian Cloud site (Jira and/or Confluence) + OAuth.

## Setup steps
1. The install wired `atlassian` into `.mcp.json`. Authorize the Rovo MCP server via OAuth for your site (confirm the current endpoint at the source URL).
2. Confirm project/space access. Restart sessions.

## Verify
List issues in one Jira project or read one Confluence page. Real data = connected.

## Usage
- "What's in the current sprint for project X?"
- "Find the Confluence page on our deploy process."
- "Create a Jira ticket: <desc>." (after approval)

## Best practices / Safety
- Read-first; scope to the needed projects/spaces; require approval before transitioning issues. Cloud only (label Data Center clearly).
