"""
One entry point used by the API (and usable from notebooks / scripts):

    from app.engine.runner import run
    res = run("RELIANCE INDUSTRIES LTD", "15m", "2025-01-01", "2025-06-30",
              "EMA Crossover", {"fast": 9, "slow": 21}, mode="backtest")

mode = "apply"     -> candles + strategy plots + trades (shaded zones on the chart)
       "backtest"  -> + metrics + equity / drawdown / benchmark curves
       "deep"      -> + full analysis, saved as a report (returns report_id)
"""
from __future__ import annotations

import time
from datetime import datetime

from ..data import store
from . import analysis
from .backtest import (candles_json, chart_payload, get_strategy, metrics, run_signals, series,
                       settings_dict, settings_from, simulate, trades_json)


def run(symbol: str, interval: str, start=None, end=None, strategy: str = "", params: dict | None = None,
        settings: dict | None = None, mode: str = "apply") -> dict:
    t0 = time.perf_counter()
    df = store.load(symbol, interval, start, end)
    if len(df) < 2:
        raise ValueError("Not enough candles in the selected range")
    market = store.market_of(symbol)
    spec = get_strategy(strategy)
    p = spec.resolve(params)
    s = settings_from(settings)

    sig = run_signals(spec, df, p)
    sim = simulate(df, sig, s, market)
    out = {
        "meta": {"symbol": symbol, "interval": interval, "market": market.name, "strategy": strategy,
                 "category": spec.category, "params": p, "settings": settings_dict(s), "costs": sim["costs"],
                 "start": str(df.index[0]), "end": str(df.index[-1]), "bars": len(df),
                 "created": datetime.now().isoformat(timespec="seconds")},
        "candles": candles_json(df),
        "chart": chart_payload(sig, df),
        "trades": trades_json(sim["trades"]),
    }
    if mode in ("backtest", "deep"):
        out["metrics"] = metrics(sim, df, s)
        out["series"] = series(sim, df, s)
    if mode == "deep":
        out["analysis"] = analysis.deep(sim, df, out["metrics"], s.init_cash)
        out["meta"]["source"] = spec.source()
        out["report_id"] = analysis.save_report(dict(out))
    out["meta"]["elapsed_ms"] = round((time.perf_counter() - t0) * 1000)
    return out
