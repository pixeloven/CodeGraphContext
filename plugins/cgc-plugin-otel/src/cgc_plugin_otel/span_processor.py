"""
Pure-logic span processing for the OTEL plugin.

No gRPC or database dependencies — these functions transform raw span attributes
into typed dicts that the writer can persist to the graph.
"""
from __future__ import annotations


def extract_php_context(span_attrs: dict) -> dict:
    """
    Parse PHP-specific OpenTelemetry attributes from a span attribute dict.

    Returns a typed dict with all known PHP context keys.  Missing keys are
    returned as ``None`` rather than raising ``KeyError``.
    """
    return {
        "namespace": span_attrs.get("code.namespace"),
        "function": span_attrs.get("code.function"),
        "http_route": span_attrs.get("http.route"),
        "http_method": span_attrs.get("http.method"),
        "db_statement": span_attrs.get("db.statement"),
        "db_system": span_attrs.get("db.system"),
        "peer_service": span_attrs.get("peer.service"),
    }


def build_fqn(namespace: str | None, function: str | None) -> str | None:
    """
    Build a fully-qualified name from PHP code.namespace and code.function.

    Returns ``None`` if either component is missing.
    """
    if namespace is None or function is None:
        return None
    return f"{namespace}::{function}"


def is_cross_service_span(span_kind: str, span_attrs: dict) -> bool:
    """
    Return True when this span represents a call from one service to another.

    A span is cross-service when its kind is CLIENT and ``peer.service`` is set.
    """
    return span_kind == "CLIENT" and bool(span_attrs.get("peer.service"))


def should_filter_span(span_attrs: dict, filter_routes: list[str]) -> bool:
    """
    Return True when the span's HTTP route matches a configured noise filter.

    Spans without an ``http.route`` attribute are never filtered.
    """
    if not filter_routes:
        return False
    route = span_attrs.get("http.route")
    if route is None:
        return False
    return route in filter_routes


def build_span_dict(
    *,
    span_id: str,
    trace_id: str,
    parent_span_id: str | None,
    name: str,
    span_kind: str,
    start_time_ns: int,
    end_time_ns: int,
    attributes: dict,
    service_name: str,
) -> dict:
    """
    Build a normalised span dict ready for Neo4j persistence.

    Duration is converted from nanoseconds to milliseconds.
    """
    duration_ms = (end_time_ns - start_time_ns) / 1_000_000

    php_ctx = extract_php_context(attributes)
    fqn = build_fqn(php_ctx["namespace"], php_ctx["function"])

    return {
        "span_id": span_id,
        "trace_id": trace_id,
        "parent_span_id": parent_span_id,
        "name": name,
        "span_kind": span_kind,
        "service_name": service_name,
        "start_time_ns": start_time_ns,
        "end_time_ns": end_time_ns,
        "duration_ms": duration_ms,
        "http_route": php_ctx["http_route"],
        "http_method": php_ctx["http_method"],
        "class_name": php_ctx["namespace"],
        "function_name": php_ctx["function"],
        "fqn": fqn,
        "db_statement": php_ctx["db_statement"],
        "db_system": php_ctx["db_system"],
        "peer_service": php_ctx["peer_service"],
        "cross_service": is_cross_service_span(span_kind, attributes),
    }
