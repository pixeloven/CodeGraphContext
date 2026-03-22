# Manual Testing Guide — CGC Plugin Stack

Step-by-step instructions for spinning up the full plugin stack locally and verifying
each plugin works end-to-end.

---

## Prerequisites

- Docker + Docker Compose v2 (`docker compose version`)
- Python 3.10+ and pip (for CLI testing without Docker)
- `grpcurl` (optional, for OTEL gRPC smoke test — `brew install grpcurl`)
- A PHP application with OpenTelemetry SDK installed (for OTEL live test — optional)

---

## Option A: Docker Stack (Recommended)

### 1. Start the stack

```bash
cp .env.example .env
# .env defaults work for local testing — change NEO4J_PASSWORD for anything non-local

docker compose -f docker-compose.plugin-stack.yml up -d --build
```

Watch startup (Neo4j takes ~30s):
```bash
docker compose -f docker-compose.plugin-stack.yml logs -f
```

### 2. Verify all services are healthy

```bash
docker compose -f docker-compose.plugin-stack.yml ps
```

Expected: all services show `healthy` or `running`.

| Service | Port | Check |
|---|---|---|
| neo4j | 7474, 7687 | http://localhost:7474 → Neo4j Browser |
| cgc-otel-processor | 5317 | `docker logs cgc-otel-processor` → no errors |
| otel-collector | 4317, 4318 | `docker logs cgc-otel-collector` → "Everything is ready" |

### 3. Verify graph schema initialized

Open http://localhost:7474, login (neo4j / codegraph123), run:

```cypher
SHOW CONSTRAINTS
```

Expected: `service_name`, `trace_id`, `span_id`, `frame_id` constraints present.

```cypher
SHOW INDEXES
```

---

## Option B: Python (No Docker)

Install everything editable in a venv:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
pip install -e plugins/cgc-plugin-stub
pip install -e plugins/cgc-plugin-otel
pip install -e plugins/cgc-plugin-xdebug
```

Verify plugin discovery:
```bash
PYTHONPATH=src cgc plugin list
# Should show all four plugins as "loaded"

PYTHONPATH=src cgc --help
# Should show: stub, otel, xdebug command groups
```

---

## Testing Each Plugin

### Stub Plugin (smoke test — no DB needed)

```bash
# CLI
PYTHONPATH=src cgc stub hello
# Expected: "Hello from stub plugin"

PYTHONPATH=src cgc stub hello --name "Alice"
# Expected: "Hello Alice from stub plugin"
```

Via pytest (no install needed for mocked path):
```bash
PYTHONPATH=src pytest tests/unit/plugin/test_plugin_registry.py -v
```

---

### OTEL Plugin

**Requires**: Neo4j + `cgc-otel-processor` + `otel-collector` running.

#### Send a synthetic span

Using `grpcurl` (easiest):
```bash
# Check collector is accepting connections
grpcurl -plaintext localhost:4317 list
# Expected: opentelemetry.proto.collector.trace.v1.TraceService
```

Using a Python script:
```bash
python docs/plugins/examples/send_test_span.py
# See docs/plugins/examples/ for this script
```

#### Configure a PHP/Laravel app

Add to your app's `.env`:
```ini
OTEL_PHP_AUTOLOAD_ENABLED=true
OTEL_SERVICE_NAME=my-laravel-app
OTEL_TRACES_EXPORTER=otlp
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

Send a request to your app, then query:
```bash
PYTHONPATH=src cgc otel query-spans --route "/api/orders" --limit 5
PYTHONPATH=src cgc otel list-services
```

Verify in Neo4j Browser:
```cypher
MATCH (s:Service) RETURN s.name
MATCH (sp:Span) RETURN sp.name, sp.duration_ms, sp.http_route LIMIT 10
MATCH (sp:Span)-[:CORRELATES_TO]->(m:Method) RETURN sp.name, m.fqn LIMIT 10
```

---

### Xdebug Plugin

**Requires**: Neo4j + PHP with Xdebug installed.

Start the listener (Docker):
```bash
docker compose -f docker-compose.plugin-stack.yml -f docker-compose.dev.yml up -d xdebug-listener
docker logs cgc-xdebug-listener -f
# Expected: "DBGp server listening on 0.0.0.0:9003"
```

Start the listener (Python):
```bash
CGC_PLUGIN_XDEBUG_ENABLED=true PYTHONPATH=src cgc xdebug start
```

Configure PHP (`php.ini` or `.env`):
```ini
xdebug.mode=debug
xdebug.client_host=localhost
xdebug.client_port=9003
xdebug.start_with_request=trigger
```

Trigger a trace by setting the `XDEBUG_TRIGGER` cookie in your browser, then:
```bash
PYTHONPATH=src cgc xdebug list-chains --limit 10
PYTHONPATH=src cgc xdebug status
```

Verify in Neo4j Browser:
```cypher
MATCH (sf:StackFrame) RETURN sf.class_name, sf.method_name, sf.observation_count LIMIT 20
MATCH (sf:StackFrame)-[:CALLED_BY]->(parent:StackFrame) RETURN sf.method_name, parent.method_name LIMIT 10
MATCH (sf:StackFrame)-[:RESOLVES_TO]->(m:Method) RETURN sf.method_name, m.fqn LIMIT 10
```

---

## Cross-Layer Validation

After running all plugins with real data, validate the cross-layer queries:

```bash
# Execution path for a route
PYTHONPATH=src cgc query "
MATCH (s:Span {http_route: '/api/orders'})-[:CORRELATES_TO]->(m:Method)
RETURN m.fqn, count(s) AS executions, avg(s.duration_ms) AS avg_duration_ms
ORDER BY executions DESC LIMIT 10
"

# Static code never observed at runtime
PYTHONPATH=src cgc query "
MATCH (m:Method)
WHERE NOT EXISTS { MATCH (m)<-[:CORRELATES_TO]-(:Span) }
  AND NOT EXISTS { MATCH (m)<-[:RESOLVES_TO]-(:StackFrame) }
RETURN m.fqn, m.class_name LIMIT 10
"
```

See `docs/plugins/cross-layer-queries.md` for canonical queries.

---

## Teardown

```bash
# Stop all services
docker compose -f docker-compose.plugin-stack.yml down

# Remove volumes (clears Neo4j data)
docker compose -f docker-compose.plugin-stack.yml down -v
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `service_healthy` wait times out | Neo4j slow to start | Increase `start_period` in healthcheck or wait longer |
| `cgc plugin list` shows plugin as failed | Plugin not installed | `pip install -e plugins/cgc-plugin-<name>` |
| Spans sent but no graph nodes | Filter routes dropping them | Check `OTEL_FILTER_ROUTES`; default drops `/health` etc. |
| Xdebug not connecting | Wrong `client_host` | Use Docker host IP, not `localhost`, when PHP is in Docker |
