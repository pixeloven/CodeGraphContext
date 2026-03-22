# cgc-plugin-xdebug

Xdebug DBGp call-stack listener plugin for [CodeGraphContext](https://github.com/CodeGraphContext/CodeGraphContext).

**Intended for development and staging environments only — do not enable in production.**

## Overview

This plugin listens for Xdebug DBGp protocol connections on port 9003 and captures
PHP call-stack frames in real time. Parsed frames are written to the CGC Neo4j graph
as `CallChain` nodes, correlated with existing code graph nodes via their fully-qualified
names. This enables live execution path analysis alongside static code structure.

## Features

- TCP server accepting Xdebug DBGp connections on port 9003
- Parses `stack_get` XML responses into structured frame dicts
- Computes deterministic `chain_hash` for deduplicating identical call chains
- Writes call-stack data to Neo4j as `CallChain` / `CallFrame` nodes
- Exposes an `xdebug` CLI command group and MCP tools prefixed with `xdebug_`

## Requirements

- Python 3.10+
- CodeGraphContext >= 0.3.0
- Neo4j >= 5.15
- Xdebug configured with `xdebug.mode=debug` and `xdebug.client_host` pointing at the CGC host

## Installation

```bash
pip install -e plugins/cgc-plugin-xdebug
```

## Runtime activation

Set the environment variable `CGC_PLUGIN_XDEBUG_ENABLED=true` before starting the
plugin server, otherwise the DBGp listener will not start.

## MCP tool naming

All MCP tools contributed by this plugin are prefixed with `xdebug_`
(e.g. `xdebug_query_callchain`).

## Entry points

| Group | Name | Target |
|---|---|---|
| `cgc_cli_plugins` | `xdebug` | `cgc_plugin_xdebug.cli:get_plugin_commands` |
| `cgc_mcp_plugins` | `xdebug` | `cgc_plugin_xdebug.mcp_tools:get_mcp_tools` |
