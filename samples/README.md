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

# 2. Wait for Neo4j to become healthy (~30s)
docker compose logs -f neo4j   # wait for "Started", then Ctrl+C

# 3. Start a CGC indexer container (stays alive for indexing commands)
docker run --rm -d --name cgc-core-indexer \
  --network samples_cgc-network \
  -e DATABASE_TYPE=neo4j \
  -e NEO4J_URI=bolt://neo4j:7687 \
  -e NEO4J_USERNAME=neo4j \
  -e NEO4J_PASSWORD=codegraph123 \
  -v "$(cd .. && pwd)":/workspace \
  samples-cgc-core:latest sleep 3600

# 4. Index all three sample apps
docker exec cgc-core-indexer cgc index /workspace/samples/php-laravel --database-type neo4j
docker exec cgc-core-indexer cgc index /workspace/samples/python-fastapi --database-type neo4j
docker exec cgc-core-indexer cgc index /workspace/samples/ts-express-gateway --database-type neo4j

# 5. Generate traffic (sends requests to all sample app routes)
for i in 1 2 3; do
  curl -sf http://localhost:8080/api/orders > /dev/null
  curl -sf -X POST http://localhost:8080/api/orders \
    -H "Content-Type: application/json" -d "{\"name\":\"order-$i\",\"quantity\":$i}" > /dev/null
  curl -sf http://localhost:8081/api/orders > /dev/null
  curl -sf -X POST http://localhost:8081/api/orders \
    -H "Content-Type: application/json" -d "{\"name\":\"order-$i\",\"quantity\":$i}" > /dev/null
  curl -sf http://localhost:8082/api/dashboard > /dev/null
  curl -sf http://localhost:8082/api/orders > /dev/null
done

# 6. Wait ~15s for span ingestion, then explore at http://localhost:7474
#    (user: neo4j, password: codegraph123)

# Or run the automated smoke test:
bash smoke-all.sh
```

### Automated Smoke Test

The smoke script automates steps 3-6 above. It checks for the `cgc-core-indexer`
container and uses it for indexing. If the container isn't running, it prints
instructions for starting it.

```bash
bash smoke-all.sh
```

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

## Known Limitations

See [KNOWN-LIMITATIONS.md](KNOWN-LIMITATIONS.md) for documentation of the FQN
correlation gap — `CORRELATES_TO` edges between OTEL spans and static code nodes
will not form until FQN computation is added to the graph builder.

## Cleanup

```bash
cd samples/
docker compose down -v   # removes containers and volumes
```
