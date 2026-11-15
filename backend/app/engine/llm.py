"""Optional Claude integration. Off unless ANTHROPIC_API_KEY is set (or a client is injected in tests).

Design rules that keep the model honest:
  * The model only PROPOSES claims, each citing exactly one source line. It never assigns trust states.
  * Every proposal goes through the same mechanical citation check as rule-extracted claims; unsupported ones are rejected.
  * Secrets are already masked at ingest, so they never reach the model.
  * For Q&A the model sees ONLY approved claims the viewer's role may see, and its answer is validated: every claim id it
    cites must be one it was given, otherwise Baton falls back to the extractive answer.
"""
import json
import os
import re

MODEL = os.environ.get("BATON_MODEL", "claude-sonnet-5-5")
_client = None
_STOP = set("this that with from have were been they them will would could should about which their there what when where into than then also only over such very more most some each other these those".split())


def set_client(c):
    global _client
    _client = c


def enabled() -> bool:
    if os.environ.get("BATON_LLM", "on").lower() == "off":
        return False
    return _client is not None or bool(os.environ.get("ANTHROPIC_API_KEY"))


def _get():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()
    return _client


def _call(system: str, user: str, max_tokens=3000) -> str:
    r = _get().messages.create(model=MODEL, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": user}])
    return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")


def _json(text: str):
    m = re.search(r"(\[.*\]|\{.*\})", text, re.S)
    if not m:
        raise ValueError("no JSON in model output")
    return json.loads(m.group(1))


def _toks(s):
    return sorted({w for w in re.findall(r"[a-z0-9]{4,}", s.lower()) if w not in _STOP})


EXTRACT_SYS = ("You extract atomic handover claims from project evidence. Output ONLY a JSON array. Each item: "
               '{"type": one of decision|owner|risk|dependency|question|contact|fact, "text": short factual claim, "cite": "S1:3"}. '
               "Each claim must be supported by exactly ONE cited line (id format SID:LINE). Do not infer beyond the line. "
               "Do not output trust states. Skip anything you cannot cite.")


def extract_claims(chunks, limit=400):
    """Return (candidate list, note). Candidates use the verifier's per-citation `toks` overlap check."""
    by = {(c["sid"], c["line"]): c for c in chunks}
    listing = "\n".join(f"{c['sid']}:{c['line']} | {c['raw']}" for c in chunks[:limit])
    try:
        items = _json(_call(EXTRACT_SYS, listing))
    except Exception as e:  # model/network failure must never break reconstruction
        return [], f"LLM extraction skipped ({e.__class__.__name__}); rule engine only"
    out = []
    for it in items if isinstance(items, list) else []:
        try:
            sid, ln = it["cite"].split(":")
            ch = by[(sid, int(ln))]
            typ, text = it["type"], str(it["text"]).strip()
        except (KeyError, ValueError, TypeError):
            continue
        if typ not in ("decision", "owner", "risk", "dependency", "question", "contact", "fact") or not text:
            continue
        e = {"sid": ch["sid"], "line": ch["line"], "date": ch["date"], "author": ch["author"], "quote": ch["raw"],
             "req": [], "toks": _toks(text), "min_overlap": 0.6}
        out.append({"key": f"llm:{typ}:{' '.join(_toks(text))}", "type": typ, "text": text, "ev": [e], "auth": False,
                    "state": "MISSING" if typ == "question" else None, "meta": {"source": "llm"}})
    return out, f"rule engine + {MODEL} ({len(out)} proposals, citation-checked)"


ANSWER_SYS = ("Answer the question using ONLY the numbered claims provided. Output ONLY JSON: "
              '{"answer": string, "cited": [claim numbers used]}. If the claims do not answer the question, output '
              '{"answer": "", "cited": []}. Never use outside knowledge.')


def answer(question: str, claims: list[dict]):
    """claims: [{num,text,state}]. Returns (answer, cited_nums) or (None, []) when the model cannot be trusted."""
    if not enabled() or not claims:
        return None, []
    listing = "\n".join(f"[{c['num']}] ({c['state']}) {c['text']}" for c in claims)
    try:
        j = _json(_call(ANSWER_SYS, f"Claims:\n{listing}\n\nQuestion: {question}", 600))
        ok = {c["num"] for c in claims}
        cited = [n for n in j.get("cited", []) if n in ok]
        if not j.get("answer") or not cited or len(cited) != len(j.get("cited", [])):
            return None, []
        return str(j["answer"]), cited
    except Exception:
        return None, []
