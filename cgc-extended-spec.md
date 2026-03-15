# CodeGraphContext-Extended (CGC-X)
## Requirements, Specification & Development Plan

---

## 1. Project Overview

**CodeGraphContext-Extended (CGC-X)** builds on top of the existing [CodeGraphContext](https://github.com/CodeGraphContext/CodeGraphContext) project, extending it with two additional data ingestion pipelines and bundling all components into a single, cohesive Docker Compose deployment. The result is a unified Neo4j knowledge graph that combines three complementary layers of understanding about a codebase.

### The Three Layers

| Layer | Source | What It Tells You |
|---|---|---|
| **Static** | CGC (existing) | Code structure — classes, methods, relationships as written |
| **Runtime** | OTEL + Xdebug (new) | Execution reality — what actually runs, how, across services |
| **Memory** | neo4j-memory MCP (new) | Project knowledge — specs, research, decisions, context |

### Guiding Principles

- **Same Neo4j instance** — all three layers share one database, enabling cross-layer queries
- **Non-invasive** — no required changes to target applications beyond standard OTEL instrumentation
- **Composable** — each service is independently useful; the value multiplies when combined
- **Homelab-friendly** — runs behind a reverse proxy (Traefik), k8s-compatible, self-contained

---

## 2. Repository Structure

```
cgc-extended/
├── docker-compose.yml               # Full stack
├── docker-compose.dev.yml           # Dev overrides (Xdebug enabled)
├── .env.example
├── README.md
│
├── services/
│   ├── otel-processor/              # NEW: OTEL span → Neo4j ingestion
│   │   ├── Dockerfile
│   │   ├── src/
│   │   │   ├── main.py
│   │   │   ├── span_processor.py
│   │   │   ├── neo4j_writer.py
│   │   │   └── schema.py
│   │   └── requirements.txt
│   │
│   └── xdebug-listener/             # NEW: DBGp server → Neo4j ingestion
│       ├── Dockerfile
│       ├── src/
│       │   ├── main.py
│       │   ├── dbgp_server.py
│       │   ├── neo4j_writer.py
│       │   └── schema.py
│       └── requirements.txt
│
├── config/
│   ├── otel-collector/
│   │   └── config.yaml              # OTel Collector pipeline config
│   └── neo4j/
│       └── init.cypher              # Schema constraints & indexes
│
└── docs/
    ├── neo4j-schema.md
    ├── laravel-setup.md
    └── traefik-setup.md
```

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Target Applications               │
│                                                     │
│  Laravel App A          Laravel App B               │
│  (OTEL SDK)             (OTEL SDK + Xdebug)         │
└──────┬───────────────────────┬──────────────────────┘
       │ OTLP (gRPC/HTTP)      │ OTLP + DBGp (9003)
       ▼                       │
┌──────────────┐               │
│ OTel          │               │
│ Collector    │               │
└──────┬───────┘               │
       │ OTLP (forwarded)      │
       ▼                       ▼
┌────────────────────────────────────────────────────┐
│               CGC-Extended Stack                   │
│                                                    │
│  ┌─────────────────┐    ┌──────────────────────┐   │
│  │  otel-processor │    │  xdebug-listener     │   │
│  │  (Python)       │    │  (Python, port 9003) │   │
│  └────────┬────────┘    └──────────┬───────────┘   │
│           │                        │               │
│  ┌────────▼────────────────────────▼───────────┐   │
│  │              Neo4j                          │   │
│  │  (shared with CGC static nodes)             │   │
│  └─────────────────────────────────────────────┘   │
│           │                                        │
│  ┌────────▼────────┐    ┌──────────────────────┐   │
│  │  CodeGraphCtx   │    │  neo4j-memory MCP     │   │
│  │  (CGC, static)  │    │  (specs/research)     │   │
│  └─────────────────┘    └──────────────────────┘   │
└────────────────────────────────────────────────────┘
       │
       ▼
  Traefik (reverse proxy)
  → cgc-x.your-domain.com/mcp
  → memory.your-domain.com/mcp
```

---

## 4. Neo4j Unified Schema

All nodes carry a `source` property that identifies their origin. This is the key to cross-layer querying.

### Node Labels

```cypher
// ── STATIC LAYER (CGC existing) ──────────────────────────
(:File       { path, language, repo, indexed_at })
(:Class      { name, fqn, file_path, source: 'static' })
(:Method     { name, fqn, file_path, line, source: 'static' })
(:Function   { name, fqn, file_path, line, source: 'static' })
(:Interface  { name, fqn, source: 'static' })

// ── RUNTIME LAYER (OTEL) ─────────────────────────────────
(:Service    { name, version, environment })
(:Trace      { trace_id, root_span_id, started_at, duration_ms })
(:Span       {
    span_id,
    trace_id,
    name,
    service,
    kind,             // SERVER, CLIENT, INTERNAL, PRODUCER, CONSUMER
    class_name,       // extracted from span attributes
    method_name,      // extracted from span attributes
    http_method,      // for HTTP spans
    http_route,       // for HTTP spans
    db_statement,     // for DB spans
    duration_ms,
    status,
    source: 'runtime_otel'
})

// ── RUNTIME LAYER (Xdebug) ───────────────────────────────
(:StackFrame {
    class_name,
    method_name,
    fqn,
    file_path,
    line,
    depth,
    source: 'runtime_xdebug'
})

// ── MEMORY LAYER (neo4j-memory MCP) ──────────────────────
(:Memory     {
    id,
    name,
    entity_type,      // spec, decision, research, bug, feature, etc.
    created_at,
    updated_at,
    source: 'memory'
})
(:Observation { content, created_at })
```

### Relationship Types

```cypher
// Static
(Method)-[:BELONGS_TO]->(Class)
(Class)-[:IMPLEMENTS]->(Interface)
(Class)-[:EXTENDS]->(Class)
(Method)-[:CALLS]->(Method)
(File)-[:CONTAINS]->(Class)

// Runtime — OTEL
(Span)-[:CHILD_OF]->(Span)
(Span)-[:PART_OF]->(Trace)
(Trace)-[:ORIGINATED_FROM]->(Service)
(Span)-[:CALLS_SERVICE]->(Service)        // cross-service edges

// Runtime — Xdebug
(StackFrame)-[:CALLED_BY]->(StackFrame)
(StackFrame)-[:RESOLVES_TO]->(Method)     // ← links to static layer

// Memory
(Memory)-[:HAS_OBSERVATION]->(Observation)
(Memory)-[:RELATES_TO]->(Memory)
(Memory)-[:DESCRIBES]->(Class)            // ← links to static layer
(Memory)-[:DESCRIBES]->(Method)           // ← links to static layer
(Memory)-[:COVERS]->(Span)               // ← links to runtime layer

// Cross-layer correlation
(Span)-[:CORRELATES_TO]->(Method)         // OTEL span → static method node
```

### Indexes & Constraints

```cypher
-- init.cypher
CREATE CONSTRAINT class_fqn IF NOT EXISTS
  FOR (c:Class) REQUIRE c.fqn IS UNIQUE;

CREATE CONSTRAINT method_fqn IF NOT EXISTS
  FOR (m:Method) REQUIRE m.fqn IS UNIQUE;

CREATE CONSTRAINT span_id IF NOT EXISTS
  FOR (s:Span) REQUIRE s.span_id IS UNIQUE;

CREATE INDEX span_trace IF NOT EXISTS
  FOR (s:Span) ON (s.trace_id);

CREATE INDEX span_class IF NOT EXISTS
  FOR (s:Span) ON (s.class_name);

CREATE FULLTEXT INDEX memory_search IF NOT EXISTS
  FOR (m:Memory) ON EACH [m.name, m.entity_type];

CREATE FULLTEXT INDEX observation_search IF NOT EXISTS
  FOR (o:Observation) ON EACH [o.content];
```

---

## 5. Service Specifications

### 5.1 OTEL Collector (config only, standard image)

No custom code — use `otel/opentelemetry-collector-contrib`.

```yaml
# config/otel-collector/config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 5s
    send_batch_size: 512
  filter/drop_health:             # drop noisy health check spans
    spans:
      exclude:
        match_type: strict
        attributes:
          - key: http.route
            value: /health

exporters:
  otlp/processor:                 # forward to your otel-processor
    endpoint: otel-processor:5317
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch, filter/drop_health]
      exporters: [otlp/processor]
```

**Why a collector?** Decouples the app from your processor. Handles batching, retries, and filtering before spans hit Neo4j. Standard practice — apps just point `OTEL_EXPORTER_OTLP_ENDPOINT` at the collector.

---

### 5.2 OTEL Processor Service

**Language:** Python  
**Base image:** `python:3.12-slim`  
**Port:** 5317 (OTLP gRPC, internal only)

#### Responsibilities

1. Receive spans from the OTel Collector via OTLP
2. Extract structured data (service name, class, method, HTTP route, DB queries)
3. Upsert nodes and relationships into Neo4j
4. Attempt correlation with CGC static nodes by matching `fqn`

#### Key Extraction Logic

Laravel/PHP OTEL spans carry attributes you can parse:

```python
# span_processor.py

def extract_php_context(span) -> dict:
    attrs = span.attributes or {}
    
    # Laravel auto-instrumentation sets these
    code_namespace = attrs.get('code.namespace', '')    # e.g. App\Http\Controllers\OrderController
    code_function  = attrs.get('code.function', '')     # e.g. store
    http_route     = attrs.get('http.route', '')        # e.g. /api/orders
    db_statement   = attrs.get('db.statement', '')
    db_system      = attrs.get('db.system', '')

    fqn = f"{code_namespace}::{code_function}" if code_namespace else None

    return {
        'class_name':   code_namespace,
        'method_name':  code_function,
        'fqn':          fqn,
        'http_route':   http_route,
        'db_statement': db_statement,
        'db_system':    db_system,
    }

def correlate_to_static(tx, span_id: str, fqn: str):
    """
    If CGC has already indexed a Method node with this fqn,
    draw a CORRELATES_TO edge from the Span to that Method.
    """
    tx.run("""
        MATCH (s:Span {span_id: $span_id})
        MATCH (m:Method {fqn: $fqn})
        MERGE (s)-[:CORRELATES_TO]->(m)
    """, span_id=span_id, fqn=fqn)
```

#### Cross-Service Edge Detection

When a span has `kind = CLIENT` and `http.url` or `peer.service` set, create a `CALLS_SERVICE` relationship — this is your cross-project graph edge.

```python
def handle_cross_service(tx, span, context):
    if span.kind == SpanKind.CLIENT:
        peer = span.attributes.get('peer.service') or \
               extract_host(span.attributes.get('http.url', ''))
        if peer:
            tx.run("""
                MERGE (target:Service {name: $peer})
                WITH target
                MATCH (s:Span {span_id: $span_id})
                MERGE (s)-[:CALLS_SERVICE]->(target)
            """, peer=peer, span_id=span.span_id)
```

---

### 5.3 Xdebug Listener Service

**Language:** Python  
**Base image:** `python:3.12-slim`  
**Port:** 9003 (DBGp, exposed — target dev apps connect to this)  
**When to run:** Dev/staging only (excluded from production compose)

#### Responsibilities

1. Run a DBGp TCP server on port 9003
2. Accept Xdebug connections from PHP applications
3. Walk stack frames on each breakpoint/trace event
4. Upsert `StackFrame` nodes and `CALLED_BY` edges
5. Attempt `RESOLVES_TO` correlation to CGC `Method` nodes

#### DBGp Protocol Basics

```
PHP (Xdebug client) ──connects to──> DBGp Server (your listener)

Key commands:
  run          → continue execution
  stack_get    → get current call stack (all frames)
  context_get  → get variables at a given depth
```

#### Recommended Library

Use `python-dbgp` or implement a minimal DBGp server — the protocol is XML over TCP and straightforward:

```python
# dbgp_server.py (simplified)
import socket, xml.etree.ElementTree as ET

class DBGpServer:
    def handle_connection(self, conn):
        # 1. Receive init packet from Xdebug
        init = self.recv_packet(conn)
        
        # 2. Send `run` to let execution proceed to next breakpoint
        self.send_cmd(conn, 'run')
        
        # 3. On each stop, fetch the full stack
        while True:
            response = self.recv_packet(conn)
            if response is None:
                break
            
            self.send_cmd(conn, 'stack_get -i 1')
            stack_xml = self.recv_packet(conn)
            frames = self.parse_stack(stack_xml)
            
            self.write_to_neo4j(frames)
            self.send_cmd(conn, 'run')

    def parse_stack(self, xml_str) -> list[dict]:
        root = ET.fromstring(xml_str)
        frames = []
        for stack in root.findall('stack'):
            frames.append({
                'class':    stack.get('classname', ''),
                'method':   stack.get('where', ''),
                'file':     stack.get('filename', ''),
                'line':     int(stack.get('lineno', 0)),
                'depth':    int(stack.get('level', 0)),
            })
        return frames
```

#### Deduplication Strategy

The same call chain will repeat across thousands of requests. Use a hash of the call chain to deduplicate:

```python
import hashlib

def chain_hash(frames: list[dict]) -> str:
    key = '|'.join(f"{f['class']}::{f['method']}" for f in frames)
    return hashlib.sha256(key.encode()).hexdigest()[:16]

# In neo4j_writer: only upsert if hash not seen recently
# Keep a local LRU cache of recent chain hashes to avoid Neo4j round-trips
```

---

### 5.4 Memory MCP Service

Use the official `mcp/neo4j-memory` Docker image. No custom code required.

**Configuration:**
```yaml
# docker-compose.yml excerpt
cgc-memory:
  image: mcp/neo4j-memory
  environment:
    NEO4J_URL: bolt://neo4j:7687
    NEO4J_USERNAME: neo4j
    NEO4J_PASSWORD: ${NEO4J_PASSWORD}
    NEO4J_DATABASE: neo4j          # same DB as everything else
    NEO4J_MCP_SERVER_HOST: 0.0.0.0
    NEO4J_MCP_SERVER_PORT: 8766
```

**Usage guidance for your team:**

Store the following entity types to get maximum value:
- `spec` — functional requirements, acceptance criteria
- `decision` — architectural decisions with rationale (lightweight ADR)
- `research` — spike findings, library evaluations
- `bug` — known issues, reproduction steps, root cause once found
- `feature` — planned work with context
- `integration` — notes on cross-service contracts and dependencies

When a Memory node `DESCRIBES` a Class or Method that CGC has indexed, the AI assistant can answer questions like: *"Show me the spec for the payment service and which methods implement it."*

---

## 6. Docker Compose

```yaml
# docker-compose.yml
services:

  neo4j:
    image: neo4j:5
    container_name: cgc-neo4j
    restart: unless-stopped
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD}
      NEO4J_PLUGINS: '["apoc"]'
      NEO4J_dbms_memory_heap_max__size: 2G
    volumes:
      - neo4j_data:/data
      - ./config/neo4j/init.cypher:/var/lib/neo4j/import/init.cypher
    ports:
      - "7687:7687"           # Bolt (internal use)
      - "7474:7474"           # Browser (optional, disable in prod)
    healthcheck:
      test: ["CMD", "neo4j", "status"]
      interval: 30s
      timeout: 10s
      retries: 5

  codegraphcontext:
    image: codegraphcontext/codegraphcontext:latest   # or build from source
    container_name: cgc-static
    restart: unless-stopped
    environment:
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USERNAME: neo4j
      NEO4J_PASSWORD: ${NEO4J_PASSWORD}
    depends_on:
      neo4j:
        condition: service_healthy
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.cgc.rule=Host(`cgc.${DOMAIN}`)"

  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    container_name: cgc-otel-collector
    restart: unless-stopped
    volumes:
      - ./config/otel-collector/config.yaml:/etc/otelcol-contrib/config.yaml
    ports:
      - "4317:4317"           # OTLP gRPC (apps send here)
      - "4318:4318"           # OTLP HTTP (apps send here)
    depends_on:
      - otel-processor

  otel-processor:
    build: ./services/otel-processor
    container_name: cgc-otel-processor
    restart: unless-stopped
    environment:
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USERNAME: neo4j
      NEO4J_PASSWORD: ${NEO4J_PASSWORD}
      LISTEN_PORT: 5317
      LOG_LEVEL: INFO
    depends_on:
      neo4j:
        condition: service_healthy

  cgc-memory:
    image: mcp/neo4j-memory
    container_name: cgc-memory
    restart: unless-stopped
    environment:
      NEO4J_URL: bolt://neo4j:7687
      NEO4J_USERNAME: neo4j
      NEO4J_PASSWORD: ${NEO4J_PASSWORD}
      NEO4J_DATABASE: neo4j
      NEO4J_MCP_SERVER_HOST: 0.0.0.0
      NEO4J_MCP_SERVER_PORT: 8766
    depends_on:
      neo4j:
        condition: service_healthy
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.cgc-memory.rule=Host(`memory.${DOMAIN}`)"

volumes:
  neo4j_data:
```

```yaml
# docker-compose.dev.yml (override for development)
services:
  xdebug-listener:
    build: ./services/xdebug-listener
    container_name: cgc-xdebug
    restart: unless-stopped
    environment:
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USERNAME: neo4j
      NEO4J_PASSWORD: ${NEO4J_PASSWORD}
      LISTEN_HOST: 0.0.0.0
      LISTEN_PORT: 9003
      DEDUP_CACHE_SIZE: 10000
      LOG_LEVEL: DEBUG
    ports:
      - "9003:9003"           # DBGp — PHP apps connect to this
    depends_on:
      neo4j:
        condition: service_healthy
```

---

## 7. Laravel Application Setup

### OTEL Instrumentation (Production + Dev)

```bash
composer require \
  open-telemetry/sdk \
  open-telemetry/exporter-otlp \
  open-telemetry/opentelemetry-auto-laravel \
  open-telemetry/opentelemetry-auto-psr18
```

Add to `.env`:
```ini
OTEL_PHP_AUTOLOAD_ENABLED=true
OTEL_SERVICE_NAME=your-service-name
OTEL_TRACES_EXPORTER=otlp
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_EXPORTER_OTLP_ENDPOINT=http://cgc-otel-collector:4317
OTEL_PROPAGATORS=tracecontext,baggage
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=1.0          # 1.0 = 100% in dev, lower in prod
```

Add to `Dockerfile`:
```dockerfile
RUN pecl install opentelemetry
RUN echo "extension=opentelemetry.so" >> /usr/local/etc/php/conf.d/opentelemetry.ini
```

### Xdebug (Dev only)

```dockerfile
# dev.Dockerfile or override
RUN pecl install xdebug
```

```ini
; xdebug.ini
xdebug.mode=debug,trace
xdebug.client_host=cgc-xdebug       ; container name in same Docker network
xdebug.client_port=9003
xdebug.start_with_request=trigger   ; use XDEBUG_TRIGGER header/cookie
; or: xdebug.start_with_request=yes for all requests (noisy)
```

**Recommended:** use `trigger` mode. Set the `XDEBUG_TRIGGER` cookie in your browser to selectively capture traces rather than flooding Neo4j on every request.

---

## 8. Development Phases

### Phase 1 — Foundation (Week 1–2)

Goal: Neo4j running, CGC indexing, schema in place.

- [ ] Set up repository structure
- [ ] Write `config/neo4j/init.cypher` with constraints and indexes
- [ ] Wire up `docker-compose.yml` with Neo4j + CGC + memory MCP
- [ ] Verify CGC indexes a Laravel project into Neo4j
- [ ] Verify `mcp/neo4j-memory` connects to same DB and nodes are queryable
- [ ] Set up Traefik labels and confirm both MCP endpoints are accessible
- [ ] Write `docs/neo4j-schema.md` as living document

**Success criterion:** AI assistant can query static code nodes AND store/retrieve memory entities, in the same Neo4j instance.

---

### Phase 2 — OTEL Processor (Week 2–3)

Goal: Laravel spans flowing into Neo4j, basic cross-layer correlation working.

- [ ] Scaffold `services/otel-processor/` — Python OTLP receiver
- [ ] Implement span → Neo4j upsert for `Span`, `Trace`, `Service` nodes
- [ ] Implement `CHILD_OF` relationship from `parent_span_id`
- [ ] Implement PHP attribute extraction (`code.namespace`, `code.function`)
- [ ] Implement `CORRELATES_TO` correlation against existing CGC `Method` nodes
- [ ] Implement cross-service edge detection (`SpanKind.CLIENT`)
- [ ] Wire `otel-collector` → `otel-processor` in compose
- [ ] Test with a real Laravel app: instrument, send request, verify nodes appear
- [ ] Write `docs/laravel-setup.md`

**Success criterion:** A single HTTP request to the Laravel app produces a complete span tree in Neo4j, with at least some spans connected to static Method nodes.

---

### Phase 3 — Xdebug Listener (Week 3–4)

Goal: Dev-time method-level traces captured and linked to static nodes.

- [ ] Scaffold `services/xdebug-listener/` — Python DBGp server
- [ ] Implement TCP server, DBGp handshake, `stack_get` command
- [ ] Implement stack frame parsing and `StackFrame` node upsert
- [ ] Implement `CALLED_BY` chain from frame depth
- [ ] Implement call chain deduplication (hash + LRU cache)
- [ ] Implement `RESOLVES_TO` correlation to CGC `Method` nodes by `fqn`
- [ ] Wire into `docker-compose.dev.yml`
- [ ] Test: trigger Xdebug on a Laravel request, verify frame graph in Neo4j

**Success criterion:** Xdebug trace for a request shows container-resolved classes (e.g., concrete repository implementation rather than interface) connected to the static graph.

---

### Phase 4 — Cross-Layer Queries & MCP Tooling (Week 4–5)

Goal: The unified graph is queryable in useful ways from an AI assistant.

**Example queries to validate and document:**

```cypher
-- "Show me everything that executes when POST /api/orders is called"
MATCH (s:Span {http_route: '/api/orders', http_method: 'POST'})
MATCH (s)-[:CHILD_OF*1..10]->(child:Span)
OPTIONAL MATCH (child)-[:CORRELATES_TO]->(m:Method)
RETURN s, child, m

-- "Which specs describe code that was called in the last hour?"
MATCH (mem:Memory)-[:DESCRIBES]->(m:Method)
MATCH (s:Span)-[:CORRELATES_TO]->(m)
WHERE s.started_at > timestamp() - 3600000
RETURN mem.name, mem.entity_type, m.fqn, s.name

-- "Show cross-service call chains"
MATCH (svc1:Service)-[:ORIGINATED_FROM]-(t:Trace)-[:PART_OF]-(s:Span)
MATCH (s)-[:CALLS_SERVICE]->(svc2:Service)
RETURN svc1.name, svc2.name, count(*) as call_count
ORDER BY call_count DESC

-- "What code runs that has no spec?"
MATCH (m:Method)<-[:CORRELATES_TO]-(s:Span)
WHERE NOT EXISTS { MATCH (mem:Memory)-[:DESCRIBES]->(m) }
RETURN m.fqn, count(s) as execution_count
ORDER BY execution_count DESC
```

- [ ] Write and test the above canonical queries
- [ ] Document queries in `docs/neo4j-schema.md`
- [ ] Consider a thin MCP wrapper exposing these as named tools (optional)

---

### Phase 5 — Polish & Release (Week 5–6)

- [ ] Write comprehensive `README.md` with architecture diagram
- [ ] Create `.env.example` with all required variables documented
- [ ] Add `CONTRIBUTING.md` with credit to upstream CGC project
- [ ] Add health check endpoints to both custom services
- [ ] Test full stack teardown and restart (data persistence)
- [ ] Test k8s manifests (port from existing homelab patterns)
- [ ] Tag v0.1.0

---

## 9. Environment Variables Reference

```ini
# .env.example

# Neo4j
NEO4J_PASSWORD=changeme
DOMAIN=yourdomain.local

# OTEL Processor
OTEL_PROCESSOR_LOG_LEVEL=INFO
OTEL_PROCESSOR_BATCH_SIZE=100
OTEL_PROCESSOR_FLUSH_INTERVAL=5

# Xdebug Listener (dev only)
XDEBUG_DEDUP_CACHE_SIZE=10000
XDEBUG_MAX_DEPTH=20             # max stack depth to capture

# Memory MCP
# (uses NEO4J_* vars above, no additional config needed)
```

---

## 10. Key Design Decisions

**Why Python for otel-processor and xdebug-listener?**
The `opentelemetry-sdk` Python package has excellent OTLP receiver support and Neo4j's official `neo4j` Python driver is the most mature. Keeps both services consistent.

**Why same Neo4j database (not separate databases)?**
Cross-layer queries require traversing between node types. If CGC static nodes and OTEL span nodes are in different databases, you cannot do `MATCH (s:Span)-[:CORRELATES_TO]->(m:Method)` in a single query. The unified schema with `source` property labels is sufficient to distinguish origins.

**Why the OTel Collector in between?**
Direct OTLP from app → otel-processor works but is fragile. The collector handles batching, retry on failure, and gives you a place to add sampling rules or additional exporters (e.g., Jaeger for visual trace inspection) without touching application config.

**Why `mcp/neo4j-memory` rather than a custom memory service?**
It's maintained, well-documented, and covers the generic memory use case well. The value of CGC-X is the unified graph — not reinventing memory storage.

**Xdebug `trigger` mode rather than `yes` mode?**
`yes` mode captures every request, generating massive graph noise and degrading performance. `trigger` mode lets you selectively capture specific requests using the `XDEBUG_TRIGGER` cookie/header, giving you targeted, high-quality traces.
