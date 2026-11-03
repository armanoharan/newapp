import json

import pytest

KEY = "test-key-123"
MCP_HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json",
               "host": "localhost:8000"}


@pytest.fixture
def secured(client, monkeypatch):
    """The app with API_KEY set."""
    monkeypatch.setenv("API_KEY", KEY)
    return client


def rpc(method, params=None, id_=1):
    return {"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}}


def test_requires_key(secured):
    assert secured.get("/companies").status_code == 401
    assert secured.get("/companies", headers={"X-API-Key": "wrong"}).status_code == 401
    assert secured.get("/companies", headers={"X-API-Key": KEY}).status_code == 200
    assert secured.get("/companies", headers={"Authorization": f"Bearer {KEY}"}).status_code == 200
    assert secured.get(f"/companies?api_key={KEY}").status_code == 200


def test_public_paths_open(secured):
    assert secured.get("/health").status_code == 200
    assert secured.get("/docs").status_code == 200


def test_mcp_requires_key(secured):
    assert secured.post("/mcp", json=rpc("tools/list"), headers=MCP_HEADERS).status_code == 401


def test_mcp_over_http(secured):
    h = {**MCP_HEADERS, "X-API-Key": KEY}
    init = secured.post("/mcp", headers=h, json=rpc("initialize", {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"}}))
    assert init.status_code == 200, init.text

    tools = secured.post("/mcp", headers=h, json=rpc("tools/list", id_=2)).json()
    assert len(tools["result"]["tools"]) == 18

    res = secured.post("/mcp", headers=h, json=rpc("tools/call", {
        "name": "update_deal", "arguments": {"deal_id": 11, "stage": "closed_won"}}, id_=3)).json()
    deal = json.loads(res["result"]["content"][0]["text"])
    assert deal["stage"] == "closed_won" and deal["probability"] == 100
    # The change is visible through the REST API too (same database).
    assert secured.get("/deals/11", headers={"X-API-Key": KEY}).json()["stage"] == "closed_won"

    err = secured.post("/mcp", headers=h, json=rpc("tools/call", {
        "name": "get_company", "arguments": {"company_id": 999}}, id_=4)).json()
    assert err["result"]["isError"] is True
    assert "Company 999 not found" in err["result"]["content"][0]["text"]


def test_mcp_rejects_unknown_host(secured):
    h = {**MCP_HEADERS, "X-API-Key": KEY, "host": "evil.example.com"}
    assert secured.post("/mcp", headers=h, json=rpc("tools/list")).status_code == 421
