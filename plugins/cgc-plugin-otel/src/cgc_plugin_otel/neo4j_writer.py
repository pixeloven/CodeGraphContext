"""
Async Neo4j writer for the OTEL plugin.

Batches incoming span dicts and flushes them periodically to Neo4j,
with a dead-letter queue for retries during database unavailability.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

_BATCH_SIZE = 100
_FLUSH_TIMEOUT_S = 5.0
_QUEUE_MAXSIZE = 10_000
_DLQ_MAXSIZE = 100_000

# ---------------------------------------------------------------------------
# Cypher templates
# ---------------------------------------------------------------------------

_MERGE_SERVICE = """
MERGE (s:Service {name: $service_name})
ON CREATE SET s.first_seen = datetime()
ON MATCH  SET s.last_seen  = datetime()
"""

_MERGE_TRACE = """
MERGE (t:Trace {trace_id: $trace_id})
ON CREATE SET t.first_seen = datetime()
"""

_MERGE_SPAN = """
MERGE (sp:Span {span_id: $span_id})
ON CREATE SET
    sp.trace_id      = $trace_id,
    sp.name          = $name,
    sp.span_kind     = $span_kind,
    sp.service_name  = $service_name,
    sp.http_route    = $http_route,
    sp.http_method   = $http_method,
    sp.class_name    = $class_name,
    sp.function_name = $function_name,
    sp.fqn           = $fqn,
    sp.db_statement  = $db_statement,
    sp.db_system     = $db_system,
    sp.peer_service  = $peer_service,
    sp.duration_ms   = $duration_ms,
    sp.start_time_ns = $start_time_ns,
    sp.end_time_ns   = $end_time_ns,
    sp.first_seen    = datetime()
ON MATCH SET
    sp.observation_count = coalesce(sp.observation_count, 0) + 1,
    sp.last_seen         = datetime()
"""

_LINK_SPAN_TO_TRACE = """
MATCH (sp:Span {span_id: $span_id}), (t:Trace {trace_id: $trace_id})
MERGE (sp)-[:PART_OF]->(t)
"""

_LINK_SPAN_TO_SERVICE = """
MATCH (sp:Span {span_id: $span_id}), (s:Service {name: $service_name})
MERGE (sp)-[:ORIGINATED_FROM]->(s)
"""

_LINK_PARENT_SPAN = """
MATCH (child:Span {span_id: $span_id}), (parent:Span {span_id: $parent_span_id})
MERGE (child)-[:CHILD_OF]->(parent)
"""

_LINK_CROSS_SERVICE = """
MATCH (sp:Span {span_id: $span_id}), (svc:Service {name: $peer_service})
MERGE (sp)-[:CALLS_SERVICE]->(svc)
"""

_CORRELATE_TO_METHOD = """
MATCH (sp:Span {span_id: $span_id})
WHERE sp.fqn IS NOT NULL
MATCH (m:Method {fqn: sp.fqn})
MERGE (sp)-[:CORRELATES_TO]->(m)
"""


class AsyncOtelWriter:
    """
    Buffers spans in an asyncio queue and flushes them to Neo4j in batches.

    Usage::

        writer = AsyncOtelWriter(db_manager)
        asyncio.create_task(writer.run())   # start background flush loop
        await writer.enqueue(span_dict)
    """

    def __init__(self, db_manager: Any) -> None:
        self._db = db_manager
        self._queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        self._dlq: asyncio.Queue[dict] = asyncio.Queue(maxsize=_DLQ_MAXSIZE)
        self._running = False

    async def enqueue(self, span: dict) -> None:
        """Add a span to the processing queue, dropping if full."""
        try:
            self._queue.put_nowait(span)
        except asyncio.QueueFull:
            logger.warning("OTEL span queue full — dropping span %s", span.get("span_id"))

    async def run(self) -> None:
        """Background task: collect batches and flush."""
        self._running = True
        logger.info("AsyncOtelWriter started")
        while self._running:
            batch = await self._collect_batch()
            if batch:
                await self._flush_batch(batch)
            await self._retry_dlq()

    async def stop(self) -> None:
        self._running = False
        # Drain remaining items
        batch: list[dict] = []
        while not self._queue.empty():
            try:
                batch.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if batch:
            await self._flush_batch(batch)

    async def write_batch(self, spans: list[dict]) -> None:
        """Write a list of span dicts directly (used in tests and integration)."""
        await self._flush_batch(spans)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _collect_batch(self) -> list[dict]:
        batch: list[dict] = []
        try:
            # Wait for first item
            span = await asyncio.wait_for(self._queue.get(), timeout=_FLUSH_TIMEOUT_S)
            batch.append(span)
        except asyncio.TimeoutError:
            return batch

        # Drain up to batch size
        while len(batch) < _BATCH_SIZE:
            try:
                batch.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return batch

    async def _flush_batch(self, spans: list[dict]) -> None:
        try:
            driver = self._db.get_driver()
            async with driver.session() as session:
                for span in spans:
                    await self._write_span(session, span)
            logger.debug("Flushed %d spans to Neo4j", len(spans))
        except Exception as exc:
            logger.error("Neo4j flush failed (%s) — moving %d spans to DLQ", exc, len(spans))
            for span in spans:
                try:
                    self._dlq.put_nowait(span)
                except asyncio.QueueFull:
                    logger.warning("DLQ full — permanently dropping span %s", span.get("span_id"))

    async def _write_span(self, session: Any, span: dict) -> None:
        await session.run(_MERGE_SERVICE, service_name=span["service_name"])
        await session.run(_MERGE_TRACE, trace_id=span["trace_id"])
        await session.run(_MERGE_SPAN, **span)
        await session.run(_LINK_SPAN_TO_TRACE, span_id=span["span_id"], trace_id=span["trace_id"])
        await session.run(_LINK_SPAN_TO_SERVICE, span_id=span["span_id"], service_name=span["service_name"])
        if span.get("parent_span_id"):
            await session.run(_LINK_PARENT_SPAN, span_id=span["span_id"], parent_span_id=span["parent_span_id"])
        if span.get("cross_service") and span.get("peer_service"):
            await session.run(_LINK_CROSS_SERVICE, span_id=span["span_id"], peer_service=span["peer_service"])
        if span.get("fqn"):
            await session.run(_CORRELATE_TO_METHOD, span_id=span["span_id"])

    async def _retry_dlq(self) -> None:
        if self._dlq.empty():
            return
        retry_batch: list[dict] = []
        while len(retry_batch) < _BATCH_SIZE and not self._dlq.empty():
            try:
                retry_batch.append(self._dlq.get_nowait())
            except asyncio.QueueEmpty:
                break
        if retry_batch:
            logger.info("Retrying %d spans from DLQ", len(retry_batch))
            await self._flush_batch(retry_batch)
