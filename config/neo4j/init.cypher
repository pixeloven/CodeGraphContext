// CGC Plugin Extension — Graph Schema Initialization
// Run this against Neo4j after startup to create all constraints and indexes.
// Idempotent: uses IF NOT EXISTS throughout.

// ── OTEL Plugin: Service nodes ─────────────────────────────────────────────
CREATE CONSTRAINT service_name IF NOT EXISTS
  FOR (s:Service) REQUIRE s.name IS UNIQUE;

// ── OTEL Plugin: Trace nodes ───────────────────────────────────────────────
CREATE CONSTRAINT trace_id IF NOT EXISTS
  FOR (t:Trace) REQUIRE t.trace_id IS UNIQUE;

// ── OTEL Plugin: Span nodes ────────────────────────────────────────────────
CREATE CONSTRAINT span_id IF NOT EXISTS
  FOR (s:Span) REQUIRE s.span_id IS UNIQUE;

CREATE INDEX span_trace IF NOT EXISTS
  FOR (s:Span) ON (s.trace_id);

CREATE INDEX span_class IF NOT EXISTS
  FOR (s:Span) ON (s.class_name);

CREATE INDEX span_route IF NOT EXISTS
  FOR (s:Span) ON (s.http_route);

// ── Xdebug Plugin: StackFrame nodes ───────────────────────────────────────
CREATE CONSTRAINT frame_id IF NOT EXISTS
  FOR (sf:StackFrame) REQUIRE sf.frame_id IS UNIQUE;

CREATE INDEX frame_fqn IF NOT EXISTS
  FOR (sf:StackFrame) ON (sf.fqn);
