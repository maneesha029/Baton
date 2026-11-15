"""Role-filtered handover: only approved claims, redacted by clearance BEFORE anything is composed or exported."""
import time

from .. import db
from . import analysis, audit, ledger
from .cases import BadInput, get_case

SECTIONS = [("owner", "Who owns what"), ("decision", "Decisions and why"), ("risk", "Risks"), ("dependency", "Dependencies"),
            ("question", "Open questions"), ("fact", "Facts"), ("contact", "Contacts")]
BUCKETS = [("before", "Before the leaver goes"), ("week", "First week"), ("month1", "First month"), ("month2", "Second month"), ("later", "Later")]


def _bucket(days):
    if days is None:
        return "week"
    return "before" if days < 0 else "month1" if days <= 30 else "month2" if days <= 60 else "later"


def _plan(claims, radar, leaver):
    dl = {}
    for d in radar:
        dl.setdefault(d["claim"], []).append(d)
    items = []
    for c in claims:
        gap = c["state"] in ("MISSING", "CONFLICT", "TESTIMONY")
        if c["type"] not in ("risk", "dependency", "question") and not (c["type"] == "owner" and gap):
            continue
        ds = sorted(dl.get(c["id"], []), key=lambda d: d["iso"])
        d0 = ds[0] if ds else None
        verb = {"question": "Find out", "risk": "Mitigate", "dependency": "Secure"}.get(c["type"], "Find an owner for" if c["state"] == "MISSING" else "Resolve")
        title = f"{verb}: " + (c["subject"] if c["type"] == "owner" and c["state"] == "MISSING" and c.get("subject") else c["text"].split("  >>")[0])
        solo = analysis.is_solo(c) and analysis.holders(c) == {leaver}
        items.append({"ref": c["ref"], "claim": c["id"], "title": title, "state": c["state"], "bucket": _bucket(d0["days_after"] if d0 else None),
                      "deadline": d0["iso"] if d0 else None, "days_after": d0["days_after"] if d0 else None, "unverified": c["state"] not in ("VERIFIED", "TESTIMONY"),
                      "leaver_only": solo, "unowned": d0["unowned"] if d0 else [], "priority": (3 if c["type"] in ("risk", "owner") else 2) + (2 if solo else 0)})
    groups = []
    for key, name in BUCKETS:
        its = sorted([i for i in items if i["bucket"] == key], key=lambda i: (i["deadline"] or "9999", -i["priority"]))
        if its:
            groups.append({"bucket": key, "title": name, "items": its})
    return groups


def build(cid, role):
    case = get_case(cid)
    claims, hidden = ledger.view(cid, role, approved_only=True)
    cnt = ledger.counts(cid)
    approved_total = cnt["status"].get("approved", 0)
    radar = analysis.deadlines(cid, claims)
    return {"case": {"id": case["id"], "name": case["name"], "leaver": case["leaver"], "last_day": case["last_day"]}, "role": role,
            "version": audit.verify(cid)["length"], "shown": len(claims), "hidden": hidden, "pending": cnt["total"] - approved_total,
            "sections": [{"key": k, "title": t, "claims": [c for c in claims if c["type"] == k]} for k, t in SECTIONS if any(c["type"] == k for c in claims)],
            "plan": _plan(claims, radar, case["leaver"]), "radar": radar, "ack": ack_of(cid), "readiness": ledger.readiness(cid),
            "bus_factor": analysis.bus_factor(claims)}


def ack_of(cid):
    return db.one("SELECT name,role,version,at FROM acks WHERE case_id=? ORDER BY at DESC LIMIT 1", (cid,))


def acknowledge(cid, name, role):
    name = (name or "").strip()
    if not name:
        raise BadInput("name required")
    if not db.one("SELECT 1 x FROM claims WHERE case_id=? AND status='approved'", (cid,)):
        raise BadInput("approve at least one claim before acknowledging a handover")
    ver = audit.verify(cid)["length"]
    db.run("INSERT INTO acks(case_id,name,role,version,at) VALUES(?,?,?,?,?)", (cid, name[:80], role, ver, time.time()))
    audit.log(cid, name.lower(), "Receipt acknowledged", "", f"{role} view v{ver}")
    return ack_of(cid)


def markdown(h):
    lines = [f"# Handover: {h['case']['name']} ({h['role']} view, v{h['version']})", "",
             f"Leaver: {h['case']['leaver'].title() or 'n/a'}. Last day: {h['case']['last_day'] or 'n/a'}. Readiness {h['readiness']['percent']}%.", ""]
    if h["plan"]:
        lines.append("## Start here")
        for g in h["plan"]:
            lines.append(f"**{g['title']}**")
            lines += [f"- {'[unverified] ' if i['unverified'] else ''}{i['title']}" + (f" (by {i['deadline']})" if i["deadline"] else "") + f" [{i['ref']}]" for i in g["items"]]
            lines.append("")
    for s in h["sections"]:
        lines.append(f"## {s['title']}")
        for c in s["claims"]:
            lines.append(f"- [{c['state']}] {c['text']} ({', '.join(e['source'] + ':' + str(e['line'] + 1) for e in c['evidence'])})")
        lines.append("")
    if h["hidden"]:
        lines.append(f"> {h['hidden']} item(s) restricted at {h['role']} clearance. Request access from the reviewer.\n")
    return "\n".join(lines)


def bundle(cid, role):
    h = build(cid, role)
    return {"handover": h, "audit": audit.verify(cid), "markdown": markdown(h)}
