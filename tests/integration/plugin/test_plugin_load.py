"""
Integration tests for CGC plugin loading with the stub plugin.

These tests use the real entry-point mechanism.  The stub plugin must be
installed in editable mode before running:

    pip install -e plugins/cgc-plugin-stub

Tests MUST FAIL before Phase 3 implementation (T012-T016) is complete.
"""
import importlib.metadata
import logging
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stub_installed() -> bool:
    """Return True if cgc-plugin-stub is installed in the current environment."""
    try:
        importlib.metadata.version("cgc-plugin-stub")
        return True
    except importlib.metadata.PackageNotFoundError:
        return False


stub_required = pytest.mark.skipif(
    not _stub_installed(),
    reason="cgc-plugin-stub not installed — run: pip install -e plugins/cgc-plugin-stub",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def registry():
    """Fresh PluginRegistry instance for each test."""
    from codegraphcontext.plugin_registry import PluginRegistry
    return PluginRegistry()


# ---------------------------------------------------------------------------
# Tests — stub plugin via real entry points (requires editable install)
# ---------------------------------------------------------------------------

@stub_required
class TestStubPluginLoad:
    """Tests that use the real installed stub plugin via entry-point discovery."""

    def test_stub_cli_command_discovered(self, registry):
        """Stub CLI command group 'stub' appears after discover_cli_plugins()."""
        registry.discover_cli_plugins()
        assert "stub" in registry.loaded_plugins, (
            "stub plugin not in loaded_plugins — is PLUGIN_METADATA defined in __init__.py?"
        )
        assert registry.loaded_plugins["stub"]["status"] == "loaded"

    def test_stub_cli_commands_populated(self, registry):
        """cli_commands list contains ('stub', <typer.Typer>) after load."""
        registry.discover_cli_plugins()
        names = [name for name, _ in registry.cli_commands]
        assert "stub" in names

    def test_stub_mcp_tool_discovered(self, registry):
        """MCP tool 'stub_hello' appears in mcp_tools after discover_mcp_plugins()."""
        registry.discover_mcp_plugins()
        assert "stub_hello" in registry.mcp_tools, (
            "stub_hello tool missing — is get_mcp_tools() implemented in mcp_tools.py?"
        )

    def test_stub_mcp_handler_registered(self, registry):
        """Handler for 'stub_hello' is registered in mcp_handlers."""
        registry.discover_mcp_plugins()
        assert "stub_hello" in registry.mcp_handlers

    def test_stub_mcp_handler_returns_greeting(self, registry):
        """stub_hello handler returns a dict containing 'greeting'."""
        registry.discover_mcp_plugins()
        handler = registry.mcp_handlers["stub_hello"]
        result = handler(name="Tester")
        assert "greeting" in result
        assert "Tester" in result["greeting"]


# ---------------------------------------------------------------------------
# Tests — isolation behaviour (always run, use mocked entry points)
# ---------------------------------------------------------------------------

class TestPluginIsolationBehaviour:
    """
    Behavioural isolation tests that do NOT require the stub to be installed.
    They use hand-crafted mocks to verify the registry enforces contracts.
    """

    def _make_stub_ep(self, name="stub"):
        """Build a minimal stub entry-point mock with valid metadata."""
        import typer

        ep = MagicMock()
        ep.name = name

        mod = MagicMock()
        mod.PLUGIN_METADATA = {
            "name": name,
            "version": "0.1.0",
            "cgc_version_constraint": ">=0.1.0",
            "description": f"Stub plugin '{name}'",
        }
        stub_app = typer.Typer()

        @stub_app.command()
        def hello():
            """Hello from stub."""

        mod.get_plugin_commands = MagicMock(return_value=(name, stub_app))
        mod.get_mcp_tools = MagicMock(return_value={
            f"{name}_hello": {
                "name": f"{name}_hello",
                "description": "Say hello",
                "inputSchema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            }
        })
        mod.get_mcp_handlers = MagicMock(
            return_value={f"{name}_hello": lambda name="World": {"greeting": f"Hello {name}"}}
        )

        ep.load.return_value = mod
        return ep

    def test_second_incompatible_plugin_skipped(self, registry):
        """A second plugin with incompatible version constraint is skipped with warning."""
        good_ep = self._make_stub_ep("good")

        bad_mod = MagicMock()
        bad_mod.PLUGIN_METADATA = {
            "name": "old",
            "version": "0.0.1",
            "cgc_version_constraint": ">=99.0.0",
            "description": "Too new",
        }
        bad_ep = MagicMock()
        bad_ep.name = "old"
        bad_ep.load.return_value = bad_mod

        with patch("codegraphcontext.plugin_registry.entry_points", return_value=[good_ep, bad_ep]):
            registry.discover_cli_plugins()

        assert "good" in registry.loaded_plugins
        assert "old" not in registry.loaded_plugins
        assert "old" in registry.failed_plugins

    def test_duplicate_name_loads_only_first(self, registry):
        """Two plugins with identical names: first wins, second is silently skipped."""
        ep1 = self._make_stub_ep("dupe")
        ep2 = self._make_stub_ep("dupe")

        with patch("codegraphcontext.plugin_registry.entry_points", return_value=[ep1, ep2]):
            registry.discover_cli_plugins()

        assert registry.loaded_plugins["dupe"]["status"] == "loaded"
        # Only one entry in cli_commands for this name
        assert sum(1 for name, _ in registry.cli_commands if name == "dupe") == 1

    def test_conflicting_mcp_tool_loads_only_first(self, registry):
        """Two plugins registering the same MCP tool name: first plugin's definition wins."""
        ep1 = self._make_stub_ep("plugin_a")
        ep2 = self._make_stub_ep("plugin_b")

        # Make plugin_b register a tool with the same key as plugin_a
        ep2.load.return_value.get_mcp_tools.return_value = {
            "plugin_a_hello": {  # conflicts with plugin_a
                "name": "plugin_a_hello",
                "description": "conflict",
                "inputSchema": {"type": "object", "properties": {}},
            }
        }

        with patch("codegraphcontext.plugin_registry.entry_points", return_value=[ep1, ep2]):
            registry.discover_mcp_plugins()

        # Tool exists, registered by first plugin
        assert "plugin_a_hello" in registry.mcp_tools
        # Both plugins loaded (even though one tool was skipped)
        assert "plugin_a" in registry.loaded_plugins
        assert "plugin_b" in registry.loaded_plugins

    def test_registry_reports_correct_counts(self, registry):
        """loaded_plugins and failed_plugins counts are accurate after mixed load."""
        ep_good = self._make_stub_ep("ok_plugin")
        ep_bad = MagicMock()
        ep_bad.name = "broken"
        ep_bad.load.side_effect = ImportError("missing dep")

        with patch("codegraphcontext.plugin_registry.entry_points",
                   return_value=[ep_good, ep_bad]):
            registry.discover_cli_plugins()

        assert len(registry.loaded_plugins) == 1
        assert len(registry.failed_plugins) == 1
        assert "ok_plugin" in registry.loaded_plugins
        assert "broken" in registry.failed_plugins
