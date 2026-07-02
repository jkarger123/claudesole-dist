# Email Archive — agent guide

You have a searchable index of the operator's **archived (exported) email** — typically years of old-work mail
from a Gmail Takeout `.mbox`. It's separate from live Gmail (that's the `google-workspace` extension). Read-only,
node-local, instant. Reach for it whenever the answer might be in the operator's email history: an old thread,
a past invoice/order, who-said-what, a contact from a prior job, a number you need to reconcile.

## How to use it (CLI — `cc-email`, on your PATH)
```
cc-email search "<query>" [limit]     # ranked matches: "id | date | from | subject" + a snippet line
cc-email get <id>                      # the FULL message (headers + body) — include it in your working context
cc-email stats                         # index status + message count
```
- **Query = SQLite FTS5.** Bare words are AND-ed; use `"quoted phrases"`; `OR` / `NOT` work.
  Examples: `cc-email search "purchase order emily" 10` · `cc-email search '"tracking number" OR shipment'`.
- **Workflow:** `search` to find the id, then `get <id>` to pull the whole email in. Don't guess from the
  snippet — `get` the message before you rely on its contents.
- It's **read-only**: you can read/search, never send or modify. To send mail, use `google-workspace`.

## Draggable (when the operator is driving the dashboard)
Every result row in the **Email Archive** lens is draggable: the operator can drop one onto a Claude session
(or into the Basket) and you'll receive the full email as a `.md` (same headers+body as `cc-email get`). If the
operator says "here's the email" and a message file appears in your context, that's where it came from.

## Good judgment
- Prefer `search` with **specific** terms (a name + a noun) — a single common word returns noise.
- The archive can be large (tens of thousands of messages). Use a `limit`, refine, then `get` the one you need.
- It reflects a **point-in-time export** — it won't have anything newer than the last Takeout. For recent mail,
  use live Gmail (`google-workspace`).
- Never paste raw archive dumps into a deliverable wholesale; quote/summarize the relevant part.

## If it's not working
- `cc-email stats` says "index not ready" → the index isn't built or `email_archive_db` isn't set. That's an
  operator/setup task (see this extension's `SETUP.md`), not something you retry — surface it and move on.
