# Cross-Layer Cypher Queries

These five canonical queries validate **SC-005** (cross-layer intelligence) by joining
static code analysis nodes (Class, Method) with runtime nodes (Span, StackFrame) and
project knowledge nodes (Memory, Observation).

All queries assume:
- CGC has indexed a PHP/Laravel repository (Method, Class, File nodes exist)
- OTEL or Xdebug plugin has written at least some runtime data
- Memory plugin has stored at least some project knowledge entries

---

## 1. Execution Path for a Route

Find every method observed at runtime for a given HTTP route, ordered by frequency.

```cypher
MATCH (s:Span {http_route: "/api/orders"})-[:CORRELATES_TO]->(m:Method)
RETURN
  m.fqn                  AS method,
  m.class_name           AS class,
  count(s)               AS executions,
  avg(s.duration_ms)     AS avg_duration_ms
ORDER BY executions DESC
LIMIT 20
```

**Expected result schema**:

| Column | Type | Description |
|--------|------|-------------|
| `method` | string | Fully-qualified method name, e.g. `App\Http\Controllers\OrderController::store` |
| `class` | string | Class name |
| `executions` | int | Number of spans that correlated to this method |
| `avg_duration_ms` | float | Average span duration in milliseconds |

---

## 2. Recently Executed Methods With No Spec

Identify code that has been observed at runtime but has no Memory/Observation linked to it.
Useful for finding undocumented hot paths.

```cypher
MATCH (m:Method)<-[:CORRELATES_TO]-(s:Span)
WHERE NOT EXISTS {
  MATCH (mem:Memory)-[:DESCRIBES]->(m)
}
RETURN
  m.fqn                  AS method,
  count(s)               AS executions,
  max(s.start_time_ns)   AS last_seen_ns
ORDER BY executions DESC
LIMIT 20
```

**Expected result schema**:

| Column | Type | Description |
|--------|------|-------------|
| `method` | string | FQN of the method |
| `executions` | int | Total observed executions |
| `last_seen_ns` | int | Unix nanosecond timestamp of most recent span |

---

## 3. Cross-Service Call Chains

Trace spans that exit the local service boundary (CLIENT kind with `peer.service` set),
showing the full service-to-service call path.

```cypher
MATCH path = (caller:Span)-[:CALLS_SERVICE]->(callee:Service)
MATCH (caller)-[:PART_OF]->(t:Trace)
MATCH (caller)-[:ORIGINATED_FROM]->(src:Service)
RETURN
  src.name               AS from_service,
  callee.name            AS to_service,
  caller.name            AS span_name,
  caller.duration_ms     AS duration_ms,
  t.trace_id             AS trace_id
ORDER BY caller.start_time_ns DESC
LIMIT 25
```

**Expected result schema**:

| Column | Type | Description |
|--------|------|-------------|
| `from_service` | string | Originating service name |
| `to_service` | string | Called downstream service name |
| `span_name` | string | Name of the CLIENT span |
| `duration_ms` | float | Duration of the outbound call |
| `trace_id` | string | Trace identifier |

---

## 4. Specs Describing Recently-Active Code

Show Memory entries that describe code observed at runtime in the last N spans.
Surfaces "well-documented hot paths".

```cypher
MATCH (mem:Memory)-[:DESCRIBES]->(m:Method)<-[:CORRELATES_TO]-(s:Span)
RETURN
  mem.name               AS spec_name,
  mem.entity_type        AS spec_type,
  m.fqn                  AS method,
  count(s)               AS executions,
  collect(DISTINCT mem.content)[0..1][0] AS spec_excerpt
ORDER BY executions DESC
LIMIT 20
```

**Expected result schema**:

| Column | Type | Description |
|--------|------|-------------|
| `spec_name` | string | Memory node name |
| `spec_type` | string | Entity type (e.g. `spec`, `note`, `adr`) |
| `method` | string | FQN of the described method |
| `executions` | int | Runtime execution count |
| `spec_excerpt` | string | First 0–1 items of content for context |

---

## 5. Static Code Never Observed at Runtime

Find Method nodes with no CORRELATES_TO span and no StackFrame. Surfaces dead code
candidates or code paths never triggered in the current environment.

```cypher
MATCH (m:Method)
WHERE NOT EXISTS { MATCH (m)<-[:CORRELATES_TO]-(:Span) }
  AND NOT EXISTS { MATCH (m)<-[:RESOLVES_TO]-(:StackFrame) }
  AND m.fqn IS NOT NULL
RETURN
  m.fqn                  AS method,
  m.class_name           AS class,
  m.file_path            AS file
ORDER BY m.class_name, m.fqn
LIMIT 50
```

**Expected result schema**:

| Column | Type | Description |
|--------|------|-------------|
| `method` | string | FQN of method with no observed execution |
| `class` | string | Owning class |
| `file` | string | Source file path |

---

## Running These Queries

Via CGC CLI:

```bash
cgc query "MATCH (m:Method)<-[:CORRELATES_TO]-(s:Span) WHERE NOT EXISTS { MATCH (mem:Memory)-[:DESCRIBES]->(m) } RETURN m.fqn, count(s) AS executions ORDER BY executions DESC LIMIT 20"
```

Via MCP tool (`otel_cross_layer_query`):

```json
{
  "tool": "otel_cross_layer_query",
  "arguments": {"query_type": "unspecced_running_code"}
}
```

Via Neo4j Browser: connect to `bolt://localhost:7687` and paste any query above.
