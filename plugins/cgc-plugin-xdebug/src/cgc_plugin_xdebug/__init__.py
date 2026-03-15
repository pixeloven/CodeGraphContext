"""Xdebug plugin for CodeGraphContext — captures PHP call stacks via DBGp and writes them to the graph.

NOTE: This plugin is intended for development and staging environments only.
It must be explicitly enabled via CGC_PLUGIN_XDEBUG_ENABLED=true.
"""

from cgc_plugin_xdebug.cli import get_plugin_commands
from cgc_plugin_xdebug.mcp_tools import get_mcp_handlers, get_mcp_tools

PLUGIN_METADATA = {
    "name": "cgc-plugin-xdebug",
    "version": "0.1.0",
    "cgc_version_constraint": ">=0.1.0",
    "description": (
        "Runs a TCP DBGp listener, captures PHP call stacks from Xdebug, "
        "deduplicates chains, and writes StackFrame nodes to the code graph. "
        "Development/staging only — requires CGC_PLUGIN_XDEBUG_ENABLED=true."
    ),
}
