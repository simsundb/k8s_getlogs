# PyInstaller runtime hook: fix PySide6 6.11 shibokensupport crash in frozen apps
#
# Root cause: PySide6's shibokensupport.signature (IDE signature feature) calls
# `inspect.getsource` on every imported module to detect PySide6 usage. In a
# frozen app, modules loaded via `_SixMetaPathImporter` (six) have no source
# file; `inspect.getfile` -> `_module_repr` raises AttributeError, crashing the
# import (observed with matplotlib -> dateutil.rrule).
#
# Fix: make inspect.getfile tolerate frozen modules (return a fake filename)
# and inspect.findsource return empty source when the file cannot be read.
# The signature feature is only used for IDE tooltips; this is harmless.
import inspect


def _getfile_safe(obj):
    """Return a filename for `obj`; fall back to a placeholder for frozen
    modules that have no physical source file."""
    try:
        return inspect._original_getfile(obj)
    except Exception:
        # satisfies inspect._module_repr and findsource's file-open step
        return "<frozen>"


def _findsource_safe(obj):
    try:
        return inspect._original_findsource(obj)
    except Exception:
        return ("", 0)


# stash originals (PyInstaller's pyi_rth_inspect may already wrap getfile)
inspect._original_getfile = getattr(inspect, "_original_getfile", None) or (
    getattr(inspect, "_pyi_getsourcefile", inspect.getfile)
    if hasattr(inspect, "_pyi_getsourcefile") else inspect.getfile
)
inspect._original_findsource = inspect.findsource

inspect.getfile = _getfile_safe
inspect.findsource = _findsource_safe
