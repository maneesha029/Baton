"""Cases and sources: creation, demo seeding, ingestion with masking, ACL-aware source viewing, deletion."""
import json
import re
import secrets
import time
from pathlib import Path

from .. import db
from ..ingest import parsers
from ..security import LEVELS, can_see, mask
from . import audit

DEMO = Path(__file__).resolve().parent.parent / "demo"
MAX_SOURCE_BYTES = 400_000


class NotFound(Exception):
    pass


class Forbidden(Exception):
    pass


class BadInput(Exception):
    pass


def create_case(name="Untitled case", leaver="", last_day="", demo=False):
    db.purge_old(24)
    cid = "KP-" + secrets.token_hex(3).upper() if demo else "BT-" + secrets.token_hex(3).upper()
    now = time.time()
    db.run("INSERT INTO cases(id,name,leaver,last_day,created,touched,demo) VALUES(?,?,?,?,?,?,?)",
           (cid, name, leaver.lower(), last_day, now, now, int(demo)))
    audit.log(cid, "system", "Case opened", "", name)
    if demo:
        m = json.loads((DEMO / "manifest.json").read_text())
        db.run("UPDATE cases SET name=?,leaver=?,last_day=? WHERE id=?", (m["name"], m["leaver"], m["last_day"], cid))
        for s in m["sources"]:
            add_source(cid, s["name"], (DEMO / s["file"]).read_text(), s["kind"], s["acl"], s["origin"], actor="system")
    return get_case(cid)


def get_case(cid):
    c = db.one("SELECT * FROM cases WHERE id=?", (cid,))
    if not c:
        raise NotFound(f"case {cid} not found")
    db.run("UPDATE cases SET touched=? WHERE id=?", (time.time(), cid))
    return c


def update_case(cid, **kw):
    get_case(cid)
    for k in ("name", "leaver", "last_day"):
        if k in kw and kw[k] is not None:
            v = kw[k].strip().lower() if k == "leaver" else kw[k].strip()
            if k == "last_day" and v and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                raise BadInput("last_day must be YYYY-MM-DD")
            db.run(f"UPDATE cases SET {k}=? WHERE id=?", (v, cid))
    return get_case(cid)


def add_source(cid, name, text, kind=None, acl="team", origin="upload", actor="reviewer"):
    get_case(cid)
    if acl not in LEVELS:
        raise BadInput("acl must be public, team or confidential")
    if len(text.encode()) > MAX_SOURCE_BYTES:
        raise BadInput("source too large (max 400 KB)")
    name = (name or "notes/untitled.txt").strip()[:120]
    kind = kind or parsers.detect_kind(name, text)
    try:
        lines = parsers.normalise(name, kind, text)
    except ValueError as e:
        raise BadInput(str(e))
    masked, n = mask("\n".join(lines))
    nxt = (db.one("SELECT COALESCE(MAX(CAST(SUBSTR(id,2) AS INTEGER)),0) m FROM sources WHERE case_id=?", (cid,)) or {"m": 0})["m"] + 1
    sid = f"S{nxt}"
    db.run("INSERT INTO sources(id,case_id,name,kind,acl,text,redactions,included,origin,added) VALUES(?,?,?,?,?,?,?,1,?,?)",
           (sid, cid, name, kind, acl, masked, n, origin, time.time()))
    audit.log(cid, actor, "Source added", sid, f"{name} [{acl}] {n} secrets masked")
    return source_meta(db.one("SELECT * FROM sources WHERE case_id=? AND id=?", (cid, sid)))


def source_meta(s):
    return {"id": s["id"], "name": s["name"], "kind": s["kind"], "acl": s["acl"], "included": bool(s["included"]),
            "lines": s["text"].count("\n") + 1, "redactions": s["redactions"], "origin": s["origin"]}


def list_sources(cid, role="manager"):
    """Metadata only (never text). Sources above the viewer's clearance are listed as restricted placeholders."""
    get_case(cid)
    out = []
    for s in db.q("SELECT * FROM sources WHERE case_id=? ORDER BY CAST(SUBSTR(id,2) AS INTEGER)", (cid,)):
        out.append(source_meta(s) if can_see(LEVELS[s["acl"]], role) else {"id": s["id"], "restricted": True})
    return out


def source_view(cid, sid, role):
    s = db.one("SELECT * FROM sources WHERE case_id=? AND id=?", (cid, sid))
    if not s:
        raise NotFound("source not found")
    if not can_see(LEVELS[s["acl"]], role):
        raise Forbidden("this source needs higher clearance")
    return {**source_meta(s), "text": s["text"], "content": s["text"].split("\n")}


def patch_source(cid, sid, included=None, acl=None, actor="reviewer"):
    s = db.one("SELECT * FROM sources WHERE case_id=? AND id=?", (cid, sid))
    if not s:
        raise NotFound("source not found")
    if acl is not None:
        if acl not in LEVELS:
            raise BadInput("bad acl")
        db.run("UPDATE sources SET acl=? WHERE case_id=? AND id=?", (acl, cid, sid))
        audit.log(cid, actor, "Source clearance changed", sid, acl)
    if included is not None:
        db.run("UPDATE sources SET included=? WHERE case_id=? AND id=?", (int(included), cid, sid))
        audit.log(cid, actor, "Source included" if included else "Source excluded", sid)
    return source_meta(db.one("SELECT * FROM sources WHERE case_id=? AND id=?", (cid, sid)))


def delete_source(cid, sid, actor="reviewer"):
    s = db.one("SELECT * FROM sources WHERE case_id=? AND id=?", (cid, sid))
    if not s:
        raise NotFound("source not found")
    db.run("DELETE FROM sources WHERE case_id=? AND id=?", (cid, sid))
    audit.log(cid, actor, "Source deleted", sid, s["name"])
    return {"deleted": sid}
