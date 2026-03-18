#!/usr/bin/env bash
# smoke-all.sh — Automated end-to-end validation for CGC sample applications.
#
# Runs 6 phases:
#   1. Wait for services to be healthy
#   2. Index sample code via cgc
#   3. Generate HTTP traffic to all sample apps
#   4. Wait for span ingestion
#   5. Assert graph state via Cypher queries
#   6. Print summary
#
# Usage:
#   cd samples/
#   docker compose up -d
#   bash smoke-all.sh
#
# Exit codes:
#   0 — all assertions passed (WARNs are OK)
#   1 — at least one assertion FAILed

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────

NEO4J_URI="${NEO4J_URI:-bolt://localhost:7687}"
NEO4J_USERNAME="${NEO4J_USERNAME:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-codegraph123}"

PHP_URL="${PHP_URL:-http://localhost:8080}"
PYTHON_URL="${PYTHON_URL:-http://localhost:8081}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:8082}"

WAIT_TIMEOUT="${WAIT_TIMEOUT:-120}"   # seconds to wait for services
INGEST_WAIT="${INGEST_WAIT:-15}"      # seconds to wait for span ingestion

# ── Helpers ──────────────────────────────────────────────────────────────────

PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0

pass() { echo "  ✓ PASS: $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
warn() { echo "  ⚠ WARN: $1"; WARN_COUNT=$((WARN_COUNT + 1)); }
fail() { echo "  ✗ FAIL: $1"; FAIL_COUNT=$((FAIL_COUNT + 1)); }

cypher_count() {
    local query="$1"
    # Use cypher-shell if available, otherwise fall back to Neo4j HTTP API
    if command -v cypher-shell &>/dev/null; then
        cypher-shell -u "$NEO4J_USERNAME" -p "$NEO4J_PASSWORD" -a "$NEO4J_URI" \
            --format plain "$query" 2>/dev/null | tail -1 | tr -d '[:space:]'
    else
        # Use Neo4j HTTP API (available at port 7474)
        local http_url="${NEO4J_HTTP_URL:-http://localhost:7474}"
        local result
        result=$(curl -s -X POST "$http_url/db/neo4j/tx/commit" \
            -H "Content-Type: application/json" \
            -u "$NEO4J_USERNAME:$NEO4J_PASSWORD" \
            -d "{\"statements\":[{\"statement\":\"$query\"}]}" 2>/dev/null)
        echo "$result" | python3 -c "
import sys, json
data = json.load(sys.stdin)
rows = data.get('results', [{}])[0].get('data', [])
if rows:
    print(rows[0]['row'][0])
else:
    print(0)
" 2>/dev/null || echo "0"
    fi
}

wait_for_url() {
    local url="$1"
    local name="$2"
    local elapsed=0
    while [ $elapsed -lt "$WAIT_TIMEOUT" ]; do
        if curl -sf "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    echo "  Timed out waiting for $name ($url)"
    return 1
}

# ── Phase 1: Wait for services ──────────────────────────────────────────────

echo "Phase 1: Waiting for services to be healthy..."

wait_for_url "$PHP_URL/health" "PHP/Laravel" || { fail "PHP app not reachable"; }
wait_for_url "$PYTHON_URL/health" "Python/FastAPI" || { fail "Python app not reachable"; }
wait_for_url "$GATEWAY_URL/health" "TS/Express gateway" || { fail "Gateway not reachable"; }
wait_for_url "http://localhost:7474" "Neo4j" || { fail "Neo4j not reachable"; }

echo "  All services responding."
echo

# ── Phase 2: Index sample code ──────────────────────────────────────────────

echo "Phase 2: Indexing sample application code..."

SAMPLES_DIR="$(cd "$(dirname "$0")" && pwd)"

if docker exec cgc-core-indexer cgc --help &>/dev/null 2>&1; then
    # Use the cgc-core container (preferred — no local install needed)
    echo "  Using cgc-core-indexer container..."
    docker exec cgc-core-indexer cgc index /workspace/samples/php-laravel --database-type neo4j 2>/dev/null || true
    docker exec cgc-core-indexer cgc index /workspace/samples/python-fastapi --database-type neo4j 2>/dev/null || true
    docker exec cgc-core-indexer cgc index /workspace/samples/ts-express-gateway --database-type neo4j 2>/dev/null || true
    echo "  Indexing complete."
elif command -v cgc &>/dev/null; then
    # Fall back to local cgc install
    echo "  Using local cgc CLI..."
    cgc index "$SAMPLES_DIR/php-laravel" --database-type neo4j 2>/dev/null || true
    cgc index "$SAMPLES_DIR/python-fastapi" --database-type neo4j 2>/dev/null || true
    cgc index "$SAMPLES_DIR/ts-express-gateway" --database-type neo4j 2>/dev/null || true
    echo "  Indexing complete."
else
    echo "  No cgc available — start the indexer first:"
    echo "    docker run --rm -d --name cgc-core-indexer \\"
    echo "      --network samples_cgc-network \\"
    echo "      -e DATABASE_TYPE=neo4j -e NEO4J_URI=bolt://neo4j:7687 \\"
    echo "      -e NEO4J_USERNAME=neo4j -e NEO4J_PASSWORD=codegraph123 \\"
    echo "      -v \$(cd .. && pwd):/workspace \\"
    echo "      samples-cgc-core:latest sleep 3600"
    echo "  Then re-run this script."
    fail "cgc indexer not available"
fi
echo

# ── Phase 3: Generate traffic ────────────────────────────────────────────────

echo "Phase 3: Generating HTTP traffic to sample apps..."

# PHP app
curl -sf "$PHP_URL/api/orders" >/dev/null 2>&1 || true
curl -sf -X POST "$PHP_URL/api/orders" \
    -H "Content-Type: application/json" \
    -d '{"name":"test-order","quantity":1}' >/dev/null 2>&1 || true
curl -sf "$PHP_URL/api/orders" >/dev/null 2>&1 || true

# Python app
curl -sf "$PYTHON_URL/api/orders" >/dev/null 2>&1 || true
curl -sf -X POST "$PYTHON_URL/api/orders" \
    -H "Content-Type: application/json" \
    -d '{"name":"test-order","quantity":2}' >/dev/null 2>&1 || true
curl -sf "$PYTHON_URL/api/orders" >/dev/null 2>&1 || true

# TS gateway (triggers cross-service calls)
curl -sf "$GATEWAY_URL/api/orders" >/dev/null 2>&1 || true
curl -sf "$GATEWAY_URL/api/dashboard" >/dev/null 2>&1 || true
curl -sf "$GATEWAY_URL/api/dashboard" >/dev/null 2>&1 || true

echo "  Traffic generated (3 requests per app + gateway aggregation)."
echo

# ── Phase 4: Wait for span ingestion ────────────────────────────────────────

echo "Phase 4: Waiting ${INGEST_WAIT}s for span ingestion..."
sleep "$INGEST_WAIT"
echo "  Done."
echo

# ── Phase 5: Assert graph state ─────────────────────────────────────────────

echo "Phase 5: Running assertions..."

# Assertion 1: service_count >= 3
count=$(cypher_count "MATCH (s:Service) RETURN count(s)")
if [ "$count" -ge 3 ] 2>/dev/null; then
    pass "service_count = $count (>= 3)"
else
    fail "service_count = $count (expected >= 3)"
fi

# Assertion 2: span_orders > 0
count=$(cypher_count "MATCH (sp:Span) WHERE sp.http_route CONTAINS '/api/orders' RETURN count(sp)")
if [ "$count" -gt 0 ] 2>/dev/null; then
    pass "span_orders = $count (> 0)"
else
    fail "span_orders = $count (expected > 0)"
fi

# Assertion 3: static_functions > 0
count=$(cypher_count "MATCH (f:Function) WHERE f.path CONTAINS 'samples/' RETURN count(f)")
if [ "$count" -gt 0 ] 2>/dev/null; then
    pass "static_functions = $count (> 0)"
else
    fail "static_functions = $count (expected > 0 — was cgc index run?)"
fi

# Assertion 4: static_classes > 0
count=$(cypher_count "MATCH (c:Class) WHERE c.path CONTAINS 'samples/' RETURN count(c)")
if [ "$count" -gt 0 ] 2>/dev/null; then
    pass "static_classes = $count (> 0)"
else
    fail "static_classes = $count (expected > 0 — was cgc index run?)"
fi

# Assertion 5: cross_service > 0
count=$(cypher_count "MATCH (sp:Span)-[:CALLS_SERVICE]->(svc:Service) RETURN count(sp)")
if [ "$count" -gt 0 ] 2>/dev/null; then
    pass "cross_service = $count (> 0)"
else
    fail "cross_service = $count (expected > 0)"
fi

# Assertion 6: trace_links > 0
count=$(cypher_count "MATCH (sp:Span)-[:PART_OF]->(t:Trace) RETURN count(sp)")
if [ "$count" -gt 0 ] 2>/dev/null; then
    pass "trace_links = $count (> 0)"
else
    fail "trace_links = $count (expected > 0)"
fi

# Assertion 7: correlates_to == 0 (known gap — WARN, not FAIL)
count=$(cypher_count "MATCH (sp:Span)-[:CORRELATES_TO]->(m) RETURN count(sp)")
if [ "$count" -eq 0 ] 2>/dev/null; then
    warn "correlates_to = 0 (known FQN gap — see KNOWN-LIMITATIONS.md)"
else
    pass "correlates_to = $count (> 0 — FQN gap may be resolved!)"
fi

echo

# ── Phase 6: Summary ────────────────────────────────────────────────────────

echo "════════════════════════════════════════════════════════════"
echo " Smoke Test Summary"
echo "════════════════════════════════════════════════════════════"
echo "  PASS: $PASS_COUNT"
echo "  WARN: $WARN_COUNT"
echo "  FAIL: $FAIL_COUNT"
echo "════════════════════════════════════════════════════════════"

if [ "$FAIL_COUNT" -gt 0 ]; then
    echo " Result: FAILED"
    exit 1
else
    echo " Result: PASSED"
    exit 0
fi
