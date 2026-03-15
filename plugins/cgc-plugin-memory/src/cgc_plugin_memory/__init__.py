"""Memory plugin for CodeGraphContext — stores and searches project knowledge in the graph."""

from cgc_plugin_memory.cli import get_plugin_commands
from cgc_plugin_memory.mcp_tools import get_mcp_handlers, get_mcp_tools

PLUGIN_METADATA = {
    "name": "cgc-plugin-memory",
    "version": "0.1.0",
    "cgc_version_constraint": ">=0.1.0",
    "description": (
        "Exposes MCP tools and CLI commands to store, search, and link knowledge "
        "entities (specs, decisions, notes) in the Neo4j graph, enabling cross-layer "
        "queries like 'which code has no spec?'."
    ),
}
