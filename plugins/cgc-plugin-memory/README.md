# cgc-plugin-memory

Project knowledge memory plugin for [CodeGraphContext](https://github.com/CodeGraphContext/CodeGraphContext).

## Overview

This plugin provides a persistent, searchable memory layer for project-level knowledge
stored in the CGC Neo4j graph. It allows AI assistants and developers to store
specifications, notes, and design decisions as `Memory` nodes, link them to specific
code graph entities (classes, functions, files), and retrieve them via full-text search.

## Features

- Store arbitrary knowledge as typed `Memory` nodes (spec, note, decision, etc.)
- Link memory entries to code graph nodes using `DESCRIBES` relationships
- Full-text search across stored memory via a Neo4j fulltext index
- Query undocumented code nodes (classes, functions without any linked memory)
- Exposes a `memory` CLI command group and MCP tools prefixed with `memory_`

## Requirements

- Python 3.10+
- CodeGraphContext >= 0.3.0
- Neo4j >= 5.15

## Installation

```bash
pip install -e plugins/cgc-plugin-memory
```

## MCP tools

| Tool | Description |
|---|---|
| `memory_store` | Persist a knowledge entry, optionally linking it to a code node |
| `memory_search` | Full-text search across stored memory entries |
| `memory_undocumented` | List code nodes that have no linked memory entries |
| `memory_link` | Create a `DESCRIBES` edge between an existing memory entry and a code node |

## Entry points

| Group | Name | Target |
|---|---|---|
| `cgc_cli_plugins` | `memory` | `cgc_plugin_memory.cli:get_plugin_commands` |
| `cgc_mcp_plugins` | `memory` | `cgc_plugin_memory.mcp_tools:get_mcp_tools` |
