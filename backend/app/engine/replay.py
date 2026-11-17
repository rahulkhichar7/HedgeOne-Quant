"""
Bar replay — like TradingView's replay, but strict about the future.

How "no future data" is guaranteed
----------------------------------
1. prepare() computes the strategy / indicators once on the whole range and the UI only
   ever *draws* values up to the replay cursor.  That is exact **only if** every value at
   bar i depends on bars <= i.
2. So prepare() also runs a LOOK-AHEAD CHECK: it recomputes the strategy and each
   indicator on data truncated at several cut points and compares with the full run.
   Any difference means the code peeked at future bars (e.g. `shift(-1)`, centred windows,
   `df.close.iloc[-1]`, normalising by the whole-series max ...).
3. Anything that fails the check is replayed in EXACT mode: step() recomputes it on
   df[:cursor + 1] every time the cursor moves, so it can only ever see the past.

Trades: vectorbt's simulation is causal, so a trade is shown only once its entry / exit
would have been known at the cursor (the UI also hides exits that happen inside a bar
that is still forming).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..data import store
from ..data.sources import interval_seconds, parse_interval
from .backtest import (candles_json, chart_payload, get_strategy, indicator_values, metrics, run_signals,
                       series, settings_from, simulate, trades_json)

SUB_LADDER = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h"]
MAX_SUBSTEPS = 30           # forming-candle steps per chart bar in "intrabar" mode


# ======================================================================
# Look-ahead check
# ======================================================================
def _cuts(n: int, k: int = 5) -> list[int]:
    """Cut points spread over the range (skip the warm-up and the very end)."""
    if n < 40:
        return [n // 2] if n > 4 else []
    return sorted({int(n * f) for f in (0.3, 0.45, 0.6, 0.75, 0.9)[:k]})


def _compare(full: dict[str, np.ndarray], part: dict[str, np.ndarray], cut: int, idx) -> str | None:
    """Return a description of the first mismatch on bars [0, cut], or None."""
    for name, a in full.items():
        b = part.get(name)
        if b is None:
            continue
        a, b = np.asarray(a)[: cut + 1], np.asarray(b)[: cut + 1]
        if a.dtype == bool or b.dtype == bool:
            diff = np.flatnonzero(a.astype(bool) != b.astype(bool))
        else:
            a, b = a.astype(float), b.astype(float)
            same = np.isclose(a, b, rtol=1e-7, atol=1e-9, equal_nan=True)
            diff = np.flatnonzero(~same)
        if len(diff):
            i = int(diff[0])
            return f"'{name}' at {idx[i]} differs when bars after {idx[cut]} are hidden"
    return None


def _sig_arrays(sig, df) -> dict[str, np.ndarray]:
    out = {"entries": sig.entries.to_numpy(), "exits": sig.exits.to_numpy()}
    if sig.short_entries is not None:
        out["short_entries"] = sig.short_entries.to_numpy()
        out["short_exits"] = sig.short_exits.to_numpy()
    for k, v in sig.overlays.items():
        out[k] = pd.Series(v).reindex(df.index).to_numpy(dtype=float)
    for p, d in sig.panes.items():
        for k, v in d.items():
            out[f"{p}/{k}"] = pd.Series(v).reindex(df.index).to_numpy(dtype=float)
    return out


def _slice(df: pd.DataFrame, end: int) -> pd.DataFrame:
    part = df.iloc[: end + 1].copy()
    part.attrs.update(df.attrs)
    return part


def _sim_arrays(spec, df, params, settings, market) -> dict[str, np.ndarray]:
    sig = run_signals(spec, df, params)
    sim = simulate(df, sig, settings_from(settings), market)
    return {**_sig_arrays(sig, df), "equity (simulation)": sim["pf"].value().to_numpy()}


def check_strategy(spec, df: pd.DataFrame, params: dict, settings: dict | None = None, market=None) -> dict:
    """Signals, plotted series AND the simulated equity must be identical when the future is hidden."""
    market = market or store.market_of(df.attrs["symbol"])
    full = _sim_arrays(spec, df, params, settings, market)
    for cut in _cuts(len(df)):
        part_df = _slice(df, cut)
        try:
            part = _sim_arrays(spec, part_df, params, settings, market)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "detail": f"fails on truncated data ({type(e).__name__}: {e})"}
        bad = _compare(full, part, cut, df.index)
        if bad:
            return {"ok": False, "detail": bad}
    return {"ok": True, "detail": "no look-ahead detected (signals, plots and simulated equity)"}


def check_indicator(name: str, df: pd.DataFrame, params: dict) -> dict:
    full = {k: np.array(v, dtype=float) for k, v in indicator_values(name, df, params)["series"].items()}
    for cut in _cuts(len(df)):
        part = {k: np.array(v, dtype=float) for k, v in indicator_values(name, _slice(df, cut), params)["series"].items()}
        bad = _compare(full, part, cut, df.index)
        if bad:
            return {"ok": False, "detail": bad}
    return {"ok": True, "detail": "no look-ahead detected"}


# ======================================================================
# Intrabar (forming candle) data
# ======================================================================
def _sub_interval(symbol: str, interval: str) -> str | None:
    """Finest interval we can build from stored data that gives <= MAX_SUBSTEPS per chart bar."""
    target = interval_seconds(interval)
    stored = store.stored_intervals(symbol)
    if not stored:
        return None
    finest = min(interval_seconds(i) for i in stored)
    for iv in SUB_LADDER:
        s = interval_seconds(iv)
        if s < finest or s >= target or target % s or s % finest:
            continue
        if target / s <= MAX_SUBSTEPS:
            return iv
    return None


def sub_candles(symbol: str, interval: str, df: pd.DataFrame) -> dict | None:
    if parse_interval(interval)[1] not in ("s", "m", "h", "d"):
        return None
    iv = _sub_interval(symbol, interval)
    if iv is None:
        return None
    sub = store.load(symbol, iv, df.index[0], df.index[-1] + pd.Timedelta(seconds=interval_seconds(interval) - 1))
    if sub.empty:
        return None
    parent = np.searchsorted(df.index.values, sub.index.values, side="right") - 1
    keep = parent >= 0
    sub, parent = sub[keep], parent[keep]
    c = candles_json(sub)
    c["p"] = parent.astype(int).tolist()
    c["interval"] = iv
    return c


# ======================================================================
# API helpers
# ======================================================================
def _strategy_part(spec, df, params, settings, market) -> dict:
    s = settings_from(settings)
    sig = run_signals(spec, df, params)
    sim = simulate(df, sig, s, market)
    return {"chart": chart_payload(sig, df), "trades": trades_json(sim["trades"]),
            "series": series(sim, df, s), "metrics": metrics(sim, df, s), "costs": sim["costs"],
            "execution": s.execution}


def prepare(symbol, interval, start=None, end=None, strategy=None, params=None, settings=None,
            indicators: list[dict] | None = None, intrabar: bool = True) -> dict:
    df = store.load(symbol, interval, start, end)
    if len(df) < 3:
        raise ValueError("Not enough candles in the selected range")
    market = store.market_of(symbol)
    out = {"symbol": symbol, "interval": interval, "market": market.name, "candles": candles_json(df),
           "sub": sub_candles(symbol, interval, df) if intrabar else None,
           "strategy": None, "indicators": [], "causal": {"strategy": None, "indicators": {}}}
    if strategy:
        spec = get_strategy(strategy)
        p = spec.resolve(params)
        out["strategy"] = {"name": strategy, "params": p, **_strategy_part(spec, df, p, settings, market)}
        out["causal"]["strategy"] = check_strategy(spec, df, p, settings, market)
    for ind in indicators or []:
        key = ind.get("key") or ind["name"]
        vals = indicator_values(ind["name"], df, ind.get("params") or {})
        out["indicators"].append({"key": key, **vals})
        out["causal"]["indicators"][key] = check_indicator(ind["name"], df, ind.get("params") or {})
    return out


MAX_PIT_STEPS = 400          # bars computed per /replay/step call in exact mode


def _last(series_like, idx) -> float | None:
    v = pd.Series(series_like).reindex(idx).iloc[-1] if len(idx) else np.nan
    return None if pd.isna(v) else float(v)


def step(symbol, interval, start=None, end=None, cursor: int = 0, strategy=None, params=None, settings=None,
         indicators: list[dict] | None = None, pit: dict | None = None) -> dict:
    """EXACT (point-in-time) mode for code that failed the look-ahead check.

    The strategy "goes live" at the replay start bar. For every bar i after that we run it on
    df[:i+1] and keep ONLY its decision / plotted values for bar i — exactly what you would
    have seen live — then simulate the trades from those frozen decisions.

    `pit` is the state returned by the previous call (the UI sends it back):
      {start, last, long_entry, long_exit, short_entry, short_exit}
    """
    df = store.load(symbol, interval, start, end)
    cursor = int(max(1, min(cursor, len(df) - 1)))
    market = store.market_of(symbol)
    out = {"cursor": cursor, "strategy": None, "indicators": [], "pit": None, "done": True}
    keys = ("long_entry", "long_exit", "short_entry", "short_exit")
    init = not pit
    if init:
        pit = {"start": cursor, "last": cursor - 1, **{k: [] for k in keys}}
    pit = {**pit}
    if cursor <= pit["last"]:                       # stepped back: forget decisions after the cursor
        for k in keys:
            pit[k] = [i for i in pit[k] if i <= cursor]
        pit["last"] = cursor
    lo, hi = pit["last"] + 1, min(cursor, pit["last"] + MAX_PIT_STEPS)
    out["done"] = hi >= cursor
    spec = get_strategy(strategy) if strategy else None
    p = spec.resolve(params) if spec else {}
    new_pts: dict[str, list] = {}
    ind_pts: dict[str, dict[str, list]] = {}

    def record(name, d, i, v):
        d.setdefault(name, []).append([i, v])

    for i in range(lo, hi + 1):
        part = _slice(df, i)
        if spec:
            sig = run_signals(spec, part, p)
            if sig.entries.iloc[-1]: pit["long_entry"].append(i)
            if sig.exits.iloc[-1]: pit["long_exit"].append(i)
            if sig.short_entries is not None:
                if sig.short_entries.iloc[-1]: pit["short_entry"].append(i)
                if sig.short_exits.iloc[-1]: pit["short_exit"].append(i)
            for k, v in sig.overlays.items():
                record(k, new_pts, i, _last(v, part.index))
            for pn, dct in sig.panes.items():
                for k, v in dct.items():
                    record(k, new_pts, i, _last(v, part.index))
        for ind in indicators or []:
            vals = indicator_values(ind["name"], part, ind.get("params") or {})["series"]
            d = ind_pts.setdefault(ind.get("key") or ind["name"], {})
            for k, v in vals.items():
                record(k, d, i, v[-1] if v else None)
    pit["last"] = hi

    upto = _slice(df, hi)
    if spec:
        # history before the live start = what the chart showed at that moment
        base = None
        if init:
            first = run_signals(spec, _slice(df, pit["start"] - 1), p) if pit["start"] > 1 else None
            if first is not None:
                base = {"overlays": {k: pd.Series(v).reindex(first.entries.index).round(6).tolist() for k, v in first.overlays.items()},
                        "panes": {pn: {k: pd.Series(v).reindex(first.entries.index).round(6).tolist() for k, v in d.items()}
                                  for pn, d in first.panes.items()},
                        "levels": first.levels}
        mk = lambda lst: pd.Series(np.isin(np.arange(len(upto)), lst), index=upto.index)  # noqa: E731
        from .base import Signals
        sig = Signals(entries=mk(pit["long_entry"]), exits=mk(pit["long_exit"]),
                      short_entries=mk(pit["short_entry"]) if (pit["short_entry"] or pit["short_exit"]) else None,
                      short_exits=mk(pit["short_exit"]) if (pit["short_entry"] or pit["short_exit"]) else None)
        s = settings_from(settings)
        sim = simulate(upto, sig, s, market)
        out["strategy"] = {"trades": trades_json(sim["trades"]), "series": series(sim, upto, s),
                           "points": new_pts, "base": base,
                           "signals": {"long_entry": pit["long_entry"], "long_exit": pit["long_exit"],
                                       "short_entry": pit["short_entry"], "short_exit": pit["short_exit"]}}
    for ind in indicators or []:
        key = ind.get("key") or ind["name"]
        item = {"key": key, "points": ind_pts.get(key, {})}
        if init and pit["start"] > 1:
            item["base"] = indicator_values(ind["name"], _slice(df, pit["start"] - 1), ind.get("params") or {})
        out["indicators"].append(item)
    out["pit"] = pit
    return out
