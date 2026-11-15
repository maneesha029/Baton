"""Baton API. Every read endpoint takes a `role` and filters BEFORE serialising: restricted text never leaves the database layer."""
import json
import os
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db
from .engine import llm, pipeline
from .ingest import github
from .security import ROLES
from .services import analysis, audit, cases, handover, ledger, qa

app = FastAPI(title="Baton", version="3.0", description="Evidence-ledger knowledge handover")
FRONT = Path(os.environ.get("BATON_FRONT", Path(__file__).resolve().parents[2] / "frontend"))


@app.exception_handler(cases.NotFound)
async def _nf(_, e):
    return JSONResponse({"error": str(e)}, 404)


@app.exception_handler(cases.Forbidden)
async def _fb(_, e):
    return JSONResponse({"error": str(e), "restricted": True}, 403)


@app.exception_handler(cases.BadInput)
async def _bi(_, e):
    return JSONResponse({"error": str(e)}, 400)


@app.exception_handler(github.GitHubError)
async def _gh(_, e):
    return JSONResponse({"error": str(e)}, e.status)


@app.exception_handler(ValueError)
async def _ve(_, e):
    return JSONResponse({"error": str(e)}, 400)


def R(role: str) -> str:
    if role not in ROLES:
        raise ValueError(f"role must be one of {', '.join(ROLES)}")
    return role


class CaseIn(BaseModel):
    demo: bool = False
    name: str = "Untitled case"
    leaver: str = ""
    last_day: str = ""


class CasePatch(BaseModel):
    name: str | None = None
    leaver: str | None = None
    last_day: str | None = None


class SourceIn(BaseModel):
    name: str = Field(max_length=120)
    text: str
    kind: str | None = None
    acl: str = "team"
    origin: str = "upload"


class SourcePatch(BaseModel):
    included: bool | None = None
    acl: str | None = None


class GithubIn(BaseModel):
    repo: str
    token: str | None = None
    acl: str = "team"


class ReviewIn(BaseModel):
    action: str
    actor: str = "reviewer"
    text: str | None = None
    choice: str | None = None


class TestimonyIn(BaseModel):
    author: str
    answer: str
    choice: str | None = None


class AskIn(BaseModel):
    question: str
    role: str = "developer"


class AckIn(BaseModel):
    name: str
    role: str = "developer"


@app.get("/api/health")
def health():
    return {"status": "ok", "llm": llm.enabled(), "model": llm.MODEL if llm.enabled() else None, "version": "3.0"}


@app.post("/api/cases")
def new_case(b: CaseIn):
    c = cases.create_case(b.name, b.leaver, b.last_day, demo=b.demo)
    return case_state(c["id"])


def case_state(cid):
    c = cases.get_case(cid)
    return {"case": c, "sources": cases.list_sources(cid), "counts": ledger.counts(cid), "readiness": ledger.readiness(cid)}


@app.get("/api/cases/{cid}")
def get_case(cid: str):
    return case_state(cid)


@app.patch("/api/cases/{cid}")
def patch_case(cid: str, b: CasePatch):
    cases.update_case(cid, **b.model_dump())
    return case_state(cid)


@app.get("/api/cases/{cid}/sources")
def sources(cid: str, role: str = "manager"):
    return cases.list_sources(cid, R(role))


@app.post("/api/cases/{cid}/sources")
def add_source(cid: str, b: SourceIn):
    return cases.add_source(cid, b.name, b.text, b.kind, b.acl, b.origin)


@app.post("/api/cases/{cid}/sources/github")
def add_github(cid: str, b: GithubIn):
    text, info = github.fetch(b.repo, b.token or os.environ.get("GITHUB_TOKEN"))
    s = cases.add_source(cid, f"repo/{info['repo']}.json", text, "git", b.acl, f"GitHub API ({info['items']} items)")
    return {"source": s, "info": info}


@app.get("/api/cases/{cid}/sources/{sid}")
def source_view(cid: str, sid: str, role: str = "manager"):
    return cases.source_view(cid, sid, R(role))


@app.patch("/api/cases/{cid}/sources/{sid}")
def patch_source(cid: str, sid: str, b: SourcePatch):
    return cases.patch_source(cid, sid, b.included, b.acl)


@app.delete("/api/cases/{cid}/sources/{sid}")
def del_source(cid: str, sid: str):
    return cases.delete_source(cid, sid)


@app.post("/api/cases/{cid}/reconstruct")
def reconstruct(cid: str):
    cases.get_case(cid)
    if not db.q("SELECT 1 FROM sources WHERE case_id=? AND included=1 LIMIT 1", (cid,)):
        raise cases.BadInput("include at least one source")
    out = pipeline.reconstruct(cid)
    return {**out, **case_state(cid)}


@app.get("/api/cases/{cid}/claims")
def claims(cid: str, role: str = "manager", approved_only: bool = False):
    vis, hidden = ledger.view(cid, R(role), approved_only)
    return {"claims": vis, "hidden": hidden, "counts": ledger.counts(cid), "readiness": ledger.readiness(cid)}


@app.post("/api/cases/{cid}/claims/bulk-approve")
def bulk(cid: str):
    return ledger.bulk_approve(cid)


@app.get("/api/cases/{cid}/claims/{num}")
def claim(cid: str, num: int, role: str = "manager"):
    return ledger.get_claim(cid, num, R(role))


@app.get("/api/cases/{cid}/claims/{num}/history")
def claim_history(cid: str, num: int):
    return ledger.history(cid, num)


@app.post("/api/cases/{cid}/claims/{num}/review")
def review(cid: str, num: int, b: ReviewIn):
    return ledger.review(cid, num, b.action, b.actor, b.text, b.choice)


@app.post("/api/cases/{cid}/claims/{num}/testimony")
def testimony(cid: str, num: int, b: TestimonyIn):
    return ledger.testimony(cid, num, b.author, b.answer, b.choice)


@app.get("/api/cases/{cid}/interview")
def interview(cid: str):
    return ledger.interview(cid)


@app.get("/api/cases/{cid}/handover")
def get_handover(cid: str, role: str = "developer"):
    return handover.build(cid, R(role))


@app.get("/api/cases/{cid}/handover/export")
def export(cid: str, role: str = "developer", fmt: str = "md"):
    R(role)
    if fmt == "json":
        return Response(json.dumps(handover.bundle(cid, role), indent=1), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="baton-{cid}-{role}.json"'})
    return PlainTextResponse(handover.markdown(handover.build(cid, role)), media_type="text/markdown",
                             headers={"Content-Disposition": f'attachment; filename="baton-{cid}-{role}.md"'})


@app.post("/api/cases/{cid}/ack")
def ack(cid: str, b: AckIn):
    return handover.acknowledge(cid, b.name, R(b.role))


@app.get("/api/cases/{cid}/graph")
def graph(cid: str, role: str = "manager", approved_only: bool = False):
    return analysis.graph(cid, R(role), approved_only)


@app.get("/api/cases/{cid}/analysis/simulate")
def simulate(cid: str, person: str, role: str = "manager"):
    return analysis.simulate(cid, R(role), person)


@app.get("/api/cases/{cid}/analysis/bus-factor")
def bus(cid: str, role: str = "manager"):
    vis, _ = ledger.view(cid, R(role))
    return analysis.bus_factor(vis)


@app.get("/api/cases/{cid}/analysis/deadlines")
def deadlines(cid: str, role: str = "manager"):
    vis, _ = ledger.view(cid, R(role))
    return analysis.deadlines(cid, vis)


@app.post("/api/cases/{cid}/ask")
def ask(cid: str, b: AskIn):
    cases.get_case(cid)
    return qa.ask(cid, R(b.role), b.question)


@app.get("/api/cases/{cid}/audit")
def get_audit(cid: str):
    cases.get_case(cid)
    return {"entries": audit.entries(cid), "verify": audit.verify(cid)}


@app.get("/api/cases/{cid}/audit/verify")
def audit_verify(cid: str):
    cases.get_case(cid)
    return audit.verify(cid)


@app.post("/api/cases/{cid}/audit/tamper-test")
def audit_tamper(cid: str):
    cases.get_case(cid)
    return audit.tamper_test(cid)


if FRONT.exists():
    app.mount("/", StaticFiles(directory=str(FRONT), html=True), name="ui")
