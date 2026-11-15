import json

from conftest import SECRETS

from app import db
from app.engine import llm

ROLE_ENDPOINTS = ["/claims", "/claims?approved_only=true", "/handover", "/handover/export?fmt=md", "/handover/export?fmt=json", "/graph",
                  "/graph?approved_only=true", "/analysis/bus-factor", "/analysis/deadlines", "/analysis/simulate?person=asha", "/sources"]
QUESTIONS = ["Who is the vendor contact?", "How much does the vendor renewal cost?", "What is the API key?", "Who handles the vendor relationship?",
             "Will we drop the vendor if the renewal exceeds budget?", "renegotiate vendor contract"]


# ---------- permissions: the headline guarantee ----------
def test_no_restricted_text_leaks_to_guest_or_developer(client, demo):
    for role in ("guest", "developer"):
        blobs = [client.get(f"/api/cases/{demo}{p}{'&' if '?' in p else '?'}role={role}").text for p in ROLE_ENDPOINTS]
        blobs += [client.post(f"/api/cases/{demo}/ask", json={"question": q, "role": role}).text for q in QUESTIONS]
        blobs.append(client.get(f"/api/cases/{demo}/sources/S4?role={role}").text)
        text = "\n".join(blobs).lower()
        for s in SECRETS:
            assert s.lower() not in text, f"{role} response leaked {s!r}"
    mgr = client.get(f"/api/cases/{demo}/handover?role=manager").text
    assert "priya@vendorco.com" in mgr and "sk_live" not in mgr   # manager sees it; the secret is masked for everyone


def test_guest_gets_counts_not_content(client, demo):
    h = client.get(f"/api/cases/{demo}/handover?role=guest").json()
    assert h["hidden"] > 0 and h["shown"] >= 1
    g = client.get(f"/api/cases/{demo}/graph?role=guest").json()
    restricted = [n for n in g["nodes"] if n.get("restricted")]
    assert restricted and all(set(n) <= {"id", "num", "kind", "restricted"} for n in restricted)
    assert client.get(f"/api/cases/{demo}/claims/12?role=developer").status_code == 404   # level-2 claim
    assert client.get(f"/api/cases/{demo}/sources/S4?role=developer").status_code == 403


def test_unreviewed_claims_never_in_handover(client):
    cid = client.post("/api/cases", json={"demo": True}).json()["case"]["id"]
    client.post(f"/api/cases/{cid}/reconstruct")
    h = client.get(f"/api/cases/{cid}/handover?role=manager").json()
    assert h["shown"] == 0 and h["pending"] > 0


# ---------- review, versions, drift, persistence ----------
def test_conflict_cannot_be_approved_silently(client):
    cid = client.post("/api/cases", json={"demo": True}).json()["case"]["id"]
    client.post(f"/api/cases/{cid}/reconstruct")
    c = [c for c in client.get(f"/api/cases/{cid}/claims").json()["claims"] if c["state"] == "CONFLICT"][0]
    assert client.post(f"/api/cases/{cid}/claims/{c['id']}/review", json={"action": "approve"}).status_code == 400
    assert client.post(f"/api/cases/{cid}/claims/{c['id']}/review", json={"action": "resolve", "choice": "Oracle"}).status_code == 400
    r = client.post(f"/api/cases/{cid}/claims/{c['id']}/review", json={"action": "resolve", "choice": c["variants"][0]}).json()
    assert r["state"] == "VERIFIED" and r["status"] == "approved" and len(r["evidence"]) >= 2   # disagreeing evidence stays attached


def test_edit_undo_versions(client):
    cid = client.post("/api/cases", json={"demo": True}).json()["case"]["id"]
    client.post(f"/api/cases/{cid}/reconstruct")
    u = f"/api/cases/{cid}/claims/5/review"
    orig = client.get(f"/api/cases/{cid}/claims/5").json()["text"]
    assert client.post(u, json={"action": "edit", "text": "Asha owns payments (corrected)"}).json()["status"] == "approved"
    r = client.post(u, json={"action": "undo"}).json()
    assert r["text"] == orig and r["status"] == "pending"
    h = client.get(f"/api/cases/{cid}/claims/5/history").json()
    assert [x["action"] for x in h] == ["baseline", "Edited and approved", "Undid last action"]


def test_decisions_survive_rerun_and_drift_is_flagged(client):
    cid = client.post("/api/cases", json={"demo": True}).json()["case"]["id"]
    client.post(f"/api/cases/{cid}/reconstruct")
    client.post(f"/api/cases/{cid}/claims/8/review", json={"action": "approve"})     # Meera owns Admin dashboard (S3 line 1)
    client.post(f"/api/cases/{cid}/claims/19/review", json={"action": "approve"})    # Mobile app depends on payments API v2 (S2)
    src = client.get(f"/api/cases/{cid}/sources/S3").json()["text"]
    client.delete(f"/api/cases/{cid}/sources/S3")                                      # source removed
    client.post(f"/api/cases/{cid}/reconstruct")
    cl = {c["id"]: c for c in client.get(f"/api/cases/{cid}/claims").json()["claims"]}
    assert 8 not in cl                                                               # evidence vanished, claim goes with it
    assert cl[19]["status"] == "approved"                                            # untouched claim keeps its decision
    client.post(f"/api/cases/{cid}/sources", json={"name": "board/tasks.json", "text": src, "kind": "text", "acl": "team"})
    # approve the (resolved) Database decision, then new evidence arrives -> the approved claim must become DRIFTED
    db_claim = [c for c in client.get(f"/api/cases/{cid}/claims").json()["claims"] if c["attr"] == "Database"][0]
    client.post(f"/api/cases/{cid}/claims/{db_claim['id']}/review", json={"action": "resolve", "choice": "MongoDB"})
    client.post(f"/api/cases/{cid}/reconstruct")
    assert client.get(f"/api/cases/{cid}/claims/{db_claim['id']}").json()["status"] == "approved"
    client.post(f"/api/cases/{cid}/sources", json={"name": "chat/infra.txt", "text": "[2026-10-12] @meera: database is MongoDB now", "kind": "text", "acl": "team"})
    client.post(f"/api/cases/{cid}/reconstruct")
    d = client.get(f"/api/cases/{cid}/claims/{db_claim['id']}").json()
    assert d["status"] == "drifted" and "Re-review" in d["note"] and d["text"] == "Database is MongoDB"


def test_testimony_is_attributed_and_never_verified(client):
    cid = client.post("/api/cases", json={"demo": True}).json()["case"]["id"]
    client.post(f"/api/cases/{cid}/reconstruct")
    r = client.post(f"/api/cases/{cid}/claims/22/testimony", json={"author": "Asha", "answer": "Meera renews it"}).json()
    assert r["state"] == "TESTIMONY" and "Asha says: Meera renews it" in r["text"] and r["confidence"] < 0.7
    client.post(f"/api/cases/{cid}/reconstruct")                                       # survives a re-run
    assert client.get(f"/api/cases/{cid}/claims/22").json()["state"] == "TESTIMONY"
    assert client.post(f"/api/cases/{cid}/claims/5/testimony", json={"author": "a", "answer": "x"}).status_code == 400  # only gaps/conflicts


def test_interview_targets_only_conflicts_and_gaps(client):
    cid = client.post("/api/cases", json={"demo": True}).json()["case"]["id"]
    client.post(f"/api/cases/{cid}/reconstruct")
    iv = client.get(f"/api/cases/{cid}/interview").json()
    assert {q["kind"] for q in iv["questions"]} == {"conflict", "missing"} and len(iv["questions"]) == 9
    assert iv["questions"][0]["priority"] >= iv["questions"][-1]["priority"]


def test_handover_plan_and_ack(client, demo):
    h = client.get(f"/api/cases/{demo}/handover?role=manager").json()
    assert h["plan"] and h["radar"] and any(d["unowned"] for d in h["radar"])
    assert any(i["leaver_only"] for g in h["plan"] for i in g["items"])
    assert client.post(f"/api/cases/{demo}/ack", json={"name": "Meera", "role": "manager"}).json()["name"] == "Meera"
    assert client.get(f"/api/cases/{demo}/handover?role=manager").json()["readiness"]["percent"] == 80   # 40+25+0 (gaps unanswered)+15
    md = client.get(f"/api/cases/{demo}/handover/export?role=manager&fmt=md").text
    assert md.startswith("# Handover") and "Start here" in md


# ---------- audit chain ----------
def test_audit_chain_and_tamper(client, demo):
    v = client.get(f"/api/cases/{demo}/audit/verify").json()
    assert v["ok"] and v["length"] > 10
    t = client.post(f"/api/cases/{demo}/audit/tamper-test").json()
    assert t["detected"] and client.get(f"/api/cases/{demo}/audit/verify").json()["ok"]   # original untouched
    db.run("UPDATE audit SET action='rewritten' WHERE case_id=? AND seq=3", (demo,))        # real tampering in the DB
    bad = client.get(f"/api/cases/{demo}/audit/verify").json()
    assert not bad["ok"] and bad["broken_at"] == 3


# ---------- evidence-only Q&A ----------
def test_qa_cites_or_refuses(client, demo):
    r = client.post(f"/api/cases/{demo}/ask", json={"question": "Who renews the vendor sandbox contract?", "role": "manager"}).json()
    assert not r["refused"] and r["claims"] and all(c["evidence"] for c in r["claims"])
    nope = client.post(f"/api/cases/{demo}/ask", json={"question": "What is the weather in Pune tomorrow?", "role": "manager"}).json()
    assert nope["refused"] and not nope["claims"]
    g = client.post(f"/api/cases/{demo}/ask", json={"question": "How much does the vendor renewal cost?", "role": "guest"}).json()
    assert g["refused"] and g["hidden_matches"] >= 1 and "4,200" not in json.dumps(g)


def test_qa_llm_answer_validated(client, demo, monkeypatch):
    monkeypatch.setenv("BATON_LLM", "on")
    class C:
        def __init__(self, t):
            self.messages = self
            self.t = t

        def create(self, **k):
            b = type("B", (), {"type": "text", "text": self.t})()
            return type("R", (), {"content": [b]})()
    q = {"question": "Who renews the vendor sandbox contract?", "role": "manager"}
    llm.set_client(C(json.dumps({"answer": "Meera, per testimony.", "cited": [999]})))     # cites a claim it was never given
    assert client.post(f"/api/cases/{demo}/ask", json=q).json()["mode"] == "extractive"
    ids = [c["id"] for c in client.post(f"/api/cases/{demo}/ask", json=q).json()["claims"]]
    llm.set_client(C(json.dumps({"answer": "Meera, per testimony.", "cited": ids[:1]})))
    r = client.post(f"/api/cases/{demo}/ask", json=q).json()
    assert r["mode"] == "llm" and [c["id"] for c in r["claims"]] == ids[:1]


# ---------- analysis ----------
def test_bus_factor_and_simulation(client, demo):
    bf = client.get(f"/api/cases/{demo}/analysis/bus-factor?role=manager").json()
    assert bf[0]["name"] == "asha" and bf[0]["solo_count"] >= 2
    s = client.get(f"/api/cases/{demo}/analysis/simulate?person=asha&role=manager").json()
    assert s["found"] and s["orphaned"] and s["survive"] >= 1
    assert client.get(f"/api/cases/{demo}/analysis/simulate?person=ghost&role=manager").json()["found"] is False
    dev = client.get(f"/api/cases/{demo}/analysis/simulate?person=asha&role=developer").json()
    assert all("vendor relationship" not in o["text"] for o in dev["orphaned"])            # restricted claim not counted for developer


# ---------- sources & validation ----------
def test_add_custom_source_and_validation(client):
    cid = client.post("/api/cases", json={"name": "Club", "leaver": "Sam", "last_day": "2026-12-01"}).json()["case"]["id"]
    r = client.post(f"/api/cases/{cid}/sources", json={"name": "notes.md", "text": "## 2026-11-01 Meeting\n- Sam owns treasury\n- Risk: grant expires Dec 15\n", "acl": "team"})
    assert r.status_code == 200 and r.json()["kind"] == "notes"
    assert client.post(f"/api/cases/{cid}/sources", json={"name": "x.txt", "text": "  \n", "acl": "team"}).status_code == 400
    assert client.post(f"/api/cases/{cid}/sources", json={"name": "x.txt", "text": "a", "acl": "secret"}).status_code == 400
    assert client.post(f"/api/cases/{cid}/reconstruct").json()["claims"] == 2
    assert client.get(f"/api/cases/{cid}/claims?role=root").status_code == 400
    assert client.get("/api/cases/NOPE").status_code == 404
    empty = client.post("/api/cases", json={}).json()["case"]["id"]
    assert client.post(f"/api/cases/{empty}/reconstruct").status_code == 400
