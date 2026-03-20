# tests/integration/test_http_transport_integration.py
"""Integration tests for the CGC HTTP transport layer (T073).

These tests start the HTTPTransport backed by a mocked MCPServer on a random
ephemeral port and exercise the full request/response cycle via
``starlette.testclient.TestClient`` (synchronous ASGI test client — no live
TCP socket needed).

A separate async section uses ``pytest-asyncio`` + ``httpx.AsyncClient``
mounted against the ASGI app for async call paths.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
import httpx
from starlette.testclient import TestClient

from codegraphcontext.http_transport import HTTPTransport


# ---------------------------------------------------------------------------
# Shared mock factory
# ---------------------------------------------------------------------------

def _make_server(
    *,
    connected: bool = True,
    tools: dict | None = None,
) -> MagicMock:
    """Return a fully-wired MCPServer mock."""
    server = MagicMock()
    server.db_manager = MagicMock()
    server.db_manager.is_connected.return_value = connected
    server.tools = tools if tools is not None else {
        "find_code": {"name": "find_code", "description": "Find code"},
        "execute_cypher_query": {"name": "execute_cypher_query", "description": "Run Cypher"},
    }

    async def _handle_request(
        method: str,
        params: dict[str, Any],
        request_id: Any,
    ) -> dict[str, Any] | None:
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2025-03-26",
                    "serverInfo": {"name": "CodeGraphContext", "version": "0.1.0"},
                    "capabilities": {"tools": {"listTools": True}},
                },
            }
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"tools": list(server.tools.values())},
            }
        if method == "tools/call":
            tool_name = params.get("name")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({"called": tool_name})}]
                },
            }
        if method == "notifications/initialized":
            return None
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    server.handle_request = AsyncMock(side_effect=_handle_request)
    return server


# ---------------------------------------------------------------------------
# Synchronous integration tests (TestClient)
# ---------------------------------------------------------------------------

@pytest.fixture()
def server() -> MagicMock:
    return _make_server()


@pytest.fixture()
def client(server: MagicMock) -> TestClient:
    transport = HTTPTransport(server)
    return TestClient(transport.app, raise_server_exceptions=True)


class TestMcpIntegration:
    """Full request-response cycle for MCP methods."""

    def test_initialize_returns_capabilities(self, client: TestClient) -> None:
        resp = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["result"]["protocolVersion"] == "2025-03-26"
        assert body["result"]["capabilities"]["tools"]["listTools"] is True

    def test_tools_list_returns_tools(self, client: TestClient, server: MagicMock) -> None:
        resp = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert resp.status_code == 200
        tools = resp.json()["result"]["tools"]
        tool_names = {t["name"] for t in tools}
        assert tool_names == set(server.tools.keys())

    def test_tools_call_returns_result(self, client: TestClient) -> None:
        resp = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "find_code", "arguments": {"query": "hello"}},
            },
        )
        assert resp.status_code == 200
        content = resp.json()["result"]["content"]
        assert content[0]["type"] == "text"
        data = json.loads(content[0]["text"])
        assert data["called"] == "find_code"

    def test_notification_returns_204(self, client: TestClient) -> None:
        resp = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        assert resp.status_code == 204

    def test_unknown_method_returns_error(self, client: TestClient) -> None:
        resp = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 9, "method": "bogus/method"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == -32601


class TestHealthzIntegration:
    def test_healthz_200_when_connected(self) -> None:
        tools = {f"t{i}": {"name": f"t{i}"} for i in range(4)}
        server = _make_server(connected=True, tools=tools)
        c = TestClient(HTTPTransport(server).app)

        resp = c.get("/healthz")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["tools"] == 4

    def test_healthz_503_when_disconnected(self) -> None:
        server = _make_server(connected=False)
        c = TestClient(HTTPTransport(server).app)

        resp = c.get("/healthz")
        assert resp.status_code == 503
        assert resp.json()["status"] == "unhealthy"


# ---------------------------------------------------------------------------
# Async integration tests (httpx.AsyncClient + ASGI transport)
# ---------------------------------------------------------------------------

@pytest.fixture()
def async_server() -> MagicMock:
    return _make_server()


@pytest.fixture()
def asgi_app(async_server: MagicMock):
    return HTTPTransport(async_server).app


@pytest.mark.asyncio
async def test_async_initialize(asgi_app) -> None:
    """initialize works correctly via httpx AsyncClient."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=asgi_app), base_url="http://testserver"
    ) as ac:
        resp = await ac.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 10, "method": "initialize", "params": {}},
        )
    assert resp.status_code == 200
    assert resp.json()["result"]["protocolVersion"] == "2025-03-26"


@pytest.mark.asyncio
async def test_async_tools_list(asgi_app, async_server: MagicMock) -> None:
    """tools/list works correctly via httpx AsyncClient."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=asgi_app), base_url="http://testserver"
    ) as ac:
        resp = await ac.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 11, "method": "tools/list"},
        )
    assert resp.status_code == 200
    tool_names = {t["name"] for t in resp.json()["result"]["tools"]}
    assert tool_names == set(async_server.tools.keys())


@pytest.mark.asyncio
async def test_async_healthz_ok(asgi_app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=asgi_app), base_url="http://testserver"
    ) as ac:
        resp = await ac.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_async_healthz_unhealthy() -> None:
    server = _make_server(connected=False)
    app = HTTPTransport(server).app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        resp = await ac.get("/healthz")
    assert resp.status_code == 503
    assert resp.json()["status"] == "unhealthy"
