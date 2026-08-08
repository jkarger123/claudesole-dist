"""
Backfill `skimlinks_changes` from local weekly merchant snapshots.

Why this exists
---------------
The nightly sync (`skimlinks_sync.py`) used to cap inserts at the first 500
detected changes per week (see commit history). Real weekly volume is
4,000-5,000 changes, so ~90% were silently dropped from Supabase. We do
have full weekly JSON dumps in `local_backups/skimlinks/merchants_*.json`,
so we can reconstruct the missing change rows by diffing consecutive
snapshots and inserting them with the snapshot date as `detected_at`.

The forward-going cap is fixed in the same commit; this script is a
one-time recovery for the backlog.

Usage:
    python3 tools/backfill_skimlinks_changes.py            # full backfill, idempotent-ish
    python3 tools/backfill_skimlinks_changes.py --dry-run  # show counts only
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "FM Scraper" / "1.00"))

from db.client import get_admin_client  # noqa: E402

SNAPSHOTS_DIR = PROJECT_ROOT / "local_backups" / "skimlinks"
DB_BATCH = 500
COMMISSION_DELTA_THRESHOLD = 0.001  # 0.1 percentage point — matches sync script


def load_snapshot(path: Path):
    """Returns (snapshot_date, dict of advertiser_id -> merchant)."""
    with path.open() as f:
        data = json.load(f)
    # synced_at e.g. "2026-05-24T08:06:55.110709"
    synced_at = data.get("synced_at", "")
    date_part = synced_at[:10] if synced_at else path.stem.replace("merchants_", "")
    by_id = {}
    for m in data.get("merchants", []):
        aid = m.get("advertiser_id")
        if aid:
            by_id[str(aid)] = m
    return date_part, by_id


def severity(change_pct: float) -> str:
    a = abs(change_pct)
    if a >= 50:
        return "critical"
    if a >= 25:
        return "high"
    if a >= 10:
        return "medium"
    return "low"


def diff_snapshots(prev_date: str, prev: dict, curr_date: str, curr: dict):
    """Yield change rows ready for skimlinks_changes insert."""
    # Use the END-of-week (curr) date as detected_at — that's when the change
    # would have been recorded if the cap hadn't dropped it.
    detected_at = f"{curr_date}T03:00:00+00:00"

    prev_ids = set(prev.keys())
    curr_ids = set(curr.keys())

    new_ids = curr_ids - prev_ids
    removed_ids = prev_ids - curr_ids
    common = prev_ids & curr_ids

    # NEW
    for aid in new_ids:
        m = curr[aid]
        yield {
            "advertiser_id": aid,
            "merchant_name": m.get("name", ""),
            "merchant_domain": m.get("domain", ""),
            "change_type": "new",
            "old_commission": None,
            "new_commission": m.get("commission_rate"),
            "change_amount": None,
            "change_percent": None,
            "severity": "low",
            "detected_at": detected_at,
            "daily_sales": m.get("average_daily_sales"),
            "days_since_last_change": None,
        }

    # REMOVED
    for aid in removed_ids:
        m = prev[aid]
        yield {
            "advertiser_id": aid,
            "merchant_name": m.get("name", ""),
            "merchant_domain": m.get("domain", ""),
            "change_type": "removed",
            "old_commission": m.get("commission_rate"),
            "new_commission": None,
            "change_amount": None,
            "change_percent": None,
            "severity": "high",
            "detected_at": detected_at,
            "daily_sales": m.get("average_daily_sales"),
            "days_since_last_change": None,
        }

    # COMMISSION DELTAS
    for aid in common:
        old_c = prev[aid].get("commission_rate")
        new_c = curr[aid].get("commission_rate")
        if old_c is None or new_c is None:
            continue
        try:
            old_f = float(old_c)
            new_f = float(new_c)
        except (TypeError, ValueError):
            continue
        delta = new_f - old_f
        if abs(delta) < COMMISSION_DELTA_THRESHOLD:
            continue
        pct = (delta / old_f * 100) if old_f else 0.0
        m = curr[aid]
        yield {
            "advertiser_id": aid,
            "merchant_name": m.get("name", ""),
            "merchant_domain": m.get("domain", ""),
            "change_type": "increase" if delta > 0 else "decrease",
            "old_commission": old_f,
            "new_commission": new_f,
            "change_amount": delta,
            "change_percent": pct,
            "severity": severity(pct),
            "detected_at": detected_at,
            "daily_sales": m.get("average_daily_sales"),
            "days_since_last_change": None,
        }


def fetch_existing_detected_dates(client):
    """Pull DISTINCT detected_at::DATE values so we skip weeks already filled.
    A week is 'covered' if it has >500 rows (i.e. the cap didn't drop it)."""
    import requests
    env_path = PROJECT_ROOT / ".env"
    token = None
    for line in env_path.read_text().splitlines():
        if line.startswith("SUPABASE_ACCESS_TOKEN="):
            token = line.split("=", 1)[1].strip()
            break
    if not token:
        raise RuntimeError("SUPABASE_ACCESS_TOKEN not found in .env")
    r = requests.post(
        "https://api.supabase.com/v1/projects/mwcijcnxfmlbquciyrfn/database/query",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "query": (
                "SELECT detected_at::DATE AS d, COUNT(*) AS n "
                "FROM skimlinks_changes GROUP BY 1 ORDER BY 1"
            )
        },
        timeout=60,
    )
    r.raise_for_status()
    return {row["d"]: row["n"] for row in r.json()}


def main(dry_run: bool):
    snapshots = sorted(SNAPSHOTS_DIR.glob("merchants_2026-*.json"))
    if len(snapshots) < 2:
        print(f"Need at least 2 snapshots in {SNAPSHOTS_DIR}; found {len(snapshots)}.")
        return
    print(f"Found {len(snapshots)} snapshots:")
    for s in snapshots:
        print(f"  {s.name}")

    client = get_admin_client()
    existing = fetch_existing_detected_dates(client)
    print(f"\nExisting skimlinks_changes by date (>500 = already full):")
    for d, n in sorted(existing.items()):
        flag = " [FULL]" if n > 500 else (" [partial]" if n > 0 else "")
        print(f"  {d}: {n:,}{flag}")
    print()

    total_inserted = 0
    total_skipped_full_weeks = 0
    prev_date, prev = load_snapshot(snapshots[0])
    print(f"[BASELINE] {snapshots[0].name} — {len(prev):,} merchants")

    for snap_path in snapshots[1:]:
        curr_date, curr = load_snapshot(snap_path)
        rows = list(diff_snapshots(prev_date, prev, curr_date, curr))
        existing_for_date = existing.get(curr_date, 0)
        if existing_for_date > 500:
            print(
                f"[SKIP] {curr_date}: already has {existing_for_date:,} rows "
                f"(would have inserted {len(rows):,})"
            )
            total_skipped_full_weeks += 1
            prev_date, prev = curr_date, curr
            continue
        print(
            f"[DIFF] {prev_date} → {curr_date}: {len(rows):,} changes "
            f"(existing for {curr_date}: {existing_for_date:,})"
        )
        if dry_run:
            prev_date, prev = curr_date, curr
            continue
        # Delete the partial 500 capped rows for this date first to avoid dupes
        if existing_for_date > 0 and existing_for_date <= 500:
            import requests
            env_path = PROJECT_ROOT / ".env"
            token = None
            for line in env_path.read_text().splitlines():
                if line.startswith("SUPABASE_ACCESS_TOKEN="):
                    token = line.split("=", 1)[1].strip()
                    break
            requests.post(
                "https://api.supabase.com/v1/projects/mwcijcnxfmlbquciyrfn/database/query",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"query": f"DELETE FROM skimlinks_changes WHERE detected_at::DATE = '{curr_date}'"},
                timeout=60,
            )
            print(f"  Deleted partial rows for {curr_date}")
        # Insert in batches
        for i in range(0, len(rows), DB_BATCH):
            batch = rows[i : i + DB_BATCH]
            try:
                client.table("skimlinks_changes").insert(batch).execute()
                total_inserted += len(batch)
            except Exception as e:
                print(f"  [WARN] batch {i // DB_BATCH + 1} failed: {e}")
        prev_date, prev = curr_date, curr

    print(
        f"\n{'DRY RUN — would insert' if dry_run else 'DONE — inserted'} "
        f"{total_inserted:,} rows; skipped {total_skipped_full_weeks} full weeks."
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    main(dry_run=args.dry_run)
