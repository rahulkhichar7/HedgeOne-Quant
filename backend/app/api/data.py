"""Market-data routes: catalog, downloads, CSV import, candles, Upstox search / check."""
from __future__ import annotations

from datetime import datetime, timedelta

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


class BulkItem(BaseModel):
    symbol: str
    interval: str = "5m"
    start: datetime
    end: datetime | None = None


class BulkReq(BaseModel):
    items: list[BulkItem]


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



@router.get("/symbols")
def symbols():
    """Catalog + which intervals are stored locally for each symbol."""
    out = []
    own = store.own_names()
    for name, info in store.catalog().items():
        kind = info.get("kind") or ("crypto" if info.get("market") == "CRYPTO" else
                                    "index" if "INDEX" in str(info.get("symbol", "")).upper() else "stock")
        row = {"name": name, "source": info["source"], "symbol": info["symbol"], "market": info["market"],
               "kind": kind, "stored": store.stored_intervals(name)}
        if name in own:
            row["own"] = True
        if info.get("series"):
            row["series"] = info["series"]
        out.append(row)
    return {"symbols": out, "catalog": {k: v for k, v in store.catalog_status().items() if k != "log"}, "markets": list(config.MARKETS),
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


@router.post("/download-many")
def download_many(req: BulkReq):
    """Bulk download: many securities / intervals / periods in one background job (sequential)."""
    try:
        if not req.items:
            raise ValueError("Select at least one security")
        for it in req.items:
            info = store.symbol_info(it.symbol)
            src = SOURCES.get(info["source"])
            if src is None:
                raise ValueError(f"'{it.symbol}' uses source '{info['source']}', which has no downloader (import a CSV)")
            if it.interval not in src.intervals:
                raise ValueError(f"{it.symbol}: {src.label} has no '{it.interval}' interval")
        items = [it.model_dump() for it in req.items]
        return {"job": store.start_job(store.download_many, items), "count": len(items)}
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


@router.get("/upstox/search")
def upstox_search(q: str, limit: int = 25):
    """Find NSE/BSE stocks and indices by name or trading symbol (Upstox instrument list)."""
    try:
        return {"results": SOURCES["upstox"].search(q, int(limit))}
    except Exception as e:  # noqa: BLE001
        fail(e)


@router.get("/upstox/check")
def upstox_check(symbol: str = "NSE:RELIANCE"):
    """Token + connection test: fetches the last few daily candles of one instrument."""
    try:
        src = SOURCES["upstox"]
        key = src.instrument_key(symbol)
        end = datetime.now()
        df = src.fetch(symbol, "1d", end - timedelta(days=10), end)
        return {"ok": True, "symbol": symbol, "instrument_key": key, "candles": len(df),
                "last": str(df.index[-1]) if len(df) else None, "close": float(df.close.iloc[-1]) if len(df) else None}
    except Exception as e:  # noqa: BLE001
        fail(e)
