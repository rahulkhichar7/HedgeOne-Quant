"""Strategy / indicator / backtest / report routes."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import config
from ..data import store
from ..engine import INDICATORS, STRATEGIES, analysis
from ..engine.backtest import indicator_values, settings_dict
from ..engine import replay as replay_engine
from ..engine.runner import run
from .common import SafeJSON, fail

router = APIRouter(prefix="/api", tags=["engine"], default_response_class=SafeJSON)


class RunReq(BaseModel):
    symbol: str
    interval: str = "15m"
    start: str | None = None
    end: str | None = None
    strategy: str
    params: dict = Field(default_factory=dict)
    settings: dict = Field(default_factory=dict)


class IndicatorReq(BaseModel):
    symbol: str
    interval: str = "15m"
    start: str | None = None
    end: str | None = None
    name: str
    params: dict = Field(default_factory=dict)


@router.get("/strategies")
def strategies():
    from strategies import LOAD_ERRORS
    items = sorted((s.to_dict(with_source=True) for s in STRATEGIES.values()), key=lambda d: (d["category"], d["name"]))
    return {"strategies": items, "errors": LOAD_ERRORS}


@router.post("/strategies/reload")
def reload_strategies():
    """Re-import backend/strategies/*.py after you edit them in VS Code."""
    import strategies
    errors = strategies.load_all(reload=True)
    return {"count": len(STRATEGIES), "errors": errors}


@router.get("/indicators")
def indicators():
    items = sorted((s.to_dict() for s in INDICATORS.values()), key=lambda d: (d["category"], d["name"]))
    return {"indicators": items}


@router.get("/settings/defaults")
def default_settings():
    return {"settings": settings_dict(config.BacktestSettings()),
            "costs": {k: v.__dict__ for k, v in config.COST_PRESETS.items()},
            "market_costs": {k: m.default_costs for k, m in config.MARKETS.items()}}


@router.post("/indicator")
def indicator(req: IndicatorReq):
    try:
        df = store.load(req.symbol, req.interval, req.start, req.end)
        return indicator_values(req.name, df, req.params)
    except Exception as e:  # noqa: BLE001
        fail(e)


def _run(req: RunReq, mode: str):
    try:
        return run(req.symbol, req.interval, req.start, req.end, req.strategy, req.params, req.settings, mode)
    except Exception as e:  # noqa: BLE001
        fail(e)


@router.post("/apply")
def apply(req: RunReq):
    """Strategy plots + trades (green/red zones) — the 'Save / Apply' button."""
    return _run(req, "apply")


@router.post("/backtest")
def backtest(req: RunReq):
    return _run(req, "backtest")


@router.post("/deep")
def deep(req: RunReq):
    """Full analysis, stored as a report. Open /report.html?id=<report_id>."""
    res = _run(req, "deep")
    return {"report_id": res["report_id"], "url": f"/report.html?id={res['report_id']}",
            "metrics": res["metrics"], "insights": res["analysis"]["insights"]}


class ReplayReq(BaseModel):
    symbol: str
    interval: str = "15m"
    start: str | None = None
    end: str | None = None
    strategy: str | None = None
    params: dict = Field(default_factory=dict)
    settings: dict = Field(default_factory=dict)
    indicators: list[dict] = Field(default_factory=list)   # [{key, name, params}]
    intrabar: bool = True
    cursor: int = 0
    pit: dict | None = None                                 # exact-mode state from the previous step


@router.post("/replay/prepare")
def replay_prepare(req: ReplayReq):
    """Full-range data + look-ahead check. The UI reveals it bar by bar."""
    try:
        return replay_engine.prepare(req.symbol, req.interval, req.start, req.end, req.strategy, req.params,
                                     req.settings, req.indicators, req.intrabar)
    except Exception as e:  # noqa: BLE001
        fail(e)


@router.post("/replay/step")
def replay_step(req: ReplayReq):
    """Exact mode: recompute strategy / indicators on bars [0, cursor] only."""
    try:
        return replay_engine.step(req.symbol, req.interval, req.start, req.end, req.cursor, req.strategy,
                                  req.params, req.settings, req.indicators, req.pit)
    except Exception as e:  # noqa: BLE001
        fail(e)


@router.get("/reports")
def reports():
    return {"reports": analysis.list_reports()}


@router.get("/reports/{rid}")
def report(rid: str):
    try:
        return analysis.load_report(rid)
    except Exception as e:  # noqa: BLE001
        fail(e)


@router.delete("/reports/{rid}")
def delete_report(rid: str):
    analysis.delete_report(rid)
    return {"ok": True}
