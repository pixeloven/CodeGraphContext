# Data Model: CGC Plugin Extension System

**Feature**: 001-cgc-plugin-extension
**Date**: 2026-03-14

This document describes both the in-memory runtime data model for the plugin system
and the new graph nodes/relationships added to the CGC graph schema by the plugins.

---

## Part 1: Plugin System Runtime Model

These entities exist at Python runtime only (not persisted to the graph).

---

### PluginMetadata

Declared by each plugin in `__init__.py::PLUGIN_METADATA`. Validated by `PluginRegistry`
at startup.

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | str | ✅ | Unique plugin identifier (kebab-case) |
| `version` | str | ✅ | Plugin version (PEP-440, e.g. `"0.1.0"`) |
| `cgc_version_constraint` | str | ✅ | PEP-440 specifier for compatible CGC versions (e.g. `">=0.3.0,<1.0"`) |
| `description` | str | ✅ | One-line human description |
| `author` | str | ❌ | Author name or team |

**Validation rules**:
- `name` MUST be unique across all installed plugins
- `cgc_version_constraint` MUST be a valid PEP-440 specifier string
- Plugin is rejected if `cgc_version_constraint` does not match installed CGC version

---

### PluginRegistration

Runtime state of a successfully loaded plugin, held in `PluginRegistry.loaded_plugins`.

| Field | Type | Description |
|---|---|---|
| `name` | str | Plugin name (from metadata) |
| `metadata` | PluginMetadata | Validated metadata dict |
| `cli_commands` | `list[Tuple[str, typer.Typer]]` | Registered command groups |
| `mcp_tools` | `dict[str, ToolDefinition]` | Registered MCP tool schemas |
| `mcp_handlers` | `dict[str, Callable]` | Tool name → handler function |
| `status` | `"loaded" \| "failed" \| "skipped"` | Load outcome |
| `failure_reason` | `str \| None` | Set when status is failed or skipped |

---

### PluginRegistry

Singleton held by the CGC process. Manages discovery, validation, and lifecycle.

| Field | Type | Description |
|---|---|---|
| `loaded_plugins` | `dict[str, PluginRegistration]` | Name → registration for successfully loaded plugins |
| `failed_plugins` | `dict[str, str]` | Name → failure reason for failed/skipped plugins |

**State transitions**:
```
discovered → compatibility_check → [compatible] → loaded
                                 → [incompatible] → skipped
                                 → [import error] → failed
                                 → [call error] → failed
```

---

### CLIPluginContract

The callable contract each CLI plugin entry point MUST satisfy.

```python
def get_plugin_commands() -> tuple[str, typer.Typer]:
    """
    Returns:
        (command_group_name, typer_app_instance)

    Raises:
        Any exception → caught and logged by PluginRegistry; plugin skipped
    """
```

**Invariants**:
- `command_group_name` MUST be unique (CGC rejects duplicates with a warning)
- `typer_app` MUST be a `typer.Typer` instance
- Function MUST NOT have side effects beyond creating the Typer app

---

### MCPPluginContract

The callable contract each MCP plugin entry point MUST satisfy.

```python
def get_mcp_tools(server_context: dict) -> dict[str, ToolDefinition]:
    """
    Args:
        server_context: {
            "db_manager": DatabaseManager,
            "version": str,
        }

    Returns:
        dict of tool_name → ToolDefinition

    Raises:
        Any exception → caught and logged by PluginRegistry; plugin skipped
    """

def get_mcp_handlers(server_context: dict) -> dict[str, Callable]:
    """
    Returns:
        dict of tool_name → handler_callable(**args) -> dict
    """
```

**ToolDefinition schema** (matches existing `tool_definitions.py` pattern):
```python
{
    "name": str,                    # MUST match dict key
    "description": str,             # Human description
    "inputSchema": {                # JSON Schema object
        "type": "object",
        "properties": { ... },
        "required": [ ... ]
    }
}
```

---

## Part 2: Graph Schema Extensions

New node labels and relationship types added by each plugin to the existing CGC graph.
All new nodes carry a `source` property identifying their origin layer.

---

### OTEL Plugin Nodes

#### Service

Represents a named microservice observed in telemetry data.

| Property | Type | Required | Index | Description |
|---|---|---|---|---|
| `name` | string | ✅ | UNIQUE | Service name from OTEL resource attributes |
| `version` | string | ❌ | — | Service version if reported |
| `environment` | string | ❌ | — | Environment tag (prod, staging, dev) |
| `source` | string | ✅ | — | Always `"runtime_otel"` |

**Constraint**: `UNIQUE (s.name)` — service names are globally unique identifiers.

---

#### Trace

Represents a single distributed trace (root span + all children).

| Property | Type | Required | Index | Description |
|---|---|---|---|---|
| `trace_id` | string | ✅ | UNIQUE | 128-bit trace ID as hex string |
| `root_span_id` | string | ✅ | — | Span ID of the root span |
| `started_at` | long | ✅ | — | Start time in Unix milliseconds |
| `duration_ms` | long | ✅ | — | Total trace duration in milliseconds |
| `source` | string | ✅ | — | Always `"runtime_otel"` |

**Constraint**: `UNIQUE (t.trace_id)`.

---

#### Span

Represents a single operation within a trace.

| Property | Type | Required | Index | Description |
|---|---|---|---|---|
| `span_id` | string | ✅ | UNIQUE | 64-bit span ID as hex string |
| `trace_id` | string | ✅ | INDEX | Parent trace ID (for batch queries) |
| `name` | string | ✅ | — | Span name |
| `service` | string | ✅ | — | Source service name |
| `kind` | string | ✅ | — | `SERVER`, `CLIENT`, `INTERNAL`, `PRODUCER`, `CONSUMER` |
| `class_name` | string | ❌ | INDEX | PHP: `code.namespace` attribute |
| `method_name` | string | ❌ | — | PHP: `code.function` attribute |
| `http_method` | string | ❌ | — | HTTP verb for SERVER/CLIENT spans |
| `http_route` | string | ❌ | INDEX | Route template (e.g. `/api/orders`) |
| `db_statement` | string | ❌ | — | SQL/query statement for DB spans |
| `duration_ms` | long | ✅ | — | Span duration in milliseconds |
| `status` | string | ✅ | — | `OK`, `ERROR`, `UNSET` |
| `source` | string | ✅ | — | Always `"runtime_otel"` |

**Constraints**: `UNIQUE (s.span_id)`.
**Indexes**: `(s.trace_id)`, `(s.class_name)`, `(s.http_route)`.

---

### Xdebug Plugin Nodes

#### StackFrame

Represents a single frame in a PHP execution call stack captured via DBGp.

| Property | Type | Required | Index | Description |
|---|---|---|---|---|
| `frame_id` | string | ✅ | UNIQUE | Hash of `class_name::method_name:file_path:line` |
| `class_name` | string | ✅ | INDEX | PHP class name (fully qualified) |
| `method_name` | string | ✅ | — | PHP method name |
| `fqn` | string | ✅ | INDEX | `ClassName::methodName` for correlation |
| `file_path` | string | ✅ | — | Absolute file path from DBGp |
| `line` | int | ✅ | — | Line number |
| `depth` | int | ✅ | — | Call stack depth (0 = top) |
| `chain_hash` | string | ✅ | INDEX | Deduplication hash of the full call chain |
| `observation_count` | int | ✅ | — | Number of times this chain was observed |
| `source` | string | ✅ | — | Always `"runtime_xdebug"` |

**Constraint**: `UNIQUE (sf.frame_id)`.
**Index**: `(sf.fqn)` for `RESOLVES_TO` correlation lookups.

---

## Part 3: Graph Relationship Extensions

New relationships added by the plugins. Existing CGC relationships are not modified.

---

### OTEL Relationships

| Relationship | From → To | Properties | Description |
|---|---|---|---|
| `CHILD_OF` | Span → Span | — | Parent-child span hierarchy |
| `PART_OF` | Span → Trace | — | Span belongs to trace |
| `ORIGINATED_FROM` | Trace → Service | — | Trace started in service |
| `CALLS_SERVICE` | Span → Service | — | Cross-service call (CLIENT spans only) |
| `CORRELATES_TO` | Span → Method | `confidence: "fqn_match"` | Runtime → static correlation |

---

### Xdebug Relationships

| Relationship | From → To | Properties | Description |
|---|---|---|---|
| `CALLED_BY` | StackFrame → StackFrame | `depth_diff: int` | Call chain (child called by parent) |
| `RESOLVES_TO` | StackFrame → Method | `match_type: "fqn_exact"` | Frame → static method node |

---

## Part 4: Schema Migration

All new node labels and relationship types are additive — they do not modify existing
CGC node labels (`File`, `Class`, `Method`, `Function`) or existing relationships
(`CALLS`, `IMPORTS`, `INHERITS`, `DEFINES`).

Required Cypher initialization statements (added to `config/neo4j/init.cypher`):

```cypher
-- OTEL constraints & indexes
CREATE CONSTRAINT service_name IF NOT EXISTS FOR (s:Service) REQUIRE s.name IS UNIQUE;
CREATE CONSTRAINT trace_id IF NOT EXISTS FOR (t:Trace) REQUIRE t.trace_id IS UNIQUE;
CREATE CONSTRAINT span_id IF NOT EXISTS FOR (s:Span) REQUIRE s.span_id IS UNIQUE;
CREATE INDEX span_trace IF NOT EXISTS FOR (s:Span) ON (s.trace_id);
CREATE INDEX span_class IF NOT EXISTS FOR (s:Span) ON (s.class_name);
CREATE INDEX span_route IF NOT EXISTS FOR (s:Span) ON (s.http_route);

-- Xdebug constraints & indexes
CREATE CONSTRAINT frame_id IF NOT EXISTS FOR (sf:StackFrame) REQUIRE sf.frame_id IS UNIQUE;
CREATE INDEX frame_fqn IF NOT EXISTS FOR (sf:StackFrame) ON (sf.fqn);
```
