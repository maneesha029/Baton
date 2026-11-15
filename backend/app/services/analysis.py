"""Graph analysis (NetworkX): bus factor, departure simulation, dependency blast radius, deadline radar, 3D graph payload.

Every function takes the claims a role may see; restricted claims never enter the graph, so nothing here can leak them.
"""
import re

import networkx as nx

from ..engine.dates import days_between
from ..security import LEVELS
from . import ledger
from .cases import get_case

_STOP = set("this that with from have were been will would could should about which their there what when where into than then also only over such very more most some each other these those depends owns work".split())


def holders(c):
    h = {e["author"] for e in c["evidence"] if e.get("author")}
    if c["type"] == "owner" and c["state"] != "CONFLICT":
        h |= set(c.get("variants") or [])
    return h


def is_solo(c):
    return len(holders(c)) == 1 and len({e["sid"] for e in c["evidence"]}) == 1


def _toks(t):
    return {w for w in re.findall(r"[a-z0-9]{4,}", t.lower()) if w not in _STOP}


def dep_graph(claims):
    """Directed claim graph: an edge A->B when B's text builds on A (shared rare tokens, B is a dependency/risk/question)."""
    G = nx.DiGraph()
    toks = {c["id"]: _toks(c["text"].split("  >>")[0]) for c in claims}
    freq = {}
    for t in toks.values():
        for w in t:
            freq[w] = freq.get(w, 0) + 1
    G.add_nodes_from(toks)
    for a in claims:
        for b in claims:
            if a["id"] >= b["id"]:
                continue
            shared = {w for w in toks[a["id"]] & toks[b["id"]] if freq[w] <= 4}
            if len(shared) >= 2 and {a["type"], b["type"]} & {"dependency", "risk"}:
                src, dst = (a, b) if a["type"] != "dependency" else (b, a)
                G.add_edge(src["id"], dst["id"], shared=sorted(shared))
    return G


def people(claims):
    P = {}
    for c in claims:
        if c["status"] == "rejected":
            continue
        for w in holders(c):
            p = P.setdefault(w, {"name": w, "claims": 0, "solo": []})
            p["claims"] += 1
            if is_solo(c):
                p["solo"].append(c["id"])
    return P


def bus_factor(claims):
    P, D = people(claims), dep_graph(claims)
    B = nx.Graph()
    for c in claims:
        for w in holders(c):
            B.add_edge("P:" + w, c["id"])
    btw = nx.betweenness_centrality(B) if B.number_of_nodes() > 2 else {}
    out = []
    for w, p in P.items():
        reach = set()
        for n in p["solo"]:
            reach |= nx.descendants(D, n)
        out.append({"name": w, "claims": p["claims"], "solo": p["solo"], "solo_count": len(p["solo"]),
                    "ripple": sorted(reach - set(p["solo"])), "betweenness": round(btw.get("P:" + w, 0), 3)})
    out.sort(key=lambda x: (-x["solo_count"], -x["claims"]))
    return out


def simulate(cid, role, person):
    claims, _ = ledger.view(cid, role)
    claims = [c for c in claims if c["status"] != "rejected"]
    P = people(claims)
    person = person.lower()
    if person not in P:
        return {"person": person, "found": False, "orphaned": [], "survive": 0, "deadlines": [], "ripple": []}
    D = dep_graph(claims)
    held = [c for c in claims if person in holders(c)]
    orphaned = [c for c in held if is_solo(c)]
    ids = {c["id"] for c in orphaned}
    ripple = set()
    for n in ids:
        ripple |= nx.descendants(D, n)
    case = get_case(cid)
    dl = [{"claim": c["id"], "iso": d["iso"], "line": d["line"], "days_after": days_between(d["iso"], case["last_day"]) if case["last_day"] else None}
          for c in orphaned for d in c["deadlines"]]
    return {"person": person, "found": True, "holds": len(held), "survive": len(held) - len(orphaned),
            "orphaned": [{"id": c["id"], "ref": c["ref"], "text": c["text"], "state": c["state"]} for c in orphaned],
            "deadlines": sorted(dl, key=lambda d: d["iso"]), "ripple": sorted(ripple - ids)}


def unowned_for(c, claims):
    """Heuristic: open (MISSING) items sharing distinctive words with this claim."""
    a = _toks(c["text"])
    return [m["id"] for m in claims if m["state"] == "MISSING" and m["id"] != c["id"] and m["status"] != "rejected" and a & _toks(m["text"])]


def deadlines(cid, claims):
    case = get_case(cid)
    last = case["last_day"]
    out = []
    for c in claims:
        for d in c["deadlines"]:
            out.append({"iso": d["iso"], "line": d["line"], "claim": c["id"], "ref": c["ref"], "state": c["state"],
                        "days_after": days_between(d["iso"], last) if last else None, "unowned": unowned_for(c, claims)})
    out.sort(key=lambda d: d["iso"])
    return out


def graph(cid, role, approved_only=False):
    """3D map payload. Claims/sources above the viewer's clearance become opaque placeholders (id only)."""
    from .. import db
    claims_all = ledger.all_claims(cid)
    clr = LEVELS_BY_ROLE[role]
    srcs = db.q("SELECT id,name,acl FROM sources WHERE case_id=? AND included=1", (cid,))
    nodes, edges = [], []
    vis = []
    for s in srcs:
        if LEVELS[s["acl"]] <= clr:
            nodes.append({"id": s["id"], "kind": "src", "name": s["name"], "acl": s["acl"]})
        else:
            nodes.append({"id": s["id"], "kind": "src", "restricted": True})
    for c in claims_all:
        if approved_only and c["status"] != "approved":
            continue
        if c["level"] > clr:
            nodes.append({"id": c["ref"], "num": c["id"], "kind": "claim", "restricted": True})
        else:
            vis.append(c)
            nodes.append({"id": c["ref"], "num": c["id"], "kind": "claim", "type": c["type"], "state": c["state"], "status": c["status"],
                          "confidence": c["confidence"], "date": c["date"], "label": c["text"].split("  >>")[0][:90], "solo": is_solo(c)})
        for sid in {e["sid"] for e in c["evidence"]}:
            edges.append({"a": c["ref"], "b": sid, "kind": "cites", "conflict": c["state"] == "CONFLICT" and c["level"] <= clr})
    bf = {b["name"]: b for b in bus_factor(vis)}
    for w, b in bf.items():
        nodes.append({"id": "P:" + w, "kind": "person", "name": w, "count": b["claims"], "solo": b["solo_count"]})
    for c in vis:
        if c["status"] == "rejected":
            continue
        for w in holders(c):
            edges.append({"a": c["ref"], "b": "P:" + w, "kind": "holds"})
    D = dep_graph(vis)
    for a, b, d in D.edges(data=True):
        edges.append({"a": f"C{a}", "b": f"C{b}", "kind": "dep", "shared": d["shared"]})
    return {"nodes": nodes, "edges": edges, "dates": sorted({c["date"] for c in vis if c["date"]}),
            "bus_factor": [b for b in bf.values() if b["solo_count"] >= 1]}


from ..security import ROLES as LEVELS_BY_ROLE  # noqa: E402
