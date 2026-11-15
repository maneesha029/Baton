import json

import pytest

from app.engine import llm
from app.engine.verify import verify_citations
from app.ingest import github, parsers
from app.security import mask


# ---------- parsers & masking ----------
def test_github_json_normalised_chronologically():
    items = [{"sha": "b", "commit": {"author": {"name": "Ravi X", "date": "2026-09-02T10:00:00Z"}, "message": "deploy: go\n\nbody"}, "author": {"login": "ravi"}},
             {"sha": "a", "commit": {"author": {"name": "Asha", "date": "2026-08-04T10:00:00Z"}, "message": "payments: use PostgreSQL"}, "author": {"login": "asha"}}]
    out = parsers.normalise("c.json", "git", json.dumps(items))
    assert out == ["[2026-08-04] @asha: payments: use PostgreSQL", "[2026-09-02] @ravi: deploy: go"]


def test_tasks_and_chat_epoch():
    t = parsers.normalise("t.json", "tasks", json.dumps({"tasks": [{"id": "T-1", "title": "X", "owner": None, "status": "todo", "updated": "2026-10-01"}]}))
    assert t == ["[2026-10-01] T-1 X | owner: unassigned | status: todo"]
    c = parsers.normalise("c.json", "chat", json.dumps([{"ts": "1790000000.000", "user": "Kavya", "text": "hi"}]))
    assert c[0].startswith("[2026-") and "@kavya: hi" in c[0]


def test_notes_dates_from_headings():
    out = parsers.normalise("n.md", "notes", "# T\n\n## 2026-08-06 Sprint\n- **Decision:** use X\n```\nskip me\n```\n")
    assert out == ["[2026-08-06] Decision: use X"]


def test_bad_json_and_empty_rejected():
    with pytest.raises(ValueError):
        parsers.normalise("x.json", "tasks", "{nope")
    with pytest.raises(ValueError):
        parsers.normalise("x.txt", "text", "\n\n")


def test_detect_kind():
    assert parsers.detect_kind("README.md", "") == "doc"
    assert parsers.detect_kind("a.json", json.dumps([{"sha": "1", "commit": {}}])) == "git"
    assert parsers.detect_kind("a.json", json.dumps([{"title": "t", "status": "x"}])) == "tasks"


def test_mask_secrets_and_phone():
    t, n = mask("key sk_live_9f8e7d6c5b4a and ghp_" + "a" * 24 + " password=hunter2 call 555-123-4567 on 2026-10-15")
    assert "sk_live" not in t and "hunter2" not in t and "555-123" not in t and "2026-10-15" in t and n == 4


# ---------- pipeline on the demo data ----------
def test_demo_reconstruction(client):
    cid = client.post("/api/cases", json={"demo": True}).json()["case"]["id"]
    r = client.post(f"/api/cases/{cid}/reconstruct").json()
    assert [s["name"] for s in r["stages"]][:3] == ["Ingest", "Extract", "Verify citations"]
    cl = client.get(f"/api/cases/{cid}/claims").json()["claims"]
    by = {c["text"]: c for c in cl}
    conflicts = {c["text"] for c in cl if c["state"] == "CONFLICT"}
    assert conflicts == {"Database: sources disagree (PostgreSQL vs MongoDB)", "Hosting: sources disagree (Render vs Heroku)",
                         "Ownership of Deploy scripts is disputed (Ravi vs Asha)"}
    assert by["No owner assigned: Deploy runbook"]["state"] == "MISSING"
    assert by["Payments webhook retry depends on vendor sandbox"]["state"] == "VERIFIED"   # task board + commit
    assert by["Asha owns vendor relationship"]["state"] == "INFERRED"                      # single source: never VERIFIED
    assert all(c["evidence"] for c in cl)
    # every citation resolves to the exact stored line
    for c in cl:
        for e in c["evidence"]:
            src = client.get(f"/api/cases/{cid}/sources/{e['sid']}").json()["content"]
            assert src[e["line"]] == e["quote"]


def test_secret_masked_before_storage(client):
    cid = client.post("/api/cases", json={"demo": True}).json()["case"]["id"]
    s = client.get(f"/api/cases/{cid}/sources/S4").json()
    assert "sk_live" not in s["text"] and "[SECRET REDACTED]" in s["text"] and s["redactions"] == 1


def test_hosting_retired_value_not_chosen(client):
    cid = client.post("/api/cases", json={"demo": True}).json()["case"]["id"]
    client.post(f"/api/cases/{cid}/reconstruct")
    c = [c for c in client.get(f"/api/cases/{cid}/claims").json()["claims"] if c["attr"] == "Hosting"][0]
    assert set(c["variants"]) == {"Render", "Heroku"} and c["hint"]["newest"] == "Render"
    assert "2026-11-30" in [d["iso"] for d in c["deadlines"]]


def test_verifier_rejects_unsupported_citations():
    cands = [{"key": "k1", "text": "x", "ev": [{"sid": "S1", "line": 0, "quote": "stale", "req": ["mongodb"]}]},
             {"key": "k2", "text": "y", "ev": [{"sid": "S1", "line": 5, "quote": "", "req": []}]},
             {"key": "k3", "text": "z", "ev": [{"sid": "S1", "line": 0, "quote": "", "req": ["postgresql"]}]}]
    kept, rej = verify_citations(cands, {"S1": ["[2026-01-01] Database is PostgreSQL"]})
    assert [c["key"] for c in kept] == ["k3"] and {r["key"] for r in rej} == {"k1", "k2"}


# ---------- optional LLM: proposals are citation-checked, answers are validated ----------
class FakeClient:
    def __init__(self, text):
        self.messages = self
        self.text = text

    def create(self, **kw):
        class B:  # noqa
            type = "text"
        b = B()
        b.text = self.text
        return type("R", (), {"content": [b]})()


def test_llm_extraction_is_citation_checked(client, monkeypatch):
    monkeypatch.setenv("BATON_LLM", "on")
    cid = client.post("/api/cases", json={"demo": True}).json()["case"]["id"]
    good = {"type": "risk", "text": "Invoice export is still in progress", "cite": "S3:4"}
    bad = {"type": "risk", "text": "The payment gateway will certainly collapse", "cite": "S3:4"}
    llm.set_client(FakeClient(json.dumps([good, bad])))
    r = client.post(f"/api/cases/{cid}/reconstruct").json()
    assert any("does not support" in x["reason"] for x in r["rejected"]) and any("collapse" in x["text"] for x in r["rejected"])
    cl = client.get(f"/api/cases/{cid}/claims").json()["claims"]
    llm_claim = [c for c in cl if c["text"] == "Invoice export is still in progress"][0]
    assert llm_claim["state"] == "INFERRED"          # the model can never assign VERIFIED
    assert not any("collapse" in c["text"] for c in cl)


def test_llm_failure_never_breaks_reconstruction(client, monkeypatch):
    monkeypatch.setenv("BATON_LLM", "on")
    class Boom:
        messages = None
    b = Boom()
    b.messages = b
    b.create = lambda **k: (_ for _ in ()).throw(RuntimeError("down"))
    llm.set_client(b)
    cid = client.post("/api/cases", json={"demo": True}).json()["case"]["id"]
    assert client.post(f"/api/cases/{cid}/reconstruct").status_code == 200


# ---------- GitHub connector ----------
def test_github_connector_mocked():
    import httpx

    def handler(req):
        if "/commits" in req.url.path:
            return httpx.Response(200, json=[{"sha": "1", "commit": {"author": {"name": "A", "date": "2026-01-02T00:00:00Z"}, "message": "m"}, "author": {"login": "a"}}])
        return httpx.Response(200, json=[{"number": 3, "title": "T", "state": "open", "user": {"login": "b"}, "updated_at": "2026-01-03T00:00:00Z"}])
    text, info = github.fetch("https://github.com/o/r", transport=httpx.MockTransport(handler))
    assert info == {"repo": "o/r", "items": 2}
    assert len(parsers.normalise("r.json", "git", text)) == 2
    with pytest.raises(github.GitHubError) as e:
        github.fetch("o/r", transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    assert e.value.status == 404
    with pytest.raises(github.GitHubError):
        github.parse_repo("not a repo")
