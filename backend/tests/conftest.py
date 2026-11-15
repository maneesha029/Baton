import os
import sys
from pathlib import Path

import pytest

os.environ["BATON_LLM"] = "off"
os.environ.pop("ANTHROPIC_API_KEY", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.engine import llm  # noqa: E402

SECRETS = ["priya@vendorco.com", "4,200", "sk_live", "9f8e7d6c5b4a", "renegotiate vendor contract", "drop the vendor", "vendor relationship"]


@pytest.fixture()
def client():
    db.init(":memory:")
    llm.set_client(None)
    from app.main import app
    return TestClient(app)


@pytest.fixture()
def demo(client):
    """A reconstructed demo case, everything approvable approved, conflicts resolved."""
    cid = client.post("/api/cases", json={"demo": True}).json()["case"]["id"]
    client.post(f"/api/cases/{cid}/reconstruct")
    for c in client.get(f"/api/cases/{cid}/claims").json()["claims"]:
        if c["state"] == "CONFLICT":
            client.post(f"/api/cases/{cid}/claims/{c['id']}/review", json={"action": "resolve", "choice": c["variants"][0]})
        else:
            client.post(f"/api/cases/{cid}/claims/{c['id']}/review", json={"action": "approve"})
    return cid
