#!/usr/bin/env python3
"""
Send a synthetic OTLP span to the CGC OTEL Collector for manual testing.

Usage:
    pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc
    python docs/plugins/examples/send_test_span.py

    # Custom endpoint:
    OTEL_ENDPOINT=localhost:4317 python docs/plugins/examples/send_test_span.py

Verifying results in Neo4j Browser (http://localhost:7474):
    MATCH (s:Span) RETURN s.name, s.http_route, s.duration_ms LIMIT 10
    MATCH (s:Service) RETURN s.name
"""
import os
import time

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

ENDPOINT = os.environ.get("OTEL_ENDPOINT", "localhost:4317")
SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "cgc-test-service")


def send_test_spans():
    resource = Resource.create({"service.name": SERVICE_NAME})
    provider = TracerProvider(resource=resource)

    exporter = OTLPSpanExporter(endpoint=ENDPOINT, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    tracer = trace.get_tracer("cgc.manual.test")

    print(f"Sending test spans to {ENDPOINT} (service: {SERVICE_NAME})...")

    # Simulate an HTTP request trace with a DB child span
    with tracer.start_as_current_span("GET /api/orders") as root_span:
        root_span.set_attribute("http.method", "GET")
        root_span.set_attribute("http.route", "/api/orders")
        root_span.set_attribute("http.status_code", 200)
        root_span.set_attribute("code.namespace", "App\\Http\\Controllers")
        root_span.set_attribute("code.function", "OrderController::index")

        time.sleep(0.01)  # simulate work

        with tracer.start_as_current_span("DB: SELECT orders") as child_span:
            child_span.set_attribute("db.system", "mysql")
            child_span.set_attribute("db.statement", "SELECT * FROM orders LIMIT 10")
            child_span.set_attribute("peer.service", "mysql")
            time.sleep(0.005)

    # Simulate a second, different route
    with tracer.start_as_current_span("POST /api/orders") as span2:
        span2.set_attribute("http.method", "POST")
        span2.set_attribute("http.route", "/api/orders")
        span2.set_attribute("http.status_code", 201)
        span2.set_attribute("code.namespace", "App\\Http\\Controllers")
        span2.set_attribute("code.function", "OrderController::store")
        time.sleep(0.02)

    # Flush
    provider.force_flush()
    print("Done. Check Neo4j: MATCH (s:Span) RETURN s.name, s.http_route LIMIT 10")


if __name__ == "__main__":
    send_test_spans()
