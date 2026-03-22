# Quickstart: CGC Plugin Extension System

**Feature**: 001-cgc-plugin-extension
**Audience**: Developers setting up CGC-X locally and contributors building plugins

---

## Prerequisites

- Python 3.10+
- pip / virtualenv
- Docker + Docker Compose (for container services)
- A running Neo4j instance (or use the provided docker-compose)

---

## 1. Run the Full CGC-X Stack (Docker Compose)

The fastest way to get the full stack running:

```bash
# Clone the repo
git clone https://github.com/CodeGraphContext/CodeGraphContext
cd CodeGraphContext

# Copy and configure environment
cp .env.example .env
# Edit .env: set NEO4J_PASSWORD and DOMAIN

# Start the plugin stack
docker compose -f docker-compose.plugin-stack.yml up -d

# Start with Xdebug listener (dev profile — adds xdebug service)
docker compose -f docker-compose.plugin-stack.yml -f docker-compose.dev.yml up -d
```

**Services started**:
| Service | URL / Port | Purpose |
|---|---|---|
| Neo4j | bolt://localhost:7687 | Shared graph database |
| CGC core | MCP at localhost:8080 | Static code indexing |
| CGC MCP (HTTP) | http://localhost:8045 | Hosted MCP server (JSON-RPC) |
| OTEL plugin | gRPC at localhost:5317 | Runtime span ingestion |
| Xdebug listener (dev) | TCP at localhost:9003 | Dev-time stack traces |

---

## 2. Install CGC with Plugins (Python — Development Mode)

For local development or when running without Docker:

```bash
# Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install CGC core + all plugins in editable mode
pip install -e .
pip install -e plugins/cgc-plugin-otel
pip install -e plugins/cgc-plugin-xdebug

# Verify plugins loaded
cgc --help
# Should show: otel, xdebug command groups alongside built-in commands
```

**Install specific plugins only** (production use):
```bash
pip install codegraphcontext[otel]    # core + OTEL plugin
pip install codegraphcontext[all]     # core + all plugins
```

---

## 3. Verify Plugin Discovery

```bash
# List all loaded plugins
cgc plugin list

# Expected output:
# ✓ cgc-plugin-otel      v0.1.0   3 tools (otel_query_spans, otel_list_services, otel_cross_layer_query)  3 commands
# ✓ cgc-plugin-xdebug    v0.1.0   2 tools (xdebug_list_chains, xdebug_query_chain)  3 commands (dev only)
```

---

## 4. Index a Repository

```bash
# Index a local PHP/Laravel project
cgc index /path/to/your/laravel-project

# Verify nodes were created
cgc query "MATCH (c:Class) RETURN c.name LIMIT 5"
```

---

## 5. Enable Runtime Intelligence (OTEL Plugin)

Add to your Laravel application's `.env`:
```ini
OTEL_PHP_AUTOLOAD_ENABLED=true
OTEL_SERVICE_NAME=my-service
OTEL_TRACES_EXPORTER=otlp
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

Send a request to your application. Verify spans appear in the graph:
```bash
cgc otel query-spans --route /api/orders --limit 5
```

Or via MCP tool:
```json
{
    "tool": "otel_query_spans",
    "arguments": {"http_route": "/api/orders", "limit": 5}
}
```

---

## 6. Enable Dev-Time Traces (Xdebug Plugin)

Ensure your PHP application has Xdebug installed with these settings:
```ini
xdebug.mode=debug,trace
xdebug.client_host=localhost     ; or Docker host IP
xdebug.client_port=9003
xdebug.start_with_request=trigger
```

Trigger a trace by setting the `XDEBUG_TRIGGER` cookie in your browser, then query:
```bash
cgc xdebug list-chains --limit 10
```

---

## 7. Cross-Layer Query Example

After indexing code + collecting runtime spans, run this cross-layer query to find
static code never observed at runtime:

```bash
cgc query "
MATCH (m:Method)
WHERE NOT EXISTS { MATCH (m)<-[:CORRELATES_TO]-(:Span) }
  AND NOT EXISTS { MATCH (m)<-[:RESOLVES_TO]-(:StackFrame) }
  AND m.fqn IS NOT NULL
RETURN m.fqn, m.class_name
ORDER BY m.class_name, m.fqn
LIMIT 20
"
```

---

## 8. Run the Hosted MCP Server (HTTP Transport)

Deploy the MCP server as a network service accessible to multiple AI clients:

```bash
# Start the MCP server with HTTP transport via Docker Compose
docker compose -f docker-compose.plugin-stack.yml up -d cgc-mcp neo4j

# Verify the server is healthy
curl http://localhost:8045/healthz
# Expected: {"status":"ok","tools":N}

# Send an MCP request (initialize)
curl -X POST http://localhost:8045/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'

# List available tools
curl -X POST http://localhost:8045/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

**Or run locally without Docker**:
```bash
# Start MCP server in HTTP mode (default port 8045)
cgc mcp start --transport http

# Configure AI clients to connect to http://localhost:8045/mcp
```

**Notes**:
- No application-level authentication — use a reverse proxy or network controls for access management
- CORS is configurable via `CGC_CORS_ORIGIN` env var (default: `*`)
- `/healthz` returns 503 when Neo4j is unreachable

---

## 9. Build and Push Container Images

```bash
# Trigger a release build (creates all plugin images)
git tag v0.1.0
git push origin v0.1.0
# GitHub Actions automatically builds and pushes:
# ghcr.io/<org>/cgc-core:0.1.0
# ghcr.io/<org>/cgc-plugin-otel:0.1.0

# Monitor at: github.com/<org>/CodeGraphContext/actions
```

---

## 10. Write Your Own Plugin

```bash
# Use the plugin scaffold (coming in a future task)
# For now, copy the stub plugin:
cp -r plugins/cgc-plugin-stub plugins/cgc-plugin-myname

# Edit pyproject.toml: change name, entry points, dependencies
# Edit src/cgc_plugin_myname/__init__.py: update PLUGIN_METADATA
# Implement cli.py and mcp_tools.py following the plugin-interface.md contract
# Install and test:
pip install -e plugins/cgc-plugin-myname
cgc plugin list   # Should show your plugin
```

See `specs/001-cgc-plugin-extension/contracts/plugin-interface.md` for the full
plugin contract specification.
