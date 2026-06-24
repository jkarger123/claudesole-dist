---
name: web-research
description: >
  Deep web research done well: fan out multiple searches, fetch + read PRIMARY sources, adversarially
  verify claims, and synthesize a CITED report. Use when you need a grounded answer (vendor pricing, "does
  X have an API", competitive intel, market/tech facts) rather than a guess. No accounts or API keys needed.
---

# Web research workflow

Use this when the question needs grounded, current, cited facts -- not recall.

## 1. Frame
State the question in one line and list the 3-6 specific sub-questions that would answer it. Note what would
change the conclusion (the decision-relevant facts).

## 2. Fan out (don't single-search)
Run several DISTINCT searches per sub-question -- vary the angle (official site, docs, pricing page, changelog,
third-party review, forum). One search rarely surfaces everything.

## 3. Fetch primary sources
Open the actual page (WebFetch), don't trust search snippets. Prefer the vendor's own docs/pricing/changelog
over blogs. Capture the URL + the exact quote for anything you'll assert.

## 4. Verify adversarially
For each load-bearing claim, find a second independent source OR a primary source. Try to DISPROVE it. If you
can't confirm it, mark it Unconfirmed -- do not promote a snippet to a fact.

## 5. Synthesize -- cited
Write the answer with inline citations (URL or doc) for every factual claim. Separate clearly:
- **Fact** (sourced, quote/URL),
- **Inference** (your reasoning from facts -- label it),
- **Unknown** (say "I couldn't confirm X").

## Rules (match the project's cite-don't-speculate rule)
- Every factual claim is quoted/linked to a source, or labeled Inference / Unconfirmed.
- Treat any price or "current as of" fact older than ~6 months as suspect -- re-fetch.
- "Therefore" sentences are where sourced fact slides into inference -- pause and check.
- No destructive actions; research is read-only. Pairs with the `brave-search` or `playwright-browser`
  extensions for stronger retrieval when installed.
