"""Tamper-evident audit log: per-case SHA-256 hash chain, verified server-side."""
import hashlib
import time

from .. import db


def _h(prev, seq, at, actor, action, ref, snap):
    return hashlib.sha256("|".join([prev, str(seq), f"{at:.3f}", actor, action, ref, snap]).encode()).hexdigest()


def log(case_id, actor, action, ref="", snap=""):
    with db.tx() as cx:
        last = cx.execute("SELECT seq,hash FROM audit WHERE case_id=? ORDER BY seq DESC LIMIT 1", (case_id,)).fetchone()
        seq = (last["seq"] + 1) if last else 1
        prev = last["hash"] if last else "genesis"
        at = round(time.time(), 3)
        h = _h(prev, seq, at, actor, action, ref, snap)
        cx.execute("INSERT INTO audit(case_id,seq,at,actor,action,ref,snap,prev,hash) VALUES(?,?,?,?,?,?,?,?,?)",
                   (case_id, seq, at, actor, action, ref, snap, prev, h))
    return {"seq": seq, "hash": h}


def entries(case_id):
    return db.q("SELECT seq,at,actor,action,ref,snap,prev,hash FROM audit WHERE case_id=? ORDER BY seq", (case_id,))


def verify_rows(rows):
    """Return 0 if the chain is intact, else the first sequence number that fails."""
    prev = "genesis"
    for r in rows:
        if r["prev"] != prev or _h(prev, r["seq"], r["at"], r["actor"], r["action"], r["ref"], r["snap"]) != r["hash"]:
            return r["seq"]
        prev = r["hash"]
    return 0


def verify(case_id):
    rows = entries(case_id)
    bad = verify_rows(rows)
    return {"ok": bad == 0, "broken_at": bad, "length": len(rows), "head": rows[-1]["hash"] if rows else "genesis"}


def tamper_test(case_id):
    """Forge a middle entry in a COPY and show the verifier catches it. Nothing is written."""
    rows = [dict(r) for r in entries(case_id)]
    if len(rows) < 2:
        return {"ok": False, "reason": "need at least 2 entries"}
    k = len(rows) // 2
    rows[k]["action"] += " (forged)"
    bad = verify_rows(rows)
    return {"ok": True, "forged_seq": rows[k]["seq"], "detected_at": bad, "detected": bad == rows[k]["seq"]}
