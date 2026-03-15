# Contract: CGC Plugin Interface

**Version**: 1.0.0
**Feature**: 001-cgc-plugin-extension
**Audience**: Plugin authors

This document is the authoritative contract for building CGC-compatible plugins.
Plugins that satisfy this contract will be auto-discovered and loaded by CGC core.

---

## 1. Package Structure

A CGC plugin is a standard Python package installable via pip. It MUST follow this
structure:

```
cgc-plugin-<name>/
├── pyproject.toml              # Entry point declarations (required)
└── src/
    └── cgc_plugin_<name>/
        ├── __init__.py         # PLUGIN_METADATA declaration (required)
        ├── cli.py              # CLI contract (required if contributing CLI commands)
        └── mcp_tools.py        # MCP contract (required if contributing MCP tools)
```

---

## 2. Plugin Metadata (REQUIRED)

Every plugin MUST declare `PLUGIN_METADATA` in its package `__init__.py`:

```python
PLUGIN_METADATA = {
    "name": "my-plugin",                     # str, kebab-case, globally unique
    "version": "0.1.0",                      # str, PEP-440
    "cgc_version_constraint": ">=0.3.0,<1.0",  # str, PEP-440 specifier
    "description": "One-line description",   # str
    "author": "Your Name",                   # str, optional
}
```

**Rules**:
- `name` MUST be unique across all installed plugins. Conflicts are resolved by
  skipping the second plugin with a warning.
- `cgc_version_constraint` MUST be a valid PEP-440 specifier. Plugins whose constraint
  does not match the installed CGC version are skipped at startup.
- All required fields MUST be present. A plugin with missing required fields is skipped.

---

## 3. Entry Point Declarations

In the plugin's `pyproject.toml`, declare entry points under one or both groups:

```toml
[project.entry-points."cgc_cli_plugins"]
my-plugin = "cgc_plugin_myname.cli:get_plugin_commands"

[project.entry-points."cgc_mcp_plugins"]
my-plugin = "cgc_plugin_myname.mcp_tools:get_mcp_tools"
```

- A plugin MAY declare CLI entry points only, MCP entry points only, or both.
- The entry point name (left of `=`) MUST match the plugin's `name` in `PLUGIN_METADATA`.

---

## 4. CLI Contract

If the plugin declares a `cgc_cli_plugins` entry point, the target function MUST have
this signature:

```python
def get_plugin_commands() -> tuple[str, typer.Typer]:
    """
    Returns a (command_group_name, typer_app) tuple.

    - command_group_name: str, kebab-case, globally unique across plugins
    - typer_app: typer.Typer instance with commands registered on it

    MUST NOT:
    - Have side effects (no database access, no file writes, no network calls)
    - Raise unhandled exceptions (caught and logged by PluginRegistry)
    - Import CGC internals at module level (use lazy imports inside handlers)
    """
```

**Example**:
```python
# cgc_plugin_myname/cli.py
import typer

my_app = typer.Typer(help="My plugin commands")

@my_app.command("hello")
def hello():
    """Say hello."""
    typer.echo("Hello from my-plugin!")

def get_plugin_commands() -> tuple[str, typer.Typer]:
    return ("my-plugin", my_app)
```

After installation, the user sees: `cgc my-plugin hello`

---

## 5. MCP Contract

If the plugin declares a `cgc_mcp_plugins` entry point, the target module MUST expose
two functions:

### 5.1 get_mcp_tools()

```python
def get_mcp_tools(server_context: dict) -> dict[str, dict]:
    """
    Returns tool definitions for registration in CGC's MCP tool manifest.

    Args:
        server_context: {
            "db_manager": DatabaseManager,  # shared graph DB connection
            "version": str,                 # installed CGC version
        }

    Returns:
        dict mapping tool_name (str) → ToolDefinition (dict)

    MUST NOT:
    - Register tools whose names conflict with built-in CGC tools
      (conflicts are silently skipped with a warning)
    - Raise unhandled exceptions
    """
```

### 5.2 get_mcp_handlers()

```python
def get_mcp_handlers(server_context: dict) -> dict[str, callable]:
    """
    Returns handler callables for each tool registered in get_mcp_tools().

    Args:
        server_context: same as get_mcp_tools()

    Returns:
        dict mapping tool_name (str) → handler callable

    Handler callable signature:
        def handler(**kwargs) -> dict:
            # kwargs match the tool's inputSchema properties
            # Returns a JSON-serialisable dict
    """
```

### 5.3 ToolDefinition Schema

Each value in the `get_mcp_tools()` return dict MUST conform to this schema:

```python
{
    "name": str,           # MUST match the dict key
    "description": str,    # Human-readable description (shown in AI tool listings)
    "inputSchema": {       # JSON Schema draft-07 object
        "type": "object",
        "properties": {
            "<param>": {
                "type": "string" | "integer" | "boolean" | "array" | "object",
                "description": str,
                # ... other JSON Schema keywords
            }
        },
        "required": [str, ...]   # list of required property names
    }
}
```

**Example**:
```python
# cgc_plugin_myname/mcp_tools.py

def get_mcp_tools(server_context):
    db = server_context["db_manager"]
    return {
        "myplugin_greet": {
            "name": "myplugin_greet",
            "description": "Greet by name",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name to greet"}
                },
                "required": ["name"]
            }
        }
    }

def get_mcp_handlers(server_context):
    db = server_context["db_manager"]
    def greet_handler(name: str) -> dict:
        return {"greeting": f"Hello, {name}!"}
    return {"myplugin_greet": greet_handler}
```

---

## 6. Naming Conventions

To prevent conflicts in a shared namespace, plugin-registered names MUST be prefixed:

| Artifact | Naming Rule | Example |
|---|---|---|
| CLI command group | plugin name (kebab-case) | `cgc otel ...` |
| MCP tool names | `<pluginname>_<toolname>` | `otel_query_spans` |
| Graph node labels | PascalCase, no prefix needed | `Span`, `StackFrame` |
| Graph `source` values | `"runtime_<protocol>"` or `"memory"` | `"runtime_otel"` |

---

## 7. Error Handling Expectations

CGC wraps all plugin calls. Plugins SHOULD still implement defensive error handling:

- Handlers SHOULD catch database exceptions and return an `{"error": "..."}` dict
  rather than raising exceptions, to produce clean error messages for AI agents.
- Handlers MUST be idempotent for write operations (use MERGE, not CREATE).
- Handlers MUST NOT retain state across calls beyond what the `db_manager` persists.

---

## 8. Testing Requirements

Plugin packages MUST include:

- `tests/unit/` — unit tests for extraction/parsing logic (mocked database)
- `tests/integration/` — tests verifying the plugin registers correctly with a real
  CGC server instance

Plugin tests MUST pass with `pytest tests/unit tests/integration`.
Plugin tests SHOULD be runnable independently without CGC core installed (via mocks).
