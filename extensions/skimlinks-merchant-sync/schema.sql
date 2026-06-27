-- ===========================================================================
-- Skimlinks Affiliate Intelligence -- Supabase schema
-- Run ONCE in the tenant's Supabase SQL editor before the first sync.
-- Exact DDL from the live project (information_schema.columns + pg_indexes).
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- skimlinks_merchants  (one row per advertiser; upsert on advertiser_id)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.skimlinks_merchants (
  id                          SERIAL PRIMARY KEY,
  advertiser_id               INTEGER NOT NULL UNIQUE,
  name                        TEXT NOT NULL,
  domain                      TEXT,
  domains                     JSONB,
  commission_rate             NUMERIC,
  conversion_rate             NUMERIC,
  ecpc                        NUMERIC,
  average_order_value         NUMERIC,
  average_daily_sales         NUMERIC,
  best_rate                   JSONB,
  maximum_rate                JSONB,
  minimum_rate                JSONB,
  attribution_window          TEXT,
  payment_days                TEXT,
  reversal_rate               NUMERIC,
  countries                   JSONB,
  verticals                   JSONB,
  logo_url                    TEXT,
  description                 TEXT,
  partner_type                TEXT,
  is_exclusive                BOOLEAN DEFAULT FALSE,
  created_at                  TIMESTAMPTZ DEFAULT NOW(),
  updated_at                  TIMESTAMPTZ DEFAULT NOW(),
  first_seen_at               TIMESTAMPTZ DEFAULT NOW(),
  last_seen_at                TIMESTAMPTZ DEFAULT NOW(),
  removed_at                  TIMESTAMPTZ,
  status                      VARCHAR DEFAULT 'active',
  previous_commission_rate    NUMERIC,
  last_commission_change_at   TIMESTAMPTZ,
  times_commission_changed    INTEGER DEFAULT 0,
  days_tracked                INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_skimlinks_merchants_name   ON public.skimlinks_merchants (lower(name));
CREATE INDEX IF NOT EXISTS idx_skimlinks_merchants_domain ON public.skimlinks_merchants (lower(domain));
CREATE INDEX IF NOT EXISTS idx_skim_status                ON public.skimlinks_merchants (status);
CREATE INDEX IF NOT EXISTS idx_skim_first_seen            ON public.skimlinks_merchants (first_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_skim_removed               ON public.skimlinks_merchants (removed_at DESC);
CREATE INDEX IF NOT EXISTS idx_skim_commission_change     ON public.skimlinks_merchants (last_commission_change_at DESC);

-- ---------------------------------------------------------------------------
-- skimlinks_changes  (append-only audit log; one row per detected change)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.skimlinks_changes (
  id                      SERIAL PRIMARY KEY,
  advertiser_id           VARCHAR,
  merchant_name           VARCHAR,
  change_type             VARCHAR,   -- 'new' | 'removed' | 'commission_change' | 'restored'
  old_commission          NUMERIC,
  new_commission          NUMERIC,
  change_amount           NUMERIC,
  change_percent          NUMERIC,
  severity                VARCHAR,   -- 'low' | 'medium' | 'high' | 'critical'
  detected_at             TIMESTAMPTZ DEFAULT NOW(),
  merchant_domain         VARCHAR,
  daily_sales             NUMERIC,
  days_since_last_change   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_changes_type     ON public.skimlinks_changes (change_type);
CREATE INDEX IF NOT EXISTS idx_changes_date     ON public.skimlinks_changes (detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_changes_severity ON public.skimlinks_changes (severity);
