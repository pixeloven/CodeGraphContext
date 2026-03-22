# tests/unit/test_http_transport.py
"""Unit tests for the CGC HTTP transport layer (T069).

All tests use ``starlette.testclient.TestClient`` (re-exported by FastAPI) and
a lightweight mock of ``MCPServer`` — no real database is required.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from codegraphcontext.http_transport import HTTPTransport


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_server(
    *,
    connected: bool = True,
    handle_request_return: dict[str, Any] | None = None,
    tools: dict | None = None,
) -> MagicMock:
    """Build a minimal MCPServer mock suitable for unit tests."""
    server = MagicMock()
    server.db_manager = MagicMock()
    server.db_manager.is_connected.return_value = connected
    server.tools = tools if tools is not None else {"tool_a": {}, "tool_b": {}}

    if handle_request_return is None:
        handle_request_return = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"protocolVersion": "2025-03-26"},
        }
    server.handle_request = AsyncMock(return_value=handle_request_return)
    return server


@pytest.fixture()
def server() -> MagicMock:
    return _make_server()


@pytest.fixture()
def client(server: MagicMock) -> TestClient:
    transport = HTTPTransport(server)
    return TestClient(transport.app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# POST /mcp — routing
# ---------------------------------------------------------------------------

class TestMcpEndpoint:
    def test_valid_request_dispatches_to_handle_request(self, client: TestClient, server: MagicMock) -> None:
        """POST /mcp deserialises body and calls server.handle_request."""
        payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        resp = client.post("/mcp", json=payload)

        assert resp.status_code == 200
        server.handle_request.assert_awaited_once_with("initialize", {}, 1)

    def test_response_body_is_json_rpc(self, client: TestClient, server: MagicMock) -> None:
        """Response body matches the dict returned by handle_request."""
        expected = {"jsonrpc": "2.0", "id": 7, "result": {"tools": []}}
        server.handle_request.return_value = expected

        resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 7, "method": "tools/list"})
        assert resp.json() == expected

    def test_notification_returns_204(self, client: TestClient, server: MagicMock) -> None:
        """When handle_request returns None (notification), HTTP 204 is returned."""
        server.handle_request.return_value = None

        resp = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        assert resp.status_code == 204
        assert resp.content == b""

    def test_malformed_json_returns_parse_error(self, client: TestClient) -> None:
        """Non-JSON body produces a 400 with JSON-RPC parse-error."""
        resp = client.post("/mcp", content=b"not-json", headers={"Content-Type": "application/json"})
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == -32700

    def test_params_defaults_to_empty_dict_when_absent(self, client: TestClient, server: MagicMock) -> None:
        """Omitting 'params' from the request should pass an empty dict."""
        client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        _, call_params, _ = server.handle_request.call_args.args
        assert call_params == {}

    def test_unknown_route_returns_404(self, client: TestClient) -> None:
        resp = client.get("/unknown-path")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /healthz
# ---------------------------------------------------------------------------

class TestHealthz:
    def test_returns_200_when_db_connected(self) -> None:
        server = _make_server(connected=True, tools={"t1": {}, "t2": {}, "t3": {}})
        c = TestClient(HTTPTransport(server).app)

        resp = c.get("/healthz")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "tools": 3}

    def test_returns_503_when_db_unreachable(self) -> None:
        server = _make_server(connected=False)
        c = TestClient(HTTPTransport(server).app)

        resp = c.get("/healthz")
        assert resp.status_code == 503
        assert resp.json() == {"status": "unhealthy"}

    def test_tool_count_reflects_server_tools(self) -> None:
        tools = {f"tool_{i}": {} for i in range(5)}
        server = _make_server(connected=True, tools=tools)
        c = TestClient(HTTPTransport(server).app)

        resp = c.get("/healthz")
        assert resp.json()["tools"] == 5


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

class TestCors:
    def test_cors_preflight_returns_correct_headers(self, client: TestClient) -> None:
        """OPTIONS preflight should return CORS allow headers."""
        resp = client.options(
            "/mcp",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        # FastAPI / Starlette CORS middleware returns 200 for preflight
        assert resp.status_code == 200
        assert "access-control-allow-origin" in resp.headers

    def test_default_cors_origin_is_wildcard(self, server: MagicMock) -> None:
        """Without CGC_CORS_ORIGIN env var the allowed origin should be '*'."""
        with patch.dict("os.environ", {}, clear=False):
            os_env = __import__("os").environ
            os_env.pop("CGC_CORS_ORIGIN", None)
            transport = HTTPTransport(server)
            c = TestClient(transport.app)
            resp = c.get(
                "/healthz",
                headers={"Origin": "http://example.com"},
            )
        assert resp.headers.get("access-control-allow-origin") in ("*", "http://example.com")

    def test_custom_cors_origin_env_var(self, server: MagicMock) -> None:
        """CGC_CORS_ORIGIN env var is forwarded to the CORS middleware."""
        with patch.dict("os.environ", {"CGC_CORS_ORIGIN": "https://my-app.example.com"}):
            transport = HTTPTransport(server)
            c = TestClient(transport.app)
            resp = c.get(
                "/healthz",
                headers={"Origin": "https://my-app.example.com"},
            )
        assert resp.headers.get("access-control-allow-origin") == "https://my-app.example.com"
