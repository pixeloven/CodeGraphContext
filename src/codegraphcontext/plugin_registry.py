"""
Plugin registry for CodeGraphContext.

Discovers and loads plugins declared via Python entry points:
  - Group ``cgc_cli_plugins``: plugins contributing Typer CLI command groups
  - Group ``cgc_mcp_plugins``: plugins contributing MCP tools

Plugins are isolated: a broken plugin logs a warning and is skipped without
affecting CGC core or other plugins.
"""
from __future__ import annotations

import logging
import signal
import sys
from typing import Any

from importlib.metadata import entry_points, version as pkg_version, PackageNotFoundError
from packaging.specifiers import SpecifierSet, InvalidSpecifier

logger = logging.getLogger(__name__)

_REQUIRED_METADATA_FIELDS = ("name", "version", "cgc_version_constraint", "description")
_LOAD_TIMEOUT_SECONDS = 5


def _get_cgc_version() -> str:
    try:
        return pkg_version("codegraphcontext")
    except PackageNotFoundError:
        return "0.0.0"


class PluginRegistry:
    """
    Discovers, validates, and loads CGC plugins at startup.

    Usage::

        registry = PluginRegistry()
        registry.discover_cli_plugins()           # populates cli_commands
        registry.discover_mcp_plugins(ctx)        # populates mcp_tools + mcp_handlers

    Results are available via:
        - ``registry.cli_commands``   list of (name, typer.Typer)
        - ``registry.mcp_tools``      dict of tool_name → ToolDefinition
        - ``registry.mcp_handlers``   dict of tool_name → callable
        - ``registry.loaded_plugins`` dict of name → registration info
        - ``registry.failed_plugins`` dict of name → failure reason
    """

    def __init__(self) -> None:
        self.cli_commands: list[tuple[str, Any]] = []
        self.mcp_tools: dict[str, dict] = {}
        self.mcp_handlers: dict[str, Any] = {}
        self.loaded_plugins: dict[str, dict] = {}
        self.failed_plugins: dict[str, str] = {}
        self._cgc_version = _get_cgc_version()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def discover_cli_plugins(self) -> None:
        """Discover and load all ``cgc_cli_plugins`` entry points."""
        eps = self._get_entry_points("cgc_cli_plugins")
        for ep in eps:
            self._load_cli_plugin(ep)
        self._log_summary()

    def discover_mcp_plugins(self, server_context: dict | None = None) -> None:
        """Discover and load all ``cgc_mcp_plugins`` entry points."""
        if server_context is None:
            server_context = {}
        eps = self._get_entry_points("cgc_mcp_plugins")
        for ep in eps:
            self._load_mcp_plugin(ep, server_context)

    # ------------------------------------------------------------------
    # Internal loaders
    # ------------------------------------------------------------------

    def _load_cli_plugin(self, ep: Any) -> None:
        plugin_name = ep.name
        mod = self._safe_import(plugin_name, ep)
        if mod is None:
            return

        # Validate metadata
        reason = self._validate_metadata(plugin_name, mod)
        if reason:
            self.failed_plugins[plugin_name] = reason
            logger.warning("Plugin '%s' skipped: %s", plugin_name, reason)
            return

        # Check for name conflict
        if plugin_name in self.loaded_plugins:
            msg = f"name conflict with already-loaded plugin '{plugin_name}'"
            self.failed_plugins[plugin_name + "_duplicate"] = msg
            logger.warning("Plugin '%s' (second instance) skipped: %s", plugin_name, msg)
            return

        # Call get_plugin_commands()
        get_cmds = getattr(mod, "get_plugin_commands", None)
        if get_cmds is None:
            reason = "missing get_plugin_commands() function"
            self.failed_plugins[plugin_name] = reason
            logger.warning("Plugin '%s' skipped: %s", plugin_name, reason)
            return

        result = self._safe_call(plugin_name, get_cmds)
        if result is None:
            return

        try:
            cmd_name, typer_app = result
        except (TypeError, ValueError) as exc:
            reason = f"get_plugin_commands() returned invalid format: {exc}"
            self.failed_plugins[plugin_name] = reason
            logger.warning("Plugin '%s' skipped: %s", plugin_name, reason)
            return

        self.cli_commands.append((cmd_name, typer_app))
        self.loaded_plugins[plugin_name] = {
            "status": "loaded",
            "metadata": mod.PLUGIN_METADATA,
            "cli_command": cmd_name,
        }
        logger.info("Plugin '%s' loaded CLI command group '%s'", plugin_name, cmd_name)

    def _load_mcp_plugin(self, ep: Any, server_context: dict) -> None:
        plugin_name = ep.name
        mod = self._safe_import(plugin_name, ep)
        if mod is None:
            return

        reason = self._validate_metadata(plugin_name, mod)
        if reason:
            self.failed_plugins[plugin_name] = reason
            logger.warning("Plugin '%s' skipped: %s", plugin_name, reason)
            return

        get_tools = getattr(mod, "get_mcp_tools", None)
        get_handlers = getattr(mod, "get_mcp_handlers", None)

        if get_tools is None:
            reason = "missing get_mcp_tools() function"
            self.failed_plugins[plugin_name] = reason
            logger.warning("Plugin '%s' skipped: %s", plugin_name, reason)
            return

        tools = self._safe_call(plugin_name, get_tools, server_context)
        if tools is None:
            return

        handlers: dict = {}
        if get_handlers is not None:
            h = self._safe_call(plugin_name, get_handlers, server_context)
            if h is not None:
                handlers = h

        registered = 0
        for tool_name, tool_def in tools.items():
            if tool_name in self.mcp_tools:
                logger.warning(
                    "Plugin '%s': tool '%s' conflicts with existing tool — skipped",
                    plugin_name, tool_name,
                )
                continue
            self.mcp_tools[tool_name] = tool_def
            if tool_name in handlers:
                self.mcp_handlers[tool_name] = handlers[tool_name]
            registered += 1

        if plugin_name not in self.loaded_plugins:
            self.loaded_plugins[plugin_name] = {
                "status": "loaded",
                "metadata": mod.PLUGIN_METADATA,
                "mcp_tools": list(tools.keys()),
            }
        else:
            self.loaded_plugins[plugin_name]["mcp_tools"] = list(tools.keys())

        logger.info("Plugin '%s' loaded %d MCP tool(s)", plugin_name, registered)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_entry_points(self, group: str) -> list:
        try:
            return list(entry_points(group=group))
        except Exception as exc:
            logger.error("Failed to query entry points for group '%s': %s", group, exc)
            return []

    def _safe_import(self, plugin_name: str, ep: Any) -> Any | None:
        """Load an entry point with timeout and full exception isolation."""
        _alarm_set = False
        try:
            if hasattr(signal, "SIGALRM"):
                def _timeout_handler(signum, frame):
                    raise TimeoutError(
                        f"Plugin '{plugin_name}' import timed out after "
                        f"{_LOAD_TIMEOUT_SECONDS}s"
                    )
                signal.signal(signal.SIGALRM, _timeout_handler)
                signal.alarm(_LOAD_TIMEOUT_SECONDS)
                _alarm_set = True

            mod = ep.load()
            return mod

        except TimeoutError as exc:
            reason = str(exc)
            self.failed_plugins[plugin_name] = reason
            logger.error("Plugin '%s' load timeout: %s", plugin_name, reason)
            return None
        except ImportError as exc:
            reason = f"ImportError: {exc}"
            self.failed_plugins[plugin_name] = reason
            logger.error("Plugin '%s' import failed (missing dependency?): %s", plugin_name, exc)
            return None
        except AttributeError as exc:
            reason = f"AttributeError: {exc}"
            self.failed_plugins[plugin_name] = reason
            logger.error("Plugin '%s' entry point invalid (bad module path?): %s", plugin_name, exc)
            return None
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            self.failed_plugins[plugin_name] = reason
            logger.error("Plugin '%s' unexpected load error: %s", plugin_name, exc, exc_info=True)
            return None
        finally:
            if _alarm_set and hasattr(signal, "SIGALRM"):
                signal.alarm(0)

    def _safe_call(self, plugin_name: str, func: Any, *args: Any) -> Any | None:
        """Call a plugin function with full exception isolation."""
        try:
            return func(*args)
        except Exception as exc:
            func_name = getattr(func, "__name__", repr(func))
            reason = f"{type(exc).__name__} in {func_name}: {exc}"
            self.failed_plugins[plugin_name] = reason
            logger.error("Plugin '%s' call failed: %s", plugin_name, exc, exc_info=True)
            return None

    def _validate_metadata(self, plugin_name: str, mod: Any) -> str:
        """Return an error reason string, or empty string if valid."""
        metadata = getattr(mod, "PLUGIN_METADATA", None)
        if metadata is None:
            return "missing PLUGIN_METADATA in __init__.py"

        for field in _REQUIRED_METADATA_FIELDS:
            if field not in metadata:
                return f"PLUGIN_METADATA missing required field '{field}'"

        constraint_str = metadata.get("cgc_version_constraint", "")
        try:
            specifier = SpecifierSet(constraint_str)
        except InvalidSpecifier:
            return f"invalid cgc_version_constraint '{constraint_str}'"

        if self._cgc_version not in specifier:
            return (
                f"version mismatch: plugin requires CGC {constraint_str}, "
                f"installed is {self._cgc_version}"
            )

        return ""

    def _log_summary(self) -> None:
        n_loaded = len(self.loaded_plugins)
        n_failed = len(self.failed_plugins)
        if n_loaded == 0 and n_failed == 0:
            return
        parts = [f"{n_loaded} plugin(s) loaded"]
        if n_failed:
            parts.append(f"{n_failed} skipped/failed")
        logger.info("CGC plugins: %s", ", ".join(parts))
        for name, reason in self.failed_plugins.items():
            logger.warning("  ✗ %s — %s", name, reason)
