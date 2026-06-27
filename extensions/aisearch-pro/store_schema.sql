-- AISearch Pro -- node-local SQLite store (the in-server data store; replaces Supabase).
-- Applied idempotently by the platform on first use. Server functions read/write this DB
-- (path in CF_STORE_DB); the lens reads it via the data_sources 'sqlite' backend.

CREATE TABLE IF NOT EXISTS aisearch_accounts (
  id            TEXT PRIMARY KEY,
  access_code   TEXT UNIQUE,
  display_name  TEXT,
  email         TEXT,
  role          TEXT DEFAULT 'user',     -- 'internal'/'admin' = MC-key fallback; others = BYOK
  is_active     INTEGER DEFAULT 1,
  byok          INTEGER DEFAULT 1,
  api_keys      TEXT DEFAULT '{}',       -- JSON: per-account BYOK keys (server-side only)
  limit_daily   REAL, limit_weekly REAL, limit_monthly REAL,
  created_at    TEXT, updated_at TEXT
);

CREATE TABLE IF NOT EXISTS aisearch_requests (
  id            TEXT PRIMARY KEY,
  created_at    TEXT,
  endpoint      TEXT, brand TEXT, competitor TEXT, query TEXT,
  providers_used TEXT, providers_succeeded TEXT,
  cost_openai REAL, cost_anthropic REAL, cost_gemini REAL, cost_total REAL DEFAULT 0,
  latency_ms    INTEGER, sources_found INTEGER DEFAULT 0,
  success       INTEGER DEFAULT 1, error_message TEXT,
  ip_address    TEXT, account_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_aisreq_created  ON aisearch_requests (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_aisreq_account  ON aisearch_requests (account_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_aisreq_endpoint ON aisearch_requests (endpoint);

CREATE TABLE IF NOT EXISTS brand_intelligence_reports (
  id            TEXT PRIMARY KEY,
  created_at    TEXT,
  brand         TEXT, query TEXT, section TEXT,
  report_data   TEXT,                    -- JSON
  latency_ms    INTEGER, brands_found INTEGER, sources_count INTEGER,
  account_id    TEXT
);
CREATE INDEX IF NOT EXISTS idx_bir_brand   ON brand_intelligence_reports (brand, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_bir_account ON brand_intelligence_reports (account_id, created_at DESC);
