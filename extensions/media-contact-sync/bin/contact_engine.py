#!/usr/bin/env python3
"""Media Contact Sync -- the ENGINE (extract -> normalize -> dedup/merge).

Pure stdlib, no I/O, fully testable in isolation. The Gmail reader and Airtable writer are thin adapters that
sit AROUND this; the value lives here. Three stages:

  1. extract_contacts(msg)   -- pull people out of an email: OUT-OF-OFFICE backups + the sender's SIGNATURE block
  2. normalize_contact(c)    -- one consistent shape (clean email/name/company/phone; publisher from domain)
  3. Dedup(master).decide(c) -- 'do we already have this person?' -> an ACTION, never a blind append

MERGE POLICY (operator-locked):
  - same EMAIL  -> same person: fill BLANK fields only; a differing non-blank field is a CONFLICT -> flag, never overwrite
  - same NAME + same PUBLISHER, email missing/different -> probably same: fill the gap BUT flag for a human
  - otherwise -> ADD (net-new)
  GOLDEN RULE: only ADD or FILL BLANKS. Never overwrite existing info automatically. Worst case = a missed add
  (a human catches it), never a corrupted record.
"""
import re

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}")
# free-mail domains never map to a "publisher"
_FREEMAIL = {"gmail.com", "googlemail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "me.com", "aol.com", "proton.me", "protonmail.com"}
# lines that OPEN a signature (name usually the next non-empty line)
_SIGN_OFF = re.compile(r"^\s*(best|thanks|thank you|regards|best regards|kind regards|warm regards|cheers|sincerely|all the best|talk soon|warmly)\b[\s,!.]*$", re.I)
# OUT-OF-OFFICE signals in subject or body
_OOO_SUBJ = re.compile(r"\b(out of (the )?office|auto[\-\s]?reply|automatic reply|on (leave|vacation|holiday|pto)|away|maternity|paternity|parental leave)\b", re.I)
# body phrases that INTRODUCE a backup contact ("please reach out to Jane Doe (jane@x.com)")
_BACKUP_CUE = re.compile(r"\b(please (reach out to|contact|email)|reach out to|in my absence,?|for (urgent|immediate|any) (matters|inquiries|questions|needs),?( please)?( contact| reach out to| email)?|my (backup|colleague|cover|teammate) (is|will be)|you can (contact|reach|email)|kindly (contact|reach out to|email)|contact my|assisting (me|in my absence) (is|will be))\b", re.I)
_NAME_TOK = re.compile(r"[A-Z][a-zA-Z'’\-]+(?:\s+[A-Z][a-zA-Z'’\-]+){1,2}")
_ROLE_HINT = re.compile(r"\b(editor|manager|director|coordinator|writer|producer|lead|head|chief|vp|president|associate|specialist|strategist|analyst|buyer|commerce|affiliate|partnerships?|marketing|content|senior|junior|staff|contributor)\b", re.I)


def _clean_email(e):
    return (e or "").strip().strip(".,;:<>()[]\"'").lower()


def _publisher_from_domain(email):
    e = _clean_email(email)
    if "@" not in e:
        return ""
    dom = e.split("@", 1)[1]
    if dom in _FREEMAIL:
        return ""
    core = dom.split(".")[0]                      # buzzfeed.com -> buzzfeed
    core = re.sub(r"[^a-z0-9]+", " ", core).strip()
    return core.title() if core else ""


def _split_name(name):
    parts = [p for p in re.split(r"\s+", (name or "").strip()) if p]
    if not parts:
        return ("", "")
    if len(parts) == 1:
        return (parts[0], "")
    return (parts[0], parts[-1])


def normalize_contact(c):
    """One canonical shape. Blank (missing) fields stay "" so dedup can gap-fill them. Idempotent."""
    email = _clean_email(c.get("email"))
    name = re.sub(r"\s+", " ", (c.get("name") or "").strip()).strip(",.;")
    # strip a trailing role that got glued onto the name ("Jane Doe, Commerce Editor")
    name = re.sub(r"\s*[,|-].*$", "", name).strip() if "," in name or " - " in name else name
    name = " ".join(w if (w.isupper() and len(w) <= 3) else w.capitalize() for w in name.split())
    first, last = _split_name(name)
    company = (c.get("company") or "").strip()
    company = re.sub(r"[,.]?\s*(inc|llc|ltd|co|corp|company|media|group)\.?$", "", company, flags=re.I).strip() or company
    if not company:
        company = _publisher_from_domain(email)
    phone = c.get("phone") or ""
    pm = PHONE_RE.search(phone) or (PHONE_RE.search(c.get("_raw", "")) if not phone else None)
    phone = re.sub(r"[^\d+]", "", pm.group(0)) if pm else ""
    title = re.sub(r"\s+", " ", (c.get("title") or "").strip()).strip(",.;")
    return {"name": name, "first": first, "last": last, "email": email, "title": title,
            "company": company, "phone": phone,
            "source": c.get("source", ""), "source_msg": c.get("source_msg", "")}


def _signature_block(body):
    """Return the trailing signature lines (after a sign-off, or the tail block that holds the sender's email)."""
    lines = [ln.rstrip() for ln in (body or "").splitlines()]
    # cut quoted history ("On ... wrote:", ">")
    cut = len(lines)
    for i, ln in enumerate(lines):
        if re.match(r"^\s*>", ln) or re.match(r"^\s*On .+wrote:\s*$", ln) or re.match(r"^-{2,}\s*Original Message", ln, re.I):
            cut = i
            break
    lines = lines[:cut]
    # prefer the block after the LAST sign-off line
    idx = None
    for i, ln in enumerate(lines):
        if _SIGN_OFF.match(ln):
            idx = i
    if idx is not None:
        return "\n".join(lines[idx + 1: idx + 9]).strip()
    # else: the last non-empty ~8 lines that contain an email
    tail = [ln for ln in lines[-10:] if ln.strip()]
    return "\n".join(tail).strip() if any(EMAIL_RE.search(ln) for ln in tail) else ""


def _parse_signature(block, sender_email=""):
    """A signature block -> one contact (name / title / company / email / phone)."""
    if not block:
        return None
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    if not lines:
        return None
    em = EMAIL_RE.search(block)
    email = _clean_email(em.group(0)) if em else _clean_email(sender_email)
    # name = first line that looks like a person's name (2-3 capitalized words), not a role/company line
    name = ""
    for ln in lines[:4]:
        m = _NAME_TOK.match(ln.strip())
        if m and not _ROLE_HINT.search(ln) and "@" not in ln:
            name = m.group(0)
            break
    title = ""
    for ln in lines[:5]:
        if _ROLE_HINT.search(ln) and "@" not in ln and ln.lower() != name.lower():
            title = re.sub(r"\s*[|•·].*$", "", ln).strip()
            break
    if not name and not email:
        return None
    return {"name": name, "title": title, "email": email, "company": "", "phone": "",
            "_raw": block, "source": "signature"}


def _parse_ooo_backups(subject, body):
    """An out-of-office reply -> the backup contact(s) it names. Pairs a NAME near a BACKUP cue with a nearby email."""
    out = []
    text = (subject or "") + "\n" + (body or "")
    if not (_OOO_SUBJ.search(subject or "") or _BACKUP_CUE.search(body or "")):
        return out
    # scan sentence-ish windows that contain a backup cue; grab the name + the nearest email in that window
    for m in _BACKUP_CUE.finditer(body or ""):
        win = (body or "")[m.start(): m.start() + 240]
        after = (body or "")[m.end(): m.end() + 160]
        nm = _NAME_TOK.search(after) or _NAME_TOK.search(win[m.start() - m.start():])
        em = EMAIL_RE.search(win)
        if not nm and not em:
            continue
        name = nm.group(0) if nm else ""
        # a name is only a real backup if it's not a generic word run; require it near the cue
        if name and _ROLE_HINT.fullmatch(name.strip()):
            name = ""
        c = {"name": name, "email": _clean_email(em.group(0)) if em else "", "title": "", "company": "",
             "phone": "", "source": "ooo"}
        if c["name"] or c["email"]:
            out.append(c)
    # dedupe within this one email (same email or same name)
    seen, uniq = set(), []
    for c in out:
        k = c["email"] or c["name"].lower()
        if k and k not in seen:
            seen.add(k)
            uniq.append(c)
    return uniq


def extract_contacts(msg):
    """msg = {subject, body, from_name, from_email}. -> list of RAW contacts (normalize them next).
    Pulls OOO backups (people OTHER than the sender) + the sender's signature (the sender themselves)."""
    subject = msg.get("subject", "")
    body = msg.get("body", "")
    found = []
    # 1) OOO backups
    found += _parse_ooo_backups(subject, body)
    # 2) the sender's own signature (only if not a pure autoresponder with no signature)
    sig = _parse_signature(_signature_block(body), sender_email=msg.get("from_email", ""))
    if sig:
        if not sig.get("name") and msg.get("from_name"):
            sig["name"] = msg["from_name"]
        found.append(sig)
    elif msg.get("from_email") and not _OOO_SUBJ.search(subject):
        # no signature parsed but we know the human sender -> minimal contact
        found.append({"name": msg.get("from_name", ""), "email": _clean_email(msg["from_email"]),
                      "title": "", "company": "", "phone": "", "source": "sender"})
    return [c for c in found if c.get("email") or c.get("name")]


# ---- dedup / merge -------------------------------------------------------------------------------------------
_FIELDS = ("name", "title", "company", "phone")   # fields we may gap-fill (email is the key, handled separately)


def _norm_key(name, company):
    return (re.sub(r"[^a-z]", "", (name or "").lower()), re.sub(r"[^a-z0-9]", "", (company or "").lower()))


class Dedup:
    """Build once from the master list; decide() one normalized contact at a time."""

    def __init__(self, master):
        self.by_email = {}
        self.by_namecompany = {}
        for r in master:
            e = _clean_email(r.get("email"))
            if e:
                self.by_email[e] = r
            k = _norm_key(r.get("name"), r.get("company"))
            if k[0]:
                self.by_namecompany.setdefault(k, r)

    def decide(self, c):
        """-> {'action': skip|gap_fill|add|flag, 'target': <record|None>, 'fill': {field:val}, 'flag': bool, 'reason': str}"""
        c = normalize_contact(c) if "first" not in c else c
        email = c.get("email", "")
        # 1) hard match on email
        if email and email in self.by_email:
            tgt = self.by_email[email]
            fill, conflict = self._diff(tgt, c)
            if conflict:
                return {"action": "flag", "target": tgt, "fill": fill, "flag": True,
                        "reason": "email match but a non-blank field differs (%s) -- never overwrite; needs a human" % ", ".join(conflict)}
            if fill:
                return {"action": "gap_fill", "target": tgt, "fill": fill, "flag": False,
                        "reason": "email match; filling blank field(s): " + ", ".join(fill)}
            return {"action": "skip", "target": tgt, "fill": {}, "flag": False, "reason": "already listed, nothing new"}
        # 2) fuzzy match on name + publisher (email missing/different)
        k = _norm_key(c.get("name"), c.get("company"))
        if k[0] and k in self.by_namecompany:
            tgt = self.by_namecompany[k]
            fill, conflict = self._diff(tgt, c)
            # a NEW email for a record that had none is a gap-fill -- but ALWAYS flag a fuzzy identity match
            if email and not _clean_email(tgt.get("email")):
                fill["email"] = email
            return {"action": "flag", "target": tgt, "fill": fill, "flag": True,
                    "reason": "same name at %s but email missing/different -- likely same person; fill+confirm" % (c.get("company") or "same publisher")}
        # 3) net-new
        return {"action": "add", "target": None, "fill": {}, "flag": False, "reason": "net-new contact"}

    @staticmethod
    def _diff(existing, new):
        """Which blank fields in `existing` can `new` fill (fill), and which non-blank fields CONFLICT (conflict)."""
        fill, conflict = {}, []
        for f in _FIELDS:
            ev = (existing.get(f) or "").strip()
            nv = (new.get(f) or "").strip()
            if not nv:
                continue
            if not ev:
                fill[f] = nv
            elif f in ("title", "phone") and ev.lower() != nv.lower():
                conflict.append(f)   # a changed title/phone is a real change -> human decides (never auto-overwrite)
        return fill, conflict
