"""OTEL plugin for CodeGraphContext — receives OpenTelemetry spans and writes them to the graph."""

from cgc_plugin_otel.cli import get_plugin_commands
from cgc_plugin_otel.mcp_tools import get_mcp_handlers, get_mcp_tools

PLUGIN_METADATA = {
    "name": "cgc-plugin-otel",
    "version": "0.1.0",
    "cgc_version_constraint": ">=0.1.0",
    "description": (
        "Receives OpenTelemetry traces via gRPC, writes Service/Trace/Span nodes to the "
        "code graph, and correlates runtime spans to static Method nodes."
    ),
}
