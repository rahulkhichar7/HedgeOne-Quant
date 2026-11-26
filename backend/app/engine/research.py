"""
Research tools on top of the backtest engine.

  optimize()      parameter grid search  -> ranked table, heatmaps, sensitivity, top equity curves
  universe()      one strategy + one parameter set on many securities -> per-symbol and combined results
  dev_backtest()  developer mode: the same strategy on a TRAIN and a held-out TEST period, compared

All three use exactly the same simulation as a normal backtest (backtest.sim_kwargs / simulate), so
a number in a research report matches what you get when you backtest that combination by itself.
Reports are stored as JSON under data/reports/<kind>/<id>.json.
"""
from __future__ import annotations

import itertools
import json
import math
import time
import uuid
from datetime import datetime

import numpy as np
import pandas as pd
import vectorbt as vbt

from .. import config
from ..data import store
from . import analysis
from .backtest import (bars_per_year, candles_json, chart_payload, epoch_seconds, get_strategy, metrics,
                       run_signals, series, settings_dict, settings_from, sim_kwargs, simulate, to_list,
                       trades_json)
from .base import Signals, record_usage
from ..data.sources import interval_seconds

MAX_COMBOS = 20_000          # hard limit per optimization run
CURVE_POINTS = 400           # points kept per equity curve in reports
CELL_BUDGET = 12_000_000     # bars x combinations simulated in one vectorbt call (memory guard)

# metrics computed for every optimizer combination (all "higher is better"; max_dd is negative %)
OPT_METRICS = [
    ("sharpe", "Sharpe", "ratio"), ("sortino", "Sortino", "ratio"), ("calmar", "Calmar", "ratio"),
    ("total_return", "Return", "pct"), ("cagr", "CAGR", "pct"), ("excess", "Excess vs B&H", "pct"),
    ("max_dd", "Max DD", "pct"), ("win_rate", "Win rate", "pct"), ("profit_factor", "Profit factor", "ratio"),
    ("expectancy_pct", "Avg trade", "pct"), ("trades", "Trades", "int"), ("exposure", "Time in mkt", "pct"),
]
OBJECTIVES = {k: l for k, l, _ in OPT_METRICS if k not in ("trades", "exposure")}

# candle sizes the optimizer can test as a "timeframe" parameter
TF_ORDER = ["1m", "2m", "3m", "5m", "10m", "15m", "20m", "30m", "45m", "1h", "2h", "3h", "4h", "1d", "1w"]
DAY = 86_400


# ======================================================================
# small helpers
# ======================================================================
def _num(v):
    """float or None (JSON has no NaN/inf)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (bool, np.bool_)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return _num(o)
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    if isinstance(o, (pd.Timestamp, datetime)):
        return o.isoformat()
    if isinstance(o, pd.Timedelta):
        return str(o)
    return o


def sample_idx(n: int, k: int = CURVE_POINTS) -> np.ndarray:
    """~k evenly spaced positions in [0, n), always including the first and last bar."""
    if n <= k:
        return np.arange(n)
    return np.unique(np.linspace(0, n - 1, k).round().astype(int))


def _bucket_min(a: np.ndarray, pos: np.ndarray) -> np.ndarray:
    """min of `a` between consecutive sample positions (keeps drawdown troughs when downsampling)."""
    if len(pos) == len(a):
        return a
    starts = np.concatenate([[0], pos[:-1] + 1])
    starts = np.minimum(starts, pos)
    return np.minimum.reduceat(a, starts) if len(a) else a


def sec_type(name: str) -> str:
    info = store.symbol_info(name)
    if info.get("market") == "CRYPTO":
        return "Crypto"
    if "INDEX" in str(info.get("symbol", "")).upper():
        return "Index"
    return "Stock"


def _flat(groups: list[dict]) -> dict:
    return {i["key"]: i["value"] for g in groups for i in g["items"]}


def _seg_df(df: pd.DataFrame, mask) -> pd.DataFrame:
    out = df.loc[mask].copy()
    out.attrs.update(df.attrs)
    return out


# ======================================================================
# Parameter grid
# ======================================================================
def _frange(a: float, b: float, step: float) -> list[float]:
    if step is None or step <= 0:
        raise ValueError("Step must be greater than 0")
    if b < a:
        a, b = b, a
    n = int(math.floor((b - a) / step + 1e-9)) + 1
    if n > 10_000:
        raise ValueError(f"Range {a}..{b} step {step} gives {n:,} values — use a bigger step")
    return [round(a + i * step, 10) for i in range(n)]


def param_values(p, spec: dict | None) -> list:
    """Values to test for one parameter.  spec:
         {"mode": "fixed", "value": 20}
         {"mode": "range", "start": 10, "stop": 50, "step": 5}
         {"mode": "list",  "values": [10, 20, 50]}   (also used for bool / dropdown params)
    """
    spec = spec or {}
    mode = spec.get("mode", "fixed")
    if mode == "range":
        vals = [p.cast(v) for v in _frange(float(spec["start"]), float(spec["stop"]), float(spec["step"]))]
    elif mode == "list":
        raw = spec.get("values")
        if isinstance(raw, str):
            raw = [x.strip() for x in raw.split(",") if x.strip()]
        vals = [p.cast(v) for v in (raw or [])]
        if not vals:
            raise ValueError("A list parameter needs at least one value")
    else:
        vals = [p.cast(spec.get("value", p.default))]
    out = []
    for v in vals:                                    # dedupe (int casting can collapse a float range)
        if v not in out:
            out.append(v)
    return out


def expand_grid(spec, grid: dict, constraint: str | None = None) -> tuple[dict, list[dict], int]:
    """-> ({param: values}, combinations, number removed by the constraint)"""
    values = {k: param_values(p, grid.get(k)) for k, p in spec.params.items()}
    total = math.prod(len(v) for v in values.values()) if values else 1
    if total > MAX_COMBOS:
        raise ValueError(f"{total:,} combinations — the limit is {MAX_COMBOS:,}. Use bigger steps or fix some parameters.")
    keys = list(values)
    combos = [dict(zip(keys, vs)) for vs in itertools.product(*values.values())] if keys else [{}]
    dropped = 0
    if constraint and constraint.strip():
        code = compile(constraint.strip(), "<constraint>", "eval")
        safe = {"__builtins__": {"abs": abs, "min": min, "max": max, "round": round}}
        kept = []
        for c in combos:
            try:
                ok = bool(eval(code, safe, dict(c)))  # noqa: S307 — local research tool, user's own expression
            except Exception as e:  # noqa: BLE001
                raise ValueError(f"Constraint error: {e}") from e
            if ok:
                kept.append(c)
        dropped = len(combos) - len(kept)
        combos = kept
    return values, combos, dropped


# ======================================================================
# Timeframe (candle size) as an optimizer dimension
# ======================================================================
def tf_key(spec) -> str:
    """name of the pseudo-parameter that holds the interval (never clashes with a real parameter)"""
    return "timeframe" if "timeframe" not in spec.params else "tf_interval"


def _tf_rule(spec, symbol: str, interval: str, start, end, params: dict | None):
    """-> (predicate(seconds) -> bool, reason shown for blocked intervals, how it was decided)"""
    tf = spec.timeframes
    if tf == "fixed":
        cur = interval_seconds(interval)
        return (lambda sec: sec == cur), "the strategy is marked timeframes=\"fixed\"", "fixed"
    if tf in (None, "auto"):
        try:                                     # probe: which helpers does the strategy actually use?
            df = store.load(symbol, interval, start, end)
            df = df.tail(3000).copy()
            df.attrs.update(symbol=symbol, interval=interval, market=store.market_of(symbol).name)
            with record_usage() as used:
                run_signals(spec, df, params or {})
        except Exception as e:  # noqa: BLE001
            return (lambda sec: True), "", f"auto (probe failed: {type(e).__name__}) — all intervals offered"
        limit, inclusive, why = math.inf, False, []
        if any(k == "intraday" for k, _ in used):
            limit, why = DAY, ["uses intraday timing (" + ", ".join(sorted({v for k, v in used if k == "intraday"})) + ")"]
        for k, v in used:
            if k == "htf":
                sec = interval_seconds(v)
                if sec < limit or (sec == limit and inclusive):
                    limit, inclusive = sec, False
                why.append(f"uses {v} candles via htf()")
            elif k == "load":
                sec = interval_seconds(v)
                if sec < limit:
                    limit, inclusive = sec, True
                why.append(f"loads other data at {v}")
        if limit == math.inf:
            return (lambda sec: True), "", "auto — the strategy only uses the chart's candles"
        pred = (lambda sec: sec <= limit) if inclusive else (lambda sec: sec < limit)
        return pred, "the strategy " + "; ".join(dict.fromkeys(why)), "auto — " + "; ".join(dict.fromkeys(why))
    if tf == "any":
        return (lambda sec: True), "", "any (set on the strategy)"
    if tf == "intraday":
        return (lambda sec: sec < DAY), "the strategy is marked intraday-only", "intraday (set on the strategy)"
    if isinstance(tf, tuple) and len(tf) == 2:
        lo, hi = interval_seconds(tf[0]), interval_seconds(tf[1])
        return (lambda sec: lo <= sec <= hi), f"outside the strategy's range {tf[0]}–{tf[1]}", f"{tf[0]}–{tf[1]} (set on the strategy)"
    if isinstance(tf, (list, set)):
        ok = {interval_seconds(x) for x in tf}
        return (lambda sec: sec in ok), "not in the strategy's list", "list (set on the strategy): " + ", ".join(tf)
    return (lambda sec: True), "", f"unknown timeframes={tf!r} — all intervals offered"


def timeframe_options(symbol: str, strategy: str, interval: str, start=None, end=None, params: dict | None = None) -> dict:
    spec = get_strategy(strategy)
    have = store.stored_intervals(symbol)
    if not have:
        raise FileNotFoundError(f"No data stored for '{symbol}'")
    pred, why, mode = _tf_rule(spec, symbol, interval, start, end, params)
    allowed, blocked = [], {}
    for iv in TF_ORDER:
        try:
            store.best_base(symbol, iv)
        except Exception:  # noqa: BLE001
            blocked[iv] = f"can't be built from the stored data ({', '.join(have)})"
            continue
        if not pred(interval_seconds(iv)):
            blocked[iv] = why
            continue
        allowed.append(iv)
    return {"allowed": allowed, "blocked": blocked, "mode": mode, "stored": have, "current": interval,
            "fixed": spec.timeframes == "fixed", "key": tf_key(spec)}


# ======================================================================
# Fast per-combination metrics
# ======================================================================
def _compact(eq: np.ndarray, recs, init_cash: float, bpy: float, bh_pct: float, n_bars: int, exposure=None) -> dict:
    eq = np.asarray(eq, dtype=float)
    total = (eq[-1] / init_cash - 1) * 100
    rets = np.concatenate([[eq[0] / init_cash - 1], eq[1:] / eq[:-1] - 1])
    rets = rets[np.isfinite(rets)]
    n = max(len(rets), 1)
    growth = 1 + total / 100
    cagr = (growth ** (bpy / n) - 1) * 100 if growth > 0 else -100.0
    sd = rets.std(ddof=1) if len(rets) > 1 else 0.0
    sharpe = rets.mean() / sd * math.sqrt(bpy) if sd > 0 else np.nan
    dsd = math.sqrt(np.mean(np.minimum(rets, 0) ** 2)) if len(rets) else 0.0
    sortino = rets.mean() / dsd * math.sqrt(bpy) if dsd > 0 else np.nan
    peak = np.maximum.accumulate(np.concatenate([[init_cash], eq]))[1:]
    max_dd = float((eq / peak - 1).min() * 100)
    calmar = (cagr / 100) / abs(max_dd / 100) if max_dd < 0 else np.nan

    closed = recs[recs["status"] == 1] if len(recs) else recs
    pnl = closed["pnl"] if len(closed) else np.array([])
    r = closed["return"] * 100 if len(closed) else np.array([])
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    if exposure is None:
        held = (recs["exit_idx"] - recs["entry_idx"]).sum() if len(recs) else 0
        exposure = min(100.0, held / max(n_bars, 1) * 100)
    return {
        "sharpe": _num(sharpe), "sortino": _num(sortino), "calmar": _num(calmar),
        "total_return": _num(total), "cagr": _num(cagr), "excess": _num(total - bh_pct),
        "max_dd": _num(max_dd), "trades": int(len(recs)),
        "win_rate": _num(len(wins) / len(pnl) * 100) if len(pnl) else None,
        "profit_factor": _num(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else None,
        "expectancy_pct": _num(r.mean()) if len(r) else None,
        "exposure": _num(exposure), "final": _num(eq[-1]),
    }


_STACK = ("entries", "exits", "short_entries", "short_exits", "sl_stop", "sl_trail", "tp_stop")


def _batch(kws: list[dict]) -> list[tuple[np.ndarray, np.ndarray]]:
    """Simulate many combinations in ONE vectorbt call (one column per combination).
    Returns [(equity array, trade records), ...].  Falls back to one call per combination
    if the batched call fails for any reason."""
    if len(kws) > 1:
        try:
            return _batch_2d(kws)
        except Exception:  # noqa: BLE001 — correctness first, the loop below is the reference path
            pass
    out = []
    for kw in kws:
        pf = vbt.Portfolio.from_signals(**kw)
        out.append((np.asarray(pf.value(), dtype=float), pf.trades.values))
    return out


def _batch_2d(kws: list[dict]) -> list[tuple[np.ndarray, np.ndarray]]:
    base = {k: v for k, v in kws[0].items() if k not in _STACK}
    for kw in kws[1:]:                     # everything else must be identical (it is: same df + settings)
        if set(k for k in kw if k not in _STACK) != set(base):
            raise ValueError("incompatible")
    idx = kws[0]["entries"].index
    cols = pd.RangeIndex(len(kws))
    false = pd.Series(False, index=idx)

    def frame(key, fill, dtype):
        data = {}
        for j, kw in enumerate(kws):
            v = kw.get(key)
            if v is None:
                data[j] = fill if isinstance(fill, pd.Series) else pd.Series(fill, index=idx)
            elif isinstance(v, pd.Series):
                data[j] = v
            else:
                data[j] = pd.Series(v, index=idx)
        return pd.DataFrame(data, index=idx, columns=cols).astype(dtype)

    kw2 = dict(base)
    kw2["entries"] = frame("entries", false, bool)
    kw2["exits"] = frame("exits", false, bool)
    if any(kw.get("short_entries") is not None for kw in kws):
        kw2["short_entries"] = frame("short_entries", false, bool)
        kw2["short_exits"] = frame("short_exits", false, bool)
    if any(kw.get("sl_stop") is not None for kw in kws):
        kw2["sl_stop"] = frame("sl_stop", np.nan, float)
        kw2["sl_trail"] = frame("sl_trail", False, bool)
    if any(kw.get("tp_stop") is not None for kw in kws):
        kw2["tp_stop"] = frame("tp_stop", np.nan, float)
    pf = vbt.Portfolio.from_signals(**kw2)
    val = np.asarray(pf.value(), dtype=float)
    if val.ndim == 1:
        val = val[:, None]
    recs = pf.trades.values
    has_col = recs.dtype.names is not None and "col" in recs.dtype.names
    out = []
    for j in range(len(kws)):
        r = recs[recs["col"] == j] if has_col else (recs if len(kws) == 1 else None)
        if r is None:
            raise ValueError("no col field")
        out.append((val[:, j], r))
    return out


# ======================================================================
# 1) Parameter optimizer
# ======================================================================
def _norm_tfs(intervals, interval: str) -> list[str]:
    tfs = list(dict.fromkeys([x for x in (intervals or []) if x])) or [interval]
    for x in tfs:
        interval_seconds(x)                       # validates the spelling
    return sorted(tfs, key=interval_seconds)


def count_combos(spec, grid, constraint, intervals, interval) -> dict:
    values, combos, dropped = expand_grid(spec, grid or {}, constraint)
    tfs = _norm_tfs(intervals, interval)
    total = len(combos) * len(tfs)
    if total > MAX_COMBOS:
        raise ValueError(f"{total:,} combinations ({len(combos):,} × {len(tfs)} timeframes) — the limit is "
                         f"{MAX_COMBOS:,}. Use bigger steps, fewer timeframes or fix some parameters.")
    return {"combos": total, "per_timeframe": len(combos), "timeframes": tfs, "dropped": dropped * len(tfs), "values": values}


def optimize(symbol: str, interval: str, start=None, end=None, strategy: str = "", grid: dict | None = None,
             settings: dict | None = None, objective: str = "sharpe", min_trades: int = 5,
             constraint: str | None = None, context: dict | None = None, intervals: list[str] | None = None,
             progress=None) -> dict:
    t0 = time.perf_counter()
    say = progress or (lambda m: None)
    if objective not in OBJECTIVES:
        raise ValueError(f"Unknown objective '{objective}'")
    market = store.market_of(symbol)
    spec = get_strategy(strategy)
    s = settings_from(settings)
    cnt = count_combos(spec, grid, constraint, intervals, interval)
    values, combos, dropped = expand_grid(spec, grid or {}, constraint)
    if not combos:
        raise ValueError("No combinations left to test (check the constraint)")
    tfs = cnt["timeframes"]
    multi = len(tfs) > 1
    TFK = tf_key(spec)
    if multi:
        values[TFK] = tfs                          # the interval behaves like one more parameter
    varying = [k for k, v in values.items() if len(v) > 1]
    total = cnt["combos"]
    say(f"[0/{total}] {total:,} combinations" + (f" on {len(tfs)} timeframes" if multi else ""))

    rows, curves, errors, frames, tf_failed = [], [], [], {}, {}
    done = 0
    for tf in tfs:
        try:
            df = store.load(symbol, tf, start, end)
            if len(df) < 2:
                raise ValueError("not enough candles in the selected range")
        except Exception as e:  # noqa: BLE001
            errors.append({"params": {TFK: tf} if multi else {}, "error": f"{tf}: {type(e).__name__}: {e}"})
            tf_failed[tf] = f"{type(e).__name__}: {e}"
            done += len(combos)
            continue
        n = len(df)
        bpy = bars_per_year(tf, market)
        bh = float((df.close.iloc[-1] / df.close.iloc[0] - 1) * 100)
        pos = sample_idx(n)
        frames[tf] = {"df": df, "pos": pos, "t": epoch_seconds(df.index[pos]), "bh": bh, "bars": n,
                      "start": str(df.index[0]), "end": str(df.index[-1]), "base": store.best_base(symbol, tf, start, end)}
        chunk = max(1, min(400, CELL_BUDGET // max(n, 1)))
        for k in range(0, len(combos), chunk):
            part = combos[k:k + chunk]
            kws, ok = [], []
            for c in part:
                try:
                    sig = run_signals(spec, df, c)
                    kw, _ = sim_kwargs(df, sig, s, market)
                    kws.append(kw)
                    ok.append(c)
                except Exception as e:  # noqa: BLE001 — one bad combination must not kill the run
                    errors.append({"params": {**c, **({TFK: tf} if multi else {})}, "error": f"{type(e).__name__}: {e}"})
            if kws:
                for c, (eq, recs) in zip(ok, _batch(kws)):
                    m = _compact(eq, recs, s.init_cash, bpy, bh, n)
                    rows.append({"params": {**c, **({TFK: tf} if multi else {})}, "interval": tf, **m})
                    curves.append((tf, np.round(eq[pos] / s.init_cash * 100 - 100, 3).astype(np.float32)))
            done += len(part)
            say(f"[{done}/{total}] backtested {done:,} of {total:,} combinations" + (f" ({tf})" if multi else ""))
    if not rows:
        raise ValueError("Every combination failed: " + (errors[0]["error"] if errors else "unknown error"))

    # ---- rank
    def score(r):
        v = r.get(objective)
        return v if v is not None else -math.inf
    order = sorted(range(len(rows)), key=lambda i: (rows[i]["trades"] >= min_trades, score(rows[i])), reverse=True)
    rows = [rows[i] for i in order]
    curves = [curves[i] for i in order]
    for rank, r in enumerate(rows, 1):
        r["rank"] = rank
        r["eligible"] = r["trades"] >= min_trades
    best = rows[0]

    # ---- the best combination, fully (same path as the Backtest button)
    say(f"[{total}/{total}] full backtest of the best combination")
    F = frames[best["interval"]]
    df, pos, n, bh = F["df"], F["pos"], F["bars"], F["bh"]
    sig = run_signals(spec, df, best["params"])
    sim = simulate(df, sig, s, market)
    best_metrics = metrics(sim, df, s)
    eq = np.asarray(sim["pf"].value(), dtype=float)
    dd = np.asarray(sim["pf"].drawdown(), dtype=float) * 100
    times = epoch_seconds(df.index[pos])
    best_series = {"t": times, "equity": to_list(eq[pos], 2),
                   "benchmark": to_list((df.close.to_numpy()[pos] / df.close.iloc[0]) * s.init_cash, 2),
                   "drawdown": to_list(_bucket_min(dd, pos), 3)}

    top = [i for i, r in enumerate(rows) if r["eligible"]][:10] or [0]
    top_curves = [{"rank": rows[i]["rank"], "params": rows[i]["params"], "interval": curves[i][0],
                   "t": frames[curves[i][0]]["t"], "values": to_list(curves[i][1], 3)} for i in top]
    by_tf = []
    for tf in tfs:
        if tf not in frames:
            continue
        rs = [r for r in rows if r["interval"] == tf]
        el = [r for r in rs if r["eligible"]] or rs
        b = el[0] if el else None                                      # rows are already ranked
        by_tf.append({"interval": tf, "bars": frames[tf]["bars"], "buy_hold": frames[tf]["bh"], "tested": len(rs),
                      "start": frames[tf]["start"], "end": frames[tf]["end"], "built_from": frames[tf]["base"],
                      "eligible": sum(r["eligible"] for r in rs),
                      "profitable": _num(np.mean([(r["total_return"] or 0) > 0 for r in rs]) * 100) if rs else None,
                      "best": {k: b[k] for k in ("params", "rank", "total_return", "sharpe", "trades", "max_dd", objective)} if b else None})
    sens = _sensitivity(rows, values, varying, objective)
    neighbours = _neighbours(rows, values, varying, objective)
    elapsed = round((time.perf_counter() - t0) * 1000)

    payload = {
        "kind": "optimize",
        "meta": {"symbol": symbol, "interval": best["interval"], "base_interval": interval, "timeframes": tfs,
                 "tf_key": TFK if multi else None, "tf_failed": tf_failed,
                 "tf_minutes": {tf: interval_seconds(tf) / 60 for tf in tfs},
                 "market": market.name, "strategy": strategy,
                 "category": spec.category, "start": str(df.index[0]), "end": str(df.index[-1]), "bars": n,
                 "objective": objective, "objective_label": OBJECTIVES[objective], "min_trades": int(min_trades),
                 "constraint": constraint or "", "settings": settings_dict(s), "costs": sim["costs"],
                 "grid": grid or {}, "values": values, "varying": varying, "combos": total,
                 "tested": len(rows), "failed": len(errors), "dropped_by_constraint": dropped,
                 "buy_hold": bh, "elapsed_ms": elapsed, "context": context or {},
                 "created": datetime.now().isoformat(timespec="seconds"), "source": spec.source()},
        "metric_defs": [{"key": k, "label": l, "fmt": f} for k, l, f in OPT_METRICS],
        "rows": rows,
        "best": {"params": best["params"], "metrics": best_metrics, "series": best_series,
                 "trades": int(len(sim["trades"]))},
        "curves": {"t": times, "top": top_curves},
        "by_timeframe": by_tf,
        "sensitivity": sens,
        "neighbours": neighbours,
        "errors": errors[:50],
    }
    payload["insights"] = _opt_insights(payload)
    rid = save("optimize", payload)
    say(f"[{total}/{total}] done in {elapsed / 1000:.1f}s")
    return {"kind": "optimize", "id": rid, "url": f"/optimize.html?id={rid}"}


def _sensitivity(rows, values, varying, objective):
    """For each varying parameter: how the objective changes with its value (over all other params)."""
    out = {}
    for k in varying:
        stats = []
        for v in values[k]:
            sc = [r[objective] for r in rows if r["params"].get(k) == v and r.get(objective) is not None]
            prof = [r for r in rows if r["params"].get(k) == v]
            stats.append({"value": v, "n": len(prof),
                          "mean": _num(np.mean(sc)) if sc else None, "median": _num(np.median(sc)) if sc else None,
                          "best": _num(np.max(sc)) if sc else None, "worst": _num(np.min(sc)) if sc else None,
                          "profitable": _num(np.mean([(r["total_return"] or 0) > 0 for r in prof]) * 100) if prof else None})
        out[k] = stats
    return out


def _neighbours(rows, values, varying, objective):
    """Is the best result a plateau (neighbours almost as good) or a lonely spike?"""
    if not varying:
        return None
    best = rows[0]
    pos = {k: {v: i for i, v in enumerate(values[k])} for k in varying}
    bi = {k: pos[k][best["params"][k]] for k in varying}
    nb = []
    for r in rows[1:]:
        try:
            if all(abs(pos[k][r["params"][k]] - bi[k]) <= 1 for k in varying) and \
               all(r["params"].get(k) == best["params"].get(k) for k in best["params"] if k not in varying):
                nb.append(r)
        except KeyError:
            continue
    sc = [r[objective] for r in nb if r.get(objective) is not None]
    return {"count": len(nb), "mean": _num(np.mean(sc)) if sc else None, "min": _num(np.min(sc)) if sc else None,
            "best": best.get(objective),
            "profitable": _num(np.mean([(r["total_return"] or 0) > 0 for r in nb]) * 100) if nb else None}


def _opt_insights(P) -> list[dict]:
    m, rows, best = P["meta"], P["rows"], P["rows"][0]
    obj, lab = m["objective"], m["objective_label"]
    out = []
    add = lambda lvl, t, x: out.append({"level": lvl, "title": t, "text": x})  # noqa: E731
    if m.get("context", {}).get("dev"):
        add("info", "Optimized on the TRAIN period only",
            "The test period was not used. Load the best parameters in the terminal and press Backtest "
            "in developer mode to see how they do on unseen data.")
    if m.get("tf_failed"):
        add("warn", f"{len(m['tf_failed'])} timeframe(s) couldn't be tested",
            "; ".join(f"{k}: {v}" for k, v in m["tf_failed"].items()))
    bt = [x for x in (P.get("by_timeframe") or []) if x.get("best")]
    if len(bt) > 1:
        fmt = lambda v: "—" if v is None else f"{v:.2f}"  # noqa: E731
        add("info", f"Best timeframe: {best.get('interval')}",
            f"Best {lab} per timeframe — " + " · ".join(f"{x['interval']} {fmt(x['best'].get(obj))}" for x in bt) +
            ". Parameters are counted in candles, so similar results on neighbouring timeframes with "
            "proportionally different lengths are the same idea (see 'Lookback in time').")
        tfs = m.get("timeframes") or []
        if len(tfs) > 2 and best.get("interval") in (tfs[0], tfs[-1]):
            add("info", "Best timeframe is at the edge of the tested ones",
                f"{best['interval']} is the {'smallest' if best['interval'] == tfs[0] else 'largest'} timeframe tested — "
                "include the next one too, to see whether it keeps improving.")
        span = {x["interval"]: (pd.Timestamp(x["end"]) - pd.Timestamp(x["start"])).total_seconds() for x in bt}
        longest = max(span.values()) or 1
        short = [k for k, v in span.items() if v < longest * 0.9]
        if short:
            add("warn", "Timeframes cover different periods",
                "Less history is stored for " + ", ".join(f"{x['interval']} ({x['start'][:10]} → {x['end'][:10]}, built from {x['built_from']})"
                                                         for x in bt if x["interval"] in short) +
                " than for the others, so they aren't compared on the same market. Set a common date range, or download "
                "the finest interval for the whole period (the larger timeframes are built from it).")
        fin = bt[0]
        if (fin["best"].get("total_return") or 0) <= 0 and any((x["best"].get("total_return") or 0) > 0 for x in bt[1:]):
            add("info", f"The smallest candles ({fin['interval']}) don't pay", "More trades means more fees and slippage — "
                "the same idea only makes money on larger candles here.")
    if not best["eligible"]:
        add("bad", "No combination reached the minimum trade count",
            f"Every combination made fewer than {m['min_trades']} trades, so the ranking is not meaningful.")
    if best["trades"] < 30:
        add("warn", "Small sample", f"The best combination made only {best['trades']} trades. "
            "Results this small can easily be luck — prefer longer periods or more active settings.")
    nb = P.get("neighbours")
    bv = best.get(obj)
    if nb and nb["count"] and nb["mean"] is not None and bv not in (None, 0):
        ratio = nb["mean"] / bv if bv > 0 else None
        if ratio is not None and ratio >= 0.75:
            add("good", "Stable plateau", f"Neighbouring parameter values (±1 step) average {lab} {nb['mean']:.2f} "
                f"vs {bv:.2f} for the best — small changes don't break it, which is what a real edge looks like.")
        elif ratio is not None and ratio < 0.5:
            add("warn", "Isolated peak", f"Neighbouring values (±1 step) average only {lab} {nb['mean']:.2f} vs "
                f"{bv:.2f} for the best. A lonely spike is usually curve-fitting — pick a value from a broad good area instead.")
    prof = np.mean([(r["total_return"] or 0) > 0 for r in rows]) * 100
    if prof < 30:
        add("warn", f"Only {prof:.0f}% of combinations are profitable",
            "Most settings lose money, so the strategy idea itself may not have an edge on this data.")
    elif prof > 70:
        add("good", f"{prof:.0f}% of combinations are profitable", "The idea works across most settings, not just a lucky few.")
    if m["tested"] > 200:
        add("info", f"{m['tested']:,} combinations tested",
            "The more combinations you try, the more the top result is inflated by chance. Confirm it on the "
            "test period (developer mode) and on other securities (universe test).")
    for k in m["varying"]:
        vals = m["values"][k]
        v = best["params"].get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and len(vals) > 2 and v in (vals[0], vals[-1]):
            add("info", f"Best '{k}' is at the edge of the tested range",
                f"{k} = {v} is the {'lowest' if v == vals[0] else 'highest'} value tested — widen the range to check whether it keeps improving.")
    if (best.get("excess") or 0) < 0:
        add("info", "Doesn't beat buy & hold", f"The best combination returns {best['total_return'] or 0:.2f}% vs "
            f"{m['buy_hold'] or 0:.2f}% for buy & hold over the same period (but check drawdown and time in market).")
    return out


# ======================================================================
# 2) Universe test
# ======================================================================
def universe(symbols: list[str], interval: str, start=None, end=None, strategy: str = "",
             params: dict | None = None, settings: dict | None = None, progress=None) -> dict:
    t0 = time.perf_counter()
    say = progress or (lambda m: None)
    symbols = list(dict.fromkeys(symbols or []))
    if not symbols:
        raise ValueError("Select at least one security")
    spec = get_strategy(strategy)
    p = spec.resolve(params)
    s = settings_from(settings)
    results = []
    for i, sym in enumerate(symbols):
        say(f"[{i}/{len(symbols)}] {sym}")
        try:
            results.append(_one_security(sym, interval, start, end, spec, p, s))
        except Exception as e:  # noqa: BLE001
            results.append({"symbol": sym, "ok": False, "error": f"{type(e).__name__}: {e}",
                            "type": _safe_type(sym)})
    ok = [r for r in results if r["ok"]]
    elapsed = round((time.perf_counter() - t0) * 1000)
    payload = {
        "kind": "universe",
        "meta": {"strategy": strategy, "category": spec.category, "params": p, "interval": interval,
                 "start": start, "end": end, "settings": settings_dict(s), "symbols": symbols,
                 "ok": len(ok), "failed": len(results) - len(ok), "elapsed_ms": elapsed,
                 "created": datetime.now().isoformat(timespec="seconds"), "source": spec.source()},
        "results": results,
        "summary": _uni_summary(ok),
    }
    payload["insights"] = _uni_insights(payload)
    rid = save("universe", payload)
    say(f"[{len(symbols)}/{len(symbols)}] done in {elapsed / 1000:.1f}s")
    return {"kind": "universe", "id": rid, "url": f"/universe.html?id={rid}"}


def _safe_type(sym):
    try:
        return sec_type(sym)
    except Exception:  # noqa: BLE001
        return "Unknown"


def _one_security(sym, interval, start, end, spec, p, s) -> dict:
    df = store.load(sym, interval, start, end)
    if len(df) < 2:
        raise ValueError("Not enough candles in the selected range")
    market = store.market_of(sym)
    sig = run_signals(spec, df, p)
    sim = simulate(df, sig, s, market)
    groups = metrics(sim, df, s)
    eq_s = sim["pf"].value()
    eq = np.asarray(eq_s, dtype=float)
    dd = np.asarray(sim["pf"].drawdown(), dtype=float) * 100
    close = df.close.to_numpy(dtype=float)
    pos = sample_idx(len(df))
    curve = {"t": epoch_seconds(df.index[pos]),
             "eq": to_list(eq[pos] / s.init_cash * 100 - 100, 3),
             "bh": to_list(close[pos] / close[0] * 100 - 100, 3),
             "dd": to_list(_bucket_min(dd, pos), 3)}
    # daily closes of equity and price -> combined portfolio & correlations in the report
    d_eq = eq_s.resample("1D").last().dropna()
    d_px = df.close.resample("1D").last().reindex(d_eq.index).ffill()
    daily = {"d": [x.strftime("%Y-%m-%d") for x in d_eq.index], "eq": to_list(d_eq.to_numpy(), 4),
             "px": to_list(d_px.to_numpy(), 6)}
    yearly = []
    for y in sorted(set(eq_s.index.year)):
        e, c = eq_s[eq_s.index.year == y], df.close[df.close.index.year == y]
        pe = eq_s[eq_s.index.year < y].iloc[-1] if (eq_s.index.year < y).any() else s.init_cash
        pc = df.close[df.close.index.year < y].iloc[-1] if (df.close.index.year < y).any() else df.close.iloc[0]
        yearly.append({"year": int(y), "strategy": _num((e.iloc[-1] / pe - 1) * 100),
                       "buy_hold": _num((c.iloc[-1] / pc - 1) * 100)})
    tr = sim["trades"]
    return {"symbol": sym, "ok": True, "type": sec_type(sym), "market": market.name,
            "start": str(df.index[0]), "end": str(df.index[-1]), "bars": len(df), "costs": sim["costs"],
            "metrics": groups, "kp": _flat(groups), "curve": curve, "daily": daily, "yearly": yearly,
            "monthly": analysis.monthly_table(eq_s), "drawdowns": analysis.drawdown_periods(eq_s),
            "trades": trades_json(tr.tail(500)) if len(tr) else [], "trade_count": int(len(tr))}


def _uni_summary(ok: list[dict]) -> dict:
    if not ok:
        return {}
    g = lambda k: [r["kp"].get(k) for r in ok if r["kp"].get(k) is not None]  # noqa: E731
    ret, sh = g("total_return"), g("sharpe")
    best = max(ok, key=lambda r: r["kp"].get("total_return") or -1e18)
    worst = min(ok, key=lambda r: r["kp"].get("total_return") or 1e18)
    return {"n": len(ok), "profitable": sum(1 for v in ret if v > 0),
            "beat_bh": sum(1 for r in ok if (r["kp"].get("excess") or 0) > 0),
            "median_return": _num(np.median(ret)) if ret else None, "mean_return": _num(np.mean(ret)) if ret else None,
            "median_sharpe": _num(np.median(sh)) if sh else None,
            "best": {"symbol": best["symbol"], "ret": best["kp"].get("total_return")},
            "worst": {"symbol": worst["symbol"], "ret": worst["kp"].get("total_return")},
            "trades": int(sum(r["kp"].get("trades") or 0 for r in ok))}


def _uni_insights(P) -> list[dict]:
    S, res = P["summary"], [r for r in P["results"] if r["ok"]]
    out = []
    add = lambda lvl, t, x: out.append({"level": lvl, "title": t, "text": x})  # noqa: E731
    if not res:
        return [{"level": "bad", "title": "No security could be tested", "text": "See the errors at the bottom."}]
    share = S["profitable"] / S["n"] * 100
    if share >= 70:
        add("good", f"Profitable on {S['profitable']} of {S['n']} securities",
            "The edge generalises — it isn't tied to one lucky chart.")
    elif share < 40:
        add("bad", f"Profitable on only {S['profitable']} of {S['n']} securities",
            "The parameters probably fit the security you developed them on, not a general behaviour.")
    else:
        add("warn", f"Profitable on {S['profitable']} of {S['n']} securities", "Mixed results — look for what the winners have in common (type, volatility, trend).")
    by = {}
    for r in res:
        by.setdefault(r["type"], []).append(r["kp"].get("total_return") or 0)
    if len(by) > 1:
        med = {t: float(np.median(v)) for t, v in by.items()}
        bt, wt = max(med, key=med.get), min(med, key=med.get)
        if med[bt] - med[wt] > 5:
            add("info", f"Works best on {bt}", f"Median return: " + ", ".join(f"{t} {v:.1f}%" for t, v in sorted(med.items(), key=lambda x: -x[1])) + ".")
    few = [r["symbol"] for r in res if (r["kp"].get("trades") or 0) < 10]
    if few:
        add("warn", f"{len(few)} securit{'y' if len(few) == 1 else 'ies'} with fewer than 10 trades",
            "Their results are not statistically meaningful: " + ", ".join(few[:8]) + ("…" if len(few) > 8 else ""))
    if S["beat_bh"] < S["n"] / 2:
        add("info", f"Beats buy & hold on {S['beat_bh']} of {S['n']}", "Compare drawdown and time in market too — "
            "lower risk can be worth a lower return.")
    if P["meta"]["failed"]:
        add("warn", f"{P['meta']['failed']} securit{'y' if P['meta']['failed'] == 1 else 'ies'} failed", "Usually missing data for this interval or date range — see the list at the bottom.")
    return out


# ======================================================================
# 3) Developer mode: train vs test
# ======================================================================
COMPARE = [("total_return", "Total return", "pct"), ("cagr", "CAGR", "pct"), ("excess", "Excess vs buy & hold", "pct"),
           ("sharpe", "Sharpe ratio", "ratio"), ("sortino", "Sortino ratio", "ratio"), ("calmar", "Calmar ratio", "ratio"),
           ("max_dd", "Max drawdown", "pct"), ("volatility", "Volatility (ann.)", "pct"),
           ("trades", "Total trades", "int"), ("win_rate", "Win rate", "pct"), ("profit_factor", "Profit factor", "ratio"),
           ("expectancy_pct", "Avg trade return", "pct"), ("avg_win", "Avg win", "pct"), ("avg_loss", "Avg loss", "pct"),
           ("exposure", "Time in market", "pct")]


def _ts(v, end=False):
    if not v:
        raise ValueError("Train and test periods need a start and an end date")
    t = pd.Timestamp(v)
    if end and len(str(v)) <= 10:
        t = t + pd.Timedelta(hours=23, minutes=59, seconds=59)
    return t


def dev_backtest(symbol: str, interval: str, train: dict, test: dict, strategy: str,
                 params: dict | None = None, settings: dict | None = None) -> dict:
    t0 = time.perf_counter()
    a0, a1 = _ts(train.get("start")), _ts(train.get("end"), True)
    b0, b1 = _ts(test.get("start")), _ts(test.get("end"), True)
    if a1 <= a0 or b1 <= b0:
        raise ValueError("Each period's end must be after its start")
    if not (a1 < b0 or b1 < a0):
        raise ValueError("Train and test periods overlap — the test period must be data the strategy has never seen")
    lo, hi = min(a0, b0), max(a1, b1)
    df = store.load(symbol, interval, lo, hi)
    market = store.market_of(symbol)
    spec = get_strategy(strategy)
    p = spec.resolve(params)
    s = settings_from(settings)
    # one continuous run so indicators are warmed up when the test period starts (signals at bar i only
    # use bars <= i — the replay look-ahead check verifies that), then each period is traded separately
    sig = run_signals(spec, df, p)
    full = {"candles": candles_json(df), "chart": chart_payload(sig, df)}
    n = len(df)
    out = {}
    for name, (x0, x1) in (("train", (a0, a1)), ("test", (b0, b1))):
        mask = (df.index >= x0) & (df.index <= x1)
        if mask.sum() < 2:
            raise ValueError(f"Not enough candles in the {name} period ({x0.date()} → {x1.date()})")
        off = int(np.flatnonzero(mask)[0])
        seg = _seg_df(df, mask)
        ss = Signals(entries=sig.entries[mask], exits=sig.exits[mask],
                     short_entries=sig.short_entries[mask] if sig.short_entries is not None else None,
                     short_exits=sig.short_exits[mask] if sig.short_exits is not None else None,
                     sl=sig.sl, tp=sig.tp, trailing=sig.trailing)
        sim = simulate(seg, ss, s, market)
        groups = metrics(sim, seg, s)
        ser = series(sim, seg, s)
        trades = trades_json(sim["trades"])
        for t in trades:
            t["entry_idx"] += off
            t["exit_idx"] += off
            t["segment"] = name
        # full-length series (None outside the period) so the chart can draw both periods
        pad = lambda vals: [None] * off + vals + [None] * (n - off - len(vals))  # noqa: E731
        out[name] = {"start": str(seg.index[0]), "end": str(seg.index[-1]), "bars": len(seg), "offset": off,
                     "metrics": groups, "kp": _flat(groups), "trades": trades,
                     "series": {k: pad(v) for k, v in ser.items()}, "costs": sim["costs"]}
    rows = []
    for k, label, fmt in COMPARE:
        tv, sv = out["train"]["kp"].get(k), out["test"]["kp"].get(k)
        rows.append({"key": k, "label": label, "fmt": fmt, "train": tv, "test": sv,
                     "diff": _num(sv - tv) if isinstance(tv, (int, float)) and isinstance(sv, (int, float)) else None})
    verdict, insights = _dev_verdict(out["train"]["kp"], out["test"]["kp"])
    return {
        "meta": {"symbol": symbol, "interval": interval, "market": market.name, "strategy": strategy,
                 "category": spec.category, "params": p, "settings": settings_dict(s),
                 "train": {"start": str(a0), "end": str(a1)}, "test": {"start": str(b0), "end": str(b1)},
                 "elapsed_ms": round((time.perf_counter() - t0) * 1000)},
        "full": full, "train": out["train"], "test": out["test"],
        "trades": out["train"]["trades"] + out["test"]["trades"],
        "compare": rows, "verdict": verdict, "insights": insights,
    }


def _dev_verdict(tr: dict, te: dict) -> tuple[dict, list[dict]]:
    ins = []
    add = lambda lvl, t, x: ins.append({"level": lvl, "title": t, "text": x})  # noqa: E731
    g = lambda d, k: d.get(k) if isinstance(d.get(k), (int, float)) else None  # noqa: E731
    r_tr, r_te = g(tr, "total_return") or 0, g(te, "total_return") or 0
    s_tr, s_te = g(tr, "sharpe"), g(te, "sharpe")
    n_te = g(te, "trades") or 0
    score = 0
    if r_tr <= 0:
        add("bad", "Loses money even on the training data", "There's nothing to validate yet — keep developing on the train period.")
        return {"level": "bad", "title": "Not working in-sample", "text": "Improve the strategy on the train period first."}, ins
    if r_te > 0:
        score += 1
        add("good", "Profitable on unseen data", f"Test return {r_te:.2f}% (train {r_tr:.2f}%).")
    else:
        score -= 2
        add("bad", "Loses money on the test period", f"Test return {r_te:.2f}% vs {r_tr:.2f}% on train — classic sign of over-fitting.")
    if s_tr and s_te is not None and s_tr > 0:
        keep = s_te / s_tr
        if keep >= 0.7:
            score += 1
            add("good", "Risk-adjusted return holds up", f"Test Sharpe {s_te:.2f} is {keep * 100:.0f}% of train Sharpe {s_tr:.2f}.")
        elif keep >= 0.4:
            add("warn", "Sharpe degrades on test", f"Test Sharpe {s_te:.2f} is {keep * 100:.0f}% of train {s_tr:.2f}. Some decay is normal; this much suggests partial over-fit.")
        else:
            score -= 1
            add("bad", "Sharpe collapses on test", f"Test Sharpe {s_te:.2f} vs train {s_tr:.2f} ({keep * 100:.0f}% kept).")
    w_tr, w_te = g(tr, "win_rate"), g(te, "win_rate")
    if w_tr is not None and w_te is not None and w_tr - w_te > 12:
        add("warn", "Win rate drops", f"{w_tr:.0f}% on train → {w_te:.0f}% on test.")
    d_tr, d_te = g(tr, "max_dd"), g(te, "max_dd")
    if d_tr is not None and d_te is not None and d_tr < 0 and abs(d_te) > abs(d_tr) * 1.5:
        add("warn", "Deeper drawdown on test", f"Max drawdown {d_te:.1f}% on test vs {d_tr:.1f}% on train.")
    pf_te = g(te, "profit_factor")
    if pf_te is not None and pf_te < 1:
        add("bad", "Profit factor below 1 on test", f"Profit factor {pf_te:.2f} — losing trades outweigh winners.")
    if n_te < 15:
        add("warn", f"Only {int(n_te)} trades in the test period", "Too few to judge with confidence — use a longer test period if you can.")
    if score >= 2:
        v = {"level": "good", "title": "Holds up out-of-sample",
             "text": "The test results confirm the train results. Next: run a universe test with these parameters."}
    elif score >= 0:
        v = {"level": "warn", "title": "Partly holds up", "text": "Usable but weaker on unseen data. Prefer simpler rules / broader parameter plateaus."}
    else:
        v = {"level": "bad", "title": "Does not hold up", "text": "The train result doesn't carry over — likely over-fitted. Don't tune on the test period; go back to the train period."}
    return v, ins


# ======================================================================
# Report storage: data/reports/<kind>/<id>.json
# ======================================================================
KINDS = ("optimize", "universe")


def _dir(kind: str):
    if kind not in KINDS:
        raise KeyError(f"Unknown report kind '{kind}'")
    d = config.REPORTS_DIR / kind
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_id(rid: str) -> str:
    if not rid or any(c in rid for c in "/\\.") or len(rid) > 64:
        raise FileNotFoundError(rid)
    return rid


def dumps(payload) -> str:
    return json.dumps(_clean(payload), allow_nan=False, separators=(",", ":"), default=str)


def save(kind: str, payload: dict) -> str:
    rid = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    payload["id"] = rid
    (_dir(kind) / f"{rid}.json").write_text(dumps(payload), encoding="utf-8")
    return rid


def load(kind: str, rid: str) -> dict:
    p = _dir(kind) / f"{_safe_id(rid)}.json"
    if not p.exists():
        raise FileNotFoundError(rid)
    return json.loads(p.read_text(encoding="utf-8"))


def delete(kind: str, rid: str):
    p = _dir(kind) / f"{_safe_id(rid)}.json"
    if p.exists():
        p.unlink()


def list_all() -> list[dict]:
    out = []
    for kind in KINDS:
        for p in sorted(_dir(kind).glob("*.json"), reverse=True):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            m = d.get("meta", {})
            item = {"kind": kind, "id": d.get("id", p.stem), "strategy": m.get("strategy"),
                    "interval": m.get("interval"), "created": m.get("created")}
            if kind == "optimize":
                b = (d.get("rows") or [{}])[0]
                item.update(symbol=m.get("symbol"), start=m.get("start"), end=m.get("end"), combos=m.get("tested"),
                            objective=m.get("objective_label"), best=b.get(m.get("objective")),
                            best_params=b.get("params"), dev=bool(m.get("context", {}).get("dev")))
            else:
                sm = d.get("summary", {})
                item.update(symbols=len(m.get("symbols", [])), profitable=sm.get("profitable"), ok=m.get("ok"),
                            median_return=sm.get("median_return"), start=m.get("start"), end=m.get("end"),
                            params=m.get("params"))
            out.append(item)
    out.sort(key=lambda x: x.get("created") or "", reverse=True)
    return out
