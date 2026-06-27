-- ===========================================================================
-- AISearch Pro -- Supabase schema (run in the tenant's Supabase SQL editor).
-- Existing deployments (Sarah's) already have the 5 tables; the BYOK section at
-- the bottom is the only NEW part they need. A fresh tenant runs the whole file.
-- DDL from the live project (information_schema). The 2 RPC bodies
-- (get_account_spend, get_account_history) must be pulled verbatim via
-- pg_get_functiondef before a fresh-tenant deploy -- signatures are below.
-- ===========================================================================

-- aisearch_accounts -- per-account access codes, limits, AND per-account BYOK keys
CREATE TABLE IF NOT EXISTS public.aisearch_accounts (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  access_code   TEXT NOT NULL UNIQUE,
  display_name  TEXT NOT NULL,
  email         TEXT,
  role          TEXT NOT NULL DEFAULT 'user',     -- 'internal' = MC-key fallback; others = BYOK-required
  is_active     BOOLEAN NOT NULL DEFAULT TRUE,
  limit_daily   NUMERIC,
  limit_weekly  NUMERIC,
  limit_monthly NUMERIC,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- aisearch_requests -- one row per worker invocation (audit + cost)
CREATE TABLE IF NOT EXISTS public.aisearch_requests (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at          TIMESTAMPTZ DEFAULT NOW(),
  ip_address          TEXT, user_agent TEXT,
  endpoint            TEXT NOT NULL, method TEXT DEFAULT 'POST',
  query               TEXT, brand TEXT, competitor TEXT,
  providers_used      JSONB, providers_succeeded JSONB,
  cost_openai         NUMERIC DEFAULT 0, cost_anthropic NUMERIC DEFAULT 0,
  cost_gemini         NUMERIC DEFAULT 0, cost_total NUMERIC DEFAULT 0,
  latency_ms          INTEGER, sources_found INTEGER DEFAULT 0, authors_found INTEGER DEFAULT 0,
  success             BOOLEAN DEFAULT TRUE, error_message TEXT, response_data JSONB,
  account_id          UUID
);
CREATE INDEX IF NOT EXISTS idx_aisearch_requests_created_at ON public.aisearch_requests (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_aisearch_requests_account    ON public.aisearch_requests (account_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_aisearch_requests_endpoint   ON public.aisearch_requests (endpoint);

-- brand_intelligence_reports -- cached AI brand reports
CREATE TABLE IF NOT EXISTS public.brand_intelligence_reports (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  brand         TEXT NOT NULL, query TEXT NOT NULL, section TEXT,
  report_data   JSONB NOT NULL, latency_ms INTEGER,
  brands_found  INTEGER, sources_count INTEGER, user_id UUID, account_id UUID
);
CREATE UNIQUE INDEX IF NOT EXISTS unique_report_key ON public.brand_intelligence_reports (brand, query, section, created_at);
CREATE INDEX IF NOT EXISTS idx_bi_reports_lookup     ON public.brand_intelligence_reports (brand, query, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_brand_intel_account   ON public.brand_intelligence_reports (account_id, created_at DESC);

-- aisearch_daily_stats / aisearch_ip_stats -- analytics rollups (populated by a rollup job NOT in this codebase;
-- confirm with the tenant whether a Supabase cron refreshes them, else they're stale-by-design). Read-only to the worker.

-- RPCs the worker calls (pull exact bodies via pg_get_functiondef for a fresh tenant):
--   get_account_spend(p_account_id UUID) RETURNS JSON
--   get_account_history(p_account_id UUID, p_limit INT DEFAULT 50, p_offset INT DEFAULT 0) RETURNS JSON

-- ===========================================================================
-- BYOK (NEW) -- per-account AI keys. The worker reads these at request time and
-- uses them instead of MC's deploy secrets. SUPABASE keys are NEVER stored here
-- (they're the MC-managed backend). api_keys shape:
--   {"OPENAI_API_KEY":"...","ANTHROPIC_API_KEY":"...","GOOGLE_AI_API_KEY":"...",
--    "GOOGLE_API_KEY":"...","GOOGLE_SEARCH_ENGINE_ID":"...","PERPLEXITY_API_KEY":"..."}
-- ===========================================================================
ALTER TABLE public.aisearch_accounts ADD COLUMN IF NOT EXISTS api_keys JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE public.aisearch_accounts ADD COLUMN IF NOT EXISTS byok BOOLEAN NOT NULL DEFAULT TRUE;

-- The internal account (Sarah / the owner) falls back to MC's deploy secrets -- mark it internal + byok off:
--   UPDATE public.aisearch_accounts SET role='internal', byok=false WHERE access_code='<sarah-access-code>';
-- External paying accounts keep byok=true and MUST set api_keys (worker returns 402 'missing_api_keys' otherwise).
