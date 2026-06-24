# Telegram -- setup walkthrough

Brief for the **setup agent**: get the user a working bot, store the token in the deployment's gitignored
env, and verify a round-trip message. ASCII only. Concrete, friendly.

## What it does
Bridges ClaudeFather to a Telegram bot so you can (a) get push notifications on your phone when
something happens (a Ralph loop finishes, a deploy is ready, an incident opens) and (b) message your
agents back from Telegram, from anywhere.

## Why use it
You don't sit in the dashboard all day. With Telegram wired in, the control center reaches you on your
phone the moment it needs you, and you can answer or kick off work without opening a laptop. It turns a
dashboard you have to watch into an assistant that pings you.

## How it works
A Telegram bot (made via @BotFather) is the bridge. Outbound: ClaudeFather calls the Telegram HTTP API
(`sendMessage`) with your bot token + chat id to push a message to your phone. Inbound: the bot receives
your replies (via `getUpdates` / webhook) and the bridge relays them to the right agent. The bot token
is the credential for the whole thing and lives only in the deployment's gitignored env.

## Prerequisites
- The Telegram app installed (phone or desktop) and a Telegram account.
- Nothing to pay for; @BotFather and the Bot API are free.

## Setup steps
1. In Telegram, message **@BotFather** -> `/newbot` -> pick a name + a username ending in `bot`.
   He replies with an **HTTP API token** (looks like `123456:ABC-...`). Have the user paste it to you.
   Wait for the token before continuing.
2. Store it -- write `TELEGRAM_BOT_TOKEN=<token>` into the deployment's gitignored env file
   (`<deployment>/.env.claudefather` or the extension's `config.json` under the deployment state -- both
   gitignored). NEVER echo the full token back or commit it.
3. Get the chat id: have the user open their new bot and send it any message (e.g. "hi"). Then call
   `https://api.telegram.org/bot<token>/getUpdates` and read `result[].message.chat.id`. Save it as
   `TELEGRAM_CHAT_ID` in the same gitignored env.

## Verify
Send a test message and confirm the user receives it:
`https://api.telegram.org/bot<token>/sendMessage?chat_id=<id>&text=ClaudeFather%20connected`
Ask the user to confirm "ClaudeFather connected" arrived on their phone. For inbound, have them reply
to the bot and confirm the bridge relayed it.

## Usage
Two or three real things the user can now do:
- Notifications: get pinged when a Ralph loop finishes, a deploy is ready, or an incident opens
  (wire into the relevant agent-tools / loop hooks).
- Inbound: message the bot to ask an agent something from your phone; the bridge relays it.
- Quick status: text the bot "status" and have an agent reply with the current project posture.
  (Inbound relay is the deeper build -- see TWO_WAY_COMMS_RESEARCH.md in the text2tune tree for prior design.)

## Best practices / Safety
- The bot token is a full credential -- gitignored env only, never printed in full, never committed.
- Rate-limit / authorize: only respond to the configured TELEGRAM_CHAT_ID; ignore messages from anyone else.
- Keep outbound messages free of secrets (don't push tokens / full logs to a phone).
- Uninstall is reversible: it removes the bridge wiring + stored token; you can also revoke the bot in
  @BotFather. It never deletes your Telegram account.
