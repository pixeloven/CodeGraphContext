# Sample Apps Validation Report

**Date**: 2026-03-20
**Branch**: `001-cgc-plugin-extension`
**Neo4j**: 2026.02.2
**Stack**: 3 sample apps + OTEL Collector + OTEL Processor + Xdebug Listener + Neo4j

## Graph Summary

| Node Type | Count | Source |
|-----------|-------|--------|
| Span | 362 | OTEL plugin (runtime) |
| Variable | 110 | CGC indexer (static) |
| Trace | 67 | OTEL plugin (runtime) |
| Function | 32 | CGC indexer (static) |
| File | 28 | CGC indexer (static) |
| Module | 28 | CGC indexer (static) |
| Directory | 17 | CGC indexer (static) |
| Parameter | 16 | CGC indexer (static) |
| Class | 14 | CGC indexer (static) |
| Service | 3 | OTEL plugin (runtime) |
| Repository | 3 | CGC indexer (static) |
| Interface | 2 | CGC indexer (static) |

| Relationship | Count | Source |
|-------------|-------|--------|
| PART_OF | 362 | Span → Trace |
| ORIGINATED_FROM | 362 | Span → Service |
| CONTAINS | 232 | File/Class/Module containment |
| IMPORTS | 35 | Module imports |
| CALLS | 33 | Static function calls |
| CALLS_SERVICE | 20 | Cross-service CLIENT spans |
| HAS_PARAMETER | 17 | Function parameters |
| CHILD_OF | 7 | Distributed trace parent-child |
| CORRELATES_TO | 0 | Runtime → Static (broken) |

---

## What Works

### Static Analysis (CGC Indexer)

The indexer correctly identifies the Controller → Service → Repository architecture
across all three apps. The full static call graph is visible:

**PHP/Laravel** (13 functions, 6 classes):
```
OrderController.index → OrderService.listOrders → OrderRepository.findAll
OrderController.store → OrderService.createOrder → OrderRepository.create
OrderRepository.__construct → OrderRepository.ensureTableExists
```

**Python/FastAPI** (11 functions, 4 classes):
```
list_orders (router) → OrderService.list_orders → OrderRepository.find_all
create_order (router) → OrderService.create_order → OrderRepository.create
lifespan → OrderRepository.init_db
```

**TypeScript/Express** (8 functions, 4 classes):
```
DashboardService.getDashboard → httpGet (×2, one per backend)
ProxyService.proxyGet → httpRequest
ProxyService.proxyPost → httpRequest
```

### Runtime Intelligence (OTEL Plugin)

Three services discovered with accurate traffic attribution:

| Service | Spans | Span Kinds |
|---------|-------|------------|
| sample-ts-gateway | 239 | 180 INTERNAL, 32 CLIENT, 27 SERVER |
| sample-python | 83 | 59 INTERNAL, 24 SERVER |
| sample-php | 40 | 40 SERVER |

**Route-level performance**:

| Service | Route | Avg Latency | Requests |
|---------|-------|-------------|----------|
| sample-python | /api/orders GET | 1.09 ms | 21 |
| sample-php | api/orders | 12.52 ms | 36 |
| sample-ts-gateway | /api/orders GET | 54.10 ms | 12 |
| sample-ts-gateway | /api/dashboard GET | 54.43 ms | 15 |

The gateway routes are ~54ms because they proxy to backends — this is correctly
reflected in the latency data and explainable by the cross-service call graph.

### Cross-Service Topology (CALLS_SERVICE)

The OTEL plugin correctly identifies service-to-service dependencies:

```
sample-ts-gateway → sample-php     (13 calls, 51ms avg)
sample-ts-gateway → sample-python  (7 calls, 3ms avg)
```

This reveals that the gateway is a fan-out aggregator and that the PHP backend
is significantly slower than the Python backend (51ms vs 3ms for the same
GET operation).

### Distributed Trace Linking (CHILD_OF)

Parent-child span relationships work across services:

```
sample-ts-gateway: GET /api/dashboard
  └─ sample-ts-gateway: GET (CLIENT → sample-php)
  └─ sample-ts-gateway: GET (CLIENT → sample-python)
       └─ sample-python: GET /api/orders (SERVER)
```

---

## What Doesn't Work

### Cross-Layer Correlation (CORRELATES_TO): 0 edges

**This is the documented FQN gap.** Runtime spans and static code nodes exist as
disconnected islands in the graph. No edges connect them.

**Root cause (two-fold)**:

1. **Graph builder stores `Function` nodes without `fqn` property.**
   The OTEL writer attempts `MATCH (m:Method {fqn: sp.fqn})` but:
   - Static nodes are labeled `Function`, not `Method`
   - No `fqn` property exists on static nodes
   - See `src/codegraphcontext/tools/graph_builder.py:379`

2. **OTEL auto-instrumentation doesn't emit `code.namespace` / `code.function`.**
   The standard auto-instrumentation libraries for PHP, Python, and Node.js
   produce span names like `GET /api/orders` and `middleware - jsonParser` —
   not function-level code attributes. All spans have `class_name: null`,
   `function_name: null`, `fqn: null`.

**Impact**: Queries that attempt to answer "which code paths are never executed
at runtime" report ALL functions as unobserved, which is misleading since the
services are clearly running and handling traffic.

### Queries That Return Misleading Results

**"Functions never observed at runtime"** — returns all 32 functions because
no correlation edges exist. This is the primary use case that cross-layer
queries are meant to serve, and it produces false negatives today.

**"Class activity status"** — reports all 14 classes as DORMANT despite the
services actively processing requests. Same root cause.

**"Gateway route → backend dependency map"** via SERVER spans → CALLS_SERVICE
join returns empty because the CALLS_SERVICE edges are on CLIENT spans, not
SERVER spans. This is a query design issue, not a data issue — querying
CLIENT spans directly works correctly.

---

## Smoke Script Results

```
Phase 5: Running assertions...
  PASS: service_count = 3 (>= 3)
  PASS: span_orders = 16 (> 0)
  PASS: static_functions = 27 (> 0)
  PASS: static_classes = 12 (> 0)
  PASS: cross_service > 0
  PASS: trace_links = 106 (> 0)
  WARN: correlates_to = 0 (known FQN gap)
```

6 PASS, 1 WARN, 0 FAIL.

---

## Recommendations for Future Work

### To fix cross-layer correlation (separate story):

1. Add FQN computation to graph builder — combine path, class name, and function
   name into a language-appropriate FQN property on Function/Method nodes
2. Add custom OTEL instrumentation hooks to emit `code.namespace` and
   `code.function` attributes (or compute FQN from span name + service context)
3. Change the CORRELATES_TO query to match `Function` nodes (not just `Method`)

### To improve the sample apps:

1. Add custom PHP OTEL hook to populate `code.namespace`/`code.function` from
   Laravel route resolution
2. Add Python OTEL hook using `opentelemetry-instrumentation-fastapi` to emit
   code attributes from route handlers
3. Consider adding `peer.service` to the OTEL Collector config via a processor
   rather than hardcoding in the gateway instrumentation

### To improve the OTEL plugin:

1. Accept `net.peer.name` as a fallback for `peer.service` in cross-service
   detection (the HTTP instrumentation sets `net.peer.name` even without
   `peer.service`)
2. Add a span attribute for the target URL so that cross-service calls can be
   correlated even without explicit `peer.service`
