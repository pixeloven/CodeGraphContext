"""Stub plugin for testing the CGC plugin system."""

from cgc_plugin_stub.cli import get_plugin_commands
from cgc_plugin_stub.mcp_tools import get_mcp_handlers, get_mcp_tools

PLUGIN_METADATA = {
    "name": "cgc-plugin-stub",
    "version": "0.1.0",
    "cgc_version_constraint": ">=0.1.0",
    "description": "Minimal stub plugin for testing CGC plugin discovery and loading.",
}

__all__ = ["PLUGIN_METADATA", "get_plugin_commands", "get_mcp_tools", "get_mcp_handlers"]
