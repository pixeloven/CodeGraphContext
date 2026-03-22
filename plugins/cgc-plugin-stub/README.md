# cgc-plugin-stub

Minimal stub plugin for testing the CGC plugin extension system.

## Overview

This package is a reference fixture used by the CGC test suite to exercise plugin
discovery, registration, and lifecycle without requiring any real infrastructure.
It implements the minimum required interface (`PLUGIN_METADATA`, `get_plugin_commands()`,
`get_mcp_tools()`, `get_mcp_handlers()`) and contributes a no-op `stub` CLI command
group and a single `stub_ping` MCP tool.

## Usage

Install for development to enable the plugin integration and E2E test suites:

```bash
pip install -e plugins/cgc-plugin-stub
```

Then run:

```bash
PYTHONPATH=src pytest tests/unit/plugin/ tests/integration/plugin/ tests/e2e/plugin/ -v
```

## Entry points

| Group | Name | Target |
|---|---|---|
| `cgc_cli_plugins` | `stub` | `cgc_plugin_stub.cli:get_plugin_commands` |
| `cgc_mcp_plugins` | `stub` | `cgc_plugin_stub.mcp_tools:get_mcp_tools` |

## Note

This plugin is not intended for production use. It exists solely as a test fixture.
