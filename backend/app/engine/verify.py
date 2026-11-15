"""Verifier: citation re-reading, trust-state assignment, explainable confidence, conflict hints.

Trust rules (stricter than "one current source", on purpose; see README):
  CONFLICT  sources name different values / owners (never averaged, never silently resolved)
  MISSING   an open question or an item with no owner/evidence (becomes a question for the leaver)
  VERIFIED  an authoritative record (task board) OR >= 2 independent sources agree
  INFERRED  everything else, always labelled, always needs a reviewer
A claim with no resolvable citation can never be VERIFIED.
"""
from ..security import LEVELS
from .dates import days_between

BASE = {"VERIFIED": 0.78, "INFERRED": 0.45, "CONFLICT": 0.25, "MISSING": 0.10, "TESTIMONY": 0.60}


def verify_citations(cands, lines_by_sid):
    """Re-read each cited span from the stored text. Returns (kept, rejected)."""
    kept, rejected = [], []
    for c in cands:
        good = []
        for e in c["ev"]:
            lines = lines_by_sid.get(e["sid"], [])
            if not (0 <= e["line"] < len(lines)):
                continue
            e["quote"] = lines[e["line"]]  # the stored text is the source of truth
            low = e["quote"].lower()
            if "toks" in e:  # LLM-proposed: fraction of distinctive claim words found in the cited line
                ok = sum(t in low for t in e["toks"]) / max(1, len(e["toks"])) >= e.get("min_overlap", 0.6) and bool(e["toks"])
            else:
                ok = all(r in low for r in e.get("req", []))
            if ok:
                good.append(e)
        if good:
            c["ev"] = good
            kept.append(c)
        else:
            rejected.append({"key": c["key"], "text": c["text"], "reason": "cited text does not support the claim"})
    return kept, rejected


def assign(c, src_meta, last_day):
    """Set state, confidence, factors, level, date on a candidate (in place)."""
    sids = {e["sid"] for e in c["ev"]}
    dates = sorted(e["date"] for e in c["ev"] if e["date"])
    c["date"] = dates[-1] if dates else ""
    c["level"] = max(LEVELS[src_meta[s]["acl"]] for s in sids)
    state = c["state"]
    if not state:
        state = "VERIFIED" if (c["auth"] or len(sids) >= 2) else "INFERRED"
    if not c["ev"]:
        state = "MISSING" if state == "MISSING" else "INFERRED"
    c["state"] = state
    f = [(f"Base for {state}", BASE[state])]
    if state in ("VERIFIED", "INFERRED"):
        if len(sids) > 1:
            f.append((f"{len(sids)} independent sources agree", min(0.15, 0.06 * (len(sids) - 1))))
        if c["auth"]:
            f.append(("authoritative record (task board)", 0.07))
        if c["date"] and last_day and 0 <= days_between(last_day, c["date"]) <= 45:
            f.append(("recent evidence (within 45 days of the last day)", 0.04))
        if not c["date"]:
            f.append(("only undated evidence", -0.10))
    c["factors"] = [{"label": a, "delta": round(b, 2)} for a, b in f]
    c["confidence"] = round(max(0.05, min(0.97, sum(b for _, b in f))), 2)
    if state == "CONFLICT":
        c["meta"]["hint"] = _hint(c)
    return c


def _hint(c):
    """Recency hint for conflicts. Advisory only: undated sources cannot be ordered."""
    by = {}
    for e in c["ev"]:
        v = e.get("variant")
        if v:
            by.setdefault(v, []).append(e["date"])
    newest = {v: (max(d for d in ds if d) if any(ds) else "") for v, ds in by.items()}
    dated = sorted(((d, v) for v, d in newest.items() if d), reverse=True)
    undated = [v for v, d in newest.items() if not d]
    out = {"newest": None, "undated": undated, "newest_by_value": newest}
    if dated and (len(dated) == 1 or dated[0][0] > dated[1][0]):
        out["newest"] = dated[0][1]
    return out
