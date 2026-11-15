"""Reconstruct pipeline: sources -> chunks -> candidates -> verified claims -> persisted ledger.

Re-running is safe and idempotent: reviewer decisions, edits, conflict resolutions and leaver testimony survive,
and an approved claim whose evidence changed is flagged DRIFTED so it must be re-reviewed.
"""
import hashlib
import json
import time

from .. import db
from ..ingest.parsers import parse_line
from . import llm
from .extract import extract
from .verify import assign, verify_citations
from ..services import audit

TYPE_ORDER = {"decision": 0, "owner": 1, "risk": 2, "dependency": 3, "question": 4, "fact": 5, "contact": 6}


def _chunks(sources):
    out, lines_by = [], {}
    for s in sources:
        lines = s["text"].split("\n")
        lines_by[s["id"]] = lines
        for i, raw in enumerate(lines):
            p = parse_line(raw)
            if p["body"]:
                out.append({"sid": s["id"], "line": i, "raw": raw, "kind": s["kind"], "acl": s["acl"], **p})
    return out, lines_by


def _fp(ev):
    return hashlib.sha1(json.dumps(sorted((e["sid"], e["line"], e["quote"]) for e in ev)).encode()).hexdigest()[:12]


def reconstruct(case_id: str, actor="system"):
    t0 = time.perf_counter()
    stages = []

    def stage(name, n, t, note=""):
        stages.append({"name": name, "count": n, "ms": round((time.perf_counter() - t) * 1000, 1), "note": note})

    case = db.one("SELECT * FROM cases WHERE id=?", (case_id,))
    sources = db.q("SELECT * FROM sources WHERE case_id=? AND included=1 ORDER BY id", (case_id,))
    meta = {s["id"]: s for s in sources}

    t = time.perf_counter()
    chunks, lines_by = _chunks(sources)
    stage("Ingest", len(chunks), t, f"{len(sources)} sources, {sum(s['redactions'] for s in sources)} secrets masked")

    t = time.perf_counter()
    cands = extract(chunks)
    note = "rule engine"
    if llm.enabled():
        extra, note = llm.extract_claims(chunks)
        cands = _merge(cands, extra)
    stage("Extract", len(cands), t, note)

    t = time.perf_counter()
    cands, rejected = verify_citations(cands, lines_by)
    stage("Verify citations", len(cands), t, f"{len(rejected)} unsupported candidates rejected")

    t = time.perf_counter()
    for c in cands:
        assign(c, meta, case["last_day"])
    stage("Trust states", len(cands), t, ", ".join(f"{n} {s}" for s, n in _count(cands)))

    t = time.perf_counter()
    persist(case_id, cands, actor)
    n_conf = sum(c["state"] == "CONFLICT" for c in cands)
    stage("Contradictions", n_conf, t, "conflicting sources kept side by side")

    db.run("UPDATE cases SET reconstructed=1, touched=? WHERE id=?", (time.time(), case_id))
    audit.log(case_id, actor, "Reconstructed case", "", f"{len(cands)} claims from {len(sources)} sources")
    return {"stages": stages, "claims": len(cands), "rejected": rejected, "total_ms": round((time.perf_counter() - t0) * 1000, 1)}


def _count(cands):
    from collections import Counter
    return Counter(c["state"] for c in cands).most_common()


def _merge(a, b):
    by = {c["key"]: c for c in a}
    for c in b:
        if c["key"] in by:
            seen = {(e["sid"], e["line"]) for e in by[c["key"]]["ev"]}
            by[c["key"]]["ev"] += [e for e in c["ev"] if (e["sid"], e["line"]) not in seen]
        else:
            by[c["key"]] = c
    return list(by.values())


def persist(case_id, cands, actor):
    now = time.time()
    existing = {r["key"]: r for r in db.q("SELECT * FROM claims WHERE case_id=?", (case_id,))}
    tes = {}
    for r in db.q("SELECT * FROM testimony WHERE case_id=? ORDER BY id", (case_id,)):
        tes.setdefault(r["key"], []).append(r)
    resol = {r["key"]: r["choice"] for r in db.q("SELECT * FROM resolutions WHERE case_id=?", (case_id,))}
    nxt = (db.one("SELECT COALESCE(MAX(num),0) m FROM claims WHERE case_id=?", (case_id,)) or {"m": 0})["m"]
    cands = sorted(cands, key=lambda c: (TYPE_ORDER.get(c["type"], 9), c["ev"][0]["sid"], c["ev"][0]["line"]))
    keep = set()
    with db.tx() as cx:
        for c in cands:
            keep.add(c["key"])
            old = existing.get(c["key"])
            fp = _fp(c["ev"])
            text, state, conf, status, version, drift = c["text"], c["state"], c["confidence"], "pending", 1, False
            m = dict(c["meta"], factors=c["factors"], was=c["state"])
            if old:
                om = json.loads(old["meta"] or "{}")
                status, version = old["status"], old["version"]
                if om.get("edited"):
                    text, m["edited"], m["note"] = old["text"], True, om.get("note")
                drift = status == "approved" and old["fp"] != fp
            if c["key"] in resol and state == "CONFLICT":
                v = resol[c["key"]]
                text = f"{c['meta'].get('attr', 'Value')} is {v}" if c["meta"].get("attr") != "owner" else f"{v.title()} owns {c['meta'].get('subject', '')}"
                state, conf = "VERIFIED", 0.85
                m["note"] = f"Reviewer resolved the conflict and kept {v}. The disagreeing sources stay attached as evidence."
                m["resolved"] = v
            if state == "MISSING" and c["key"] in tes:
                a = tes[c["key"]][-1]
                text, state, conf = f"{text}  >>  {a['author'].title()} says: {a['answer']}", "TESTIMONY", 0.60
                m["note"] = "Testimony is the leaver's own statement. It is not independently verified."
            if drift:  # applied last so no later note can hide it
                status, m["note"] = "drifted", "Evidence changed after approval. Re-review required."
            if state == "CONFLICT" and c["key"] in tes:
                m["testimony"] = [{"author": r["author"], "answer": r["answer"], "choice": r["choice"]} for r in tes[c["key"]]]
            row = (json.dumps(c["ev"]), json.dumps(m), fp, c["date"], c["level"], c["type"], text, state, conf, status, version, now)
            if old:
                cx.execute("UPDATE claims SET evidence=?,meta=?,fp=?,date=?,level=?,type=?,text=?,state=?,confidence=?,status=?,version=?,updated=? WHERE id=?", row + (old["id"],))
            else:
                nxt += 1
                cx.execute("INSERT INTO claims(evidence,meta,fp,date,level,type,text,state,confidence,status,version,updated,case_id,num,key,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           row + (case_id, nxt, c["key"], now))
        for k, r in existing.items():
            if k not in keep:  # evidence vanished (e.g. source deleted): the claim goes with it
                cx.execute("DELETE FROM claims WHERE id=?", (r["id"],))
