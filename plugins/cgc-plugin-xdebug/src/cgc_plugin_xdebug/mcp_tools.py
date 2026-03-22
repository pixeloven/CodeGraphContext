"""MCP tools contributed by the Xdebug plugin."""
from __future__ import annotations

from typing import Any

_TOOLS: dict[str, dict] = {
    "xdebug_list_chains": {
        "name": "xdebug_list_chains",
        "description": (
            "List the most-observed PHP call stack chains captured by Xdebug. "
            "Returns StackFrame nodes ordered by observation count."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20, "description": "Max results"},
                "min_observations": {
                    "type": "integer",
                    "default": 1,
                    "description": "Minimum observation count to include",
                },
            },
            "required": [],
        },
    },
    "xdebug_query_chain": {
        "name": "xdebug_query_chain",
        "description": (
            "Query the call stack chains that include a specific class or method. "
            "Returns StackFrame nodes with their CALLED_BY chain."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "class_name": {"type": "string", "description": "PHP class name (partial match)"},
                "method_name": {"type": "string", "description": "PHP method name (partial match)"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": [],
        },
    },
}


def _make_list_chains_handler(db_manager: Any):
    def handle(limit: int = 20, min_observations: int = 1, **_: Any) -> dict:
        driver = db_manager.get_driver()
        with driver.session() as session:
            rows = session.run(
                "MATCH (sf:StackFrame) WHERE sf.observation_count >= $min_obs "
                "RETURN sf.fqn AS fqn, sf.file_path AS file, sf.lineno AS lineno, "
                "sf.observation_count AS observations "
                "ORDER BY observations DESC LIMIT $limit",
                min_obs=min_observations,
                limit=limit,
            ).data()
        return {"chains": rows}
    return handle


def _make_query_chain_handler(db_manager: Any):
    def handle(class_name: str | None = None, method_name: str | None = None, limit: int = 10, **_: Any) -> dict:
        where_parts = []
        params: dict = {"limit": limit}
        if class_name:
            where_parts.append("sf.class_name CONTAINS $class_name")
            params["class_name"] = class_name
        if method_name:
            where_parts.append("sf.method_name CONTAINS $method_name")
            params["method_name"] = method_name

        where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
        cypher = (
            f"MATCH (sf:StackFrame) {where} "
            "OPTIONAL MATCH (sf)-[:CALLED_BY*1..5]->(caller:StackFrame) "
            "RETURN sf.fqn AS root_fqn, collect(caller.fqn) AS call_chain, "
            "sf.observation_count AS observations "
            "ORDER BY observations DESC LIMIT $limit"
        )
        driver = db_manager.get_driver()
        with driver.session() as session:
            return {"results": session.run(cypher, **params).data()}
    return handle


def get_mcp_tools(server_context: dict | None = None) -> dict[str, dict]:
    """Entry point: return tool_name → ToolDefinition mapping."""
    return _TOOLS


def get_mcp_handlers(server_context: dict | None = None) -> dict[str, Any]:
    """Entry point: return tool_name → callable mapping."""
    if server_context is None:
        server_context = {}
    db_manager = server_context.get("db_manager")
    if db_manager is None:
        return {}
    return {
        "xdebug_list_chains": _make_list_chains_handler(db_manager),
        "xdebug_query_chain": _make_query_chain_handler(db_manager),
    }
