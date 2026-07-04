# AISearch Pro — setup

## What it does
A hosted, serverless brand-visibility engine: ask "is my brand visible across ChatGPT / Claude / Gemini /
Perplexity, who's cited, how do I compare to a competitor?" It fans a query across multiple AI models + Google
Custom Search + journalist/source scraping and returns a scored report. Each account brings its own AI keys
(BYOK), so you only pay your own AI bill. A built-in **AI Visibility** lens shows usage, cost, and past reports.

## Why use it
Buyers increasingly ask AI engines, not Google. This tells you whether the AI engines surface your brand, what
sources they pull from, and where competitors beat you — on a $5/mo seat with your own AI keys (no platform AI markup).

## How it works
The worker is deployed serverless on Cloudflare Pages (no daemon, no tunnel, no Mac). Accounts authenticate with
an access code; the worker reads that account's keys from its record and calls the AI providers with them. Results
+ cost are logged to Supabase; the lens reads them read-only. (This is the offload of the old Mac daemon —
`wrangler pages dev` + cloudflared tunnel are gone.)

## Prerequisites
- (Tenant) Your own AI keys for the providers you want: OpenAI + Anthropic (required), and optionally Gemini,
  Perplexity, Google Custom Search.
- (Mission Control, one-time) A Cloudflare account + deploy token to host the worker; a Supabase project for the
  data (the schema below).

## Setup steps
### A. Mission Control (one-time deploy)
1. Run `schema.sql` in the Supabase project (creates the 5 tables + the BYOK `api_keys`/`byok` columns; pull the
   2 RPC bodies for a fresh project).
2. Deploy the worker: `wrangler pages deploy` the product source (from the deploy working area) to the Cloudflare
   Pages project. Set the MC/owner secrets as Pages secrets: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, and the
   OWNER's AI keys (these are the fallback for the internal account only).
3. Set this node's deploy env (gitignored): `AISEARCH_WORKER_URL=https://<pages-url>`,
   `AISEARCH_SUPABASE_URL=...`, `AISEARCH_SUPABASE_KEY=<service-role>` (for the analytics lens proxy).
4. Mark the owner/internal account: `UPDATE aisearch_accounts SET role='internal', byok=false WHERE access_code='<owner>'`.

### B. Each account (BYOK)
1. In **AI Visibility → Settings**, paste your OpenAI + Anthropic (+ optional Gemini/Perplexity/Google) keys.
   They are stored on YOUR account record (`api_keys`), server-side, used only for your requests.
2. (owner) keys are auto-filled from the prior `.dev.vars` — nothing to do.

## Verify
- `GET <AISEARCH_WORKER_URL>/api/health` → `{ok:true, supabase_url:true, supabase_key:true}`.
- Open the **AI Visibility** lens — usage + reports populate.
- Run one `/api/analyze {brand}` from your account — a row appears in the lens with its cost.

## Usage
- Analyze a brand; compare to a competitor; generate a full visibility report; review cost per query in the lens.

## Best practices / safety
- **BYOK keys are secrets** — per-account, server-side, never shown to other accounts or the browser.
- **Cost is real** (~$0.20–0.45/query; a visibility-report can be $1–2). Prefer the cached brand-intelligence
  endpoint; don't loop the heavy report. External accounts without keys are blocked (402) so they can't spend MC's.
- The owner/internal account is the only one allowed to fall back to MC's deploy keys.
