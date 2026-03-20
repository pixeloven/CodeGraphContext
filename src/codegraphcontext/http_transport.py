# src/codegraphcontext/http_transport.py
"""HTTP transport layer for the CGC MCP server.

Exposes the MCP JSON-RPC interface over plain HTTP POST at ``/mcp`` and a
liveness probe at ``/healthz``.  Authentication is intentionally absent —
callers should rely on a reverse proxy or network-level controls.

Environment variables
---------------------
CGC_CORS_ORIGIN
    Allowed CORS origin passed to ``CORSMiddleware``.  Defaults to ``*``.
"""
from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from .server import MCPServer


class HTTPTransport:
    """Wraps an :class:`~codegraphcontext.server.MCPServer` behind a FastAPI app.

    Args:
        server: A fully-initialised ``MCPServer`` instance.
    """

    def __init__(self, server: "MCPServer") -> None:
        self.server = server
        self._app = self._build_app()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_app(self) -> FastAPI:
        """Construct and configure the FastAPI application."""
        cors_origin: str = os.environ.get("CGC_CORS_ORIGIN", "*")

        app = FastAPI(title="CodeGraphContext MCP HTTP Transport", docs_url=None, redoc_url=None)

        app.add_middleware(
            CORSMiddleware,
            allow_origins=[cors_origin],
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type"],
        )

        @app.post("/mcp")
        async def mcp_endpoint(request: Request) -> Response:
            """Deserialise a JSON-RPC request, dispatch to MCPServer, return response."""
            try:
                body = await request.body()
                payload: dict[str, Any] = json.loads(body)
            except Exception:
                return JSONResponse(
                    status_code=400,
                    content={
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": "Parse error"},
                    },
                )

            method: str = payload.get("method", "")
            params: dict[str, Any] = payload.get("params", {}) or {}
            request_id: Any = payload.get("id")

            response = await self.server.handle_request(method, params, request_id)

            if response is None:
                # Notification — return 204 No Content.
                return Response(status_code=204)

            return JSONResponse(content=response)

        @app.get("/healthz")
        async def healthz() -> Response:
            """Liveness probe.  Returns 200 when DB is reachable, 503 otherwise."""
            connected: bool = self.server.db_manager.is_connected()
            tool_count: int = len(self.server.tools)
            if connected:
                return JSONResponse(
                    status_code=200,
                    content={"status": "ok", "tools": tool_count},
                )
            return JSONResponse(
                status_code=503,
                content={"status": "unhealthy"},
            )

        return app

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def app(self) -> FastAPI:
        """The underlying FastAPI application (useful for testing)."""
        return self._app

    def start(self, port: int = 8045) -> None:
        """Run the HTTP server synchronously using uvicorn.

        This method blocks until the server is stopped.  It runs in the
        default asyncio event loop provided by uvicorn (single-process,
        no workers).

        Args:
            port: TCP port to listen on.
        """
        uvicorn.run(self._app, host="0.0.0.0", port=port, log_level="info")
