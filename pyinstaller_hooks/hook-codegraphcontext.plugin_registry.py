# PyInstaller hook for codegraphcontext.plugin_registry
#
# plugin_registry.py uses importlib.metadata.entry_points(group=...) to
# discover installed CGC plugins at runtime.  For this to work in a frozen
# binary the distribution METADATA (including entry_points.txt) for every
# relevant package must be bundled.
#
# This hook:
#   1. Collects the codegraphcontext distribution metadata so the core
#      package's own entry points are resolvable in the frozen binary.
#   2. Declares importlib.metadata internals as hidden imports to ensure
#      the metadata resolution machinery is included.

from PyInstaller.utils.hooks import collect_data_files, collect_entry_point

datas = []
hiddenimports = [
    "importlib.metadata",
    "importlib.metadata._meta",
    "importlib.metadata._adapters",
    "importlib.metadata._itertools",
    "importlib.metadata._functools",
    "importlib.metadata._text",
    "importlib.metadata.compat.functools",
    "importlib.metadata.compat.py39",
    "pkg_resources",
    "pkg_resources.extern",
]

# Bundle the codegraphcontext package distribution metadata so that
# importlib.metadata.version("codegraphcontext") resolves inside the frozen
# binary and PluginRegistry._get_cgc_version() returns the correct version.
try:
    datas += collect_data_files("codegraphcontext", includes=["**/*.dist-info/**/*"])
except Exception:
    pass

# Collect distribution METADATA for both plugin entry-point groups so that
# entry_points(group="cgc_cli_plugins") and entry_points(group="cgc_mcp_plugins")
# resolve correctly for any plugin that is installed at freeze time.
for _group in ("cgc_cli_plugins", "cgc_mcp_plugins"):
    try:
        _ep_datas, _ep_hidden = collect_entry_point(_group)
        datas += _ep_datas
        hiddenimports += _ep_hidden
    except Exception as exc:
        import warnings
        warnings.warn(
            f"hook-codegraphcontext.plugin_registry: collect_entry_point('{_group}') "
            f"failed: {exc}"
        )
