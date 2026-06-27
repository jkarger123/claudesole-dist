AISearch Pro (brand-visibility across AI engines) is installed on this node.

WHAT IT IS: a hosted serverless worker that answers "how visible is a brand across ChatGPT / Claude / Gemini /
Perplexity + Google + journalist sources, and how does it compare to competitors?". Each ACCOUNT brings its own
AI keys (BYOK) -- you only spend your own AI budget.

USE THE PRODUCT (needs an account access_code):
  POST <AISEARCH_WORKER_URL>/api/analyze            {brand, query}            # is my brand visible
  POST <AISEARCH_WORKER_URL>/api/compare            {brand, competitor}       # brand vs competitor
  POST <AISEARCH_WORKER_URL>/api/visibility-report  {brand}                   # full report (heavy: ~80 AI calls)
  POST <AISEARCH_WORKER_URL>/api/brand-intelligence {brand, query}            # cached brand report
  POST <AISEARCH_WORKER_URL>/api/trace              {query}                   # sources for a query
  GET  <AISEARCH_WORKER_URL>/api/health                                       # liveness
  (auth: pass the account access_code per the worker's auth; AISEARCH_WORKER_URL is in this node's config.)

READ THE ANALYTICS (read-only, via the control center proxy -- no keys needed):
  GET /api/ext-data?ext=aisearch-pro&resource=requests&limit=50      # usage + cost + latency per request
  GET /api/ext-data?ext=aisearch-pro&resource=reports&search=<brand> # past brand reports
  GET /api/ext-data?ext=aisearch-pro&resource=accounts              # accounts + limits

BYOK: an external account with no keys gets HTTP 402 {error:"missing_api_keys"} -- it must add its OpenAI /
Anthropic / Gemini / Perplexity keys in Settings first. The internal/owner account falls back to MC's keys.
Cost is real (~$0.20-0.45/query; a visibility-report can be $1-2): prefer cached brand-intelligence; don't loop
visibility-report.

SAFETY: never expose another account's API keys; keys are per-account, server-side. AI calls cost money -- don't
fan out uncapped.
