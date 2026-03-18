# CodeGraphContext Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-03-14

## Active Technologies

- Python 3.10+ (constitutional constraint) (001-cgc-plugin-extension)

## Project Structure

```text
src/
  codegraphcontext/
    plugin_registry.py       ← PluginRegistry (discovers cgc_cli_plugins + cgc_mcp_plugins entry points)
    cli/main.py              ← CLI app; loads plugin CLI commands at import time
    server.py                ← MCPServer; loads plugin MCP tools at init time
tests/
  unit/plugin/               ← Unit tests for plugin system (mocked entry points)
  integration/plugin/        ← Integration tests (real stub plugin if installed)
  e2e/plugin/                ← Full lifecycle E2E tests
plugins/
  cgc-plugin-stub/           ← Reference stub plugin (minimal test fixture)
  cgc-plugin-otel/           ← OpenTelemetry span receiver plugin
  cgc-plugin-xdebug/         ← Xdebug DBGp call-stack listener plugin
docs/
  plugins/
    authoring-guide.md       ← How to write a CGC plugin
    cross-layer-queries.md   ← Canonical cross-layer Cypher queries
```

## Commands

cd src [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] pytest [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] ruff check .

## Code Style

Python 3.10+ (constitutional constraint): Follow standard conventions

## Recent Changes

- 001-cgc-plugin-extension: Added Python 3.10+ (constitutional constraint)

<!-- MANUAL ADDITIONS START -->
## Plugin System (001-cgc-plugin-extension)

### Entry-point groups
- `cgc_cli_plugins` — plugins contribute a `(name, typer.Typer)` via `get_plugin_commands()`
- `cgc_mcp_plugins` — plugins contribute MCP tools via `get_mcp_tools()` and `get_mcp_handlers()`

### Plugin layout convention
```
plugins/cgc-plugin-<name>/
├── pyproject.toml          ← entry-points in both cgc_cli_plugins + cgc_mcp_plugins
└── src/cgc_plugin_<name>/
    ├── __init__.py         ← PLUGIN_METADATA dict (required)
    ├── cli.py              ← get_plugin_commands()
    └── mcp_tools.py        ← get_mcp_tools() + get_mcp_handlers()
```

### MCP tool naming
Plugin tools must be prefixed with plugin name: `<pluginname>_<toolname>` (e.g. `otel_query_spans`).

### Install plugins for development
```bash
pip install -e plugins/cgc-plugin-stub      # minimal test fixture
pip install -e plugins/cgc-plugin-otel
pip install -e plugins/cgc-plugin-xdebug
```

### Run plugin tests
```bash
PYTHONPATH=src pytest tests/unit/plugin/ tests/integration/plugin/ -v
PYTHONPATH=src pytest tests/e2e/plugin/ -v   # e2e (needs plugins installed)
```
<!-- MANUAL ADDITIONS END -->
