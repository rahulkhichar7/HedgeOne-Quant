"""Shared API helpers: NaN-safe JSON response and error mapping."""
from __future__ import annotations

import datetime as dt
import json
import math

import numpy as np
import pandas as pd
from fastapi import HTTPException
from fastapi.responses import Response


def _default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (pd.Timestamp, dt.datetime, dt.date)):
        return o.isoformat()
    if isinstance(o, pd.Timedelta):
        return str(o)
    return str(o)


def clean(o):
    """Recursively replace NaN/inf with None (JSON has no NaN)."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.floating):
        return float(o) if np.isfinite(o) else None
    return o


class SafeJSON(Response):
    media_type = "application/json"

    def render(self, content) -> bytes:
        try:
            s = json.dumps(content, default=_default, allow_nan=False, separators=(",", ":"))
        except ValueError:
            s = json.dumps(clean(content), default=_default, allow_nan=False, separators=(",", ":"))
        return s.encode("utf-8")


def fail(e: Exception):
    """Map Python errors to HTTP errors with a readable message for the UI."""
    code = 404 if isinstance(e, (KeyError, FileNotFoundError)) else 400
    msg = (e.args[0] if isinstance(e, KeyError) and e.args else str(e)) or type(e).__name__
    raise HTTPException(status_code=code, detail=f"{type(e).__name__}: {msg}")
