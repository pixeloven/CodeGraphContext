"""MCP tools contributed by the Memory plugin."""
from __future__ import annotations

import uuid
from typing import Any

_TOOLS: dict[str, dict] = {
    "memory_store": {
        "name": "memory_store",
        "description": (
            "Store a knowledge entity (spec, decision, note, etc.) in the graph. "
            "Optionally link it to a code node by its fully-qualified name."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "description": "Type of knowledge (spec, decision, note, requirement, …)",
                },
                "name": {"type": "string", "description": "Short descriptive name"},
                "content": {"type": "string", "description": "Full content / body text"},
                "links_to": {
                    "type": "string",
                    "description": "FQN of a Class or Method node to link this memory to via DESCRIBES",
                },
            },
            "required": ["entity_type", "name", "content"],
        },
    },
    "memory_search": {
        "name": "memory_search",
        "description": "Full-text search across stored Memory nodes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search terms"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    "memory_undocumented": {
        "name": "memory_undocumented",
        "description": (
            "Return Class or Method nodes that have no linked Memory node (no DESCRIBES relationship). "
            "Helps identify code that lacks specs or documentation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_type": {
                    "type": "string",
                    "enum": ["Class", "Method"],
                    "default": "Class",
                    "description": "Type of code node to check",
                },
                "limit": {"type": "integer", "default": 20},
            },
            "required": [],
        },
    },
    "memory_link": {
        "name": "memory_link",
        "description": "Create a DESCRIBES relationship between a Memory node and a code node.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memory_id": {"type": "string", "description": "The memory_id of the Memory node"},
                "node_fqn": {
                    "type": "string",
                    "description": "Fully-qualified name of the Class or Method node",
                },
                "node_type": {
                    "type": "string",
                    "enum": ["Class", "Method"],
                    "description": "Label of the target node",
                },
            },
            "required": ["memory_id", "node_fqn", "node_type"],
        },
    },
}

# ---------------------------------------------------------------------------
# Cypher
# ---------------------------------------------------------------------------

_MERGE_MEMORY = """
MERGE (m:Memory {memory_id: $memory_id})
ON CREATE SET
    m.entity_type = $entity_type,
    m.name        = $name,
    m.content     = $content,
    m.created_at  = datetime()
ON MATCH SET
    m.content     = $content,
    m.updated_at  = datetime()
"""

_MERGE_DESCRIBES = """
MATCH (m:Memory {memory_id: $memory_id})
MATCH (n {fqn: $node_fqn})
WHERE $node_type IN labels(n)
MERGE (m)-[:DESCRIBES]->(n)
"""

_FULLTEXT_SEARCH = """
CALL db.index.fulltext.queryNodes('memory_search', $query)
YIELD node AS m, score
RETURN m.memory_id AS memory_id, m.name AS name, m.entity_type AS entity_type,
       m.content AS content, score
ORDER BY score DESC LIMIT $limit
"""

_UNDOCUMENTED = "MATCH (n:{node_type}) WHERE NOT EXISTS {{ MATCH (m:Memory)-[:DESCRIBES]->(n) }} RETURN n.fqn AS fqn, labels(n) AS type ORDER BY n.fqn LIMIT $limit"

_LINK_DESCRIBES = """
MATCH (m:Memory {memory_id: $memory_id})
MATCH (n)
WHERE n.fqn = $node_fqn AND $node_type IN labels(n)
MERGE (m)-[:DESCRIBES]->(n)
"""


# ---------------------------------------------------------------------------
# Handler factories
# ---------------------------------------------------------------------------

def _make_store_handler(db_manager: Any):
    def handle(
        entity_type: str,
        name: str,
        content: str,
        links_to: str | None = None,
        **_: Any,
    ) -> dict:
        memory_id = str(uuid.uuid4())
        driver = db_manager.get_driver()
        with driver.session() as session:
            session.run(
                _MERGE_MEMORY,
                memory_id=memory_id,
                entity_type=entity_type,
                name=name,
                content=content,
            )
            if links_to:
                # Attempt to link to Class first, then Method
                for node_type in ("Class", "Method"):
                    session.run(
                        _MERGE_DESCRIBES,
                        memory_id=memory_id,
                        node_fqn=links_to,
                        node_type=node_type,
                    )
        return {"memory_id": memory_id, "status": "stored"}
    return handle


def _make_search_handler(db_manager: Any):
    def handle(query: str, limit: int = 10, **_: Any) -> dict:
        driver = db_manager.get_driver()
        with driver.session() as session:
            rows = session.run(_FULLTEXT_SEARCH, query=query, limit=limit).data()
        return {"results": rows}
    return handle


def _make_undocumented_handler(db_manager: Any):
    def handle(node_type: str = "Class", limit: int = 20, **_: Any) -> dict:
        # Node labels cannot be parameterized in Cypher — interpolate safely
        # (node_type is validated against enum in the tool schema)
        safe_type = node_type if node_type in ("Class", "Method") else "Class"
        cypher = _UNDOCUMENTED.format(node_type=safe_type)
        driver = db_manager.get_driver()
        with driver.session() as session:
            rows = session.run(cypher, limit=limit).data()
        return {"nodes": rows}
    return handle


def _make_link_handler(db_manager: Any):
    def handle(memory_id: str, node_fqn: str, node_type: str = "Class", **_: Any) -> dict:
        driver = db_manager.get_driver()
        with driver.session() as session:
            session.run(_LINK_DESCRIBES, memory_id=memory_id, node_fqn=node_fqn, node_type=node_type)
        return {"status": "linked"}
    return handle


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

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
        "memory_store": _make_store_handler(db_manager),
        "memory_search": _make_search_handler(db_manager),
        "memory_undocumented": _make_undocumented_handler(db_manager),
        "memory_link": _make_link_handler(db_manager),
    }
