# Usage telemetry — performance & the 2026-08-06 thread-pile incident

Why the usage/account telemetry path is shaped the way it is, what made it melt a node, and which
properties must never regress. Read this before touching `_scan_tok`, `_acct_active_at`,
`_acct_feature_since`, `_acct_model_view`, or `account_windows_store` in `command-center/server.py`.

Applies to **every node** — this is core engine behaviour, not tenant-specific. The event counts below are
from the Mission Control box (the largest store in the fleet); the shapes hold anywhere, and the cost scales
with retained events. Node-level usage reference: `command-center/Usage/CLAUDE.md` (at Mission Control).

---

## 1. The incident (2026-08-06)

The operator hit a flood of resource warnings. Measured on the affected node via `/api/vitals?dump=1`:

| | |
|---|---|
| threads | **193**, of which **146** were in the usage family |
| breakdown | 119 in `_acct_feature_since`, 27 in `usage_payload`, 5 in `usage_store` |
| CPU | pinned ~100% |
| drain | **none over 60s** — arrivals outpaced completions |

Historically this same signature drove fleet nodes to 400+ threads and self-heal restarts. An earlier
attempt to fix it by **pruning `~/.claude/projects` broke the monthly usage number (85k → 42k)** and had
to be reverted — transcripts are the only source of usage truth, so deleting them is never the fix.

## 2. Root cause — measured, not assumed

The inherited diagnosis blamed the directory walk in `_scan_tok` (a recursive glob + `getmtime`/`getsize`
over ~20,500 transcripts). **That was wrong.** Measured warm on the real store: **0.18s**. Real, but nowhere
near the tens of seconds observed.

The actual cost was `_acct_active_at`:

- It answered "which account was live at time *ts*" with a **linear walk of the whole account log**.
- `_acct_feature_since` calls it **once per event**, over **~470,000 retained events**.
- 470k events × an 81-entry log ≈ **38M comparisons → 2.06s per call**, which is **98%** of that
  function's entire cost (`_ev_cost` over the same events was only 0.11s).

Two amplifiers turned a slow function into an unbounded thread pile:

1. **The `if live` gate was removed from `_acct_model_view`** the same day. That was a *correct* fix — an
   idle reserve's `/usage` scrape is stale by construction, and trusting it is how autopilot twice rotated
   onto an account at 97% of its weekly window. But it changed `pred_pct` from live-account-only to
   **every account × every window**, taking `_acct_feature_since` from ~3 calls per refresh to **9–12**,
   i.e. **~25 seconds of CPU per uncached refresh**.
2. **`account_windows_store`'s 25s cache check was unsynchronised.** Concurrent pollers all missed
   together and each ran the full refresh in parallel. With work-per-refresh (~25s) exceeding the TTL
   (25s), **the cache could never catch up** — every poll added a thread that would itself expire the
   cache before finishing. That is the unbounded-pile mechanism.

## 3. The fix (shipped in v0.99.249)

Four changes, in descending order of impact:

| # | Change | Effect |
|---|---|---|
| 1 | `_acct_active_at` → **binary search** over a cached sorted index (`_acct_log_index`) | the 98%; 2.06s → 0.22s |
| 2 | **Single-flight lock** (`_ACCT_STORE_LOCK`) on `account_windows_store` | N parallel refreshes → 1 |
| 3 | **Memo** on `_acct_feature_since` (`_ACCT_FEAT_CACHE`, `ACCT_FEAT_TTL`) | 9–12 identical sweeps → 1 |
| 4 | **Walk-TTL guard** in `_scan_tok` (`_TOK_WALK`, `TOK_WALK_TTL`) | skips the redundant 20k-file walk |

### Tunables (`cc.config`, restart to apply)
- **`tok_walk_ttl`** (default `30`) — seconds a completed directory walk is reused.
- **`acct_feature_ttl`** (default `30`) — seconds a computed feature sum is reused.

Both are pure staleness/CPU trades. Lower = fresher and more CPU; higher = cheaper and later settling.
Neither can drop data (see §4).

## 4. Accuracy invariants — why none of this loses tokens

The operator requirement was **full usage-number accuracy AND efficiency, with no transcript archiving
and no data loss**. Each fix preserves exactness for a specific reason:

- **Skipping a walk loses nothing.** Transcripts are append-only and per-file byte offsets persist
  (`_TOK_STATE[path]["off"]`, `_tok_state.json`). A skipped walk defers reading bytes; the next walk still
  consumes **every** byte written in the meantime. Numbers settle up to `tok_walk_ttl` later — they are
  never wrong, and nothing is dropped.
- **Binary search returns the identical answer.** `bisect_right(...) - 1` lands on the last entry with
  `ts <= target`, which is exactly where the old "keep assigning until one is greater" loop converged.
  Verified exhaustively (§5), including ties and the `(before tracking)` boundary.
- **The memo is keyed exactly** on `(account, int(since_ts), model_sub)`. `since_ts` is a window boundary,
  stable for hours, so a hit answers the *same* question — never an approximation of a different one.
- **The single-flight lock changes only concurrency**, not arithmetic.

### Two traps worth knowing
- **`_feat_copy` is required, not decorative.** `_acct_feature_fleet` mutates the returned dict *and its
  nested `by_ver` sub-dicts* in place while merging peer sums. A shallow `dict()` copy shares those
  sub-dicts, so the caller would corrupt the cached entry — **verified: the shallow version does corrupt.**
  Any new cache over this function must deep-copy `by_ver`.
- **The account index is swapped in a single atomic rebind.** Assigning the timestamp list and email list
  separately would let a concurrent reader pair one revision's timestamps with another's emails — i.e.
  silently misattribute tokens to the wrong account. Keep it one assignment.

## 5. How it was verified

Reproduce these if you change anything here:

- **Exhaustive equivalence** — old vs new `_acct_active_at` over **all 470,065 real events**: 0 mismatches.
  Plus 88 edge cases (before-tracking, exact boundaries, every log timestamp, past-the-end) and empty-log.
- **Bit-identical feature sums** — full `_acct_feature_since` computed both ways over a frozen snapshot
  across **24 combinations** (3 accounts × 3 windows × 2 model filters), including `by_ver`: 0 mismatches.
- **Rolling-window control** — a before/after comparison of `/api/usage` shows some fields *decrease*.
  This is expected and is **not** data loss: with identical data and no server involved, 210s of clock
  movement alone drops `day.bill` by ~1.4M as events age out of the window. Always run this control before
  reading a decrease as a regression.
- **Concurrency** — 24k lookups across 12 threads: 0 mismatches/errors.
- **Load** — 72 concurrent requests across `/api/usage`, `/api/account-windows-all`, `/api/token-usage`.

### Results
| | before | after |
|---|---|---|
| usage-family stuck threads | 146 | **max 1**, drains to 0 in ~12s |
| threads | 193 peak / 52 idle | ~40 |
| CPU idle | 85.7% | ~22% |
| month total | 88.98B tokens | 89.02B (rising normally) |

## 6. Diagnosing a recurrence

1. `curl -s -H "Cookie: cc_auth=<pin>" "http://localhost:<port>/api/vitals?dump=1"` → read `hot_frames`.
   Several threads in `_acct_feature_since` / `_acct_fleet_reports` / `usage_payload` = this pathology.
2. **Measure before believing any diagnosis.** Time the suspect directly — the walk is cheap; per-event
   work over ~470k events is not. A function that is O(events × something) is the thing to look at.
3. Check whether a caller multiplied the call count (as the `if live` removal did) or whether a cache
   check sits outside its lock (stampede).
4. Never "fix" it by deleting transcripts — that breaks the numbers and does not address the cause.

## 7. Ongoing risk

The cost is proportional to **retained events** (31-day horizon, ~470k today). If the fleet's transcript
volume grows substantially, the per-sweep cost grows with it and the caches carry more load. The next
lever, if needed, is a time-ordered index so a 5-hour window touches only the ~5k events in range instead
of sweeping all 470k — deliberately *not* done here, because per-file chronological ordering is an
assumption that would need proving before it can be trusted for exact numbers.
