"""Evidence-only successor Q&A.

Pipeline: ACL filter FIRST -> retrieve over approved, visible claims only -> answer with citations, or refuse.
Hidden/pending matches are reported as counts, never as text. With an LLM configured, the model sees only the
retrieved visible claims and its citations are validated; otherwise a deterministic extractive answer is used.
"""
import math
import re

from ..engine import llm
from . import ledger

STOP = set("a an the of to in on at is are was were be by for with and or as it its this that these those do does did can could "
           "should would will what who whom whose when where why how which tell me about please i you we our us has have had not no".split())
INTENT = {"who": {"owner", "contact"}, "owns": {"owner"}, "contact": {"contact"}, "risk": {"risk"}, "why": {"decision"}, "decide": {"decision"},
          "depend": {"dependency"}, "blocked": {"dependency", "risk"}, "when": {"risk", "decision"}, "deadline": {"risk", "decision"}, "cost": {"fact"}}


def _stem(w):
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def toks(s):
    return [_stem(w) for w in re.findall(r"[a-z0-9]{2,}", s.lower()) if w not in STOP]


def _score(q, docs):
    N = len(docs) or 1
    df = {}
    for d in docs:
        for w in set(d):
            df[w] = df.get(w, 0) + 1
    avg = sum(len(d) for d in docs) / N or 1
    out = []
    for d in docs:
        s = 0.0
        for w in set(q):
            f = d.count(w)
            if f:
                idf = math.log(1 + (N - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * len(d) / avg))
        out.append(s)
    return out


def _match(question, claims):
    """Return claims with relevance score, only those sharing >= ceil(1/3) of the question's content words."""
    q = toks(question)
    if not q or not claims:
        return []
    docs = [toks(c["text"] + " " + c["type"]) for c in claims]
    sc = _score(q, docs)
    need = max(1, math.ceil(len(set(q)) / 3))
    want = set()
    for k, v in INTENT.items():
        if re.search(r"\b" + k, question.lower()):
            want |= v
    hits = []
    for c, d, s in zip(claims, docs, sc):
        if len(set(q) & set(d)) >= need:
            hits.append((s * (1.25 if c["type"] in want else 1.0), c))
    hits.sort(key=lambda x: -x[0])
    return hits


def ask(cid, role, question):
    question = (question or "").strip()
    if len(question) < 3:
        return {"refused": True, "answer": "", "reason": "Ask a question about the project.", "claims": [], "hidden_matches": 0, "pending_matches": 0}
    visible, hidden_n = ledger.view(cid, role, approved_only=True)   # permission gate: nothing else is ever searched for text
    every = ledger.all_claims(cid)
    vis_nums = {c["id"] for c in visible}
    # counts only: matches the viewer may NOT read, and matches still awaiting review
    hid = [c for c in every if c["status"] == "approved" and c["id"] not in vis_nums]
    pend = [c for c in every if c["status"] != "approved" and c["level"] <= ledger.clearance(role)]
    hidden_matches = len(_match(question, hid))
    pending_matches = len(_match(question, pend))
    hits = _match(question, visible)[:3]
    if not hits:
        why = f"Refused: no approved claim visible at {role} clearance supports an answer."
        if hidden_matches:
            why += " Matching evidence exists above your clearance and stays redacted."
        if pending_matches:
            why += f" {pending_matches} matching claim(s) are awaiting review and have not been shared."
        return {"refused": True, "answer": "", "reason": why, "claims": [], "hidden_matches": hidden_matches, "pending_matches": pending_matches, "mode": "refusal"}
    chosen = [c for _, c in hits]
    text, mode = None, "extractive"
    if llm.enabled():
        text, cited = llm.answer(question, [{"num": c["id"], "text": c["text"], "state": c["state"]} for c in chosen])
        if text:
            chosen, mode = [c for c in chosen if c["id"] in cited], "llm"
    if not text:
        text = " ".join(f"{c['text'].split('  >>')[0] if c['state'] != 'TESTIMONY' else c['text']} [{c['ref']}]" for c in chosen)
    caution = any(c["state"] not in ("VERIFIED",) for c in chosen)
    return {"refused": False, "answer": text, "mode": mode, "caution": "Includes items that are not fully verified (INFERRED or testimony). Check the citations." if caution else None,
            "claims": [{"ref": c["ref"], "id": c["id"], "state": c["state"], "text": c["text"], "evidence": c["evidence"]} for c in chosen],
            "hidden_matches": hidden_matches, "pending_matches": pending_matches, "reason": None}
