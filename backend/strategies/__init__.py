"""
Strategy library — every .py file in this folder is imported automatically.

To add a strategy: create/edit any file here, decorate a function with @strategy,
then click ⟳ (Reload) in the UI — no server restart needed.
"""
from __future__ import annotations

import importlib
import pkgutil
import sys
import traceback

LOAD_ERRORS: dict[str, str] = {}


def load_all(reload: bool = False) -> dict[str, str]:
    """Import (or re-import) every module in this package. Returns {module: error}."""
    from app.engine.base import INDICATORS, STRATEGIES
    LOAD_ERRORS.clear()
    if reload:
        STRATEGIES.clear()
        # keep built-in indicators, drop the ones defined in strategy files
        for k in [k for k, v in INDICATORS.items() if getattr(v.func, "__module__", "").startswith(__name__)]:
            INDICATORS.pop(k)
    for m in pkgutil.iter_modules(__path__):
        if m.name.startswith("_"):
            continue
        full = f"{__name__}.{m.name}"
        try:
            if reload and full in sys.modules:
                importlib.reload(sys.modules[full])
            else:
                importlib.import_module(full)
        except Exception:  # noqa: BLE001  — a broken file must not kill the app
            LOAD_ERRORS[m.name] = traceback.format_exc(limit=3)
    return dict(LOAD_ERRORS)
