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

### Per-session comms (the built-in smart router)
Once this extension is installed AND the env has the token + chat id, every session terminal gets a
**Telegram** toggle in its bar (the more-menu, next to Compact). Flip it ON for a session and:
- When that session goes busy -> idle (task done OR blocked waiting) the bot **pings your phone** with
  the pane tail. Reply and it's injected straight back INTO that session.
- **Many sessions on at once?** Each gets a stable number. The ping is tagged `#N node/Title`. To answer:
  reply-TO the ping, or start your message with the number (`2 ship it`). If only ONE session is on,
  just reply -- no number needed.
- **Bot commands** (text the bot): `/list` (numbered sessions + status), `/focus N [30m|2h]` (stick plain
  replies to #N; bare = 1h; `/focus off` to clear), `/off N` (turn Telegram off for #N from your phone),
  `/mute N [time]` + `/unmute N`, `/help`.

## Per-instance creds (co-located nodes)
One bot per NODE. If several ClaudeFather instances run on the same machine and share one
`.env.claudefather`, give each its OWN bot so they don't fight over `getUpdates` (only one consumer per
bot token -- a second is rejected with 409). Set the per-instance token/chat in that instance's
`cc.config.json` (`telegram_bot_token` / `telegram_chat_id`); it overrides the shared env. Simplest path:
only install + configure telegram-notify on the one node you want on your phone.

## Best practices / Safety
- The bot token is a full credential -- gitignored env only, never printed in full, never committed.
- Rate-limit / authorize: only respond to the configured TELEGRAM_CHAT_ID; ignore messages from anyone else.
- Keep outbound messages free of secrets (don't push tokens / full logs to a phone).
- Uninstall is reversible: it removes the bridge wiring + stored token; you can also revoke the bot in
  @BotFather. It never deletes your Telegram account.
