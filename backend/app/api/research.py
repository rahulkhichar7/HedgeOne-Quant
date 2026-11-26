"""Research routes: parameter optimizer, universe test, developer-mode train/test, research reports."""
from __future__ import annotations

import re

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..data import store
from ..engine import research
from ..export import standalone
from .common import SafeJSON, fail

router = APIRouter(prefix="/api", tags=["research"], default_response_class=SafeJSON)


class OptimizeReq(BaseModel):
    symbol: str
    interval: str = "15m"
    start: str | None = None
    end: str | None = None
    strategy: str
    grid: dict = Field(default_factory=dict, description='{param: {"mode": "fixed"|"range"|"list", ...}}')
    settings: dict = Field(default_factory=dict)
    objective: str = "sharpe"
    min_trades: int = 5
    constraint: str | None = Field(None, description='optional Python expression, e.g. "fast < slow"')
    context: dict = Field(default_factory=dict)          # e.g. {"dev": true, "train": {...}}
    intervals: list[str] = Field(default_factory=list, description="timeframes to test; empty = the chart's interval")


class TimeframeReq(BaseModel):
    symbol: str
    interval: str = "15m"
    start: str | None = None
    end: str | None = None
    strategy: str
    params: dict = Field(default_factory=dict)


class UniverseReq(BaseModel):
    symbols: list[str]
    interval: str = "1d"
    start: str | None = None
    end: str | None = None
    strategy: str
    params: dict = Field(default_factory=dict)
    settings: dict = Field(default_factory=dict)


class Period(BaseModel):
    start: str
    end: str


class DevReq(BaseModel):
    symbol: str
    interval: str = "15m"
    train: Period
    test: Period
    strategy: str
    params: dict = Field(default_factory=dict)
    settings: dict = Field(default_factory=dict)


@router.post("/research/optimize/count")
def optimize_count(req: OptimizeReq):
    """How many combinations a grid produces (the UI shows it live)."""
    try:
        spec = research.get_strategy(req.strategy)
        return {**research.count_combos(spec, req.grid, req.constraint, req.intervals, req.interval),
                "limit": research.MAX_COMBOS}
    except Exception as e:  # noqa: BLE001
        fail(e)


@router.post("/research/timeframes")
def timeframes(req: TimeframeReq):
    """Which candle sizes the optimizer may test for this strategy + symbol (allowed and buildable)."""
    try:
        return research.timeframe_options(req.symbol, req.strategy, req.interval, req.start, req.end, req.params)
    except Exception as e:  # noqa: BLE001
        fail(e)


@router.post("/research/optimize")
def optimize(req: OptimizeReq):
    """Starts a background job; poll /api/jobs/{job}. The result holds the report url."""
    try:
        research.count_combos(research.get_strategy(req.strategy), req.grid, req.constraint,
                              req.intervals, req.interval)                                     # validate now
    except Exception as e:  # noqa: BLE001
        fail(e)
    jid = store.start_job(research.optimize, req.symbol, req.interval, req.start, req.end, req.strategy, req.grid,
                          req.settings, req.objective, req.min_trades, req.constraint, req.context, req.intervals)
    return {"job": jid, "page": f"/optimize.html?job={jid}"}


@router.post("/research/universe")
def universe(req: UniverseReq):
    try:
        research.get_strategy(req.strategy)
        if not req.symbols:
            raise ValueError("Select at least one security")
    except Exception as e:  # noqa: BLE001
        fail(e)
    jid = store.start_job(research.universe, req.symbols, req.interval, req.start, req.end, req.strategy,
                          req.params, req.settings)
    return {"job": jid, "page": f"/universe.html?job={jid}"}


@router.post("/dev/backtest")
def dev_backtest(req: DevReq):
    """Developer mode: backtest TRAIN and TEST separately and compare them."""
    try:
        return research.dev_backtest(req.symbol, req.interval, req.train.model_dump(), req.test.model_dump(),
                                     req.strategy, req.params, req.settings)
    except Exception as e:  # noqa: BLE001
        fail(e)


@router.get("/research/reports")
def research_reports():
    return {"reports": research.list_all()}


@router.get("/research/reports/{kind}/{rid}")
def research_report(kind: str, rid: str):
    try:
        return research.load(kind, rid)
    except Exception as e:  # noqa: BLE001
        fail(e)


@router.delete("/research/reports/{kind}/{rid}")
def research_delete(kind: str, rid: str):
    try:
        research.delete(kind, rid)
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        fail(e)


@router.get("/research/export/{kind}/{rid}")
def research_export(kind: str, rid: str):
    """The report as ONE offline .html file (data, scripts, styles and charts inlined)."""
    try:
        d = research.load(kind, rid)
        m = d.get("meta", {})
        title = f"{m.get('strategy', '')} · {'Optimization' if kind == 'optimize' else 'Universe test'}"
        html = standalone(f"{kind}.html", f"{kind}.js", d, title)
        fname = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"HedgeOne_{kind}_{m.get('strategy', '')}_{rid}").strip("_") + ".html"
        return Response(html, media_type="text/html; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{fname}"'})
    except Exception as e:  # noqa: BLE001
        fail(e)
