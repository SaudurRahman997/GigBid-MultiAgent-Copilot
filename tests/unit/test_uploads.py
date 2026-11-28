"""Portfolio uploads: validation, per-user isolation, search and claim support, through the API,
the in-process layer and the real Portfolio MCP server over HTTP."""

from __future__ import annotations

import base64

import pytest

from agent.mcp_client import GigBidMCPClient
from evals.inprocess_mcp import FakeMCP
from rag import uploads
from rag.retriever import retriever_for
from tests.unit.test_api import signup, world  # noqa: F401
from tests.unit.test_mcp_http import TOKEN, connections, stack  # noqa: F401

pytestmark = pytest.mark.anyio
ALICE, BOB = "u_aaaaaaaaaaaa", "u_bbbbbbbbbbbb"
CASE = (
    b"# Zyxqor telemetry anomaly detector\n\nI built a zyxqor telemetry anomaly detector in "
    b"Python for a satellite operator and cut false alarms."
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def upload_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGBID_UPLOAD_DIR", str(tmp_path / "uploads"))
    return tmp_path / "uploads"


def ids(retriever) -> list[str]:
    return [h.doc.id for h in retriever.search("zyxqor telemetry anomaly detector", 3)]


def test_upload_is_searchable_only_by_its_owner_and_delete_removes_it():
    before = ids(retriever_for("ai_ml", ALICE))
    saved = uploads.save_upload("ai_ml", ALICE, "satellite.md", CASE)
    assert saved.id.startswith("ai_ml:upload:") and saved.type == "case_study"
    assert ids(retriever_for("ai_ml", ALICE))[0] == saved.id
    assert saved.id not in ids(retriever_for("ai_ml", BOB))
    assert saved.id not in ids(retriever_for("ai_ml", None))
    assert uploads.delete_upload("ai_ml", BOB, saved.id) is False
    assert uploads.delete_upload("ai_ml", ALICE, saved.id) is True
    assert ids(retriever_for("ai_ml", ALICE)) == before


def test_same_content_twice_is_stored_once():
    a = uploads.save_upload("ai_ml", ALICE, "one.md", CASE)
    b = uploads.save_upload("ai_ml", ALICE, "two.md", CASE)
    assert a == b and len(uploads.list_uploads("ai_ml", ALICE)) == 1


@pytest.mark.parametrize(
    ("name", "data", "message"),
    [
        ("run.exe", CASE, "unsupported file type"),
        ("big.md", b"x" * (uploads.MAX_BYTES + 1), "larger than"),
        ("tiny.md", b"hi", "too little"),
        ("binary.md", b"\xff\xfe" * 100, "not UTF-8"),
        ("broken.pdf", CASE, "PDF"),
    ],
)
def test_bad_files_are_rejected(name, data, message):
    with pytest.raises(uploads.UploadError, match=message):
        uploads.save_upload("ai_ml", ALICE, name, data)


def test_names_and_users_cannot_escape_the_upload_folder(upload_dir):
    uploads.save_upload("ai_ml", ALICE, "..\\..\\../evil.md", CASE)
    [path] = list(upload_dir.rglob("*.md"))
    assert path.parent == upload_dir / ALICE / "ai_ml" and path.name.endswith("__evil.md")
    with pytest.raises(uploads.UploadError):
        uploads.save_upload("ai_ml", "../other", "a.md", CASE)
    assert uploads.list_uploads("ai_ml", "../other") == []


async def test_in_process_layer_serves_uploads_per_user():
    saved = uploads.save_upload("ai_ml", ALICE, "satellite.md", CASE)
    layer = FakeMCP("ai_ml")
    args = {"requirement": "zyxqor telemetry anomaly detector", "k": 3}
    mine = await layer.for_tenant(ALICE).call("writer", "search_evidence", args)
    theirs = await layer.for_tenant(BOB).call("writer", "search_evidence", args)
    assert mine["items"][0]["id"] == saved.id
    assert saved.id not in [i["id"] for i in theirs["items"]]


async def test_portfolio_server_over_http_scopes_uploads_by_tenant(stack):  # noqa: F811
    saved = uploads.save_upload("ai_ml", ALICE, "satellite.md", CASE)
    args = {"requirement": "zyxqor telemetry anomaly detector", "k": 3}
    found = {}
    for tenant in (ALICE, BOB, None):
        client = GigBidMCPClient(TOKEN, connections=connections(stack.urls)).for_tenant(tenant)
        out = await client.call("writer", "search_evidence", args)
        found[tenant] = [i["id"] for i in out["items"]]
    assert found[ALICE][0] == saved.id
    assert saved.id not in found[BOB] and saved.id not in found[None]
    alice = GigBidMCPClient(TOKEN, connections=connections(stack.urls)).for_tenant(ALICE)
    case = await alice.call("writer", "get_case_study", {"id": saved.id})
    assert "satellite operator" in case["text"]


def test_upload_api_requires_sign_in_and_isolates_users(world):  # noqa: F811
    client = world.client
    body = {"filename": "satellite.md", "content_base64": base64.b64encode(CASE).decode()}
    assert client.post("/portfolio/uploads", json=body).status_code == 401
    alice = signup(client, "alice@example.com")
    client.cookies.clear()
    bob = signup(client, "bob@example.com")
    client.cookies.clear()
    made = client.post("/portfolio/uploads", json=body, headers=alice)
    assert made.status_code == 201, made.text
    upload_id = made.json()["id"]
    assert [u["id"] for u in client.get("/portfolio/uploads", headers=alice).json()] == [upload_id]
    assert client.get("/portfolio/uploads", headers=bob).json() == []
    assert client.delete(f"/portfolio/uploads/{upload_id}", headers=bob).status_code == 404
    bad = {"filename": "x.exe", "content_base64": body["content_base64"]}
    assert client.post("/portfolio/uploads", json=bad, headers=alice).status_code == 422
    assert client.delete(f"/portfolio/uploads/{upload_id}", headers=alice).status_code == 204
