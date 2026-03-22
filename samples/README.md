# CGC Sample Applications

Three sample apps demonstrating the full CGC plugin pipeline: **index code → run
instrumented app → generate OTEL spans → query cross-layer graph**.

## Architecture

```
                    ┌──────────────────────────────────────────┐
                    │          docker compose up               │
                    └──────────────────────────────────────────┘
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          │                           │                           │
   ┌──────▼──────┐           ┌───────▼───────┐          ┌───────▼────────┐
   │  PHP/Laravel │           │ Python/FastAPI │          │  TS/Express    │
   │  :8080       │           │  :8081         │          │  Gateway :8082 │
   │  OTEL+Xdebug │          │  OTEL          │          │  OTEL          │
   └──────┬──────┘           └───────┬───────┘          └───┬────┬───────┘
          │ spans                    │ spans          spans │    │ HTTP
          │                          │                      │    │ (cross-service)
          └──────────┬───────────────┴──────────────────────┘    │
                     │                                           │
              ┌──────▼──────┐                          ┌────────▼────────┐
              │    OTEL     │                          │  PHP + Python   │
              │  Collector  │                          │  backends       │
              │  :4317/4318 │                          │  (called by GW) │
              └──────┬──────┘                          └─────────────────┘
                     │
              ┌──────▼──────┐
              │  CGC OTEL   │
              │  Processor  │
              │  :5317      │
              └──────┬──────┘
                     │ MERGE
              ┌──────▼──────┐
              │   Neo4j     │
              │  :7474/7687 │
              │  (graph)    │
              └─────────────┘
```

## Prerequisites

- Docker and Docker Compose v2+
- ~2 GB RAM available for all containers

No local CGC install required — indexing runs inside a container.

## Quick Start

```bash
# From the repository root:
cd samples/

# 1. Build and start everything (Neo4j + OTEL stack + 3 sample apps)
docker compose up -d --build

# 2. Index all three sample apps (one-shot container, no local install needed)
docker compose run --rm indexer

# 3. Run the automated smoke test (generates traffic + validates graph)
bash smoke-all.sh

# 4. Explore at http://localhost:7474 (neo4j / codegraph123)
```

That's it — no local CGC install, no manual container management.

## What the Smoke Script Does

| Phase | Action |
|-------|--------|
| 1. Wait | Polls `/health` on all services until ready (timeout: 120s) |
| 2. Index | Runs `cgc index` on each sample app directory |
| 3. Traffic | Sends GET/POST requests to all routes |
| 4. Ingest | Waits 15s for spans to flow through collector → processor → Neo4j |
| 5. Assert | Runs 7 Cypher assertions against the graph |
| 6. Summary | Reports PASS/WARN/FAIL counts |

## Sample Apps

### PHP/Laravel (`:8080`)

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/orders` | GET | List orders |
| `/api/orders` | POST | Create order (`{"name": "...", "quantity": N}`) |
| `/health` | GET | Health check |

Exercises both OTEL and Xdebug plugins. PHP FQN format:
`App\Http\Controllers\OrderController::index`.

### Python/FastAPI (`:8081`)

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/orders` | GET | List orders |
| `/api/orders` | POST | Create order (`{"name": "...", "quantity": N}`) |
| `/health` | GET | Health check |

Exercises OTEL with Python conventions. Python FQN format:
`app.services.order_service.OrderService.list_orders`.

### TypeScript/Express Gateway (`:8082`)

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/dashboard` | GET | Aggregates from PHP + Python backends |
| `/api/orders` | GET | Proxies to PHP backend |
| `/api/orders` | POST | Proxies to PHP backend |
| `/health` | GET | Health check |

Exercises OTEL cross-service tracing. Gateway calls produce CLIENT spans with
`peer.service` attributes → `CALLS_SERVICE` edges in the graph.

## Exploring the Graph

After running the smoke script, open Neo4j Browser at http://localhost:7474
(user: `neo4j`, password: `codegraph123`) and try:

```cypher
-- All services
MATCH (s:Service) RETURN s;

-- Spans for /api/orders
MATCH (sp:Span) WHERE sp.http_route CONTAINS '/api/orders'
RETURN sp.service_name, sp.http_route, sp.duration_ms
LIMIT 20;

-- Cross-service call graph
MATCH (sp:Span)-[:CALLS_SERVICE]->(svc:Service)
RETURN sp.service_name AS caller, svc.name AS callee, count(*) AS calls;

-- Full trace visualization
MATCH path = (sp:Span)-[:PART_OF]->(t:Trace)
RETURN path LIMIT 50;

-- Static code indexed from samples
MATCH (f:Function) WHERE f.path CONTAINS 'samples/'
RETURN f.name, f.path LIMIT 20;
```

## Hosted MCP Server (Optional)

The sample stack includes a `cgc-mcp` service that runs the CGC MCP server
over HTTP on port 8045. It is disabled by default so it does not interfere with
the plugin pipeline demo. To start it alongside the rest of the stack, use the
`mcp` Docker Compose profile:

```bash
# Start the full sample stack plus the hosted MCP server
docker compose --profile mcp up -d --build

# Or start only the MCP server after the stack is already running
docker compose --profile mcp up -d cgc-mcp
```

Once running, point any MCP-capable AI client (Claude Desktop, VS Code, Cursor,
Claude Code) at `http://localhost:8045/mcp`. The server exposes the same tools
as the local stdio mode plus the OTEL and Xdebug plugin tools bundled in the
`cgc-mcp` image. For reverse-proxy auth, TLS configuration, Kubernetes
manifests, and full client setup instructions see
[docs/docs/deployment/MCP_SERVER_HOSTING.md](../docs/docs/deployment/MCP_SERVER_HOSTING.md).

## Known Limitations

See [KNOWN-LIMITATIONS.md](KNOWN-LIMITATIONS.md) for documentation of the FQN
correlation gap — `CORRELATES_TO` edges between OTEL spans and static code nodes
will not form until FQN computation is added to the graph builder.

## Cleanup

```bash
cd samples/
docker compose down -v   # removes containers and volumes
```
