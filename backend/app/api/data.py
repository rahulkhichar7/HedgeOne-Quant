"""Market-data routes: catalog, downloads, CSV import, candles, Fyers login."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import config
from ..data import store
from ..data.sources import SOURCES
from ..engine.backtest import candles_json
from .common import SafeJSON, fail

router = APIRouter(prefix="/api", tags=["data"], default_response_class=SafeJSON)


class DownloadReq(BaseModel):
    symbol: str
    interval: str = "5m"
    start: datetime
    end: datetime = Field(default_factory=datetime.now)


class ImportReq(BaseModel):
    symbol: str
    interval: str = "1m"
    path: str = Field(..., description="Path to a CSV file on this computer")
    dayfirst: bool = True


class SymbolReq(BaseModel):
    name: str
    source: str
    symbol: str
    market: str = "NSE"


class AuthReq(BaseModel):
    auth_code: str


@router.get("/symbols")
def symbols():
    """Catalog + which intervals are stored locally for each symbol."""
    out = []
    for name, info in store.catalog().items():
        out.append({"name": name, **info, "stored": store.stored_intervals(name)})
    return {"symbols": out, "markets": list(config.MARKETS),
            "costs": {k: v.__dict__ for k, v in config.COST_PRESETS.items()}}


@router.post("/symbols")
def add_symbol(req: SymbolReq):
    try:
        return store.add_symbol(req.name, req.source, req.symbol, req.market)
    except Exception as e:  # noqa: BLE001
        fail(e)


@router.get("/sources")
def sources():
    return {name: {"label": s.label, "intervals": list(s.intervals), **s.status()} for name, s in SOURCES.items()}


@router.get("/inventory")
def inventory():
    return {"files": store.inventory()}


@router.post("/download")
def download(req: DownloadReq):
    """Starts a background download; poll /api/jobs/{id}."""
    try:
        store.symbol_info(req.symbol)
        return {"job": store.start_job(store.download, req.symbol, req.interval, req.start, req.end)}
    except Exception as e:  # noqa: BLE001
        fail(e)


@router.post("/update")
def update(symbol: str, interval: str):
    try:
        return {"job": store.start_job(store.update, symbol, interval)}
    except Exception as e:  # noqa: BLE001
        fail(e)


@router.get("/jobs/{jid}")
def job(jid: str):
    if jid not in store.JOBS:
        fail(KeyError(jid))
    return store.JOBS[jid]


@router.post("/import-csv")
def import_csv(req: ImportReq):
    try:
        return store.import_csv(req.symbol, req.interval, req.path, req.dayfirst)
    except Exception as e:  # noqa: BLE001
        fail(e)


@router.get("/candles")
def candles(symbol: str, interval: str = "15m", start: str | None = None, end: str | None = None):
    try:
        df = store.load(symbol, interval, start or None, end or None)
        return {"symbol": symbol, "interval": interval, "market": df.attrs["market"], "candles": candles_json(df)}
    except Exception as e:  # noqa: BLE001
        fail(e)


@router.get("/fyers/login-url")
def fyers_login_url():
    try:
        return {"url": SOURCES["fyers"].login_url()}
    except Exception as e:  # noqa: BLE001
        fail(e)


@router.post("/fyers/token")
def fyers_token(req: AuthReq):
    try:
        return SOURCES["fyers"].set_auth_code(req.auth_code)
    except Exception as e:  # noqa: BLE001
        fail(e)
