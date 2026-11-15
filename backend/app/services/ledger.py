"""Claim ledger: ACL-filtered reads, review actions with versions, leaver testimony, interview, readiness."""
import json
import time

from .. import db
from ..engine.dates import days_between, parse_deadlines
from ..parsers_compat import body_of
from ..security import LEVELS, LEVEL_NAMES, clearance
from . import audit
from .cases import BadInput, NotFound, get_case


def _srcmap(cid):
    return {s["id"]: s for s in db.q("SELECT id,name,acl,kind FROM sources WHERE case_id=?", (cid,))}


def deadlines_of(c, base):
    """Explicit dates in the claim text and its cited lines: [{iso, line}]."""
    seen, out = set(), []
    pieces = [c["text"].split("  >>")[0]] + [body_of(e["quote"]) for e in c["evidence"]]
    if "  >>  " in c["text"]:
        pieces.append(c["text"].split("  >>  ", 1)[1])
    for p in pieces:
        for iso in parse_deadlines(p, c["date"] or base):
            if iso not in seen:
                seen.add(iso)
                out.append({"iso": iso, "line": p})
    return out


def serialize(r, srcs, base=""):
    ev = json.loads(r["evidence"])
    for e in ev:
        s = srcs.get(e["sid"], {})
        e["source"], e["acl"] = s.get("name", e["sid"]), s.get("acl", "team")
        e.pop("req", None), e.pop("toks", None), e.pop("min_overlap", None)
    meta = json.loads(r["meta"] or "{}")
    c = {"id": r["num"], "ref": f"C{r['num']}", "type": r["type"], "text": r["text"], "state": r["state"],
         "confidence": r["confidence"], "status": r["status"], "version": r["version"], "level": r["level"],
         "access": LEVEL_NAMES[r["level"]], "date": r["date"], "evidence": ev, "factors": meta.get("factors", []),
         "note": meta.get("note"), "variants": meta.get("variants"), "hint": meta.get("hint"),
         "testimony": meta.get("testimony"), "was": meta.get("was", r["state"]), "attr": meta.get("attr"),
         "subject": meta.get("subject")}
    c["deadlines"] = deadlines_of(c, base)
    return c


def _rows(cid):
    return db.q("SELECT * FROM claims WHERE case_id=? ORDER BY num", (cid,))


def all_claims(cid):
    """Reviewer-scope read (manager clearance). Callers must apply role filtering before exposing."""
    case, srcs = get_case(cid), _srcmap(cid)
    return [serialize(r, srcs, case["last_day"]) for r in _rows(cid)]


def view(cid, role, approved_only=False):
    """THE permission gate: returns (claims the role may see, count of items withheld). Withheld items are counted, never sent."""
    clr = clearance(role)
    vis, hidden = [], 0
    for c in all_claims(cid):
        if approved_only and c["status"] != "approved":
            continue
        if c["level"] <= clr:
            vis.append(c)
        else:
            hidden += 1
    return vis, hidden


def get_claim(cid, num, role="manager"):
    for c in all_claims(cid):
        if c["id"] == num:
            if c["level"] > clearance(role):
                raise NotFound("claim not available at this clearance")
            return c
    raise NotFound("claim not found")


def _row(cid, num):
    r = db.one("SELECT * FROM claims WHERE case_id=? AND num=?", (cid, num))
    if not r:
        raise NotFound("claim not found")
    return r


def _snapshot(cx, r, actor, action):
    cx.execute("INSERT INTO claim_versions(case_id,num,version,text,state,status,actor,action,at) VALUES(?,?,?,?,?,?,?,?,?)",
               (r["case_id"], r["num"], r["version"], r["text"], r["state"], r["status"], actor, action, time.time()))


def review(cid, num, action, actor="reviewer", text=None, choice=None):
    r = _row(cid, num)
    meta = json.loads(r["meta"] or "{}")
    text0, state0, status0 = r["text"], r["state"], r["status"]
    new = {"text": r["text"], "state": r["state"], "status": r["status"], "confidence": r["confidence"]}
    label = {"approve": "Approved", "reject": "Rejected", "edit": "Edited and approved", "resolve": "Resolved conflict",
             "reopen": "Reopened", "undo": "Undid last action"}.get(action)
    if not label:
        raise BadInput("action must be approve, reject, edit, resolve, reopen or undo")
    with db.tx() as cx:
        if not cx.execute("SELECT 1 FROM claim_versions WHERE case_id=? AND num=? LIMIT 1", (cid, num)).fetchone():
            _snapshot(cx, r, "system", "baseline")
        if action == "approve":
            if r["state"] == "CONFLICT":
                raise BadInput("resolve the conflict first: pick which source is current")
            new["status"] = "approved"
        elif action == "reject":
            new["status"] = "rejected"
        elif action == "reopen":
            new["status"] = "pending"
        elif action == "edit":
            if not text or not text.strip():
                raise BadInput("text required")
            new.update(text=text.strip()[:600], status="approved")
            meta.update(edited=True, note="Edited by reviewer.")
        elif action == "resolve":
            vs = meta.get("variants") or []
            if r["state"] != "CONFLICT" or choice not in vs:
                raise BadInput("choice must be one of: " + ", ".join(vs))
            subj = meta.get("subject", "")
            new.update(text=f"{meta.get('attr')} is {choice}" if meta.get("attr") != "owner" else f"{choice.title()} owns {subj}",
                       state="VERIFIED", confidence=0.85, status="approved")
            meta.update(resolved=choice, note=f"Reviewer resolved the conflict and kept {choice}. The disagreeing sources stay attached as evidence.")
            cx.execute("INSERT OR REPLACE INTO resolutions(case_id,key,choice,actor,at) VALUES(?,?,?,?,?)", (cid, r["key"], choice, actor, time.time()))
        elif action == "undo":
            prev = cx.execute("SELECT * FROM claim_versions WHERE case_id=? AND num=? AND version=? ORDER BY id DESC LIMIT 1",
                              (cid, num, r["version"] - 1)).fetchone()
            if not prev:
                raise BadInput("nothing to undo")
            new.update(text=prev["text"], state=prev["state"], status=prev["status"])
        ver = r["version"] + 1
        cx.execute("UPDATE claims SET text=?,state=?,status=?,confidence=?,meta=?,version=?,updated=? WHERE id=?",
                   (new["text"], new["state"], new["status"], new["confidence"], json.dumps(meta), ver, time.time(), r["id"]))
        r2 = dict(r, **new, version=ver)
        _snapshot(cx, r2, actor, label)
    audit.log(cid, actor, f"{label} C{num}", f"C{num}", f"{new['state']}|{new['status']}|{new['text']}"[:300])
    return get_claim(cid, num)


def bulk_approve(cid, actor="reviewer"):
    ids = [c["id"] for c in all_claims(cid) if c["state"] == "VERIFIED" and c["status"] in ("pending", "drifted")]
    for n in ids:
        review(cid, n, "approve", actor)
    return {"approved": ids}


def history(cid, num):
    _row(cid, num)
    return db.q("SELECT version,text,state,status,actor,action,at FROM claim_versions WHERE case_id=? AND num=? ORDER BY id", (cid, num))


def testimony(cid, num, author, answer, choice=None):
    r = _row(cid, num)
    answer = (answer or "").strip()
    if not answer:
        raise BadInput("answer required")
    if r["state"] not in ("MISSING", "CONFLICT", "TESTIMONY"):
        raise BadInput("testimony is only for missing or conflicting items")
    meta = json.loads(r["meta"] or "{}")
    if choice is not None and choice not in (meta.get("variants") or []):
        raise BadInput("choice must be one of the conflicting values")
    db.run("INSERT INTO testimony(case_id,key,author,answer,choice,at) VALUES(?,?,?,?,?,?)", (cid, r["key"], author.lower(), answer[:600], choice, time.time()))
    if r["state"] == "CONFLICT":
        meta["testimony"] = meta.get("testimony", []) + [{"author": author.lower(), "answer": answer[:600], "choice": choice}]
        db.run("UPDATE claims SET meta=? WHERE id=?", (json.dumps(meta), r["id"]))
        audit.log(cid, author.lower(), f"Leaver testimony on conflict C{num}", f"C{num}", answer[:200])
        return get_claim(cid, num)
    base = r["text"].split("  >>  ")[0]
    meta["note"] = "Testimony is the leaver's own statement. It is not independently verified."
    with db.tx() as cx:
        _snapshot(cx, r, "system", "baseline") if not cx.execute("SELECT 1 FROM claim_versions WHERE case_id=? AND num=? LIMIT 1", (cid, num)).fetchone() else None
        cx.execute("UPDATE claims SET text=?,state='TESTIMONY',confidence=0.6,meta=?,version=version+1,updated=? WHERE id=?",
                   (f"{base}  >>  {author.title()} says: {answer[:600]}", json.dumps(meta), time.time(), r["id"]))
        _snapshot(cx, dict(db.one("SELECT * FROM claims WHERE id=?", (r["id"],))), author.lower(), "testimony")
    audit.log(cid, author.lower(), f"Leaver testimony recorded for C{num}", f"C{num}", answer[:200])
    return get_claim(cid, num)


def interview(cid):
    """Targeted questions only: conflicts and missing items, ranked by urgency. ~10 minute interview."""
    case = get_case(cid)
    qs = []
    for c in all_claims(cid):
        if c["status"] == "rejected" or c["state"] not in ("MISSING", "CONFLICT", "TESTIMONY") or c["was"] not in ("MISSING", "CONFLICT"):
            continue
        dl = [d["iso"] for d in c["deadlines"] if case["last_day"] and days_between(d["iso"], case["last_day"]) >= 0]
        soon = min((days_between(d, case["last_day"]) for d in dl), default=None)
        score = (2 if c["was"] == "CONFLICT" else 1) + (1.5 if soon is not None and soon <= 60 else 0) + (0.5 if c["type"] in ("owner", "risk") else 0)
        if c["was"] == "CONFLICT":
            prompt = (f"Which {c['attr'] or 'value'} is current: {' or '.join(c['variants'] or [])}? What happened?" if c["attr"] != "owner"
                      else f"Who actually owns {c['subject']}: {' or '.join(v.title() for v in c['variants'] or [])}?")
            why = "Sources disagree. Your answer is recorded as testimony; the reviewer decides."
        elif c["type"] == "owner":
            prompt = f"Who should own {c['subject']}, and what do they need to know?"
            why = "The board has no owner for this."
        else:
            prompt = c["text"].split("  >>")[0]
            why = "Raised in the evidence but never answered."
        qs.append({"claim": c["id"], "ref": c["ref"], "kind": "conflict" if c["was"] == "CONFLICT" else "missing", "prompt": prompt,
                   "why": why, "options": c["variants"] if c["was"] == "CONFLICT" else None, "priority": score,
                   "answered": c["state"] == "TESTIMONY" or bool(c["testimony"]), "deadline": soon,
                   "evidence": [{"source": e["source"], "line": e["line"], "quote": e["quote"]} for e in c["evidence"][:3]]})
    qs.sort(key=lambda q: (-q["priority"], q["claim"]))
    return {"leaver": case["leaver"], "questions": qs, "estimate_minutes": max(2, round(len(qs) * 1.5)),
            "answered": sum(q["answered"] for q in qs)}


def readiness(cid):
    cl = all_claims(cid)
    ack = db.one("SELECT 1 x FROM acks WHERE case_id=?", (cid,))
    if not cl:
        return {"percent": 0, "parts": []}
    rv = sum(c["status"] in ("approved", "rejected") for c in cl) / len(cl)
    cf = [c for c in cl if c["was"] == "CONFLICT"]
    ms = [c for c in cl if c["was"] == "MISSING"]
    cr = (sum(c["state"] != "CONFLICT" for c in cf) / len(cf)) if cf else 1
    mr = (sum(c["state"] == "TESTIMONY" for c in ms) / len(ms)) if ms else 1
    parts = [{"label": "Claims reviewed", "weight": 40, "value": round(rv, 2)}, {"label": "Conflicts resolved", "weight": 25, "value": round(cr, 2)},
             {"label": "Gaps answered by the leaver", "weight": 20, "value": round(mr, 2)}, {"label": "Receipt acknowledged", "weight": 15, "value": 1 if ack else 0}]
    return {"percent": round(sum(p["weight"] * p["value"] for p in parts)), "parts": parts}


def counts(cid):
    cl = all_claims(cid)
    out = {"total": len(cl), "state": {}, "status": {}}
    for c in cl:
        out["state"][c["state"]] = out["state"].get(c["state"], 0) + 1
        out["status"][c["status"]] = out["status"].get(c["status"], 0) + 1
    return out
