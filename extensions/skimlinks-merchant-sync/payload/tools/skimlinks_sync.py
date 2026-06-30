#!/usr/bin/env python3
"""
Skimlinks Merchant Sync Tool v2
================================
Re-downloads the full Skimlinks merchant database and syncs to Supabase.
Comprehensive tracking: new/removed merchants, commission changes, tenure.

Usage:
    python3 tools/skimlinks_sync.py                  # Full sync
    python3 tools/skimlinks_sync.py --dry-run        # Preview changes only
    python3 tools/skimlinks_sync.py --stats          # Show current stats
    python3 tools/skimlinks_sync.py --changes        # Show recent changes
    python3 tools/skimlinks_sync.py --new            # Show recently added
    python3 tools/skimlinks_sync.py --removed        # Show recently removed
    python3 tools/skimlinks_sync.py --quick          # Quick test (first 1000)

Schedule daily via cron:
    0 6 * * * cd /path/to/hummer && python3 tools/skimlinks_sync.py >> logs/skimlinks_sync.log 2>&1
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

# Load environment -- ClaudeFather extension: config comes from the deployment env (gitignored), NOT source.
# Precedence: real process env (set by the routine runner) -> the deploy env file ($CF_DEPLOY_ENV, e.g.
# .env.claudefather) -> a local .env beside the payload (legacy). Nothing is hardcoded.
def _read_env_file(path):
    out = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return out

def load_env():
    env_vars = {}
    env_vars.update(_read_env_file(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')))   # local (legacy)
    dep = os.environ.get('CF_DEPLOY_ENV')
    if dep:
        env_vars.update(_read_env_file(dep))      # the ClaudeFather deployment secrets (.env.claudefather)
    env_vars.update({k: v for k, v in os.environ.items() if v})   # real env wins
    return env_vars

ENV = load_env()

def _cfg(*keys, default=''):
    for k in keys:
        v = ENV.get(k)
        if v: return v
    return default

# API credentials -- parameterized (multi-tenant). The Skimlinks publisher ID is a non-secret hash, but it is
# still per-tenant, so it comes from config too. The Supabase SERVICE key is a real secret -> deploy env only.
SKIMLINKS_CLIENT_ID = _cfg('SKIMLINKS_CLIENT_ID', 'SKIMLINKS_PUBLISHER_ID')
SUPABASE_URL = _cfg('SKIMLINKS_SUPABASE_URL', 'SUPABASE_URL').rstrip('/')
SUPABASE_KEY = _cfg('SKIMLINKS_SUPABASE_KEY', 'SUPABASE_SERVICE_KEY')
if not (SKIMLINKS_CLIENT_ID and SUPABASE_URL and SUPABASE_KEY):
    sys.stderr.write("[config] missing SKIMLINKS_CLIENT_ID / SKIMLINKS_SUPABASE_URL / SKIMLINKS_SUPABASE_KEY "
                     "(set them in the deployment env via the extension setup)\n")

# Thresholds for alerts
COMMISSION_CHANGE_THRESHOLD = 0.005  # 0.5% change is notable
SIGNIFICANT_CHANGE = 0.02  # 2% is significant
MAJOR_CHANGE = 0.05  # 5% is major

# Thresholds for alerts
COMMISSION_CHANGE_THRESHOLD = 0.005  # 0.5% change is notable
SIGNIFICANT_CHANGE = 0.02  # 2% is significant
MAJOR_CHANGE = 0.05  # 5% is major


class SupabaseClient:
    """Minimal Supabase client."""

    def __init__(self, url: str, key: str):
        self.url = url
        self.headers = {
            'apikey': key,
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json'
        }

    def select(self, table: str, columns: str = '*', filters: Dict = None,
               order: str = None, limit: int = None, offset: int = 0) -> List[Dict]:
        url = f"{self.url}/rest/v1/{table}?select={columns}"
        if filters:
            for k, v in filters.items():
                url += f"&{k}={v}"
        if order:
            url += f"&order={order}"
        if limit:
            url += f"&limit={limit}&offset={offset}"
        resp = requests.get(url, headers=self.headers, timeout=60)
        return resp.json() if resp.status_code == 200 else []

    def select_all(self, table: str, columns: str = '*') -> List[Dict]:
        """Paginate through all records."""
        all_records = []
        offset = 0
        batch_size = 1000
        while True:
            batch = self.select(table, columns, limit=batch_size, offset=offset, order='id')
            if not batch:
                break
            all_records.extend(batch)
            offset += batch_size
            print(f"  Loaded {len(all_records):,} records...", end='\r')
        print()
        return all_records

    def upsert(self, table: str, data: List[Dict], on_conflict: str = 'id') -> bool:
        url = f"{self.url}/rest/v1/{table}?on_conflict={on_conflict}"
        headers = {**self.headers, 'Prefer': 'resolution=merge-duplicates'}
        resp = requests.post(url, headers=headers, json=data, timeout=120)
        return resp.status_code in [200, 201]

    def update(self, table: str, data: Dict, filters: Dict) -> bool:
        url = f"{self.url}/rest/v1/{table}"
        for k, v in filters.items():
            url += f"?{k}={v}"
        resp = requests.patch(url, headers=self.headers, json=data, timeout=60)
        return resp.status_code in [200, 204]

    def insert(self, table: str, data: List[Dict]) -> bool:
        url = f"{self.url}/rest/v1/{table}"
        resp = requests.post(url, headers=self.headers, json=data, timeout=60)
        return resp.status_code in [200, 201]

    def count(self, table: str, filters: Dict = None) -> int:
        url = f"{self.url}/rest/v1/{table}?select=id"
        if filters:
            for k, v in filters.items():
                url += f"&{k}={v}"
        url += "&limit=1"
        headers = {**self.headers, 'Prefer': 'count=exact', 'Range-Unit': 'items'}
        resp = requests.head(url, headers=headers, timeout=30)
        if resp.status_code in [200, 206]:
            range_header = resp.headers.get('content-range', '')
            if '/' in range_header:
                total = range_header.split('/')[-1]
                if total != '*':
                    return int(total)
        # Fallback: try GET with count
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            range_header = resp.headers.get('content-range', '')
            if '/' in range_header:
                total = range_header.split('/')[-1]
                if total != '*':
                    return int(total)
        return 0


class SkimlinksAPI:
    """Skimlinks Merchant API."""

    BASE_URL = "https://merchants.skimapis.com/v3/merchants"

    def __init__(self, client_id: str):
        self.client_id = client_id

    def fetch_all(self, limit: int = None) -> List[Dict]:
        """Fetch the FULL merchant catalog (V3 offset pagination), resilient to Skimlinks' frequent read timeouts
        and rate limits: a transient failure RETRIES the same page with escalating backoff instead of ending the
        fetch (the old code aborted at the first timeout -- that's why a full pass kept dying at ~3,400). Returns
        the COMPLETE catalog, or RAISES on an incomplete fetch -- NEVER a silent partial, because a partial would
        make the downstream diff falsely soft-delete every merchant past the cut-off. Dedups by advertiser_id."""
        all_merchants = []
        seen_ids = set()
        offset = 0
        batch_size = 200
        MAX_TRIES = 6                          # consecutive transient failures on ONE page before we give up (-> raise)

        while True:
            tries = 0
            while True:                        # inner loop: retry THIS page until a 200, or we exhaust tries
                try:
                    resp = requests.get(
                        self.BASE_URL,
                        params={'apikey': self.client_id, 'limit': batch_size, 'offset': offset},
                        timeout=60,
                    )
                    if resp.status_code == 200:
                        break
                    if resp.status_code == 429 or resp.status_code >= 500:   # rate-limited / transient server error
                        tries += 1
                        if tries >= MAX_TRIES:
                            raise RuntimeError(f"Skimlinks {resp.status_code} persisted at offset {offset}")
                        wait = min(60, 5 * (2 ** (tries - 1)))
                        print(f"\n  [WARN] {resp.status_code} at {len(all_merchants):,} merchants -- backing off {wait}s ({tries}/{MAX_TRIES})...")
                        time.sleep(wait)
                        continue
                    raise RuntimeError(f"Skimlinks API error {resp.status_code}")    # hard 4xx -> abort
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                    tries += 1
                    if tries >= MAX_TRIES:
                        raise RuntimeError(f"network failure at offset {offset} after {tries} tries: {e}")
                    wait = min(60, 5 * (2 ** (tries - 1)))
                    print(f"\n  [WARN] timeout at {len(all_merchants):,} merchants -- retry {tries}/{MAX_TRIES} in {wait}s...")
                    time.sleep(wait)
                    continue

            data = resp.json()
            merchants = data.get('merchants', [])
            if not merchants:
                break                          # natural end of the catalog -> done

            for m in merchants:
                aid = str(m.get('advertiser_id', ''))
                if aid and aid in seen_ids:
                    continue
                if aid:
                    seen_ids.add(aid)
                all_merchants.append(m)

            print(f"  Fetched {len(all_merchants):,} merchants...", end='\r')
            offset += batch_size

            if limit and len(all_merchants) >= limit:
                all_merchants = all_merchants[:limit]
                break

        print()
        return all_merchants


def safe_float(val, default=0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except:
        return default


def parse_datetime(val) -> Optional[datetime]:
    """Parse datetime from various formats."""
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    try:
        # Handle ISO format with timezone
        if 'T' in str(val):
            return datetime.fromisoformat(str(val).replace('Z', '+00:00').replace('+00:00', ''))
        return datetime.strptime(str(val), '%Y-%m-%d %H:%M:%S')
    except:
        return None


def days_ago(dt: Optional[datetime]) -> Optional[int]:
    """Calculate days since a datetime."""
    if not dt:
        return None
    now = datetime.utcnow()
    if dt.tzinfo:
        dt = dt.replace(tzinfo=None)
    return (now - dt).days


def transform_merchant(m: Dict, existing: Dict = None) -> Dict:
    """Transform API merchant to database format with tracking."""
    categories = m.get('categories', [])
    verticals = [c.get('name') for c in categories if c.get('name')]

    now = datetime.utcnow().isoformat()
    new_commission = safe_float(m.get('calculated_commission_rate'))

    # Base record
    record = {
        'advertiser_id': str(m.get('advertiser_id', m.get('id', ''))),
        'name': (m.get('name') or 'Unknown')[:500],
        'domain': (m.get('domain') or '')[:500],
        'domains': m.get('domains', []),
        'commission_rate': new_commission,
        'conversion_rate': safe_float(m.get('calculated_conversion_rate')),
        'ecpc': safe_float(m.get('calculated_ecpc')),
        'average_order_value': safe_float(m.get('average_order_value')),
        'average_daily_sales': safe_float(m.get('calculated_average_daily_sales')),
        'best_rate': safe_float(m.get('best_rate')),
        'maximum_rate': safe_float(m.get('maximum_rate')),
        'minimum_rate': safe_float(m.get('minimum_rate')),
        'attribution_window': m.get('attribution_window'),
        'payment_days': m.get('payment_days'),
        'reversal_rate': safe_float(m.get('reversal_rate')),
        'countries': m.get('country_codes', []),
        'verticals': verticals,
        'logo_url': m.get('logo_url'),
        'description': (m.get('description') or '')[:2000] if m.get('description') else None,
        'partner_type': m.get('partner_type'),
        'is_exclusive': m.get('is_exclusive', False),
        'updated_at': now,
        'last_seen_at': now,
        'status': 'active',
        'removed_at': None  # Clear if previously removed
    }

    # Track first_seen_at and commission changes
    if existing:
        # Preserve first_seen_at
        record['first_seen_at'] = existing.get('first_seen_at')

        # Calculate days tracked
        first_seen = parse_datetime(existing.get('first_seen_at'))
        if first_seen:
            record['days_tracked'] = days_ago(first_seen)

        # Check for commission change
        old_commission = safe_float(existing.get('commission_rate'))
        if abs(new_commission - old_commission) >= COMMISSION_CHANGE_THRESHOLD:
            record['previous_commission_rate'] = old_commission
            record['last_commission_change_at'] = now
            record['times_commission_changed'] = (existing.get('times_commission_changed') or 0) + 1
        else:
            # Preserve existing change tracking
            record['previous_commission_rate'] = existing.get('previous_commission_rate')
            record['last_commission_change_at'] = existing.get('last_commission_change_at')
            record['times_commission_changed'] = existing.get('times_commission_changed') or 0
    else:
        # New merchant
        record['first_seen_at'] = now
        record['days_tracked'] = 0
        record['times_commission_changed'] = 0

    return record


def detect_changes(old: Dict, new: Dict) -> Optional[Dict]:
    """Detect significant changes between old and new merchant data."""
    old_rate = safe_float(old.get('commission_rate'))
    new_rate = safe_float(new.get('commission_rate'))

    if old_rate == 0 and new_rate == 0:
        return None

    # Skip "drops to 0" - this usually means no recent sales, not a real program change
    # The merchant is still active with their base rate, just no calculated earnings
    if new_rate == 0 and old_rate > 0:
        return None

    change = new_rate - old_rate

    if abs(change) < COMMISSION_CHANGE_THRESHOLD:
        return None

    change_pct = (change / old_rate) if old_rate > 0 else 1.0

    if abs(change_pct) >= MAJOR_CHANGE:
        severity = 'major'
    elif abs(change_pct) >= SIGNIFICANT_CHANGE:
        severity = 'significant'
    else:
        severity = 'minor'

    # Calculate days since last change
    last_change = parse_datetime(old.get('last_commission_change_at'))
    days_since = days_ago(last_change) if last_change else None

    return {
        'advertiser_id': new['advertiser_id'],
        'merchant_name': new['name'],
        'merchant_domain': new.get('domain'),
        'change_type': 'commission_increase' if change > 0 else 'commission_decrease',
        'old_commission': old_rate,
        'new_commission': new_rate,
        'change_amount': change,
        'change_percent': change_pct,
        'severity': severity,
        'daily_sales': new.get('average_daily_sales'),
        'days_since_last_change': days_since,
        'detected_at': datetime.utcnow().isoformat()
    }


def run_sync(db: SupabaseClient, api: SkimlinksAPI, dry_run: bool = False, quick: bool = False):
    """Main sync process."""
    print("\n" + "=" * 70)
    print("SKIMLINKS MERCHANT SYNC v2")
    print("=" * 70)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}{' (quick)' if quick else ''}")

    # Step 1: Fetch from API
    print("\n[1/7] Fetching merchants from Skimlinks API...")
    limit = 1000 if quick else None
    try:
        api_merchants = api.fetch_all(limit=limit)
    except Exception as e:
        # fetch_all raises rather than return a partial -> abort WITHOUT writing, so we never false-delete the
        # merchants that simply weren't fetched. (This is the count-independent guard; the MIN_EXPECTED check below
        # is the secondary one for a genuinely-shrunk catalog.)
        print(f"\n  [ABORT] Skimlinks fetch did not complete: {e}")
        print("  Aborting sync to prevent falsely marking merchants as removed (no DB writes made).")
        return

    if not api_merchants:
        print("[ERROR] No merchants fetched from API")
        return

    print(f"  Fetched {len(api_merchants):,} merchants from API")

    # Safety guard: abort if API returned suspiciously few merchants
    # Normal count is ~35K. If we got less than 50% of that, the API likely
    # timed out or errored partway through — continuing would falsely mark
    # thousands of merchants as "removed".
    MIN_EXPECTED_MERCHANTS = int(_cfg('SKIMLINKS_MIN_EXPECTED', default='15000') or '15000')  # per-tenant: tuned to catalog size
    if not quick and len(api_merchants) < MIN_EXPECTED_MERCHANTS:
        print(f"\n  [ABORT] Only fetched {len(api_merchants):,} merchants — expected at least {MIN_EXPECTED_MERCHANTS:,}")
        print(f"  This likely means the Skimlinks API timed out or errored.")
        print(f"  Aborting sync to prevent falsely marking merchants as removed.")
        return

    # Step 2: Load existing from database (with full tracking data)
    print("\n[2/7] Loading existing merchants from database...")
    existing = db.select_all('skimlinks_merchants',
        'id,advertiser_id,name,domain,commission_rate,first_seen_at,last_seen_at,'
        'last_commission_change_at,previous_commission_rate,times_commission_changed,status')
    existing_by_id = {str(m['advertiser_id']): m for m in existing}
    print(f"  Loaded {len(existing):,} existing merchants")

    # Step 3: Transform and compare
    print("\n[3/7] Analyzing changes...")

    api_ids = set()
    new_merchants = []
    changes = []

    for m in api_merchants:
        aid = str(m.get('advertiser_id', m.get('id', '')))
        api_ids.add(aid)

        existing_record = existing_by_id.get(aid)
        transformed = transform_merchant(m, existing_record)
        new_merchants.append(transformed)

        # Check for commission change
        if existing_record:
            change = detect_changes(existing_record, transformed)
            if change:
                changes.append(change)

    # Identify removed merchants (in DB but not in API)
    removed_ids = set(existing_by_id.keys()) - api_ids
    new_ids = api_ids - set(existing_by_id.keys())
    returned_ids = set()  # Merchants that were removed but came back

    for aid in api_ids:
        if aid in existing_by_id and existing_by_id[aid].get('status') == 'removed':
            returned_ids.add(aid)

    # Stats
    increases = [c for c in changes if c['change_type'] == 'commission_increase']
    decreases = [c for c in changes if c['change_type'] == 'commission_decrease']

    print(f"\n  NEW MERCHANTS:           {len(new_ids):,}")
    print(f"  REMOVED MERCHANTS:       {len(removed_ids):,}")
    print(f"  RETURNED MERCHANTS:      {len(returned_ids):,}")
    print(f"  COMMISSION INCREASES:    {len(increases):,}")
    print(f"  COMMISSION DECREASES:    {len(decreases):,}")

    if dry_run:
        print("\n" + "-" * 70)
        print("[DRY RUN] Would apply the following changes:")
        print("-" * 70)

        if new_ids:
            print(f"\n  NEW MERCHANTS ({len(new_ids)}):")
            for aid in list(new_ids)[:10]:
                m = next((x for x in new_merchants if x['advertiser_id'] == aid), None)
                if m:
                    print(f"    + {m['name'][:50]} ({m['domain']})")
            if len(new_ids) > 10:
                print(f"    ... and {len(new_ids) - 10} more")

        if removed_ids:
            print(f"\n  REMOVED MERCHANTS ({len(removed_ids)}):")
            for aid in list(removed_ids)[:10]:
                m = existing_by_id.get(aid)
                if m:
                    first_seen = parse_datetime(m.get('first_seen_at'))
                    tenure = days_ago(first_seen) if first_seen else 0
                    print(f"    - {m['name'][:50]} (tracked {tenure} days)")
            if len(removed_ids) > 10:
                print(f"    ... and {len(removed_ids) - 10} more")

        if changes:
            print(f"\n  COMMISSION CHANGES ({len(changes)}):")
            for c in sorted(changes, key=lambda x: abs(x['change_percent']), reverse=True)[:15]:
                direction = '+' if c['change_type'] == 'commission_increase' else ''
                print(f"    {c['merchant_name'][:40]:<40} {c['old_commission']*100:5.1f}% -> {c['new_commission']*100:5.1f}% ({direction}{c['change_percent']*100:+.1f}%)")

        return

    # Step 4: Save local backup
    print("\n[4/7] Saving local backup...")
    try:
        # Use project-local dir (not data/ which symlinks to external SSD that
        # may lack Full Disk Access permissions when run from cron)
        backup_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'local_backups', 'skimlinks')
        os.makedirs(backup_dir, exist_ok=True)

        date_str = datetime.utcnow().strftime('%Y-%m-%d')
        backup_data = {
            'synced_at': datetime.utcnow().isoformat(),
            'total_active': len(new_merchants),
            'new_count': len(new_ids),
            'removed_count': len(removed_ids),
            'returned_count': len(returned_ids),
            'commission_changes': len(changes),
            'merchants': new_merchants,
            'removed_ids': list(removed_ids),
            'changes': changes[:500]
        }

        # Dated snapshot
        dated_file = os.path.join(backup_dir, f'merchants_{date_str}.json')
        with open(dated_file, 'w') as f:
            json.dump(backup_data, f, separators=(',', ':'))
        size_mb = os.path.getsize(dated_file) / (1024 * 1024)
        print(f"  Saved {dated_file} ({size_mb:.1f} MB)")

        # Latest (always overwritten)
        latest_file = os.path.join(backup_dir, 'merchants_latest.json')
        with open(latest_file, 'w') as f:
            json.dump(backup_data, f, separators=(',', ':'))
        print(f"  Updated {latest_file}")

        # Prune old backups (keep last 30)
        backup_files = sorted([
            f for f in os.listdir(backup_dir)
            if f.startswith('merchants_') and f != 'merchants_latest.json' and f.endswith('.json')
        ])
        if len(backup_files) > 30:
            for old_file in backup_files[:-30]:
                os.remove(os.path.join(backup_dir, old_file))
                print(f"  Pruned old backup: {old_file}")
    except Exception as e:
        print(f"  [WARN] Local backup failed: {e}")

    # Step 5: Mark removed merchants
    print("\n[5/7] Marking removed merchants...")
    now = datetime.utcnow().isoformat()
    removed_count = 0

    for aid in removed_ids:
        success = db.update('skimlinks_merchants',
            {'status': 'removed', 'removed_at': now},
            {'advertiser_id': f'eq.{aid}'})
        if success:
            removed_count += 1
    print(f"  Marked {removed_count:,} merchants as removed")

    # Step 6: Upsert all active merchants
    print("\n[6/7] Upserting active merchants...")
    batch_size = 500
    for i in range(0, len(new_merchants), batch_size):
        batch = new_merchants[i:i + batch_size]
        success = db.upsert('skimlinks_merchants', batch, 'advertiser_id')
        print(f"  Upserted {min(i + batch_size, len(new_merchants)):,}/{len(new_merchants):,}...", end='\r')
    print()

    # Step 7: Record changes
    print("\n[7/7] Recording changes...")

    # Save commission changes to database (batched — last week 5,040 changes
    # were detected but the old hardcoded [:500] cap silently dropped ~90% of
    # them. PostgREST insert size is fine; we just batch to mirror Step 6.)
    if changes:
        batch_size = 500
        recorded = 0
        for i in range(0, len(changes), batch_size):
            batch = changes[i:i + batch_size]
            try:
                db.insert('skimlinks_changes', batch)
                recorded += len(batch)
            except Exception as e:
                print(f"  [WARN] Batch {i // batch_size + 1} failed ({len(batch)} rows): {e}")
        print(f"  Recorded {recorded:,}/{len(changes):,} commission changes to database")

    # Save comprehensive summary
    try:
        # Build lookup for faster new_merchant_list construction
        merchants_by_id = {m['advertiser_id']: m for m in new_merchants}

        summary = {
            'synced_at': datetime.utcnow().isoformat(),
            'total_merchants': len(new_merchants),
            'new_merchants': len(new_ids),
            'removed_merchants': len(removed_ids),
            'returned_merchants': len(returned_ids),
            'commission_increases': len(increases),
            'commission_decreases': len(decreases),
            'new_merchant_list': [
                {'id': aid, 'name': merchants_by_id[aid]['name'],
                 'domain': merchants_by_id[aid].get('domain', '')}
                for aid in list(new_ids)[:100] if aid in merchants_by_id
            ],
            'removed_merchant_list': [
                {'id': aid, 'name': existing_by_id[aid]['name'],
                 'domain': existing_by_id[aid].get('domain', ''),
                 'days_tracked': days_ago(parse_datetime(existing_by_id[aid].get('first_seen_at')))}
                for aid in list(removed_ids)[:100] if aid in existing_by_id
            ],
            'top_increases': sorted(increases, key=lambda x: x['change_percent'], reverse=True)[:20],
            'top_decreases': sorted(decreases, key=lambda x: x['change_percent'])[:20]
        }

        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'local_backups', 'skimlinks')
        os.makedirs(data_dir, exist_ok=True)

        summary_file = os.path.join(data_dir, 'skimlinks_sync_summary.json')
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)

        # Also save to history file
        history_file = os.path.join(data_dir, 'skimlinks_sync_history.json')
        history = []
        if os.path.exists(history_file):
            try:
                with open(history_file) as f:
                    history = json.load(f)
            except:
                pass

        history.append({
            'synced_at': summary['synced_at'],
            'total': len(new_merchants),
            'new': len(new_ids),
            'removed': len(removed_ids),
            'increases': len(increases),
            'decreases': len(decreases)
        })
        history = history[-90:]  # Keep 90 days

        with open(history_file, 'w') as f:
            json.dump(history, f, indent=2)

        print(f"  Summary saved: {summary_file}")
    except Exception as e:
        print(f"  [WARN] Failed to save summary/history files: {e}")

    print("\n" + "=" * 70)
    print("SYNC COMPLETE")
    print("=" * 70)
    print(f"  Total active merchants:  {len(new_merchants):,}")
    print(f"  New:                     {len(new_ids):,}")
    print(f"  Removed:                 {len(removed_ids):,}")
    print(f"  Returned:                {len(returned_ids):,}")
    print(f"  Commission changes:      {len(changes):,}")
    print("=" * 70)


def show_stats(db: SupabaseClient):
    """Show current database stats."""
    print("\n" + "=" * 70)
    print("SKIMLINKS DATABASE STATS")
    print("=" * 70)

    # Counts by status
    active = db.count('skimlinks_merchants', {'status': 'eq.active'})
    removed = db.count('skimlinks_merchants', {'status': 'eq.removed'})
    total = active + removed

    print(f"\n  MERCHANT COUNTS:")
    print(f"    Active:    {active:,}")
    print(f"    Removed:   {removed:,}")
    print(f"    Total:     {total:,}")

    # Get metrics
    merchants = db.select('skimlinks_merchants',
        'commission_rate,ecpc,average_daily_sales,days_tracked,times_commission_changed',
        {'status': 'eq.active'}, limit=10000)

    if merchants:
        commissions = [m['commission_rate'] for m in merchants if m.get('commission_rate')]
        sales = [m['average_daily_sales'] for m in merchants if m.get('average_daily_sales')]
        tenures = [m['days_tracked'] for m in merchants if m.get('days_tracked')]
        changers = [m for m in merchants if (m.get('times_commission_changed') or 0) > 0]

        print(f"\n  NETWORK METRICS:")
        print(f"    Avg commission:      {sum(commissions)/len(commissions)*100:.2f}%")
        print(f"    Total daily sales:   ${sum(sales):,.0f}")
        print(f"    Est. annual sales:   ${sum(sales)*365:,.0f}")
        print(f"    Avg tenure:          {sum(tenures)/len(tenures):.0f} days" if tenures else "")
        print(f"    Merchants w/changes: {len(changers):,}")

    # Recent activity
    print(f"\n  RECENT ACTIVITY (7 days):")

    # New merchants (last 7 days)
    week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
    new_7d = db.select('skimlinks_merchants', 'name,domain,first_seen_at',
        {'first_seen_at': f'gte.{week_ago}', 'status': 'eq.active'},
        order='first_seen_at.desc', limit=5)
    print(f"    New merchants: {len(new_7d)}")
    for m in new_7d[:3]:
        print(f"      + {m['name'][:45]}")

    # Removed merchants (last 7 days)
    removed_7d = db.select('skimlinks_merchants', 'name,domain,removed_at,days_tracked',
        {'removed_at': f'gte.{week_ago}'}, order='removed_at.desc', limit=5)
    print(f"    Removed merchants: {len(removed_7d)}")
    for m in removed_7d[:3]:
        print(f"      - {m['name'][:45]} (after {m.get('days_tracked', 0)} days)")

    # Commission changes (last 7 days)
    changes_7d = db.select('skimlinks_changes', '*',
        {'detected_at': f'gte.{week_ago}'}, order='detected_at.desc', limit=50)
    increases = [c for c in changes_7d if c.get('change_type') == 'commission_increase']
    decreases = [c for c in changes_7d if c.get('change_type') == 'commission_decrease']
    print(f"    Commission increases: {len(increases)}")
    print(f"    Commission decreases: {len(decreases)}")

    # Last sync
    summary_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'local_backups', 'skimlinks', 'skimlinks_sync_summary.json')
    if os.path.exists(summary_file):
        with open(summary_file) as f:
            summary = json.load(f)
        print(f"\n  LAST SYNC: {summary.get('synced_at', 'Unknown')}")

    print("=" * 70)


def show_new(db: SupabaseClient, days: int = 7):
    """Show recently added merchants."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

    merchants = db.select('skimlinks_merchants',
        'name,domain,commission_rate,average_daily_sales,first_seen_at',
        {'first_seen_at': f'gte.{cutoff}', 'status': 'eq.active'},
        order='first_seen_at.desc', limit=50)

    print("\n" + "=" * 70)
    print(f"NEW MERCHANTS (Last {days} days) - {len(merchants)} total")
    print("=" * 70)

    if not merchants:
        print("  No new merchants in this period")
        return

    print(f"\n{'Merchant':<40} {'Domain':<20} {'Comm%':>7} {'Added':>12}")
    print("-" * 70)

    for m in merchants:
        comm = (m.get('commission_rate') or 0) * 100
        first_seen = parse_datetime(m.get('first_seen_at'))
        added = first_seen.strftime('%Y-%m-%d') if first_seen else 'Unknown'
        print(f"  {m['name'][:38]:<38} {(m['domain'] or '')[:18]:<18} {comm:6.1f}%  {added}")

    print("=" * 70)


def show_removed(db: SupabaseClient, days: int = 30):
    """Show recently removed merchants."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

    merchants = db.select('skimlinks_merchants',
        'name,domain,commission_rate,days_tracked,removed_at,first_seen_at',
        {'removed_at': f'gte.{cutoff}'},
        order='removed_at.desc', limit=50)

    print("\n" + "=" * 70)
    print(f"REMOVED MERCHANTS (Last {days} days) - {len(merchants)} total")
    print("=" * 70)

    if not merchants:
        print("  No removed merchants in this period")
        return

    print(f"\n{'Merchant':<35} {'Domain':<18} {'Comm%':>6} {'Tenure':>8} {'Removed':>12}")
    print("-" * 70)

    for m in merchants:
        comm = (m.get('commission_rate') or 0) * 100
        tenure = m.get('days_tracked') or 0
        removed = parse_datetime(m.get('removed_at'))
        removed_str = removed.strftime('%Y-%m-%d') if removed else 'Unknown'
        print(f"  {m['name'][:33]:<33} {(m['domain'] or '')[:16]:<16} {comm:5.1f}%  {tenure:>6}d  {removed_str}")

    print("=" * 70)


def show_changes(db: SupabaseClient, days: int = 7):
    """Show recent commission changes."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

    changes = db.select('skimlinks_changes', '*',
        {'detected_at': f'gte.{cutoff}'}, order='detected_at.desc', limit=100)

    print("\n" + "=" * 70)
    print(f"COMMISSION CHANGES (Last {days} days) - {len(changes)} total")
    print("=" * 70)

    if not changes:
        print("  No commission changes in this period")
        return

    increases = [c for c in changes if c.get('change_type') == 'commission_increase']
    decreases = [c for c in changes if c.get('change_type') == 'commission_decrease']

    print(f"\nINCREASES ({len(increases)}):")
    print("-" * 70)
    for c in sorted(increases, key=lambda x: x.get('change_percent', 0), reverse=True)[:20]:
        days_since = c.get('days_since_last_change')
        since_str = f" (after {days_since}d)" if days_since else ""
        print(f"  {c['merchant_name'][:38]:<38} {c['old_commission']*100:5.1f}% -> {c['new_commission']*100:5.1f}% (+{c['change_percent']*100:.0f}%){since_str}")

    print(f"\nDECREASES ({len(decreases)}):")
    print("-" * 70)
    for c in sorted(decreases, key=lambda x: x.get('change_percent', 0))[:20]:
        days_since = c.get('days_since_last_change')
        since_str = f" (after {days_since}d)" if days_since else ""
        print(f"  {c['merchant_name'][:38]:<38} {c['old_commission']*100:5.1f}% -> {c['new_commission']*100:5.1f}% ({c['change_percent']*100:.0f}%){since_str}")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description='Skimlinks Merchant Sync Tool v2')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    parser.add_argument('--quick', action='store_true', help='Quick test with first 1000 merchants')
    parser.add_argument('--stats', action='store_true', help='Show current database stats')
    parser.add_argument('--changes', action='store_true', help='Show recent commission changes')
    parser.add_argument('--new', action='store_true', help='Show recently added merchants')
    parser.add_argument('--removed', action='store_true', help='Show recently removed merchants')
    parser.add_argument('--days', type=int, default=7, help='Days to look back (default: 7)')

    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[ERROR] SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
        sys.exit(1)

    db = SupabaseClient(SUPABASE_URL, SUPABASE_KEY)
    api = SkimlinksAPI(SKIMLINKS_CLIENT_ID)

    if args.stats:
        show_stats(db)
    elif args.changes:
        show_changes(db, args.days)
    elif args.new:
        show_new(db, args.days)
    elif args.removed:
        show_removed(db, args.days)
    else:
        run_sync(db, api, dry_run=args.dry_run, quick=args.quick)


if __name__ == '__main__':
    main()
