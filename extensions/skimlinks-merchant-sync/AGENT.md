Skimlinks Affiliate Intelligence is installed on this node. You can use it directly.

WHAT IT IS: a weekly-synced catalog of every Skimlinks affiliate merchant + an append-only log of changes
(new/removed merchants, commission moves). Data lives in this node's Supabase; you reach it through the
control center's read-only proxy -- you never need the DB key.

QUERY THE DATA (read-only, via the server proxy):
- Merchants:  GET /api/ext-data?ext=skimlinks-merchant-sync&resource=merchants&search=<text>&status=active&limit=50
- Changes:    GET /api/ext-data?ext=skimlinks-merchant-sync&resource=changes&change_type=commission_change&limit=50
  Returns JSON rows. Use `search` (matches name/domain), `status` (active|removed), `change_type`
  (commission_increase | commission_decrease | new | removed | restored), `severity`, `advertiser_id`,
  and `limit`. It is READ-ONLY -- you cannot write through this path. commission_rate is a FRACTION (0.0368 = 3.68%).

RUN THE SYNC ON DEMAND (normally it runs every Sunday 03:00 as a routine):
- POST /api/routine-run {"name":"Skimlinks weekly sync"}   (a full pass takes ~30-50 min; it WRITES to Supabase)

ANSWER QUESTIONS like: "which merchants raised commissions this week?", "what's <brand>'s current rate and
history?", "how many merchants did we lose this month?" -- pull from the changes resource (sorted newest-first)
or merchants resource and summarize. Sub-1000-row weekly deltas are normal; a >5K delta usually means Skimlinks
did a catalog cleanup, not a bug.

DRAG-IN: the Affiliate Intel lens lets the user drag a merchant row into a session -- you'll receive a markdown
card with its name/domain/commission/status. Use it as the subject of the request.

SAFETY: never expose the Supabase service key (it's server-side only). The sync writes to a live DB -- only
trigger a full sync when asked; prefer read queries for answering questions.
