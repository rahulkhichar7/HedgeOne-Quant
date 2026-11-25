"""
HedgeOne Quant — FastAPI application.

Run (from the backend/ folder):   python run.py      → http://127.0.0.1:8000
API docs:                          http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from . import config
from .api import data, engine, research

# make `import strategies` work regardless of the working directory
if str(config.BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(config.BACKEND_DIR))

import strategies  # noqa: E402

strategies.load_all()

app = FastAPI(title="HedgeOne Quant API", version="2.0")
app.add_middleware(GZipMiddleware, minimum_size=2048)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(data.router)
app.include_router(engine.router)
app.include_router(research.router)


@app.get("/api/health")
def health():
    from .engine import INDICATORS, STRATEGIES
    return {"ok": True, "strategies": len(STRATEGIES), "indicators": len(INDICATORS),
            "strategy_errors": strategies.LOAD_ERRORS}


# The UI (index.html, report.html, js/, css/) is served from /frontend
app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")
