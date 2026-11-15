"""Deterministic, transparent claim extraction.

Input: chunks  {sid, line, date, author, body, raw, kind}
Output: candidate claims. Every citation carries `req`: substrings that MUST occur in the cited line. The verifier
re-reads the stored line and drops any citation (and any claim) the text does not support. The same contract is used
by the optional LLM extractor, which is why LLM output can be checked mechanically.
"""
import json
import re
from pathlib import Path

ONT = json.loads(Path(__file__).with_name("ontology.json").read_text())
Q_RE = re.compile(r"(\?|\bunsure\b|\bnot sure\b|\btbd\b|^who\b|\bunknown\b)", re.I)
TASK_RE = re.compile(r"^([A-Z]{1,5}-\d+)\s+(.+?)(?:\s*\|(.*))?$")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+\w")
FACT_RE = re.compile(r"((?:[A-Za-z]+\s+){0,2}costs?\s+[\d,.]+\s*(?:USD|INR|EUR|GBP|\$))", re.I)
DEP_RE = re.compile(r"\b(?:depends on|waiting on|blocked by|requires)\s+(.+?)(?:[)|,;.]|$)", re.I)
OWN_RES = [
    (re.compile(r"^(\w+) owns (.+?)\.?$", re.I), "who_first"),
    (re.compile(r"^(.+?) (?:is|are) owned by (\w+)", re.I), "who_last"),
    (re.compile(r"^(\w+) is responsible for (.+?)\.?$", re.I), "who_first"),
    (re.compile(r"^(?:i|we)\s+(?:handle|manage|run|own)\s+(?:the\s+)?([^;.,]+)", re.I), "author"),
]


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^\w ]+", " ", s.lower())).strip()


def subj_norm(s):
    s = re.sub(r"^(?:the|our|a)\s+", "", norm(s))
    return re.sub(r"\s+(?:module|service|component|project)$", "", s)


def attr_hit(body):
    low = body.lower()
    for attr, spec in ONT["attributes"].items():
        if not any(re.search(r"\b" + re.escape(n) + r"\b", low) for n in spec["nouns"]):
            continue
        vals = [v for v in spec["values"] if re.search(r"(?<!\w)" + re.escape(v.lower()) + r"(?!\w)", low)]
        retired = [v for v in vals if re.search(re.escape(v.lower()) + r"\W+(?:\w+\W+){0,5}?(?:shut\s?down|sunset|retire[d]?|deprecat\w*|decommission\w*|replaced)", low)]
        cur = [v for v in vals if v not in retired] or vals[:1]
        if cur:
            return attr, cur[0]
    return None


def extract(chunks):
    C, attrs, owners, commits = {}, {}, {}, []
    disp = {}

    def ev(ch, req, **extra):
        return {"sid": ch["sid"], "line": ch["line"], "date": ch["date"], "author": ch["author"], "quote": ch["raw"],
                "req": [r.lower() for r in req], **extra}

    def add(key, typ, text, e, auth=False, state=None, **meta):
        c = C.setdefault(key, {"key": key, "type": typ, "text": text, "ev": [], "auth": False, "state": None, "meta": {}})
        if auth and not c["auth"]:
            c["text"] = text  # prefer the wording of an authoritative record
        c["auth"] = c["auth"] or auth
        if state:
            c["state"] = state
        c["meta"].update(meta)
        if not any(x["sid"] == e["sid"] and x["line"] == e["line"] for x in c["ev"]):
            c["ev"].append(e)
        return c

    for ch in chunks:
        body, kind, scope = ch["body"], ch["kind"], ""
        if kind == "git":
            m = re.match(r"^([\w .\-/]{1,30}):\s+(.*)$", body)
            if m:
                scope, body = m.group(1).lower(), m.group(2)
            commits.append((ch["author"], body.lower(), scope, ch))
        t = TASK_RE.match(body) if kind == "tasks" else None
        if t:
            tid, title, rest = t.group(1), t.group(2).strip(), t.group(3) or ""
            fields = {k.strip().lower(): v.strip() for k, v in (p.split(":", 1) for p in rest.split("|") if ":" in p)}
            wait = re.search(r"waiting on ([\w .\-]+?)(?:\||$)", rest)
            sub = subj_norm(title)
            disp.setdefault(sub, title)
            ow = fields.get("owner", "")
            status = fields.get("status", "")
            if ow.lower() in ("", "unassigned", "none", "null", "nobody"):
                add("owner:" + sub, "owner", f"No owner assigned: {title}", ev(ch, [tid, "unassigned"]), state="MISSING", unassigned=True, subject=title)
            else:
                owners.setdefault(sub, {}).setdefault(ow.lower(), []).append(ev(ch, [tid, ow], variant=ow.lower(), status=status))
            if wait:
                x = wait.group(1).strip()
                add("dep:" + norm(x), "dependency", f"{title} depends on {x}", ev(ch, [tid, x]), auth=True)
            elif status.lower() == "blocked":
                add("risk:blocked " + sub, "risk", f"{title} is blocked", ev(ch, [tid, "blocked"]), auth=True)
            continue

        h = attr_hit(body)
        if h:
            a, v = h
            attrs.setdefault(a, {}).setdefault(v, []).append(ev(ch, [v], variant=v))
            continue
        if Q_RE.search(body):
            qt = f"{scope}: {body}" if scope else body
            add("q:" + norm(qt), "question", qt, ev(ch, [body[:18]]), state="MISSING")
            continue
        handled = False
        for rx, mode in OWN_RES:
            m = rx.match(body)
            if m:
                if mode == "author":
                    who, subj = ch["author"], m.group(1).strip()
                elif mode == "who_first":
                    who, subj = m.group(1), m.group(2).strip()
                else:
                    who, subj = m.group(2), m.group(1).strip()
                if who:
                    sub = subj_norm(subj)
                    disp.setdefault(sub, re.sub(r"^(?:the|our)\s+", "", subj, flags=re.I))
                    owners.setdefault(sub, {}).setdefault(who.lower(), []).append(ev(ch, [subj.split()[0]] + ([] if mode == "author" else [who]), variant=who.lower()))
                    handled = True
                break
        if handled:
            continue
        for e in EMAIL_RE.findall(body):
            add("contact:" + e.lower(), "contact", f"Contact: {e}", ev(ch, [e]))
        f = FACT_RE.search(body)
        if f:
            ft = f.group(1).strip()
            add("fact:" + norm(ft), "fact", ft[:1].upper() + ft[1:], ev(ch, [ft.split()[-1]]))
        d = DEP_RE.search(body)
        if d:
            x = d.group(1).strip()
            pre = re.sub(r"[\s(]+$", "", body[:d.start()])
            pre = re.sub(r"^(?:add|implement|build|wip)\s+", "", pre, flags=re.I)
            subj = pre if pre and len(pre.split()) <= 6 else "Work"
            add("dep:" + norm(x), "dependency", f"{subj[:1].upper() + subj[1:]} depends on {x}", ev(ch, [x]))
            continue
        low = body.lower()
        if any(re.search(r"\b" + w + r"\b", low) for w in ONT["decision_words"]):
            txt = re.sub(r"^(?:decision|decided)\s*:?\s*(?:to\s+)?", "", body, flags=re.I).strip() or body
            add("dec:" + norm(txt), "decision", txt[:1].upper() + txt[1:], ev(ch, [norm(txt).split()[0]]))
            continue
        if any(re.search(r"\b" + w + r"\b", low) for w in ONT["risk_words"]):
            txt = re.sub(r"^risk\s*:\s*", "", body, flags=re.I)
            add("risk:" + norm(txt), "risk", txt[:1].upper() + txt[1:], ev(ch, [norm(txt).split()[0]]))

    # ---- attribute choices: disagreement becomes a CONFLICT, never an average
    for a, vs in attrs.items():
        evs = [e for v in vs.values() for e in v]
        if len(vs) > 1:
            add("attr:" + a, "decision", f"{a}: sources disagree ({' vs '.join(vs)})", evs[0], state="CONFLICT", attr=a, variants=list(vs))
            C["attr:" + a]["ev"] = evs
        else:
            v = next(iter(vs))
            add("attr:" + a, "decision", f"{a} is {v}", evs[0], attr=a, variants=[v])
            C["attr:" + a]["ev"] = evs

    # ---- ownership: two named owners for one subject is a CONFLICT; commit history corroborates single owners
    for sub, who_map in owners.items():
        T = disp.get(sub, sub)
        for who, evs in who_map.items():
            hist = [c for a, b, sc, c in commits if a == who and (sub in b or sub in sc)]
            if len(hist) >= 2:
                for c in hist:
                    evs.append(ev(c, [who], variant=who, role="corroborates"))
        if len(who_map) > 1:
            names = [w.title() for w in who_map]
            T = T[:1].upper() + T[1:]
            C.pop("owner:" + sub, None)
            add("owner:" + sub, "owner", f"Ownership of {T} is disputed ({' vs '.join(names)})", next(iter(who_map.values()))[0], state="CONFLICT", attr="owner", subject=T, variants=list(who_map))
            C["owner:" + sub]["ev"] = [e for v in who_map.values() for e in v]
        else:
            who, evs = next(iter(who_map.items()))
            st = next((e.get("status") for e in evs if e.get("status")), "")
            old = C.pop("owner:" + sub, None)  # an 'unassigned' note is superseded by a named owner
            c = add("owner:" + sub, "owner", f"{who.title()} owns {T}" + (f" ({st})" if st else ""), evs[0], auth=any(e.get("status") for e in evs), subject=T, variants=[who], who=who)
            c["ev"] = evs
    return list(C.values())
