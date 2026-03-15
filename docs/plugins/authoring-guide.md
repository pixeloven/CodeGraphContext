# Plugin Authoring Guide

This guide walks through creating a CGC plugin from scratch.
The `plugins/cgc-plugin-stub` directory is the canonical worked example — reference it
throughout.

For the full contract specification see:
[`specs/001-cgc-plugin-extension/contracts/plugin-interface.md`](../../specs/001-cgc-plugin-extension/contracts/plugin-interface.md)

---

## 1. Package Scaffold

A CGC plugin is a standard Python package with two entry-point groups.

```
plugins/cgc-plugin-<name>/
├── pyproject.toml
└── src/
    └── cgc_plugin_<name>/
        ├── __init__.py       ← PLUGIN_METADATA + re-exports
        ├── cli.py            ← get_plugin_commands()
        └── mcp_tools.py      ← get_mcp_tools() + get_mcp_handlers()
```

Bootstrap it by copying the stub:

```bash
cp -r plugins/cgc-plugin-stub plugins/cgc-plugin-myname
# then edit: pyproject.toml, __init__.py, cli.py, mcp_tools.py
```

---

## 2. `pyproject.toml`

Minimum required configuration:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "cgc-plugin-myname"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["typer[all]>=0.9.0"]

[project.entry-points.cgc_cli_plugins]
myname = "cgc_plugin_myname"

[project.entry-points.cgc_mcp_plugins]
myname = "cgc_plugin_myname"
```

**Key points**:
- Entry point group: `cgc_cli_plugins` — for CLI commands
- Entry point group: `cgc_mcp_plugins` — for MCP tools
- Entry point name (`myname`) becomes the CLI command group name and the registry key
- Both groups must point to the same module for most plugins

---

## 3. `__init__.py` — PLUGIN_METADATA

```python
PLUGIN_METADATA = {
    "name": "cgc-plugin-myname",           # must match pyproject.toml name
    "version": "0.1.0",
    "cgc_version_constraint": ">=0.1.0",   # PEP 440 specifier
    "description": "One-line description of what this plugin does",
}
```

**Required fields**: `name`, `version`, `cgc_version_constraint`, `description`.
Missing any field causes the plugin to be skipped at startup with a clear warning.

The `cgc_version_constraint` is checked against the installed `codegraphcontext` version.
Use `">=0.1.0"` for maximum compatibility during early development.

---

## 4. CLI Contract — `cli.py`

```python
import typer

myname_app = typer.Typer(help="My plugin commands.")

@myname_app.command("hello")
def hello(name: str = typer.Option("World", help="Name to greet")):
    """Say hello from myname plugin."""
    typer.echo(f"Hello from myname plugin, {name}!")


def get_plugin_commands():
    """Return (command_group_name, typer_app) to be registered with CGC."""
    return ("myname", myname_app)
```

**Contract**:
- `get_plugin_commands()` must return a `(str, typer.Typer)` tuple
- The string becomes the sub-command group: `cgc myname <command>`
- Raising an exception in `get_plugin_commands()` quarantines the plugin safely

---

## 5. MCP Contract — `mcp_tools.py`

```python
def get_mcp_tools(server_context: dict | None = None):
    """Return dict of tool_name → MCP tool definition."""
    return {
        "myname_hello": {
            "name": "myname_hello",
            "description": "Say hello from myname plugin",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name to greet"},
                },
                "required": ["name"],
            },
        },
    }


def get_mcp_handlers(server_context: dict | None = None):
    """Return dict of tool_name → callable handler."""
    db = (server_context or {}).get("db_manager")

    def handle_hello(name: str = "World"):
        return {"greeting": f"Hello {name} from myname plugin!"}

    return {"myname_hello": handle_hello}
```

**Contract**:
- `get_mcp_tools()` returns `dict[str, ToolDefinition]`
- `get_mcp_handlers()` returns `dict[str, callable]`
- Tool names **must** be prefixed with the plugin name: `<pluginname>_<toolname>`
- `server_context` carries `{"db_manager": <DatabaseManager>}` when available
- Conflicting tool names: the first plugin to register a name wins

---

## 6. Accessing Neo4j

If your plugin needs graph access, use the `db_manager` from `server_context`:

```python
def get_mcp_handlers(server_context=None):
    db = (server_context or {}).get("db_manager")

    def handle_query(limit: int = 10):
        if db is None:
            return {"error": "No database connection available"}
        results = db.execute_query(
            "MATCH (n:Method) RETURN n.fqn LIMIT $limit",
            {"limit": limit}
        )
        return {"methods": [r["n.fqn"] for r in results]}

    return {"myname_query": handle_query}
```

---

## 7. Testing Your Plugin

Write tests in `tests/unit/plugin/` and `tests/integration/plugin/`.

```python
# tests/unit/plugin/test_myname_tools.py
from cgc_plugin_myname.mcp_tools import get_mcp_tools, get_mcp_handlers

def test_tools_defined():
    tools = get_mcp_tools()
    assert "myname_hello" in tools

def test_hello_handler():
    handlers = get_mcp_handlers()
    result = handlers["myname_hello"](name="Test")
    assert result["greeting"] == "Hello Test from myname plugin!"
```

Run tests:
```bash
PYTHONPATH=src pytest tests/unit/plugin/ tests/integration/plugin/ -v
```

---

## 8. Install and Verify

```bash
pip install -e plugins/cgc-plugin-myname

# Verify CLI registration
cgc --help                    # should show 'myname' group
cgc plugin list               # should show cgc-plugin-myname as loaded

# Verify MCP registration (start MCP server and inspect tools/list)
cgc mcp start
# In MCP client: tools/list → should include myname_hello
```

---

## 9. Publishing to PyPI

```bash
cd plugins/cgc-plugin-myname
pip install build
python -m build
pip install twine
twine upload dist/*
```

Users then install your plugin with:
```bash
pip install cgc-plugin-myname
```

CGC discovers it automatically at next startup — no configuration required.
