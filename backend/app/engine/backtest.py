"""
Backtest engine on top of vectorbt (open-source, >=1.2).

Pipeline:   candles ─► strategy(df, **params) ─► Signals ─► vbt.Portfolio.from_signals
                                                         ─► trades / metrics / series

Realism choices (all switchable in BacktestSettings):
  * signals are computed on bar close and FILLED ON THE NEXT BAR'S OPEN (no look-ahead)
  * per-side fees + slippage from a market cost preset (config.COST_PRESETS)
  * Sharpe/Sortino/CAGR annualised with the market's real trading calendar
    (NSE: 252 days x session bars, crypto: 365 x 24h)
  * optional NSE intraday square-off (no overnight positions)
"""
from __future__ import annotations

import math
import warnings
from dataclasses import asdict, fields

import numpy as np
import pandas as pd
import vectorbt as vbt

from .. import config
from ..data.sources import interval_timedelta, parse_interval
from .base import INDICATORS, STRATEGIES, Signals, Spec, last_bar_of_day

warnings.filterwarnings("ignore", category=RuntimeWarning)


# ======================================================================
# Helpers
# ======================================================================
def settings_from(d: dict | None) -> config.BacktestSettings:
    """Build BacktestSettings from a loose dict (UI / CLI), casting strings to the field types."""
    out = {}
    for f in fields(config.BacktestSettings):
        v = (d or {}).get(f.name)
        if v is None or v == "":
            continue
        t = str(f.type)
        if "bool" in t:
            v = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")
        elif "float" in t:
            v = float(v)
        elif "dict" in t:
            v = dict(v)
        else:
            v = str(v)
        out[f.name] = v
    return config.BacktestSettings(**out)


def bars_per_year(interval: str, market: config.Market) -> float:
    n, unit = parse_interval(interval)
    if unit == "d":
        return market.trading_days / n
    if unit == "w":
        return 52 / n
    if unit == "M":
        return 12 / n
    bar_min = interval_timedelta(interval).total_seconds() / 60
    return math.ceil(market.session_minutes / bar_min) * market.trading_days


def to_list(s: pd.Series | np.ndarray, nd: int = 6) -> list:
    a = np.asarray(s, dtype=float)
    a = np.round(a, nd)
    return [None if not np.isfinite(x) else float(x) for x in a]


def epoch_seconds(idx: pd.DatetimeIndex) -> list[int]:
    """Naive IST timestamps -> 'UTC' seconds, so the chart shows IST wall-clock time."""
    return (pd.DatetimeIndex(idx).as_unit("s").asi8).tolist()


def _bool(s, index) -> pd.Series:
    if s is None:
        return pd.Series(False, index=index)
    if not isinstance(s, pd.Series):
        s = pd.Series(s, index=index)
    return s.reindex(index).fillna(False).astype(bool)


def _hm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


# ======================================================================
# Strategy / indicator execution
# ======================================================================
def get_strategy(name: str) -> Spec:
    if name not in STRATEGIES:
        raise KeyError(f"Unknown strategy '{name}'")
    return STRATEGIES[name]


def run_signals(spec: Spec, df: pd.DataFrame, params: dict) -> Signals:
    sig = spec.func(df, **spec.resolve(params))
    if not isinstance(sig, Signals):
        raise TypeError(f"Strategy '{spec.name}' must return Signals(...), got {type(sig).__name__}")
    idx = df.index
    sig.entries = _bool(sig.entries, idx)
    sig.exits = _bool(sig.exits, idx)
    if sig.short_entries is not None:
        sig.short_entries = _bool(sig.short_entries, idx)
        sig.short_exits = _bool(sig.short_exits, idx)
    return sig


def indicator_values(name: str, df: pd.DataFrame, params: dict) -> dict:
    if name not in INDICATORS:
        raise KeyError(f"Unknown indicator '{name}'")
    spec = INDICATORS[name]
    p = spec.resolve(params)
    out = spec.func(df, **p)
    if isinstance(out, pd.Series):
        out = {name: out}
    return {"name": name, "params": p, "overlay": spec.overlay, "levels": spec.levels,
            "series": {k: to_list(v.reindex(df.index)) for k, v in out.items()}}


# ======================================================================
# Simulation
# ======================================================================
def simulate(df: pd.DataFrame, sig: Signals, s: config.BacktestSettings, market: config.Market) -> dict:
    idx = df.index
    preset = config.COST_PRESETS[s.cost_preset or market.default_costs]
    fees = (s.fees_pct if s.fees_pct is not None else preset.fees_pct) / 100
    fixed = s.fixed_fee if s.fixed_fee is not None else preset.fixed_fee
    slip = (s.slippage_pct if s.slippage_pct is not None else preset.slippage_pct) / 100

    has_short = sig.short_entries is not None
    le, lx = sig.entries.copy(), sig.exits.copy()
    se = sig.short_entries.copy() if has_short else None
    sx = sig.short_exits.copy() if has_short else None

    # --- execution timing
    if s.execution == "next_open":
        sh = lambda x: x.shift(1, fill_value=False).astype(bool)  # noqa: E731
        le, lx = sh(le), sh(lx)
        if has_short:
            se, sx = sh(se), sh(sx)
        price = df.open
    else:
        price = df.close

    # --- intraday square-off (session markets, intraday bars only)
    intraday = parse_interval(df.attrs.get("interval", "1d"))[1] in ("s", "m", "h")
    square = pd.Series(False, index=idx)
    if s.square_off and intraday and market.session_start:
        mins = pd.Series(idx.hour * 60 + idx.minute, index=idx)
        sq_t, ne_t = _hm(s.square_off_time), _hm(s.no_entry_after)
        after = mins >= sq_t
        day = idx.normalize()
        first_after = after & ~(after.groupby(day).shift(1, fill_value=False).astype(bool))
        square = first_after | last_bar_of_day(df)
        block = (mins > ne_t) | square
        le &= ~block
        lx |= square
        if has_short:
            se &= ~block
            sx |= square
        if s.execution == "next_open":
            # a square-off on the day's last bar fills at that bar's close
            price = price.where(~(last_bar_of_day(df) & square & ~first_after), df.close)

    sl = s.sl_pct if s.sl_pct is not None else sig.sl
    tp = s.tp_pct if s.tp_pct is not None else sig.tp
    trailing = s.trailing if s.trailing is not None else sig.trailing

    kw = dict(
        close=df.close, entries=le, exits=lx, price=price,
        open=df.open, high=df.high, low=df.low,
        init_cash=s.init_cash, fees=fees, fixed_fees=fixed, slippage=slip,
        freq=interval_timedelta(df.attrs.get("interval", "1d")),
    )
    if s.size_pct < 100:
        # vectorbt: percent sizing can't reverse in one order -> opposite entry closes first
        kw.update(size=s.size_pct / 100, size_type="percent", upon_opposite_entry="close")
    else:
        kw.update(size=np.inf)            # all available equity (supports long<->short reversal)
    if has_short:
        kw.update(short_entries=se, short_exits=sx)
    if sl:
        kw.update(sl_stop=sl / 100, sl_trail=bool(trailing))
    if tp:
        kw.update(tp_stop=tp / 100)

    pf = vbt.Portfolio.from_signals(**kw)
    year_freq = kw["freq"] * bars_per_year(df.attrs.get("interval", "1d"), market)
    trades = _trades(pf, df, lx, sx, square, sl, tp, trailing)
    return {"pf": pf, "trades": trades, "year_freq": year_freq,
            "costs": {"preset": preset.label, "fees_pct": fees * 100, "fixed_fee": fixed,
                      "slippage_pct": slip * 100, "note": preset.note}}


def _trades(pf, df, lx, sx, square, sl, tp, trailing) -> pd.DataFrame:
    rec = pf.trades.values          # structured numpy record array
    cols = ["id", "direction", "status", "entry_idx", "exit_idx", "entry_time", "exit_time",
            "entry_price", "exit_price", "size", "pnl", "return_pct", "fees", "bars",
            "mae_pct", "mfe_pct", "exit_reason"]
    if len(rec) == 0:
        return pd.DataFrame(columns=cols)
    hi, lo = df.high.to_numpy(), df.low.to_numpy()
    lxv, sxv, sqv = lx.to_numpy(), (sx.to_numpy() if sx is not None else None), square.to_numpy()
    rows = []
    for r in rec:
        e, x = int(r["entry_idx"]), int(r["exit_idx"])
        long = int(r["direction"]) == 0
        ep, xp = float(r["entry_price"]), float(r["exit_price"])
        hmax, lmin = hi[e:x + 1].max(), lo[e:x + 1].min()
        if long:
            mfe, mae = hmax / ep - 1, lmin / ep - 1
        else:
            mfe, mae = 1 - lmin / ep, 1 - hmax / ep
        open_ = int(r["status"]) == 0
        ret = float(r["return"])
        if open_:
            reason = "Open"
        elif sqv[x]:
            reason = "Square-off"
        elif (long and lxv[x]) or ((not long) and sxv is not None and sxv[x]):
            reason = "Signal"
        elif sl and ret <= 0:
            reason = "Trailing stop" if trailing else "Stop loss"
        elif trailing and sl:
            reason = "Trailing stop"
        elif tp and ret > 0:
            reason = "Take profit"
        else:
            reason = "Reversal"
        rows.append({
            "id": int(r["id"]), "direction": "Long" if long else "Short", "status": "Open" if open_ else "Closed",
            "entry_idx": e, "exit_idx": x, "entry_time": df.index[e], "exit_time": df.index[x],
            "entry_price": ep, "exit_price": xp, "size": float(r["size"]), "pnl": float(r["pnl"]),
            "return_pct": ret * 100, "fees": float(r["entry_fees"] + r["exit_fees"]), "bars": x - e,
            "mae_pct": mae * 100, "mfe_pct": mfe * 100, "exit_reason": reason})
    return pd.DataFrame(rows, columns=cols)


# ======================================================================
# Metrics
# ======================================================================
def _streaks(wins: np.ndarray) -> tuple[int, int]:
    best = worst = cur_w = cur_l = 0
    for w in wins:
        cur_w, cur_l = (cur_w + 1, 0) if w else (0, cur_l + 1)
        best, worst = max(best, cur_w), max(worst, cur_l)
    return best, worst


def _max_dd_duration(equity: pd.Series) -> pd.Timedelta | None:
    peak = equity.cummax()
    under = equity < peak
    if not under.any():
        return pd.Timedelta(0)
    grp = (~under).cumsum()
    spans = equity.index.to_series()[under].groupby(grp[under]).agg(["first", "last"])
    return (spans["last"] - spans["first"]).max()


def _fmt_td(td) -> str | None:
    if td is None or pd.isna(td):
        return None
    sec = int(pd.Timedelta(td).total_seconds())
    d, sec = divmod(sec, 86400)
    h, sec = divmod(sec, 3600)
    m = sec // 60
    return " ".join(p for p in (f"{d}d" if d else "", f"{h}h" if h else "", f"{m}m" if m else "") if p) or "0m"


def metrics(sim: dict, df: pd.DataFrame, s: config.BacktestSettings) -> list[dict]:
    pf, tr, yf = sim["pf"], sim["trades"], sim["year_freq"]
    eq = pf.value()
    ra = pf.get_returns_acc(year_freq=yf)
    closed = tr[tr.status == "Closed"] if len(tr) else tr
    rets = closed.return_pct.to_numpy() if len(closed) else np.array([])
    pnl = closed.pnl.to_numpy() if len(closed) else np.array([])
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    win_r, loss_r = rets[rets > 0], rets[rets <= 0]
    best_streak, worst_streak = _streaks(pnl > 0)
    bh = (df.close.iloc[-1] / df.close.iloc[0] - 1) * 100 if len(df) else np.nan
    total_ret = (eq.iloc[-1] / s.init_cash - 1) * 100
    gross_profit = wins.sum() if len(wins) else 0.0
    exposure = float((pf.assets() != 0).mean() * 100)
    longs = closed[closed.direction == "Long"] if len(closed) else closed
    shorts = closed[closed.direction == "Short"] if len(closed) else closed
    dur = lambda sub: _fmt_td((sub.exit_time - sub.entry_time).mean()) if len(sub) else None  # noqa: E731

    def g(title, items):
        return {"title": title, "items": [{"key": k, "label": l, "value": v, "fmt": f} for k, l, v, f in items]}

    return [
        g("Performance", [
            ("net_profit", "Net profit", eq.iloc[-1] - s.init_cash, "money"),
            ("total_return", "Total return", total_ret, "pct"),
            ("cagr", "CAGR", ra.annualized() * 100, "pct"),
            ("buy_hold", "Buy & hold return", bh, "pct"),
            ("excess", "Excess vs buy & hold", total_ret - bh, "pct"),
            ("end_value", "Final equity", eq.iloc[-1], "money"),
            ("exposure", "Time in market", exposure, "pct"),
        ]),
        g("Risk", [
            ("max_dd", "Max drawdown", -abs(ra.max_drawdown() * 100), "pct"),
            ("max_dd_dur", "Longest drawdown", _fmt_td(_max_dd_duration(eq)), "text"),
            ("volatility", "Volatility (ann.)", ra.annualized_volatility() * 100, "pct"),
            ("sharpe", "Sharpe ratio", ra.sharpe_ratio(), "ratio"),
            ("sortino", "Sortino ratio", ra.sortino_ratio(), "ratio"),
            ("calmar", "Calmar ratio", ra.calmar_ratio(), "ratio"),
            ("ulcer", "Ulcer index", ra.ulcer_index(), "ratio"),
            ("var95", "VaR 95% (per bar)", ra.value_at_risk() * 100, "pct"),
            ("beta", "Beta vs buy & hold", ra.beta(), "ratio"),
            ("alpha", "Alpha (ann.) vs buy & hold", ra.alpha(), "ratio"),
        ]),
        g("Trades", [
            ("trades", "Total trades", int(len(tr)), "int"),
            ("win_rate", "Win rate", (len(wins) / len(pnl) * 100) if len(pnl) else np.nan, "pct"),
            ("profit_factor", "Profit factor", (gross_profit / abs(losses.sum())) if len(losses) and losses.sum() != 0 else np.nan, "ratio"),
            ("expectancy", "Expectancy / trade", pnl.mean() if len(pnl) else np.nan, "money"),
            ("expectancy_pct", "Avg trade return", rets.mean() if len(rets) else np.nan, "pct"),
            ("avg_win", "Avg win", win_r.mean() if len(win_r) else np.nan, "pct"),
            ("avg_loss", "Avg loss", loss_r.mean() if len(loss_r) else np.nan, "pct"),
            ("payoff", "Payoff ratio (win/loss)", (win_r.mean() / abs(loss_r.mean())) if len(win_r) and len(loss_r) and loss_r.mean() != 0 else np.nan, "ratio"),
            ("best", "Best trade", rets.max() if len(rets) else np.nan, "pct"),
            ("worst", "Worst trade", rets.min() if len(rets) else np.nan, "pct"),
            ("streak_w", "Max consecutive wins", best_streak, "int"),
            ("streak_l", "Max consecutive losses", worst_streak, "int"),
            ("dur_win", "Avg hold (winners)", dur(closed[closed.pnl > 0]) if len(closed) else None, "text"),
            ("dur_loss", "Avg hold (losers)", dur(closed[closed.pnl <= 0]) if len(closed) else None, "text"),
        ]),
        g("Sides & costs", [
            ("long_n", "Long trades", int(len(longs)), "int"),
            ("long_wr", "Long win rate", (longs.pnl > 0).mean() * 100 if len(longs) else np.nan, "pct"),
            ("short_n", "Short trades", int(len(shorts)), "int"),
            ("short_wr", "Short win rate", (shorts.pnl > 0).mean() * 100 if len(shorts) else np.nan, "pct"),
            ("fees", "Total fees", float(tr.fees.sum()) if len(tr) else 0.0, "money"),
            ("fees_share", "Fees / gross profit", (tr.fees.sum() / gross_profit * 100) if gross_profit > 0 else np.nan, "pct"),
        ]),
    ]


def series(sim: dict, df: pd.DataFrame, s: config.BacktestSettings) -> dict:
    pf = sim["pf"]
    eq = pf.value()
    return {"equity": to_list(eq, 2),
            "benchmark": to_list(df.close / df.close.iloc[0] * s.init_cash, 2),
            "drawdown": to_list(pf.drawdown() * 100, 3)}


def trades_json(tr: pd.DataFrame) -> list[dict]:
    if not len(tr):
        return []
    out = tr.copy()
    out["entry_time"] = out.entry_time.astype(str)
    out["exit_time"] = out.exit_time.astype(str)
    out["entry_t"] = epoch_seconds(pd.DatetimeIndex(tr.entry_time))
    out["exit_t"] = epoch_seconds(pd.DatetimeIndex(tr.exit_time))
    return out.round(6).to_dict(orient="records")


def candles_json(df: pd.DataFrame) -> dict:
    return {"t": epoch_seconds(df.index), "o": to_list(df.open), "h": to_list(df.high),
            "l": to_list(df.low), "c": to_list(df.close), "v": to_list(df.volume, 2)}


def chart_payload(sig: Signals, df: pd.DataFrame) -> dict:
    """Strategy plots + raw signal bars, aligned 1:1 with candles."""
    idx = df.index
    lv = dict(sig.levels)
    return {
        "overlays": {k: to_list(pd.Series(v).reindex(idx)) for k, v in sig.overlays.items()},
        "panes": {p: {k: to_list(pd.Series(v).reindex(idx)) for k, v in d.items()} for p, d in sig.panes.items()},
        "levels": lv,
        "signals": {
            "long_entry": np.flatnonzero(sig.entries.to_numpy()).tolist(),
            "long_exit": np.flatnonzero(sig.exits.to_numpy()).tolist(),
            "short_entry": np.flatnonzero(sig.short_entries.to_numpy()).tolist() if sig.short_entries is not None else [],
            "short_exit": np.flatnonzero(sig.short_exits.to_numpy()).tolist() if sig.short_exits is not None else [],
        },
    }


def settings_dict(s: config.BacktestSettings) -> dict:
    return asdict(s)
