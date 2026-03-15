"""MCP tools contributed by the OTEL plugin."""
from __future__ import annotations

from typing import Any

_TOOLS: dict[str, dict] = {
    "otel_query_spans": {
        "name": "otel_query_spans",
        "description": (
            "Query OpenTelemetry spans stored in the graph.  "
            "Filter by HTTP route and/or service name."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "http_route": {"type": "string", "description": "Filter by HTTP route (e.g. /api/orders)"},
                "service": {"type": "string", "description": "Filter by service name"},
                "limit": {"type": "integer", "description": "Max results", "default": 20},
            },
            "required": [],
        },
    },
    "otel_list_services": {
        "name": "otel_list_services",
        "description": "List all services observed in the runtime span graph.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    "otel_cross_layer_query": {
        "name": "otel_cross_layer_query",
        "description": (
            "Run a pre-built cross-layer query combining static code structure with runtime spans.  "
            "query_type options: unspecced_running_code | cross_service_calls | recent_executions"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query_type": {
                    "type": "string",
                    "enum": ["unspecced_running_code", "cross_service_calls", "recent_executions"],
                    "description": "The cross-layer query to run",
                },
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["query_type"],
        },
    },
}

_CROSS_LAYER_QUERIES: dict[str, str] = {
    "unspecced_running_code": (
        "MATCH (sp:Span)-[:CORRELATES_TO]->(m:Method) "
        "WHERE NOT EXISTS { MATCH (m)<-[:DESCRIBES]-(:Memory) } "
        "RETURN m.fqn AS fqn, count(sp) AS run_count "
        "ORDER BY run_count DESC LIMIT $limit"
    ),
    "cross_service_calls": (
        "MATCH (sp:Span)-[:CALLS_SERVICE]->(svc:Service) "
        "RETURN sp.service_name AS caller, svc.name AS callee, sp.http_route AS route, count(*) AS calls "
        "ORDER BY calls DESC LIMIT $limit"
    ),
    "recent_executions": (
        "MATCH (sp:Span)-[:CORRELATES_TO]->(m:Method) "
        "RETURN sp.name AS span, m.fqn AS fqn, sp.duration_ms AS duration_ms "
        "ORDER BY sp.start_time_ns DESC LIMIT $limit"
    ),
}


def _make_query_spans_handler(db_manager: Any):
    def handle(http_route: str | None = None, service: str | None = None, limit: int = 20) -> dict:
        where_clauses = []
        params: dict = {"limit": limit}
        if http_route:
            where_clauses.append("sp.http_route = $http_route")
            params["http_route"] = http_route
        if service:
            where_clauses.append("sp.service_name = $service")
            params["service"] = service
        where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        cypher = (
            f"MATCH (sp:Span) {where} "
            "RETURN sp.span_id AS span_id, sp.name AS name, sp.service_name AS service, "
            "sp.duration_ms AS duration_ms, sp.http_route AS http_route "
            "ORDER BY sp.start_time_ns DESC LIMIT $limit"
        )
        driver = db_manager.get_driver()
        with driver.session() as session:
            return {"spans": session.run(cypher, **params).data()}
    return handle


def _make_list_services_handler(db_manager: Any):
    def handle(**_kwargs: Any) -> dict:
        driver = db_manager.get_driver()
        with driver.session() as session:
            rows = session.run("MATCH (s:Service) RETURN s.name AS name ORDER BY s.name").data()
        return {"services": [r["name"] for r in rows]}
    return handle


def _make_cross_layer_handler(db_manager: Any):
    def handle(query_type: str, limit: int = 20, **_kwargs: Any) -> dict:
        cypher = _CROSS_LAYER_QUERIES.get(query_type)
        if cypher is None:
            return {"error": f"Unknown query_type '{query_type}'"}
        driver = db_manager.get_driver()
        with driver.session() as session:
            return {"results": session.run(cypher, limit=limit).data()}
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
        "otel_query_spans": _make_query_spans_handler(db_manager),
        "otel_list_services": _make_list_services_handler(db_manager),
        "otel_cross_layer_query": _make_cross_layer_handler(db_manager),
    }
