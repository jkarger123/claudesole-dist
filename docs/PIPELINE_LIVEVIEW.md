# Pipeline Live-View — the emit contract

A generic Command Center lens that answers **"where is the run RIGHT NOW?"** for any node that runs a
long pipeline / cron job. The lens is zero-per-node code: your pipeline writes three standard files to a
known directory, and the lens renders whatever steps you declare — a top-to-bottom run map where each step
lights up by state, plus a **missed-run / stalled-run alarm** (the "silent until noon" failure mode).

Built at Mission Control, shipped via dist (v0.8.0). Pilot: a node (fm_nightly).

## Where the files live
`PIPELINE_DIR` — default `<project_root>/.pipeline/`. Override per deployment in `cc.config.json`:
```json
{ "pipeline_dir": "/abs/path/to/.pipeline", "pipeline_stale_sec": 600 }
```
The presence of `manifest.json` is what makes the Pipeline lens appear for a node (it self-hides otherwise).

## The three files

### 1. `manifest.json` — declares the pipeline shape (write once / on change)
```json
{
  "pipeline": "fm_nightly",
  "label": "FM Nightly Sync",
  "schedule": "0 2 * * *",        // optional: cron string, shown for context
  "expect_by": "06:00",           // optional: local HH:MM the run should be DONE by -> drives the MISSED-RUN alarm
  "steps": [
    { "id": "cars_com",   "label": "Cars.com",   "critical": true },
    { "id": "autotrader", "label": "AutoTrader", "critical": true },
    { "id": "index",      "label": "Reindex",    "critical": false }
  ]
}
```
`steps` is the ordered run map. `critical` defaults to true; mark cleanup/optional steps false.

### 2. `heartbeat.json` — the live (or last) run, OVERWRITTEN each tick
Write this atomically (tmp + rename) every time a step changes state and periodically while a step runs
(so `updated_ts` stays fresh — that's how the lens detects a stall).
```json
{
  "run_id": "2026-06-23",
  "started_ts": 1782200000,
  "updated_ts": 1782200305,       // bump every tick; stale > pipeline_stale_sec while running => STALLED alarm
  "state": "running",             // running | done | failed
  "current_step": "autotrader",
  "steps": {
    "cars_com":   { "state": "done",    "started_ts": 1782200000, "ended_ts": 1782200180, "metrics": { "listings": 1240 } },
    "autotrader": { "state": "running", "started_ts": 1782200180, "metrics": { "progress": "market 8/500" } },
    "index":      { "state": "pending" }
  }
}
```
Step `state` ∈ `pending | running | done | failed | skipped`. `metrics` is a free-form flat object — every
key/value is rendered as a chip (e.g. `listings 1240`, `progress market 8/500`, `errors 3`). `elapsed` is
computed from `started_ts`/`ended_ts`; you may also send an explicit `elapsed` (seconds).

All timestamps are **Unix epoch seconds** (UTC).

### 3. `events.jsonl` — append-only audit (one JSON object per line)
Not read by the MVP lens, but write it now so the **last-run metrics** and **7-day drift aggregates**
panels (fast-follow) light up with history the moment they ship.
```jsonl
{"run_id":"2026-06-23","step_id":"cars_com","state":"done","ts":1782200180,"metrics":{"listings":1240,"elapsed":180}}
{"run_id":"2026-06-23","step_id":"autotrader","state":"failed","ts":1782200900,"metrics":{"error":"timeout"}}
```

## Alarms (MVP)
- **STALLED** (red): `state=="running"` but no `updated_ts` bump for longer than `pipeline_stale_sec`
  (default 600s) — the run is wedged.
- **MISSED RUN** (red): `expect_by` has passed and no run reached `state=="done"` today — the run died or
  never started and would otherwise go silent.

## Minimal emitter sketch (Python)
```python
import json, os, time, tempfile
PD = os.path.expanduser("~/.../.pipeline")
def _atomic(name, obj):
    os.makedirs(PD, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=PD)
    with os.fdopen(fd, "w") as f: json.dump(obj, f)
    os.replace(tmp, os.path.join(PD, name))
def beat(hb): hb["updated_ts"] = time.time(); _atomic("heartbeat.json", hb)
def event(ev): ev["ts"] = time.time(); open(os.path.join(PD, "events.jsonl"), "a").write(json.dumps(ev) + "\n")
```
Drop `manifest.json` once; call `beat()` whenever a step changes or ticks; append an `event()` per state
change. The lens (polling `/api/pipeline` every 4s) does the rest.

## Roadmap
- **MVP (shipped):** live run map + STALLED/MISSED alarms.
- **Fast-follow:** Last-run metrics panel (per-step durations/totals from `events.jsonl`) + Trailing
  aggregates (7-day rolling avg duration / totals / source uptime / failure rate, for drift detection).
