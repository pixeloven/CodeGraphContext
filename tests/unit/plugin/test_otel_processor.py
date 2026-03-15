"""
Unit tests for cgc_plugin_otel.span_processor.

All tests run without gRPC or a real database — pure logic tests.
Tests MUST FAIL before T020 (span_processor.py) is implemented.
"""
import pytest

cgc_plugin_otel = pytest.importorskip(
    "cgc_plugin_otel",
    reason="cgc-plugin-otel is not installed; skipping otel processor unit tests",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_processor():
    from cgc_plugin_otel.span_processor import (
        extract_php_context,
        build_fqn,
        is_cross_service_span,
        should_filter_span,
        build_span_dict,
    )
    return extract_php_context, build_fqn, is_cross_service_span, should_filter_span, build_span_dict


# ---------------------------------------------------------------------------
# extract_php_context
# ---------------------------------------------------------------------------

class TestExtractPhpContext:
    def test_full_attributes_parsed(self):
        extract_php_context, *_ = _import_processor()
        attrs = {
            "code.namespace": "App\\Http\\Controllers",
            "code.function": "index",
            "http.route": "/api/orders",
            "http.method": "GET",
        }
        result = extract_php_context(attrs)
        assert result["namespace"] == "App\\Http\\Controllers"
        assert result["function"] == "index"
        assert result["http_route"] == "/api/orders"
        assert result["http_method"] == "GET"

    def test_missing_optional_attributes_return_none(self):
        extract_php_context, *_ = _import_processor()
        result = extract_php_context({})
        assert result["namespace"] is None
        assert result["function"] is None
        assert result["http_route"] is None
        assert result["http_method"] is None

    def test_db_attributes_captured(self):
        extract_php_context, *_ = _import_processor()
        attrs = {
            "db.statement": "SELECT * FROM orders",
            "db.system": "mysql",
        }
        result = extract_php_context(attrs)
        assert result["db_statement"] == "SELECT * FROM orders"
        assert result["db_system"] == "mysql"


# ---------------------------------------------------------------------------
# build_fqn
# ---------------------------------------------------------------------------

class TestBuildFqn:
    def test_namespace_and_function_joined(self):
        _, build_fqn, *_ = _import_processor()
        assert build_fqn("App\\Controllers", "store") == "App\\Controllers::store"

    def test_none_namespace_returns_none(self):
        _, build_fqn, *_ = _import_processor()
        assert build_fqn(None, "store") is None

    def test_none_function_returns_none(self):
        _, build_fqn, *_ = _import_processor()
        assert build_fqn("App\\Controllers", None) is None

    def test_both_none_returns_none(self):
        _, build_fqn, *_ = _import_processor()
        assert build_fqn(None, None) is None


# ---------------------------------------------------------------------------
# is_cross_service_span
# ---------------------------------------------------------------------------

class TestIsCrossServiceSpan:
    def test_client_kind_with_peer_service_is_cross_service(self):
        _, _, is_cross_service_span, *_ = _import_processor()
        assert is_cross_service_span("CLIENT", {"peer.service": "order-service"}) is True

    def test_client_kind_without_peer_service_is_not_cross_service(self):
        _, _, is_cross_service_span, *_ = _import_processor()
        assert is_cross_service_span("CLIENT", {}) is False

    def test_server_kind_is_not_cross_service(self):
        _, _, is_cross_service_span, *_ = _import_processor()
        assert is_cross_service_span("SERVER", {"peer.service": "anything"}) is False

    def test_internal_kind_is_not_cross_service(self):
        _, _, is_cross_service_span, *_ = _import_processor()
        assert is_cross_service_span("INTERNAL", {"peer.service": "anything"}) is False


# ---------------------------------------------------------------------------
# should_filter_span
# ---------------------------------------------------------------------------

class TestShouldFilterSpan:
    def test_health_route_filtered(self):
        _, _, _, should_filter_span, _ = _import_processor()
        assert should_filter_span({"http.route": "/health"}, ["/health", "/metrics"]) is True

    def test_metrics_route_filtered(self):
        _, _, _, should_filter_span, _ = _import_processor()
        assert should_filter_span({"http.route": "/metrics"}, ["/health", "/metrics"]) is True

    def test_normal_route_not_filtered(self):
        _, _, _, should_filter_span, _ = _import_processor()
        assert should_filter_span({"http.route": "/api/orders"}, ["/health", "/metrics"]) is False

    def test_empty_filter_list_never_filters(self):
        _, _, _, should_filter_span, _ = _import_processor()
        assert should_filter_span({"http.route": "/health"}, []) is False

    def test_span_without_route_not_filtered(self):
        _, _, _, should_filter_span, _ = _import_processor()
        assert should_filter_span({}, ["/health"]) is False


# ---------------------------------------------------------------------------
# build_span_dict
# ---------------------------------------------------------------------------

class TestBuildSpanDict:
    def test_duration_ms_computed_from_nanoseconds(self):
        _, _, _, _, build_span_dict = _import_processor()
        span = build_span_dict(
            span_id="abc123",
            trace_id="trace456",
            parent_span_id=None,
            name="GET /api/orders",
            span_kind="SERVER",
            start_time_ns=1_000_000_000,
            end_time_ns=1_500_000_000,
            attributes={},
            service_name="order-service",
        )
        assert span["duration_ms"] == pytest.approx(500.0)

    def test_required_fields_present(self):
        _, _, _, _, build_span_dict = _import_processor()
        span = build_span_dict(
            span_id="abc123",
            trace_id="trace456",
            parent_span_id="parent789",
            name="GET /api/orders",
            span_kind="SERVER",
            start_time_ns=1_000_000_000,
            end_time_ns=2_000_000_000,
            attributes={"http.route": "/api/orders"},
            service_name="order-service",
        )
        assert span["span_id"] == "abc123"
        assert span["trace_id"] == "trace456"
        assert span["parent_span_id"] == "parent789"
        assert span["service_name"] == "order-service"
        assert span["name"] == "GET /api/orders"

    def test_zero_duration_for_equal_timestamps(self):
        _, _, _, _, build_span_dict = _import_processor()
        span = build_span_dict(
            span_id="x", trace_id="y", parent_span_id=None,
            name="instant", span_kind="INTERNAL",
            start_time_ns=5_000_000, end_time_ns=5_000_000,
            attributes={}, service_name="svc",
        )
        assert span["duration_ms"] == 0.0
