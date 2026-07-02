# Email Archive — agent guide

You have a searchable index of the operator's **archived (exported) email** — typically years of old-work mail
from a Gmail Takeout `.mbox`. It's separate from live Gmail (that's the `google-workspace` extension). Read-only,
node-local, instant. Reach for it whenever the answer might be in the operator's email history: an old thread,
a past invoice/order, who-said-what, a contact from a prior job, a number you need to reconcile.

## How to use it (CLI — `cc-email`, on your PATH)
```
cc-email ask "<question>" [--no-ai]   # BEST for a task — token-bounded answer with [#n] citations
cc-email search "<query>" [limit]     # ranked matches: "id | date | from | subject" + a snippet line
cc-email get <id>                      # the FULL message (headers + body) — include it in your working context
cc-email thread <id>                   # every message in that conversation (a message id or a thread id)
cc-email contacts [n]                  # top correspondents by volume
cc-email stats                         # index status + counts
```
- **Reach for `ask` first.** It runs a token-**bounded** loop for you: a cheap model plans the query →
  DETERMINISTIC retrieval does the heavy lifting for free → a cheap model answers over only the ~12 most
  relevant emails (~2k tokens on Haiku, node subscription — NOT the corpus). It returns a cited answer plus the
  source ids. This is how you "use AI on 21k emails" without blowing your context. `--no-ai` = retrieval only.
- **Never dump the archive into your context.** Don't `search` broad and `get` dozens of messages — that's the
  token trap this tool exists to avoid. `ask` for the answer; `get`/`thread` only the specific messages you must read.
- **Query = SQLite FTS5.** Bare words AND; `"quoted phrases"`; `OR` / `NOT` work.
  Examples: `cc-email search "purchase order emily" 10` · `cc-email search '"tracking number" OR shipment'`.
- It's **read-only**: search/read only, never send or modify. To send mail, use `google-workspace`.

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
