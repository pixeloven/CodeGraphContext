"""
OTLP gRPC receiver for the OTEL plugin.

Listens for OpenTelemetry trace exports (ExportTraceServiceRequest) and
queues parsed spans for batch writing to Neo4j.

Requires:
    grpcio>=1.57.0
    opentelemetry-proto>=0.43b0

Start standalone::

    python -m cgc_plugin_otel.receiver
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_PORT = int(os.environ.get("OTEL_RECEIVER_PORT", "5317"))
_FILTER_ROUTES = [r.strip() for r in os.environ.get("OTEL_FILTER_ROUTES", "/health,/metrics,/ping").split(",") if r.strip()]


def _span_kind_name(kind_int: int) -> str:
    kinds = {0: "UNSPECIFIED", 1: "INTERNAL", 2: "SERVER", 3: "CLIENT", 4: "PRODUCER", 5: "CONSUMER"}
    return kinds.get(kind_int, "UNSPECIFIED")


def _attrs_to_dict(attributes: Any) -> dict:
    """Convert protobuf KeyValue list to a plain dict."""
    result: dict = {}
    for kv in attributes:
        val = kv.value
        if val.HasField("string_value"):
            result[kv.key] = val.string_value
        elif val.HasField("int_value"):
            result[kv.key] = val.int_value
        elif val.HasField("double_value"):
            result[kv.key] = val.double_value
        elif val.HasField("bool_value"):
            result[kv.key] = val.bool_value
    return result


class OTLPSpanReceiver:
    """
    gRPC servicer implementing the OpenTelemetry TraceService.Export RPC.

    Depends on generated protobuf stubs from ``opentelemetry-proto``.
    Import failures are caught at startup; if gRPC is not installed the
    plugin still loads but logs a warning.
    """

    def __init__(self, writer: Any, filter_routes: list[str] | None = None, loop: asyncio.AbstractEventLoop | None = None) -> None:
        self._writer = writer
        self._filter_routes = filter_routes or _FILTER_ROUTES
        self._loop = loop

    def Export(self, request: Any, context: Any) -> Any:
        """Handle ExportTraceServiceRequest — called by gRPC framework."""
        try:
            from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
                ExportTraceServiceResponse,
            )
        except ImportError:
            logger.error("opentelemetry-proto not installed — cannot process spans")
            return None  # type: ignore[return-value]

        from cgc_plugin_otel.span_processor import build_span_dict, should_filter_span

        for resource_spans in request.resource_spans:
            service_name = "unknown"
            for attr in resource_spans.resource.attributes:
                if attr.key == "service.name":
                    service_name = attr.value.string_value
                    break

            for scope_spans in resource_spans.scope_spans:
                for span in scope_spans.spans:
                    attrs = _attrs_to_dict(span.attributes)
                    if should_filter_span(attrs, self._filter_routes):
                        continue

                    span_dict = build_span_dict(
                        span_id=span.span_id.hex(),
                        trace_id=span.trace_id.hex(),
                        parent_span_id=span.parent_span_id.hex() if span.parent_span_id else None,
                        name=span.name,
                        span_kind=_span_kind_name(span.kind),
                        start_time_ns=span.start_time_unix_nano,
                        end_time_ns=span.end_time_unix_nano,
                        attributes=attrs,
                        service_name=service_name,
                    )
                    # Schedule on the main event loop — Export() runs in gRPC thread pool
                    if self._loop is not None:
                        asyncio.run_coroutine_threadsafe(self._writer.enqueue(span_dict), self._loop)

        return ExportTraceServiceResponse()


def main() -> None:
    """Start the OTLP gRPC receiver and the async writer background task."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    try:
        import grpc
        from opentelemetry.proto.collector.trace.v1 import trace_service_pb2_grpc
    except ImportError as exc:
        logger.error("Cannot start OTEL receiver — missing dependency: %s", exc)
        sys.exit(1)

    # Import db_manager from CGC core
    try:
        from codegraphcontext.core import get_database_manager
        db_manager = get_database_manager()
    except Exception as exc:
        logger.error("Cannot connect to database: %s", exc)
        sys.exit(1)

    from cgc_plugin_otel.neo4j_writer import AsyncOtelWriter

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    writer = AsyncOtelWriter(db_manager)
    servicer = OTLPSpanReceiver(writer, loop=loop)

    from concurrent.futures import ThreadPoolExecutor

    server = grpc.server(ThreadPoolExecutor(max_workers=4))
    trace_service_pb2_grpc.add_TraceServiceServicer_to_server(servicer, server)
    server.add_insecure_port(f"[::]:{_DEFAULT_PORT}")
    server.start()
    logger.info("OTLP gRPC receiver listening on port %d", _DEFAULT_PORT)

    writer_task = loop.create_task(writer.run())

    def _shutdown(signum: int, frame: Any) -> None:
        logger.info("Shutting down OTEL receiver…")
        server.stop(grace=5)
        loop.call_soon_threadsafe(writer_task.cancel)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(writer.stop())
        loop.close()


if __name__ == "__main__":
    main()
