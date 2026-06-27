# Skimlinks Affiliate Intelligence -- setup

## What it does
Syncs the full Skimlinks affiliate-merchant catalog into your Supabase every week and tracks every change --
new merchants, removed merchants, commission-rate moves, and how long each has been tracked. It gives you a
built-in **Affiliate Intel** lens (searchable merchant grid, top movers, per-merchant commission timeline) and
lets your agents query the data or drag a merchant into a session. No external website -- it all lives here.

## Why use it
Affiliate commissions change constantly and silently. This catches every change on a schedule, keeps the
history, and surfaces the movers -- so you can act on rate increases and notice when a merchant drops you,
without remembering to check anything.

## How it works
A weekly **routine** (Sundays 03:00, runs in this node -- no external scheduler) calls the Skimlinks API
(`merchants.skimapis.com/v3`, paginated), diffs against your `skimlinks_merchants` table, upserts the catalog,
and appends every change to `skimlinks_changes`. The lens + agents read that data through the control center's
**read-only proxy** -- the database key stays server-side and never reaches the browser.

## Prerequisites
- A **Skimlinks publisher ID** (a hash like `d77...`, from your Skimlinks account -> Account Settings).
- A **Supabase project** (free tier is fine) -- you'll need its URL and its **service-role key**
  (Project Settings -> API). Use a project dedicated to this (don't share it with unrelated apps).

## Setup steps
1. Open your Supabase project's SQL editor and run the shipped **`schema.sql`** (creates the two tables +
   indexes). Confirm both `skimlinks_merchants` and `skimlinks_changes` exist.
2. Put the three secrets in this deployment's gitignored env file (`.env.claudefather`). NEVER commit or echo
   them in full:
   ```
   SKIMLINKS_CLIENT_ID=<your publisher id>
   SKIMLINKS_SUPABASE_URL=https://<your-ref>.supabase.co
   SKIMLINKS_SUPABASE_KEY=<your supabase SERVICE-ROLE key>
   ```
   (Optional: `SKIMLINKS_MIN_EXPECTED=<n>` -- the sync aborts if the API returns fewer than this, to avoid
   corrupting the diff on an API hiccup. Default 15000; lower it if your catalog is smaller.)
3. Confirm the weekly routine registered: open the **Routines** lens -- you should see "Skimlinks weekly sync"
   (Sundays 03:00). You can change its cadence there.
4. Run the first sync manually to populate the tables: Routines -> "Skimlinks weekly sync" -> **Run now**
   (a full pass takes ~30-50 minutes; watch its status go green).

## Verify
- After the first sync, open the **Affiliate Intel** lens -- you should see the merchant count and a populated
  grid. Search a brand you know; click it to see its commission-change history.
- Ask an agent: "using skimlinks, which merchants changed commissions most recently?" -- it should answer from
  the data.

## Usage
- Browse/search the merchant grid; sort by commission or tenure; filter active vs removed.
- See **top movers** (recent commission changes) and per-merchant timelines.
- **Drag a merchant** onto a session tile to brief an agent about it.
- Ask agents affiliate questions; they query the read-only proxy.

## Best practices / safety
- The Supabase **service-role key is a real secret** -- deploy env only, never in git, never to the browser
  (the lens/agents read through the server proxy, which keeps the key server-side).
- The sync **writes** to your DB -- it runs read-only against Skimlinks but upserts your tables. Let the weekly
  routine handle it; only Run-now when you need a fresh pass.
- Keep this Supabase project **dedicated** to affiliate data (least-privilege; don't co-mingle with unrelated
  app data under the same service key).
- Removed merchants are **soft-deleted** (status=removed), never hard-deleted -- history is preserved.
