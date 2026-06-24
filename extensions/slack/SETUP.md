# Slack -- setup walkthrough

Brief for the setup agent: create a Slack app, get a bot token, allowlist channels, verify a round-trip.
ASCII only. Confirm the exact server package at https://github.com/modelcontextprotocol/servers.

## What it does
Lets agents read recent messages in channels you choose and post messages (status updates, digests) to them.

## Why use it
Slack is where your team already is. Pushing status there reaches people without making them open a
dashboard, and reading lets an agent pick up requests posted in a channel.

## How it works
The official Slack MCP reference server, driven by a Slack app bot token. The install wired the `slack`
server into the deployment `.mcp.json` with `${SLACK_BOT_TOKEN}` + `${SLACK_TEAM_ID}` placeholders that
resolve from your gitignored env. Data flow: agent -> MCP tool -> Slack Web API -> back.

## Prerequisites
- A Slack workspace where you can create an app and install it.
- The channel IDs you want to allow.

## Setup steps
1. Create a Slack app (api.slack.com/apps) -> add bot scopes: `chat:write`, `channels:history`,
   `channels:read` -> install to the workspace. Copy the **Bot User OAuth Token** (`xoxb-...`).
2. Store secrets in the gitignored deployment env: `SLACK_BOT_TOKEN=xoxb-...` and `SLACK_TEAM_ID=T...`.
   Never echo the full token or commit it.
3. The install already merged the `slack` MCP server into `.mcp.json`; restart sessions so it loads with the
   resolved env. (Confirm the exact server package/command from the source URL above if startup fails.)
4. Invite the bot to the channels you want it to use.

## Verify
Have the agent read the last message in a test channel, then post "ClaudeFather connected". Confirm both work.

## Usage
- "Post a summary of today's deploys to #eng."
- "What did people say in #incidents in the last hour?"
- Wire it as a notify target for loop-done / deploy-ready events.

## Best practices / Safety
- Least-privilege scopes; restrict the bot to an allowlist of channels.
- Read before enabling write-heavy flows; never post secrets/logs to public channels.
- Uninstall removes the `.mcp.json` wiring; revoke the app in Slack to fully cut access.
