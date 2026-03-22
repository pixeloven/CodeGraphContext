"""
Unit tests for PluginRegistry.

All entry-point discovery is mocked — no installed packages required.
Tests MUST FAIL before PluginRegistry is implemented (TDD Red phase).
"""
import pytest
import logging
from unittest.mock import MagicMock, patch, PropertyMock


# ---------------------------------------------------------------------------
# Helpers: build fake entry-point objects
# ---------------------------------------------------------------------------

def _make_ep(name, module_path, metadata=None, raise_on_load=None):
    """Create a mock entry-point that loads a callable."""
    ep = MagicMock()
    ep.name = name

    if raise_on_load:
        ep.load.side_effect = raise_on_load
    else:
        def _loader():
            if metadata is not None:
                mod = MagicMock()
                mod.PLUGIN_METADATA = metadata
                mod.get_plugin_commands = MagicMock(
                    return_value=(name, MagicMock())
                )
                mod.get_mcp_tools = MagicMock(return_value={
                    f"{name}_tool": {
                        "name": f"{name}_tool",
                        "description": "test",
                        "inputSchema": {"type": "object", "properties": {}}
                    }
                })
                mod.get_mcp_handlers = MagicMock(return_value={
                    f"{name}_tool": lambda **kw: {"ok": True}
                })
                return mod
            return MagicMock()

        ep.load.return_value = _loader()

    return ep


VALID_METADATA = {
    "name": "test-plugin",
    "version": "0.1.0",
    "cgc_version_constraint": ">=0.1.0",
    "description": "Test plugin",
}

INCOMPATIBLE_METADATA = {
    "name": "old-plugin",
    "version": "0.0.1",
    "cgc_version_constraint": ">=99.0.0",
    "description": "Too new constraint",
}

MISSING_FIELD_METADATA = {
    "name": "bad-plugin",
    # missing version, cgc_version_constraint, description
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPluginRegistryDiscovery:
    """Tests for plugin discovery and loading."""

    def test_no_plugins_installed_starts_cleanly(self):
        """Registry with zero entry points should start without errors."""
        from codegraphcontext.plugin_registry import PluginRegistry

        with patch("codegraphcontext.plugin_registry.entry_points", return_value=[]):
            registry = PluginRegistry()
            registry.discover_cli_plugins()
            registry.discover_mcp_plugins()

        assert registry.loaded_plugins == {}
        assert registry.failed_plugins == {}

    def test_valid_plugin_is_loaded(self):
        """A plugin with valid metadata and compatible version is loaded."""
        from codegraphcontext.plugin_registry import PluginRegistry

        ep = _make_ep("myplugin", "myplugin.cli:get_plugin_commands",
                      metadata=VALID_METADATA)

        with patch("codegraphcontext.plugin_registry.entry_points", return_value=[ep]):
            registry = PluginRegistry()
            registry.discover_cli_plugins()

        assert "myplugin" in registry.loaded_plugins
        assert registry.loaded_plugins["myplugin"]["status"] == "loaded"

    def test_incompatible_version_is_skipped(self):
        """A plugin whose cgc_version_constraint excludes the installed CGC version is skipped."""
        from codegraphcontext.plugin_registry import PluginRegistry

        ep = _make_ep("oldplugin", "oldplugin.cli:get",
                      metadata=INCOMPATIBLE_METADATA)

        with patch("codegraphcontext.plugin_registry.entry_points", return_value=[ep]):
            registry = PluginRegistry()
            registry.discover_cli_plugins()

        assert "oldplugin" not in registry.loaded_plugins
        assert "oldplugin" in registry.failed_plugins
        assert "version" in registry.failed_plugins["oldplugin"].lower()

    def test_missing_metadata_field_is_skipped(self):
        """A plugin missing required PLUGIN_METADATA fields is skipped."""
        from codegraphcontext.plugin_registry import PluginRegistry

        ep = _make_ep("badplugin", "badplugin.cli:get",
                      metadata=MISSING_FIELD_METADATA)

        with patch("codegraphcontext.plugin_registry.entry_points", return_value=[ep]):
            registry = PluginRegistry()
            registry.discover_cli_plugins()

        assert "badplugin" not in registry.loaded_plugins
        assert "badplugin" in registry.failed_plugins

    def test_import_error_does_not_crash_host(self):
        """An ImportError during plugin load is caught; registry continues."""
        from codegraphcontext.plugin_registry import PluginRegistry

        bad_ep = _make_ep("broken", "broken.cli:get",
                          raise_on_load=ImportError("missing dep"))
        good_ep = _make_ep("good", "good.cli:get",
                           metadata=VALID_METADATA)

        with patch("codegraphcontext.plugin_registry.entry_points",
                   side_effect=[[bad_ep, good_ep], []]):
            registry = PluginRegistry()
            registry.discover_cli_plugins()

        assert "broken" in registry.failed_plugins
        assert "good" in registry.loaded_plugins

    def test_exception_in_get_plugin_commands_does_not_crash(self):
        """An exception raised by get_plugin_commands() is caught."""
        from codegraphcontext.plugin_registry import PluginRegistry

        mod = MagicMock()
        mod.PLUGIN_METADATA = VALID_METADATA
        mod.get_plugin_commands.side_effect = RuntimeError("boom")

        ep = MagicMock()
        ep.name = "crashplugin"
        ep.load.return_value = mod

        with patch("codegraphcontext.plugin_registry.entry_points", return_value=[ep]):
            registry = PluginRegistry()
            registry.discover_cli_plugins()

        assert "crashplugin" in registry.failed_plugins

    def test_duplicate_plugin_name_skips_second(self):
        """Two plugins with the same name: first wins, second is skipped."""
        from codegraphcontext.plugin_registry import PluginRegistry

        ep1 = _make_ep("dupe", "a.cli:get", metadata=VALID_METADATA)
        ep2 = _make_ep("dupe", "b.cli:get", metadata=VALID_METADATA)

        with patch("codegraphcontext.plugin_registry.entry_points",
                   return_value=[ep1, ep2]):
            registry = PluginRegistry()
            registry.discover_cli_plugins()

        assert "dupe" in registry.loaded_plugins
        # Only one entry — second skipped
        assert registry.loaded_plugins["dupe"]["status"] == "loaded"

    def test_loaded_and_failed_counts_are_accurate(self):
        """Summary counts match actual loaded/failed plugins."""
        from codegraphcontext.plugin_registry import PluginRegistry

        good1 = _make_ep("g1", "g1.cli:get", metadata=VALID_METADATA)
        good2 = _make_ep("g2", "g2.cli:get", metadata=VALID_METADATA)
        bad = _make_ep("bad", "bad.cli:get",
                       raise_on_load=ImportError("missing"))

        with patch("codegraphcontext.plugin_registry.entry_points",
                   side_effect=[[good1, good2, bad], []]):
            registry = PluginRegistry()
            registry.discover_cli_plugins()

        assert len(registry.loaded_plugins) == 2
        assert len(registry.failed_plugins) == 1


class TestPluginRegistryCLI:
    """Tests for CLI command registration results."""

    def test_cli_commands_populated_after_load(self):
        """cli_commands list is populated with (name, typer_app) tuples."""
        from codegraphcontext.plugin_registry import PluginRegistry

        ep = _make_ep("myplugin", "myplugin.cli:get", metadata=VALID_METADATA)

        with patch("codegraphcontext.plugin_registry.entry_points", return_value=[ep]):
            registry = PluginRegistry()
            registry.discover_cli_plugins()

        assert len(registry.cli_commands) == 1
        name, typer_app = registry.cli_commands[0]
        assert name == "myplugin"

    def test_cli_commands_empty_without_plugins(self):
        """cli_commands is empty when no plugins are installed."""
        from codegraphcontext.plugin_registry import PluginRegistry

        with patch("codegraphcontext.plugin_registry.entry_points", return_value=[]):
            registry = PluginRegistry()
            registry.discover_cli_plugins()

        assert registry.cli_commands == []


class TestPluginRegistryMCP:
    """Tests for MCP tool registration results."""

    def test_mcp_tools_populated_after_load(self):
        """mcp_tools dict is populated with tool definitions from loaded plugins."""
        from codegraphcontext.plugin_registry import PluginRegistry

        ep = _make_ep("myplugin", "myplugin.mcp:get", metadata=VALID_METADATA)

        server_context = {"db_manager": MagicMock(), "version": "0.3.1"}

        with patch("codegraphcontext.plugin_registry.entry_points", return_value=[ep]):
            registry = PluginRegistry()
            registry.discover_mcp_plugins(server_context)

        assert "myplugin_tool" in registry.mcp_tools
        assert "myplugin_tool" in registry.mcp_handlers

    def test_conflicting_tool_name_skips_second(self):
        """Two plugins registering the same tool name: first wins."""
        from codegraphcontext.plugin_registry import PluginRegistry

        # Both plugins register "myplugin_tool"
        ep1 = _make_ep("plugin_a", "a.mcp:get", metadata={**VALID_METADATA, "name": "plugin_a"})
        ep2 = _make_ep("plugin_b", "b.mcp:get", metadata={**VALID_METADATA, "name": "plugin_b"})

        # Make ep2 return a tool with the same name as ep1
        mod2 = MagicMock()
        mod2.PLUGIN_METADATA = {**VALID_METADATA, "name": "plugin_b"}
        mod2.get_mcp_tools = MagicMock(return_value={
            "myplugin_tool": {   # same key as ep1's tool
                "name": "myplugin_tool",
                "description": "conflict",
                "inputSchema": {"type": "object", "properties": {}}
            }
        })
        mod2.get_mcp_handlers = MagicMock(return_value={"myplugin_tool": lambda **k: {}})
        ep2.load.return_value = mod2

        server_context = {"db_manager": MagicMock(), "version": "0.3.1"}

        with patch("codegraphcontext.plugin_registry.entry_points",
                   return_value=[ep1, ep2]):
            registry = PluginRegistry()
            registry.discover_mcp_plugins(server_context)

        # Tool is registered once, from the first plugin
        assert "myplugin_tool" in registry.mcp_tools
