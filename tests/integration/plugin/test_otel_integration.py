"""
Integration tests for cgc_plugin_otel.neo4j_writer.

Uses a mocked db_manager so no real Neo4j connection is required.
Tests verify that the writer issues the correct Cypher queries and
creates the expected graph structure.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch

cgc_plugin_otel = pytest.importorskip(
    "cgc_plugin_otel",
    reason="cgc-plugin-otel is not installed; skipping otel integration tests",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_span(
    span_id: str = "span001",
    trace_id: str = "trace001",
    parent_span_id: str | None = None,
    service_name: str = "order-service",
    http_route: str | None = "/api/orders",
    fqn: str | None = "App\\Controllers\\OrderController::index",
    cross_service: bool = False,
    peer_service: str | None = None,
    duration_ms: float = 12.5,
) -> dict:
    return {
        "span_id": span_id,
        "trace_id": trace_id,
        "parent_span_id": parent_span_id,
        "name": f"GET {http_route or '/'}",
        "span_kind": "CLIENT" if cross_service else "SERVER",
        "service_name": service_name,
        "start_time_ns": 1_000_000_000,
        "end_time_ns": int(1_000_000_000 + duration_ms * 1_000_000),
        "duration_ms": duration_ms,
        "http_route": http_route,
        "http_method": "GET",
        "class_name": fqn.split("::")[0] if fqn else None,
        "function_name": fqn.split("::")[1] if fqn else None,
        "fqn": fqn,
        "db_statement": None,
        "db_system": None,
        "peer_service": peer_service,
        "cross_service": cross_service,
    }


def _make_db_manager():
    """Build a mock db_manager that returns an async-capable session."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.run = AsyncMock()

    driver = MagicMock()
    driver.session = MagicMock(return_value=session)

    db_manager = MagicMock()
    db_manager.get_driver = MagicMock(return_value=driver)
    return db_manager, session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestAsyncOtelWriterBatch:

    async def test_write_batch_issues_merge_service(self):
        """write_batch() issues a MERGE for the Service node."""
        from cgc_plugin_otel.neo4j_writer import AsyncOtelWriter
        db_manager, session = _make_db_manager()
        writer = AsyncOtelWriter(db_manager)
        span = _make_span()

        await writer.write_batch([span])

        cypher_calls = [str(c.args[0]) for c in session.run.call_args_list]
        assert any("MERGE" in c and "Service" in c for c in cypher_calls), \
            f"No Service MERGE found in calls: {cypher_calls}"

    async def test_write_batch_issues_merge_span(self):
        """write_batch() issues a MERGE for the Span node."""
        from cgc_plugin_otel.neo4j_writer import AsyncOtelWriter
        db_manager, session = _make_db_manager()
        writer = AsyncOtelWriter(db_manager)
        span = _make_span()

        await writer.write_batch([span])

        cypher_calls = [str(c.args[0]) for c in session.run.call_args_list]
        assert any("MERGE" in c and "Span" in c for c in cypher_calls)

    async def test_write_batch_links_span_to_trace(self):
        """write_batch() creates a PART_OF relationship between Span and Trace."""
        from cgc_plugin_otel.neo4j_writer import AsyncOtelWriter
        db_manager, session = _make_db_manager()
        writer = AsyncOtelWriter(db_manager)
        span = _make_span()

        await writer.write_batch([span])

        cypher_calls = [str(c.args[0]) for c in session.run.call_args_list]
        assert any("PART_OF" in c for c in cypher_calls)

    async def test_write_batch_creates_child_of_for_parent_span_id(self):
        """CHILD_OF relationship is created when parent_span_id is set."""
        from cgc_plugin_otel.neo4j_writer import AsyncOtelWriter
        db_manager, session = _make_db_manager()
        writer = AsyncOtelWriter(db_manager)
        span = _make_span(span_id="child", parent_span_id="parent001")

        await writer.write_batch([span])

        cypher_calls = [str(c.args[0]) for c in session.run.call_args_list]
        assert any("CHILD_OF" in c for c in cypher_calls)

    async def test_no_child_of_when_no_parent(self):
        """CHILD_OF is NOT issued when parent_span_id is None."""
        from cgc_plugin_otel.neo4j_writer import AsyncOtelWriter
        db_manager, session = _make_db_manager()
        writer = AsyncOtelWriter(db_manager)
        span = _make_span(parent_span_id=None)

        await writer.write_batch([span])

        cypher_calls = [str(c.args[0]) for c in session.run.call_args_list]
        assert not any("CHILD_OF" in c for c in cypher_calls)

    async def test_write_batch_creates_correlates_to_for_fqn(self):
        """CORRELATES_TO relationship is attempted when fqn is set."""
        from cgc_plugin_otel.neo4j_writer import AsyncOtelWriter
        db_manager, session = _make_db_manager()
        writer = AsyncOtelWriter(db_manager)
        span = _make_span(fqn="App\\Controllers::index")

        await writer.write_batch([span])

        cypher_calls = [str(c.args[0]) for c in session.run.call_args_list]
        assert any("CORRELATES_TO" in c for c in cypher_calls)

    async def test_no_correlates_to_when_no_fqn(self):
        """CORRELATES_TO is NOT issued when fqn is None (no code context)."""
        from cgc_plugin_otel.neo4j_writer import AsyncOtelWriter
        db_manager, session = _make_db_manager()
        writer = AsyncOtelWriter(db_manager)
        span = _make_span(fqn=None)

        await writer.write_batch([span])

        cypher_calls = [str(c.args[0]) for c in session.run.call_args_list]
        assert not any("CORRELATES_TO" in c for c in cypher_calls)

    async def test_cross_service_span_creates_calls_service(self):
        """CALLS_SERVICE is created for CLIENT spans with peer_service set."""
        from cgc_plugin_otel.neo4j_writer import AsyncOtelWriter
        db_manager, session = _make_db_manager()
        writer = AsyncOtelWriter(db_manager)
        span = _make_span(cross_service=True, peer_service="payment-service")

        await writer.write_batch([span])

        cypher_calls = [str(c.args[0]) for c in session.run.call_args_list]
        assert any("CALLS_SERVICE" in c for c in cypher_calls)

    async def test_db_failure_routes_to_dlq(self):
        """When the database raises, spans are moved to the dead-letter queue."""
        from cgc_plugin_otel.neo4j_writer import AsyncOtelWriter
        db_manager = MagicMock()
        db_manager.get_driver.side_effect = Exception("Neo4j unavailable")
        writer = AsyncOtelWriter(db_manager)
        span = _make_span()

        await writer.write_batch([span])

        assert not writer._dlq.empty()
