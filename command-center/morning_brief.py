#!/usr/bin/env python3
"""Morning Brief -- a scheduled, voice-delivered brief of your day + what's coming.

Runs ~an hour before your start time (configurable). Pulls a CITED slice from your configured sources
(calendar / gmail / tasks / granola / slack -- an EXTENSIBLE registry, add more as extensions land),
synthesizes 2-3 paragraphs via a headless `claude -p` (Max subscription, NO metered key), optionally
renders it to natural speech (ElevenLabs / OpenAI / macOS say), and surfaces it in the Brief lens to
auto-play as you sit down. Per-project: each console briefs its own day.

Stdlib only. server.py calls morning_brief.init(ctx) once, then the mb_* functions behind /api/brief*.
Config (cc.config "morning_brief"): {
  "open_time": "8:00am", "lead_minutes": 60, "days": "weekdays"|"all",
  "horizon_days": 14, "length": "short"|"medium", "tone": "warm"|"crisp",
  "sources": ["calendar","gmail","tasks","granola","slack"],
  "voice": {"enabled": true, "provider": "elevenlabs"|"openai"|"say", "voice_id": "...", "autoplay": true}
}
"""
import json, os, re, subprocess, time, urllib.request, urllib.error

_CTX = {}   # injected by server.py: CC, PROJECT, STATE_DIR, sh, secret, + accessors (see init)
_LAST_TTS_FALLBACK = ""   # why a non-preferred voice provider was used (surfaced in the brief, for debugging)


def init(ctx):
    _CTX.update(ctx)


def _cfg():
    c = dict((_CTX.get("CC", {}) or {}).get("morning_brief") or {})
    c.setdefault("open_time", "8:00am"); c.setdefault("lead_minutes", 60)
    c.setdefault("days", "weekdays"); c.setdefault("horizon_days", 14)
    c.setdefault("length", "short"); c.setdefault("tone", "warm")
    c.setdefault("sources", list(SOURCES.keys()))   # ALL registered sources ON by default (each degrades to [] if its backend isn't set up); future sources auto-included
    # BUSINESS-HOURS awareness (Sarah): so the brief never counts evenings/weekends/non-working days as elapsed
    # time when judging "overdue"/"unanswered". work_days = which days I actually work; work_hours = my day.
    c.setdefault("work_days", "weekdays"); c.setdefault("work_hours", "9:00am-5:00pm")
    v = dict(c.get("voice") or {})
    v.setdefault("enabled", True); v.setdefault("provider", "openai"); v.setdefault("voice_id", "")
    v.setdefault("autoplay", True); c["voice"] = v
    return c


def _state_path():  return os.path.join(_CTX.get("STATE_DIR", "."), "_morning_brief.json")
def _audio_dir():
    d = os.path.join(_CTX.get("STATE_DIR", "."), "brief_audio"); os.makedirs(d, exist_ok=True); return d


def _load_state():
    try:
        with open(_state_path()) as f: return json.load(f)
    except Exception:
        return {"briefs": [], "last_run": 0, "last_status": "", "last_error": ""}


def _save_state(s):
    try:
        with open(_state_path(), "w") as f: json.dump(s, f, indent=2)
    except Exception: pass


# ---- SOURCE REGISTRY -- each source returns [{label, text, ts, ref}] cited items. ADD A SOURCE = ADD A FN.
SOURCES = {}            # name -> {fn, label}


def source(name, label):
    def deco(fn): SOURCES[name] = {"fn": fn, "label": label}; return fn
    return deco


def _call(key, *a, **k):
    """Call an injected server accessor by name; None if it's not wired (source degrades, never crashes)."""
    fn = _CTX.get(key)
    if not callable(fn): return None
    try: return fn(*a, **k)
    except Exception: return None


def _fmt_dt(s):
    """Best-effort: an ISO / RFC2822-email / epoch date string -> a friendly ABSOLUTE label WITH the weekday,
    e.g. 'Wed Jul 8 3:00pm' or 'Mon Jun 30'. Returns the input unchanged if unparseable. The brief MUST show the
    model each item's real date -- a date-blind brief conflates 'the Jul 8 call' with 'today' (Sarah's reschedule)."""
    import datetime as _dt, email.utils as _eu
    if s is None: return ""
    if isinstance(s, (int, float)):
        try: return _dt.datetime.fromtimestamp(s).strftime("%a %b %-d %-I:%M%p").replace("AM", "am").replace("PM", "pm")
        except Exception: return str(s)
    raw = str(s).strip()
    if not raw: return ""
    dt = None
    try: dt = _dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception: dt = None
    if dt is None:
        try: dt = _eu.parsedate_to_datetime(raw)
        except Exception: dt = None
    if dt is None:
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
            try: dt = _dt.datetime.strptime(raw[:10], fmt); break
            except Exception: continue
    if dt is None: return raw
    has_time = ("T" in raw) or (len(raw) > 10 and ":" in raw)
    if has_time and (dt.hour or dt.minute):
        return dt.strftime("%a %b %-d %-I:%M%p").replace("AM", "am").replace("PM", "pm")
    return dt.strftime("%a %b %-d")


@source("calendar", "Calendar")
def _src_calendar(cfg):
    ev = _call("calendar_events", cfg.get("horizon_days", 14))
    out = []
    if isinstance(ev, dict): ev = ev.get("events") or ev.get("items") or []
    for e in (ev or [])[:40]:
        if not isinstance(e, dict): continue
        st = e.get("start")
        when = ((st.get("dateTime") or st.get("date")) if isinstance(st, dict)
                else st if isinstance(st, str) else "") or e.get("start_str") or e.get("date") or ""
        title = e.get("summary") or e.get("title") or "(busy)"
        who = ", ".join(a.get("email", "") for a in (e.get("attendees") or []) if isinstance(a, dict))[:160]
        out.append({"label": title, "text": ("%s -- %s%s" % (_fmt_dt(when), title, (" (with " + who + ")") if who else "")),
                    "ts": when, "ref": "calendar"})   # LEAD with the real date -- the model must see WHICH day each event is
    return out


@source("gmail", "Inbox")
def _src_gmail(cfg):
    r = _call("gmail_list", "inbox", "", 18)
    msgs = (r.get("messages") if isinstance(r, dict) else r) or []
    out = []
    for m in msgs[:18]:
        if not isinstance(m, dict): continue
        frm = m.get("from") or m.get("sender") or ""; subj = m.get("subject") or "(no subject)"
        snip = (m.get("snippet") or "")[:200]
        _d = m.get("date") or m.get("ts") or ""
        out.append({"label": subj, "text": "arrived %s -- From %s: %s -- %s" % (_fmt_dt(_d), frm[:60], subj, snip),
                    "ts": _d, "ref": "gmail"})   # LEAD with when it arrived -- so a reply is tied to the right dated event
    return out


@source("drive_comments", "Doc comments")
def _src_drive_comments(cfg):
    """OPEN (unresolved) comment threads on recent Docs/Sheets/Slides, with the WHOLE thread so the brief has
    the resolution context and never re-flags a comment that was already answered (Sarah). Server side already
    drops resolved threads; here we hand the model the full back-and-forth + reply count, explicitly marked OPEN."""
    cs = _call("drive_open_comments", 7) or []
    out = []
    for c in cs[:20]:
        if not isinstance(c, dict): continue
        thread = "%s commented on \"%s\": %s" % (c.get("author", "someone"), c.get("file", "a file"),
                                                 (c.get("content") or "")[:220])
        for r in (c.get("replies") or [])[:8]:
            thread += " || reply from %s: %s" % (r.get("author", ""), (r.get("content") or "")[:160])
        n = c.get("reply_count", 0)
        thread += " [STILL OPEN/unresolved%s]" % (", %d repl%s so far" % (n, "y" if n == 1 else "ies") if n else ", no replies yet")
        out.append({"label": ("comment on " + (c.get("file") or "a file"))[:80], "text": thread,
                    "ts": c.get("created") or "", "ref": "drive"})
    return out


@source("tasks", "Tasks")
def _src_tasks(cfg):
    try:
        d = json.load(open(os.path.join(_CTX.get("STATE_DIR", "."), "_tasks.json")))
    except Exception:
        return []
    items = d.get("tasks") if isinstance(d, dict) else (d or [])
    out = []
    for t in (items or []):
        if not isinstance(t, dict): continue
        if t.get("status") in ("done", "dismissed", "skipped"): continue
        title = t.get("title") or t.get("text") or ""
        if not title: continue
        out.append({"label": title[:80], "text": title, "ts": t.get("due") or t.get("ts") or "", "ref": "tasks"})
    return out[:25]


def _from_context(kinds, cfg, ref):
    """Pull recent cited items for the given context-event kinds (granola=call, slack=slack/message...)."""
    asm = _CTX.get("context_assemble")
    if not callable(asm): return []
    try:
        b = asm(kinds=kinds, budget_tokens=1200, half_life_hours=float(cfg.get("horizon_days", 14)) * 24 / 4)
    except Exception:
        return []
    out = []
    for it in (b.get("items") if isinstance(b, dict) else []) or []:
        if not isinstance(it, dict): continue
        out.append({"label": (it.get("title") or "")[:80],
                    "text": ((it.get("title") or "") + " -- " + (it.get("snippet") or ""))[:260],
                    "ts": it.get("ts") or "", "ref": ref})
    return out[:15]


@source("granola", "Calls")
def _src_granola(cfg): return _from_context(["call"], cfg, "granola")


@source("slack", "Slack")
def _src_slack(cfg): return _from_context(["slack", "message", "chat"], cfg, "slack")


@source("notes", "Notes")
def _src_notes(cfg):
    fn = _CTX.get("notes_recent")
    if not callable(fn): return []
    try:
        out = []
        for it in (fn() or []):
            out.append({"label": it.get("label", ""), "text": it.get("text", ""), "ts": it.get("ts", ""), "ref": "notes"})
        return out
    except Exception:
        return []


def available_sources():
    """[{name,label,enabled}] -- what the lens shows; reflects which sources are wired on this node."""
    sel = set(_cfg().get("sources") or [])
    return [{"name": n, "label": s["label"], "enabled": n in sel} for n, s in SOURCES.items()]


# ---- synthesis (headless claude -p, Max subscription, no metered key) ----------------------------------
def _voice_profile():
    """The owner's VoiceMatch writing-style profile (how they talk/type), so the brief sounds like THEM."""
    f = _CTX.get("voice_profile")
    if not callable(f): return ""
    try:
        p = f() or {}
        md = (p.get("profile_md") or "").strip()
        if not md: return ""
        extra = ""
        if p.get("greetings"): extra += " Typical openers: " + ", ".join(p["greetings"][:4]) + "."
        return ("\n\n=== WRITE IT IN THIS PERSON'S OWN VOICE (their style profile -- match their cadence, word "
                "choice, warmth/bluntness; this brief is FOR them, in their voice) ===\n" + md + extra + "\n")
    except Exception:
        return ""


def _work_clause(cfg):
    """Tell the brief to reason about elapsed time in BUSINESS hours only (Sarah: a Friday-evening comment is
    not 'days old' on Monday). Uses configurable work_days + work_hours."""
    wd = cfg.get("work_days", "weekdays")
    days = ("Monday through Friday (I do NOT work weekends)" if wd == "weekdays"
            else "every day" if wd == "all" else str(wd))
    hrs = cfg.get("work_hours", "9:00am-5:00pm")
    now = time.strftime("%A %-I:%M%p")
    return ("=== MY WORKING TIME (reason about elapsed time in BUSINESS hours ONLY) ===\n"
            "It is now %s. My working days are %s; my working hours are %s. When you judge whether anything is "
            "'overdue', 'unanswered', 'sitting', 'stale', or 'ignored', count ONLY business time within those "
            "days and hours -- NEVER count evenings, nights, weekends, or non-working days. Something that "
            "arrived late on a Friday or after hours is NOT 'days old' the next working morning; treat it as just "
            "arrived. Never imply I was slow, dropped something, or let anything slip based on non-working time.\n\n"
            % (now, days, hrs))

def _brief_prompt(blocks, cfg, style=""):
    when = time.strftime("%A, %B %-d, %Y")
    length = "2 short paragraphs" if cfg.get("length") == "short" else "3 paragraphs"
    tone = "warm and personal" if cfg.get("tone") == "warm" else "crisp and businesslike"
    return (style +
            "You are MY trusted assistant writing my MORNING BRIEF for %s. You work FOR me and report TO me: be "
            "helpful and %s, like a sharp assistant briefing the person they support. You are NOT my manager -- "
            "never take a scolding, lecturing, or bossy tone, never say things like 'don't let this slip again', "
            "and never imply I failed to do something. Surface what's there plainly and let me decide what matters. "
            "Write %s of flowing prose (NO headers, NO bullet lists, NO markdown) that I'll hear read aloud as I "
            "start work. Cover, in this order and only where there's real signal: (1) the SHAPE of today -- my "
            "meetings and the 2-3 things that actually matter; (2) what's COMING UP over the next week or two worth "
            "prepping for; (3) any watch-outs or prep (e.g. a call where last time we discussed X, or a task with a "
            "real upcoming deadline). Be specific and cite real names/times from the data. Do NOT invent anything "
            "not in the data. If a section has nothing real, skip it. Keep it tight -- this is spoken, not a "
            "report.\n\n%s"
            "DATES ARE CRITICAL -- BE METICULOUS. Every calendar and email item below is PREFIXED WITH ITS REAL "
            "DATE. Today is %s. Never call something 'today' unless its date literally IS today. When an email is a "
            "reply about a meeting/hold, tie it to that event's SPECIFIC date (e.g. a reply on the Jul 8 hold is "
            "about Jul 8, not today) -- do not collapse a future reschedule into 'today'. If a reply's date and the "
            "event's date don't line up, or which occurrence is meant is ambiguous, SAY SO plainly ('heads up: this "
            "looks like it's about the Jul 8 call, but confirm') rather than guessing. Get the day of week and the "
            "date right every time.\n\n"
            "=== MY DATA (grouped by source; newest-ish first) ===\n%s\n=== END DATA ===\n"
            "Now write the brief as plain spoken prose." % (when, tone, length, _work_clause(cfg), when, blocks))


def _synthesize(blocks, cfg, style=""):
    inj = _CTX.get("extractor")          # tests inject a fake synthesizer
    if inj: return inj(blocks, cfg)
    prompt = _brief_prompt(blocks, cfg, style)
    try:
        r = subprocess.run(["claude", "--dangerously-skip-permissions", "-p", prompt],
                           capture_output=True, text=True, timeout=180,
                           env={**os.environ, "PATH": os.environ.get("PATH", "") + ":" +
                                os.path.expanduser("~/.local/bin") + ":/opt/homebrew/bin"})
        out = (r.stdout or "").strip()
        return out or ("(brief synthesis returned nothing -- " + (r.stderr or "")[:120] + ")")
    except Exception as e:
        return "(brief synthesis failed: %s)" % str(e)[:140]


# ---- text-to-speech (provider-agnostic; keys VAULT-FIRST) ----------------------------------------------
def _secret(key):
    f = _CTX.get("secret")
    try: return f(key) if callable(f) else ""
    except Exception: return ""


def _tts(text, cfg):
    """Render text -> an audio file under brief_audio/. Returns (rel_filename, provider) or (None, reason).
    Providers: elevenlabs (key ELEVENLABS_API_KEY) -> openai (OPENAI_API_KEY) -> macOS `say`."""
    v = cfg.get("voice") or {}
    if not v.get("enabled"): return (None, "voice disabled")
    global _LAST_TTS_FALLBACK
    _LAST_TTS_FALLBACK = ""
    prov = v.get("provider") or "openai"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    order = [prov] + [p for p in ("elevenlabs", "openai", "say") if p != prov]   # try chosen, then fall back
    reasons = []
    for p in order:
        try:
            if p == "elevenlabs":
                key = _secret("ELEVENLABS_API_KEY")
                if not key: reasons.append("elevenlabs: no ELEVENLABS_API_KEY in vault"); continue
                vid = v.get("voice_id") or "EXAVITQu4vr4xnSDxMaL"   # 'Sarah' default
                body = json.dumps({"text": text, "model_id": "eleven_turbo_v2_5"}).encode()
                req = urllib.request.Request(
                    "https://api.elevenlabs.io/v1/text-to-speech/" + vid, data=body,
                    headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
                with urllib.request.urlopen(req, timeout=60) as r: audio = r.read()
                fn = "brief-%s-11l.mp3" % stamp
                open(os.path.join(_audio_dir(), fn), "wb").write(audio); return (fn, "elevenlabs")
            if p == "openai":
                key = _secret("OPENAI_API_KEY")
                if not key: reasons.append("openai: no OPENAI_API_KEY resolved from vault"); continue
                body = json.dumps({"model": "tts-1-hd", "voice": (v.get("voice_id") or "nova"),
                                   "input": text[:4000]}).encode()
                req = urllib.request.Request(
                    "https://api.openai.com/v1/audio/speech", data=body,
                    headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=90) as r: audio = r.read()
                fn = "brief-%s-oai.mp3" % stamp
                open(os.path.join(_audio_dir(), fn), "wb").write(audio); return (fn, "openai")
            if p == "say":
                fn = "brief-%s-say.aiff" % stamp
                rc = subprocess.run(["say", "-o", os.path.join(_audio_dir(), fn), text[:6000]],
                                    capture_output=True, timeout=60).returncode
                if rc == 0:
                    _LAST_TTS_FALLBACK = "; ".join(reasons[:4]); return (fn, "say")
                reasons.append("say: rc=%s" % rc)
        except Exception as e:
            reasons.append("%s: %s" % (p, str(e)[:120]))
            continue
    _LAST_TTS_FALLBACK = "; ".join(reasons[:4])
    return (None, "voice failed -- " + "; ".join(reasons[:4]))


# ---- generate: the routine + the lens call this --------------------------------------------------------
def _alert(kind, msg):
    """Ping the operator when a scheduled brief fails/empties -- so a missed brief is NEVER silent. The server
    injects `notify` (Telegram/in-process notify_send) at init; no-op if not wired (e.g. tests)."""
    fn = _CTX.get("notify")
    if not callable(fn): return
    try: fn("Morning Brief %s -- %s" % (kind, (msg or "")[:240]))
    except Exception: pass


def mb_generate():
    """Assemble -> synthesize -> voice the brief. FAIL-LOUD: every exit persists last_status/last_error and a
    failure alerts the operator. A 'running' checkpoint is written up front so last_run advances immediately and
    a hang/process-kill shows as a stuck 'running' -- never a phantom 'ok' with yesterday's brief still showing.
    (Silent failure was the root cause of a missed brief: fire-and-forget thread + persist-only-at-end hid it.)"""
    cfg = _cfg()
    st = _load_state()
    # concurrency guard: a slow synthesis + a catch-up sweep (or a manual retry) must not run two at once
    if st.get("last_status") == "running" and (int(time.time()) - int(st.get("last_run", 0) or 0)) < 600:
        return {"ok": False, "error": "already generating (started %ds ago)" % (int(time.time()) - int(st.get("last_run", 0) or 0))}
    st["last_run"] = int(time.time()); st["last_status"] = "running"; st["last_error"] = ""
    _save_state(st)                                          # CHECKPOINT up front (survives a mid-synthesis kill)
    try:
        sel = [s for s in (cfg.get("sources") or []) if s in SOURCES]
        blocks, used, src_errors = [], [], []
        for name in sel:
            try:
                items = SOURCES[name]["fn"](cfg) or []       # one bad source must NEVER kill the whole brief
            except Exception as e:
                src_errors.append("%s: %s" % (name, str(e)[:80])); continue
            if not items: continue
            used.append({"source": name, "count": len(items)})
            lines = "\n".join("- " + (i.get("text") or "") for i in items[:25])
            blocks.append("## %s\n%s" % (SOURCES[name]["label"], lines))
        if not blocks:
            err = "no data from the selected sources (%s)" % ("; ".join(src_errors) if src_errors else "all empty -- check Google/Granola setup + sources")
            st["last_status"] = "empty"; st["last_error"] = err; _save_state(st)
            _alert("no data", err); return {"ok": False, "error": err}
        text = _synthesize("\n\n".join(blocks), cfg, _voice_profile())
        if not text or text.lstrip().startswith("(brief synthesis"):   # _synthesize's failure/timeout sentinel
            err = (text or "empty synthesis").strip().strip("()")       # -> don't save garbage AS a real brief
            st["last_status"] = "failed"; st["last_error"] = err; _save_state(st)
            _alert("synthesis failed", err); return {"ok": False, "error": err}
        audio_fn, prov = _tts(text, cfg)
        brief = {"id": "mb-%d" % int(time.time()), "ts": int(time.time()),
                 "date": time.strftime("%Y-%m-%d"), "text": text, "sources_used": used,
                 "audio": audio_fn, "voice_provider": prov if audio_fn else None,
                 "voice_note": (None if audio_fn else prov),
                 "voice_fallback": _LAST_TTS_FALLBACK or None,
                 "src_errors": src_errors or None, "unread": True}   # unread -> the dashboard surfaces it on open
        st["briefs"].insert(0, brief); st["briefs"] = st["briefs"][:60]
        st["last_status"] = "ok"; st["last_error"] = ""
        _save_state(st)
        return {"ok": True, "id": brief["id"], "audio": bool(audio_fn), "voice": prov, "sources_used": used,
                "chars": len(text)}
    except Exception as e:
        import traceback
        err = ("%s | %s" % (e, (traceback.format_exc().splitlines() or [""])[-1]))[:220]
        st["last_status"] = "error"; st["last_error"] = err
        try: _save_state(st)
        except Exception: pass
        _alert("errored", err)
        return {"ok": False, "error": err}


def mb_should_catchup():
    """True when today is a scheduled brief day, the scheduled time has passed, there's still no brief for today,
    and nothing is mid-generation / recently attempted. The server's catch-up sweep calls this so a failed or
    missed 8am brief SELF-HEALS instead of silently costing the whole day."""
    import datetime as _d
    cfg = _cfg(); st = _load_state()
    when = schedule_when(cfg)
    if not when: return False
    now = _d.datetime.now()
    wds = when.get("weekdays")
    if wds is not None:
        raw = wds if isinstance(wds, (list, tuple)) else [wds]
        targets = set((int(x) + 6) % 7 for x in raw)         # launchd Sun=0 -> python Mon=0..Sun=6
        if now.weekday() not in targets: return False
    sched = now.replace(hour=int(when.get("hour", 8)), minute=int(when.get("minute", 0)), second=0, microsecond=0)
    if now < sched: return False                             # not time yet today
    briefs = st.get("briefs", [])
    if briefs and briefs[0].get("date") == time.strftime("%Y-%m-%d"): return False   # already have today's
    age = int(time.time()) - int(st.get("last_run", 0) or 0)
    if st.get("last_status") == "running" and age < 600: return False   # a generation is in flight
    if age < 900: return False                               # a recent attempt just happened -> don't hammer
    return True


def mb_state():
    st = _load_state(); cfg = _cfg()
    briefs = st.get("briefs", [])
    today = briefs[0] if briefs else None
    is_today = bool(today and today.get("date") == time.strftime("%Y-%m-%d"))
    return {"ok": True, "today": today, "history": briefs[1:30], "config": cfg,
            "sources": available_sources(), "last_run": st.get("last_run", 0),
            "last_status": st.get("last_status", ""), "last_error": st.get("last_error", ""),
            "next_run_hint": _next_run_hint(cfg),
            # the dashboard polls this: surface a ready, unread brief FOR TODAY (pop up if open / be there on open)
            "unread_today": bool(is_today and today.get("unread"))}


def mb_mark_seen():
    """Mark today's brief as seen, so the dashboard stops surfacing the pop-up once she's opened it."""
    st = _load_state(); briefs = st.get("briefs", [])
    if briefs: briefs[0]["unread"] = False; _save_state(st)
    return {"ok": True}


def audio_path(fn):
    """Resolve a stored audio filename to an absolute path (the server streams it). None if invalid."""
    if not fn or "/" in fn or ".." in fn: return None
    p = os.path.join(_audio_dir(), fn)
    return p if os.path.isfile(p) else None


# ---- config + schedule ---------------------------------------------------------------------------------
def _parse_open(open_time):
    """'8:00am' / '7am' / '08:30' -> (hour, minute) 24h. Defaults 8:00."""
    s = (open_time or "").strip().lower()
    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", s)
    if not m: return (8, 0)
    h = int(m.group(1)); mi = int(m.group(2) or 0); ap = m.group(3)
    if ap == "pm" and h != 12: h += 12
    if ap == "am" and h == 12: h = 0
    return (h % 24, mi % 60)


def schedule_when(cfg):
    """Compute the routine `when` (hour/minute, weekdays) = open_time - lead_minutes."""
    h, mi = _parse_open(cfg.get("open_time"))
    total = (h * 60 + mi - int(cfg.get("lead_minutes", 60))) % (24 * 60)
    w = {"hour": total // 60, "minute": total % 60}
    if cfg.get("days", "weekdays") == "weekdays": w["weekdays"] = [1, 2, 3, 4, 5]   # launchd Sun=0 -> Mon..Fri
    return w


def _next_run_hint(cfg):
    w = schedule_when(cfg)
    return "%02d:%02d%s" % (w["hour"], w["minute"], " on weekdays" if "weekdays" in w else " daily")
