# cgc-plugin-otel

OpenTelemetry span processor plugin for [CodeGraphContext](https://github.com/CodeGraphContext/CodeGraphContext).

## Overview

This plugin ingests OpenTelemetry spans from PHP services (e.g. Laravel) via a gRPC
OTLP receiver and writes them into the CGC Neo4j graph. Spans are correlated with
code graph nodes (classes, methods) using `CORRELATES_TO` relationships, enabling
cross-layer queries that link runtime traces to static code structure.

## Features

- gRPC OTLP receiver listening on port 5317
- Extracts PHP context from OTel span attributes (`code.namespace`, `code.function`, etc.)
- Writes `Service`, `Trace`, and `Span` nodes to Neo4j
- Creates `PART_OF`, `CHILD_OF`, `CORRELATES_TO`, and `CALLS_SERVICE` relationships
- Dead-letter queue (DLQ) for spans that fail to persist
- Exposes a `otel` CLI command group and MCP tools prefixed with `otel_`

## Requirements

- Python 3.10+
- CodeGraphContext >= 0.3.0
- Neo4j >= 5.15
- grpcio >= 1.57
- opentelemetry-sdk >= 1.20

## Installation

```bash
pip install -e plugins/cgc-plugin-otel
```

## MCP tool naming

All MCP tools contributed by this plugin are prefixed with `otel_`
(e.g. `otel_query_spans`).

## Entry points

| Group | Name | Target |
|---|---|---|
| `cgc_cli_plugins` | `otel` | `cgc_plugin_otel.cli:get_plugin_commands` |
| `cgc_mcp_plugins` | `otel` | `cgc_plugin_otel.mcp_tools:get_mcp_tools` |
