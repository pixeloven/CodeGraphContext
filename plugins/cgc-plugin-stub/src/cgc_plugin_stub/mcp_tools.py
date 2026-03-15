"""MCP tools contributed by the stub plugin."""
from __future__ import annotations

from typing import Any


_TOOLS: dict[str, dict] = {
    "stub_hello": {
        "name": "stub_hello",
        "description": "Say hello — stub plugin smoke test tool.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name to greet",
                    "default": "World",
                }
            },
            "required": [],
        },
    }
}


def _handle_stub_hello(name: str = "World", **_kwargs: Any) -> dict:
    return {"greeting": f"Hello {name}"}


def get_mcp_tools(server_context: dict | None = None) -> dict[str, dict]:
    """Entry point: return tool_name → ToolDefinition mapping."""
    return _TOOLS


def get_mcp_handlers(server_context: dict | None = None) -> dict[str, Any]:
    """Entry point: return tool_name → callable mapping."""
    return {"stub_hello": _handle_stub_hello}
