#!/usr/bin/env python3
"""Demonstrate the engine on realistic sample emails against a small master list -- NO real data, NO I/O.
Run: python3 test_contacts.py   (prints every decision so a human can eyeball the dedup logic)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from contact_engine import extract_contacts, normalize_contact, Dedup

# ---- the current shared master list (what Airtable holds today) ----
MASTER = [
    {"name": "Jordan Ellis", "email": "jordan.ellis@buzzfeed.com", "company": "Buzzfeed", "title": "Commerce Editor", "phone": ""},
    {"name": "Maya Chen",    "email": "",                          "company": "Buzzfeed", "title": "Partnerships Manager", "phone": ""},  # missing email
    {"name": "Dana Whitfield","email": "dana.whitfield@hearst.com", "company": "Hearst",  "title": "Affiliate Editor", "phone": ""},
]

# ---- sample incoming emails ----
EMAILS = [
    {   # 1) THE trigger: BuzzFeed out-of-office naming 3 backups
        "subject": "Automatic reply: Out of office",
        "from_name": "Bailey Valente", "from_email": "bailey.valente@buzzfeed.com",
        "body": (
            "Thank you for your email. I am currently out of the office on parental leave and will return in "
            "September.\n\n"
            "For urgent commerce matters, please reach out to Jordan Ellis (jordan.ellis@buzzfeed.com).\n"
            "For ongoing partnerships, you can contact Maya Chen (maya.chen@buzzfeed.com).\n"
            "For anything else, kindly email Tariq Brown (tariq.brown@buzzfeed.com).\n\n"
            "Best,\nBailey"
        ),
    },
    {   # 2) a normal reply with a full signature -> a net-new contact at a new publisher
        "subject": "Re: Q3 affiliate program",
        "from_name": "Priya Nair", "from_email": "priya.nair@refinery29.com",
        "body": (
            "Sounds great, let's line up the assets next week.\n\n"
            "Best regards,\n"
            "Priya Nair\n"
            "Senior Commerce Editor\n"
            "Refinery29\n"
            "priya.nair@refinery29.com | (212) 555-0148\n"
        ),
    },
    {   # 3) an existing contact whose TITLE changed -> must FLAG, never overwrite
        "subject": "Re: media kit",
        "from_name": "Dana Whitfield", "from_email": "dana.whitfield@hearst.com",
        "body": (
            "Here's the updated kit.\n\n"
            "Thanks,\n"
            "Dana Whitfield\n"
            "Director of Commerce Partnerships\n"
            "Hearst\n"
            "dana.whitfield@hearst.com\n"
        ),
    },
]

ICON = {"add": "➕ ADD", "gap_fill": "\U0001f9e9 FILL", "skip": "✓ SKIP", "flag": "\U0001f6a9 FLAG"}


def run():
    dd = Dedup(MASTER)
    print("MASTER (%d rows): %s\n" % (len(MASTER), ", ".join("%s<%s>" % (r["name"], r["email"] or "no email") for r in MASTER)))
    counts = {}
    for i, msg in enumerate(EMAILS, 1):
        print("=" * 92)
        print("EMAIL %d  from %s <%s>  subj: %s" % (i, msg["from_name"], msg["from_email"], msg["subject"]))
        raw = extract_contacts(msg)
        for rc in raw:
            c = normalize_contact(rc)
            d = dd.decide(c)
            counts[d["action"]] = counts.get(d["action"], 0) + 1
            who = "%s <%s>" % (c["name"] or "(no name)", c["email"] or "no email")
            extra = ""
            if d["fill"]:
                extra = "  fill={%s}" % ", ".join("%s=%r" % (k, v) for k, v in d["fill"].items())
            print("   %-8s %-42s [%s]%s" % (ICON.get(d["action"], d["action"]), who, c["source"], extra))
            print("            → %s" % d["reason"])
    print("=" * 92)
    print("TOTALS:", ", ".join("%s=%d" % (k, v) for k, v in sorted(counts.items())))
    # the Bailey scenario assertion: of her 3 backups -> 1 skip, 1 flag(+fill email), 1 add
    return counts


if __name__ == "__main__":
    run()
