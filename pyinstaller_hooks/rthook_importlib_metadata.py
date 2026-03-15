# Runtime hook: ensure importlib.metadata can resolve entry points in a
# PyInstaller one-file frozen executable.
#
# When the frozen binary unpacks into sys._MEIPASS, distribution METADATA
# directories land there.  importlib.metadata uses PathDistribution finders
# that walk sys.path.  PyInstaller already inserts _MEIPASS at sys.path[0],
# but the metadata sub-directories are nested under site-packages-style paths.
# This hook adds the _MEIPASS path explicitly so entry_points(group=...) works.
#
# It also registers a fallback using pkg_resources so that any code path that
# calls pkg_resources.iter_entry_points() also resolves correctly.

import sys
import os

_meipass = getattr(sys, "_MEIPASS", None)

if _meipass:
    # Ensure _MEIPASS is in sys.path for importlib.metadata path finders.
    if _meipass not in sys.path:
        sys.path.insert(0, _meipass)

    # Force pkg_resources to rescan working_set so entry points registered
    # via .dist-info/entry_points.txt inside _MEIPASS are visible.
    try:
        import pkg_resources
        pkg_resources._initialize_master_working_set()
    except Exception:
        pass

    # Patch importlib.metadata to also search _MEIPASS for distributions.
    try:
        from importlib.metadata import MetadataPathFinder
        import importlib.metadata as _ilm

        _orig_search_paths = getattr(_ilm, "_search_paths", None)

        def _patched_search_paths(name):  # type: ignore[override]
            paths = [_meipass]
            if _orig_search_paths is not None:
                paths.extend(_orig_search_paths(name))
            return paths

        _ilm._search_paths = _patched_search_paths
    except Exception:
        pass
