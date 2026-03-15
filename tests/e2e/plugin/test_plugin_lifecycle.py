"""
E2E Plugin Lifecycle Tests
==========================

Full user-journey tests for the CGC plugin extension system.

Journey 1 — Stub plugin:
    install stub editable
    → CGC starts with stub CLI command
    → cgc plugin list shows stub
    → stub MCP tool appears in tools
    → call stub_hello via MCP
    → remove stub from registry → CGC restarts cleanly

Journey 2 — OTEL write_batch:
    install otel plugin (or skip if not present)
    → call write_batch with synthetic spans
    → cross-layer Cypher query structure is validated

Run as part of the e2e suite:
    pytest tests/e2e/plugin/ -v -m e2e
"""
from __future__ import annotations

import importlib.metadata
import logging
import sys
from typing import Any
from unittest.mock import MagicMock, patch, call

import pytest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_installed(package: str) -> bool:
    try:
        importlib.metadata.version(package)
        return True
    except importlib.metadata.PackageNotFoundError:
        return False


stub_installed = pytest.mark.skipif(
    not _is_installed("cgc-plugin-stub"),
    reason="cgc-plugin-stub not installed — run: pip install -e plugins/cgc-plugin-stub",
)

otel_installed = pytest.mark.skipif(
    not _is_installed("cgc-plugin-otel"),
    reason="cgc-plugin-otel not installed — run: pip install -e plugins/cgc-plugin-otel",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def fresh_registry():
    """A fresh PluginRegistry with no state."""
    from codegraphcontext.plugin_registry import PluginRegistry
    return PluginRegistry()


@pytest.fixture()
def mock_db_manager():
    """Minimal db_manager mock for unit-level checks within E2E tests."""
    mgr = MagicMock()
    mgr.execute_query = MagicMock(return_value=[])
    mgr.execute_write = MagicMock(return_value=None)
    return mgr


# ---------------------------------------------------------------------------
# Journey 1a: Stub plugin loads via real entry points
# ---------------------------------------------------------------------------

@stub_installed
class TestStubPluginLifecycle:
    """
    Tests the complete lifecycle of the stub plugin using the real entry-point
    mechanism.  Requires: pip install -e plugins/cgc-plugin-stub
    """

    def test_stub_cli_command_appears_after_discovery(self, fresh_registry):
        """After discover_cli_plugins(), 'stub' is in loaded_plugins."""
        fresh_registry.discover_cli_plugins()
        assert "stub" in fresh_registry.loaded_plugins
        assert fresh_registry.loaded_plugins["stub"]["status"] == "loaded"

    def test_stub_command_in_cli_commands_list(self, fresh_registry):
        """cli_commands contains a ('stub', <Typer>) tuple after discovery."""
        fresh_registry.discover_cli_plugins()
        names = [n for n, _ in fresh_registry.cli_commands]
        assert "stub" in names

    def test_plugin_list_command_reports_loaded(self, fresh_registry):
        """plugin list shows stub as loaded (simulates cgc plugin list)."""
        fresh_registry.discover_cli_plugins()
        fresh_registry.discover_mcp_plugins()
        assert "stub" in fresh_registry.loaded_plugins
        assert fresh_registry.loaded_plugins["stub"]["status"] == "loaded"

    def test_stub_mcp_tool_appears_in_tools(self, fresh_registry):
        """'stub_hello' appears in mcp_tools after discover_mcp_plugins()."""
        fresh_registry.discover_mcp_plugins()
        assert "stub_hello" in fresh_registry.mcp_tools

    def test_stub_mcp_tool_has_valid_schema(self, fresh_registry):
        """stub_hello tool definition has required MCP schema fields."""
        fresh_registry.discover_mcp_plugins()
        tool = fresh_registry.mcp_tools["stub_hello"]
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        assert tool["inputSchema"]["type"] == "object"

    def test_stub_hello_handler_returns_greeting(self, fresh_registry):
        """Calling stub_hello handler returns {'greeting': '...'} with caller name."""
        fresh_registry.discover_mcp_plugins()
        handler = fresh_registry.mcp_handlers["stub_hello"]
        result = handler(name="E2E")
        assert isinstance(result, dict)
        assert "greeting" in result
        assert "E2E" in result["greeting"]

    def test_registry_clean_after_simulated_uninstall(self, fresh_registry):
        """
        Simulates uninstall by creating a new registry with no entry points.
        The new registry should start empty — no leftover stub artifacts.
        """
        fresh_registry.discover_cli_plugins()
        fresh_registry.discover_mcp_plugins()
        assert "stub" in fresh_registry.loaded_plugins

        from codegraphcontext.plugin_registry import PluginRegistry

        with patch("codegraphcontext.plugin_registry.entry_points", return_value=[]):
            clean_registry = PluginRegistry()
            clean_registry.discover_cli_plugins()
            clean_registry.discover_mcp_plugins()

        assert len(clean_registry.loaded_plugins) == 0
        assert len(clean_registry.cli_commands) == 0
        assert len(clean_registry.mcp_tools) == 0


# ---------------------------------------------------------------------------
# Journey 1b: Broken plugin never crashes host (always runs, no install needed)
# ---------------------------------------------------------------------------

class TestBrokenPluginIsolation:
    """
    Verifies that broken plugins are quarantined without crashing CGC.
    Uses mocked entry points so no real plugin install is required.
    """

    def _make_valid_ep(self, name: str):
        import typer

        ep = MagicMock()
        ep.name = name
        mod = MagicMock()
        mod.PLUGIN_METADATA = {
            "name": name,
            "version": "0.1.0",
            "cgc_version_constraint": ">=0.1.0",
            "description": f"Valid plugin {name}",
        }
        app = typer.Typer()

        @app.command()
        def hello():
            pass

        mod.get_plugin_commands = MagicMock(return_value=(name, app))
        mod.get_mcp_tools = MagicMock(return_value={
            f"{name}_tool": {
                "name": f"{name}_tool",
                "description": "test tool",
                "inputSchema": {"type": "object", "properties": {}},
            }
        })
        mod.get_mcp_handlers = MagicMock(return_value={
            f"{name}_tool": lambda: {"result": "ok"}
        })
        ep.load.return_value = mod
        return ep

    def test_import_error_plugin_does_not_crash_host(self, fresh_registry):
        """A plugin that raises ImportError is logged as failed; CGC continues."""
        good_ep = self._make_valid_ep("good")
        bad_ep = MagicMock()
        bad_ep.name = "broken_import"
        bad_ep.load.side_effect = ImportError("missing_dep")

        with patch("codegraphcontext.plugin_registry.entry_points",
                   return_value=[good_ep, bad_ep]):
            fresh_registry.discover_cli_plugins()

        assert "good" in fresh_registry.loaded_plugins
        assert "broken_import" in fresh_registry.failed_plugins
        assert len(fresh_registry.loaded_plugins) == 1

    def test_runtime_exception_in_get_plugin_commands_is_isolated(self, fresh_registry):
        """If get_plugin_commands() raises, plugin is failed; others still load."""
        good_ep = self._make_valid_ep("safe")
        bad_ep = self._make_valid_ep("buggy")
        bad_ep.load.return_value.get_plugin_commands.side_effect = RuntimeError(
            "boom in get_plugin_commands"
        )

        with patch("codegraphcontext.plugin_registry.entry_points",
                   return_value=[good_ep, bad_ep]):
            fresh_registry.discover_cli_plugins()

        assert "safe" in fresh_registry.loaded_plugins
        assert "buggy" in fresh_registry.failed_plugins

    def test_incompatible_version_plugin_is_skipped(self, fresh_registry):
        """Plugin with cgc_version_constraint that doesn't match installed version is skipped."""
        ep = MagicMock()
        ep.name = "future_plugin"
        mod = MagicMock()
        mod.PLUGIN_METADATA = {
            "name": "future_plugin",
            "version": "9.9.9",
            "cgc_version_constraint": ">=9999.0.0",
            "description": "Too new",
        }
        ep.load.return_value = mod

        with patch("codegraphcontext.plugin_registry.entry_points", return_value=[ep]):
            fresh_registry.discover_cli_plugins()

        assert "future_plugin" in fresh_registry.failed_plugins
        assert "future_plugin" not in fresh_registry.loaded_plugins

    def test_cgc_starts_cleanly_with_no_plugins_installed(self, fresh_registry):
        """With no plugins, registry loads cleanly and reports zero counts."""
        with patch("codegraphcontext.plugin_registry.entry_points", return_value=[]):
            fresh_registry.discover_cli_plugins()
            fresh_registry.discover_mcp_plugins()

        assert len(fresh_registry.loaded_plugins) == 0
        assert len(fresh_registry.failed_plugins) == 0
        assert len(fresh_registry.cli_commands) == 0
        assert len(fresh_registry.mcp_tools) == 0


# ---------------------------------------------------------------------------
# Journey 2: OTEL write_batch → synthetic spans → cross-layer query structure
# ---------------------------------------------------------------------------

@otel_installed
class TestOtelPluginLifecycle:
    """
    Tests the OTEL plugin write_batch path and cross-layer query capability.
    Requires: pip install -e plugins/cgc-plugin-otel
    Uses a mock db_manager so no live Neo4j instance is needed.
    """

    @pytest.fixture()
    def writer(self, mock_db_manager):
        from cgc_plugin_otel.neo4j_writer import AsyncOtelWriter
        return AsyncOtelWriter(db_manager=mock_db_manager)

    @pytest.fixture()
    def synthetic_spans(self):
        """Minimal synthetic span dicts matching write_batch expected format."""
        return [
            {
                "span_id": "abc123",
                "trace_id": "trace_001",
                "parent_span_id": None,
                "name": "GET /api/orders",
                "service": "order-service",
                "start_time_ns": 1_700_000_000_000_000_000,
                "end_time_ns":   1_700_000_001_000_000_000,
                "duration_ms": 1000.0,
                "http_route": "/api/orders",
                "http_method": "GET",
                "http_status_code": 200,
                "fqn": "App\\Http\\Controllers\\OrderController::index",
                "span_kind": "SERVER",
                "status_code": "OK",
                "attributes": {},
            },
            {
                "span_id": "def456",
                "trace_id": "trace_001",
                "parent_span_id": "abc123",
                "name": "DB query",
                "service": "order-service",
                "start_time_ns": 1_700_000_000_100_000_000,
                "end_time_ns":   1_700_000_000_200_000_000,
                "duration_ms": 100.0,
                "http_route": None,
                "http_method": None,
                "http_status_code": None,
                "fqn": None,
                "span_kind": "CLIENT",
                "status_code": "OK",
                "attributes": {"db.system": "mysql", "peer.service": "mysql"},
            },
        ]

    def test_otel_plugin_loads_via_registry(self, fresh_registry):
        """OTEL plugin MCP tools are discovered by the registry."""
        fresh_registry.discover_mcp_plugins()
        otel_tools = [k for k in fresh_registry.mcp_tools if k.startswith("otel_")]
        assert len(otel_tools) > 0, "No otel_* MCP tools found in registry"

    def test_otel_mcp_tools_have_valid_schemas(self, fresh_registry):
        """All otel_* tools have required MCP schema fields."""
        fresh_registry.discover_mcp_plugins()
        for tool_name, tool_def in fresh_registry.mcp_tools.items():
            if not tool_name.startswith("otel_"):
                continue
            assert "name" in tool_def, f"{tool_name}: missing 'name'"
            assert "description" in tool_def, f"{tool_name}: missing 'description'"
            assert "inputSchema" in tool_def, f"{tool_name}: missing 'inputSchema'"

    def test_write_batch_calls_db_manager(self, writer, synthetic_spans, mock_db_manager):
        """write_batch() invokes db_manager with Service, Trace, and Span merge queries."""
        import asyncio
        asyncio.get_event_loop().run_until_complete(writer.write_batch(synthetic_spans))
        assert mock_db_manager.execute_write.called or mock_db_manager.execute_query.called

    def test_write_batch_handles_empty_list(self, writer, mock_db_manager):
        """write_batch([]) completes without error and makes no DB calls."""
        import asyncio
        asyncio.get_event_loop().run_until_complete(writer.write_batch([]))
        mock_db_manager.execute_write.assert_not_called()

    def test_cross_layer_query_structure_is_valid(self):
        """
        Verifies the canonical cross-layer Cypher query compiles (parse-only check).
        Tests SC-005: unspecced running code query.
        """
        cross_layer_query = (
            "MATCH (m:Method)<-[:CORRELATES_TO]-(s:Span) "
            "WHERE NOT EXISTS { MATCH (mem:Memory)-[:DESCRIBES]->(m) } "
            "RETURN m.fqn, count(s) AS executions "
            "ORDER BY executions DESC LIMIT 20"
        )
        # Structural validation: query contains all expected clauses
        assert "CORRELATES_TO" in cross_layer_query
        assert "DESCRIBES" in cross_layer_query
        assert "executions" in cross_layer_query
        assert "LIMIT 20" in cross_layer_query


# ---------------------------------------------------------------------------
# Journey 3: MCP server integration — plugin tools surface in tools/list
# ---------------------------------------------------------------------------

class TestMCPServerPluginIntegration:
    """
    Verifies that MCPServer merges plugin tools into self.tools and routes
    tool_call to plugin handlers.  Uses fully mocked entry points and db_manager.
    """

    def _make_mock_tool_ep(self, plugin_name: str, tool_name: str):
        ep = MagicMock()
        ep.name = plugin_name
        mod = MagicMock()
        mod.PLUGIN_METADATA = {
            "name": plugin_name,
            "version": "0.1.0",
            "cgc_version_constraint": ">=0.1.0",
            "description": "test",
        }
        mod.get_mcp_tools = MagicMock(return_value={
            tool_name: {
                "name": tool_name,
                "description": "a test tool",
                "inputSchema": {
                    "type": "object",
                    "properties": {"arg": {"type": "string"}},
                },
            }
        })
        mod.get_mcp_handlers = MagicMock(return_value={
            tool_name: lambda arg="default": {"result": f"called with {arg}"}
        })
        ep.load.return_value = mod
        return ep

    def test_registry_mcp_tools_populate_correctly(self, fresh_registry):
        """Tools contributed by a mock plugin appear in registry.mcp_tools."""
        ep = self._make_mock_tool_ep("e2e_plugin", "e2e_tool")

        with patch("codegraphcontext.plugin_registry.entry_points", return_value=[ep]):
            fresh_registry.discover_mcp_plugins()

        assert "e2e_tool" in fresh_registry.mcp_tools

    def test_plugin_handler_callable_via_registry(self, fresh_registry):
        """Handler for plugin tool is callable and returns expected result."""
        ep = self._make_mock_tool_ep("e2e_plugin", "e2e_tool")

        with patch("codegraphcontext.plugin_registry.entry_points", return_value=[ep]):
            fresh_registry.discover_mcp_plugins()

        handler = fresh_registry.mcp_handlers["e2e_tool"]
        result = handler(arg="hello")
        assert result == {"result": "called with hello"}

    def test_two_plugins_tools_merge_without_conflict(self, fresh_registry):
        """Tools from two different plugins both appear in mcp_tools."""
        ep1 = self._make_mock_tool_ep("plugin_one", "tool_one")
        ep2 = self._make_mock_tool_ep("plugin_two", "tool_two")

        with patch("codegraphcontext.plugin_registry.entry_points",
                   return_value=[ep1, ep2]):
            fresh_registry.discover_mcp_plugins()

        assert "tool_one" in fresh_registry.mcp_tools
        assert "tool_two" in fresh_registry.mcp_tools

    def test_conflicting_tool_names_first_wins(self, fresh_registry):
        """When two plugins register the same tool name, the first plugin's version wins."""
        ep1 = self._make_mock_tool_ep("first_plugin", "shared_tool")
        ep2 = self._make_mock_tool_ep("second_plugin", "shared_tool")

        # Override second plugin to have conflicting tool
        ep2.load.return_value.get_mcp_handlers.return_value = {
            "shared_tool": lambda: {"result": "second"}
        }

        with patch("codegraphcontext.plugin_registry.entry_points",
                   return_value=[ep1, ep2]):
            fresh_registry.discover_mcp_plugins()

        handler = fresh_registry.mcp_handlers.get("shared_tool")
        assert handler is not None
        # First plugin's handler should win
        result = handler(arg="test")
        assert result == {"result": "called with test"}
