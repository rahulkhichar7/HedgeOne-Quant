"""
The strategy / indicator toolkit.

Write a strategy (any .py file inside backend/strategies/):

    from app.engine import strategy, Param, Signals, ta, crossover, crossunder

    @strategy("EMA Crossover", category="Trend",
              fast=Param(9, 2, 200, help="fast EMA length"),
              slow=Param(21, 5, 400))
    def ema_cross(df, fast, slow):
        f, s = ta.ema(df.close, fast), ta.ema(df.close, slow)
        return Signals(entries=crossover(f, s), exits=crossunder(f, s),
                       overlays={"EMA fast": f, "EMA slow": s})

`df` is a pandas DataFrame (open, high, low, close, volume; DatetimeIndex in IST).
Signals are evaluated on the bar close and, by default, filled on the next bar's open.
"""
from __future__ import annotations

import inspect
import textwrap
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd


# ======================================================================
# Parameters
# ======================================================================
@dataclass
class Param:
    """A tunable input. The UI builds its form from these."""
    default: Any
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: list | None = None          # dropdown
    help: str = ""

    def to_dict(self, name: str) -> dict:
        d = self.default
        kind = ("select" if self.options else "bool" if isinstance(d, bool)
                else "int" if isinstance(d, int) else "float" if isinstance(d, float) else "str")
        step = self.step if self.step is not None else (1 if kind == "int" else 0.1 if kind == "float" else None)
        return {"name": name, "type": kind, "default": d, "min": self.min, "max": self.max,
                "step": step, "options": self.options, "help": self.help}

    def cast(self, v):
        if v is None or v == "":
            return self.default
        d = self.default
        if isinstance(d, bool):
            return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")
        if isinstance(d, int):
            return int(float(v))
        if isinstance(d, float):
            return float(v)
        return v


def _as_param(v) -> Param:
    return v if isinstance(v, Param) else Param(v)


# ======================================================================
# Strategy output
# ======================================================================
@dataclass
class Signals:
    """What a strategy returns.

    entries / exits             : long entry & exit (boolean Series aligned with df)
    short_entries / short_exits : optional short side
    overlays : {name: Series}                  drawn on the price chart
    panes    : {pane: {name: Series}}          drawn in separate panes below (e.g. RSI)
    sl / tp  : stop-loss / take-profit in PERCENT of entry price (e.g. 1.5 = 1.5 %)
    trailing : make `sl` a trailing stop
    levels   : {pane: [values]}                horizontal guide lines in panes (e.g. 30/70)
    """
    entries: pd.Series
    exits: pd.Series | None = None
    short_entries: pd.Series | None = None
    short_exits: pd.Series | None = None
    overlays: dict[str, pd.Series] = field(default_factory=dict)
    panes: dict[str, dict[str, pd.Series]] = field(default_factory=dict)
    sl: float | None = None
    tp: float | None = None
    trailing: bool = False
    levels: dict[str, list[float]] = field(default_factory=dict)


# ======================================================================
# Registries
# ======================================================================
@dataclass
class Spec:
    name: str
    func: Callable
    params: dict[str, Param]
    category: str
    description: str
    kind: str                      # "strategy" | "indicator"
    overlay: bool = True           # indicators only: draw on price or own pane
    levels: list[float] = field(default_factory=list)
    timeframes: Any = None         # strategies only: which chart intervals it may run on (see strategy())

    def resolve(self, given: dict | None) -> dict:
        given = given or {}
        return {k: p.cast(given.get(k)) for k, p in self.params.items()}

    def source(self) -> str:
        try:
            return textwrap.dedent(inspect.getsource(self.func))
        except (OSError, TypeError):
            return ""

    def to_dict(self, with_source=False) -> dict:
        d = {"name": self.name, "category": self.category, "description": self.description,
             "params": [p.to_dict(k) for k, p in self.params.items()],
             "module": getattr(self.func, "__module__", ""), "overlay": self.overlay, "levels": self.levels}
        if with_source:
            d["source"] = self.source()
        return d


STRATEGIES: dict[str, Spec] = {}
INDICATORS: dict[str, Spec] = {}


def _doc(func) -> str:
    return inspect.cleandoc(func.__doc__ or "").split("\n\n")[0]


def strategy(name: str, category: str = "Custom", description: str = "", timeframes=None, **params):
    """Register a strategy. Keyword args become UI parameters (plain values or Param).

    timeframes — which chart intervals (candle sizes) the strategy may run on; the optimizer
    can then test the interval like a parameter:
        None (default)   work it out automatically: any interval, narrowed by what the strategy uses
                         (htf(df, "1d", …) → only intervals below 1d; between_time / first_bar_of_day /
                         last_bar_of_day → intraday only; load(other, "1h") → 1h or finer)
        "any"            every interval
        "intraday"       intervals below 1 day
        "fixed"          never optimize the interval (only the chart's interval is used)
        ("5m", "1h")     a range, both ends included
        ["5m", "15m"]    exactly these
    """
    def deco(func):
        STRATEGIES[name] = Spec(name, func, {k: _as_param(v) for k, v in params.items()},
                                category, description or _doc(func), "strategy", timeframes=timeframes)
        return func
    return deco


# ---------------------------------------------------------------- timeframe usage recorder
# While a strategy runs inside `record_usage()`, the helpers below note what it relies on, so the
# optimizer knows which base intervals make sense (e.g. a daily filter needs candles below 1 day).
_USAGE: list | None = None


class record_usage:
    def __enter__(self):
        global _USAGE
        self.prev, _USAGE = _USAGE, []
        return _USAGE

    def __exit__(self, *exc):
        global _USAGE
        _USAGE = self.prev
        return False


def _note(kind: str, value=None):
    if _USAGE is not None:
        _USAGE.append((kind, value))


def indicator(name: str, category: str = "Other", overlay: bool = True, levels: list | None = None,
              description: str = "", **params):
    """Register an indicator for the chart. The function receives (df, **params) and
    returns a Series or a dict of Series."""
    def deco(func):
        INDICATORS[name] = Spec(name, func, {k: _as_param(v) for k, v in params.items()},
                                category, description or _doc(func), "indicator", overlay, levels or [])
        return func
    return deco


# ======================================================================
# Signal helpers (all return boolean Series, NaN-safe)
# ======================================================================
def _s(x, like: pd.Series) -> pd.Series:
    return x if isinstance(x, pd.Series) else pd.Series(x, index=like.index)


def crossover(a, b) -> pd.Series:
    """True on the bar where `a` crosses above `b` (b may be a number)."""
    a = _s(a, b if isinstance(b, pd.Series) else a)
    b = _s(b, a)
    return ((a > b) & (a.shift(1) <= b.shift(1))).fillna(False).astype(bool)


def crossunder(a, b) -> pd.Series:
    a = _s(a, b if isinstance(b, pd.Series) else a)
    b = _s(b, a)
    return ((a < b) & (a.shift(1) >= b.shift(1))).fillna(False).astype(bool)


def cross(a, b) -> pd.Series:
    return crossover(a, b) | crossunder(a, b)


def rising(s: pd.Series, n: int = 1) -> pd.Series:
    """s has risen for n consecutive bars."""
    return (s.diff() > 0).astype(int).rolling(n).sum().eq(n)


def falling(s: pd.Series, n: int = 1) -> pd.Series:
    return (s.diff() < 0).astype(int).rolling(n).sum().eq(n)


def highest(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).max()


def lowest(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).min()


def bars_since(cond: pd.Series) -> pd.Series:
    """Bars since `cond` was last True (NaN before the first True)."""
    idx = pd.Series(np.where(cond.values, np.arange(len(cond)), np.nan), index=cond.index).ffill()
    return pd.Series(np.arange(len(cond)), index=cond.index) - idx


def state_to_events(entry_state: pd.Series, exit_state: pd.Series | None = None):
    """Turn level conditions (e.g. price > EMA) into first-bar events."""
    en = entry_state.fillna(False).astype(bool)
    en = en & ~en.shift(1, fill_value=False)
    if exit_state is None:
        return en
    ex = exit_state.fillna(False).astype(bool)
    return en, ex & ~ex.shift(1, fill_value=False)


# ---------------------------------------------------------------- time
def between_time(df: pd.DataFrame, start: str, end: str) -> pd.Series:
    """True for bars whose time is within [start, end] e.g. ("09:30", "14:45")."""
    _note("intraday", "between_time")
    t = df.index.hour * 60 + df.index.minute
    h1, m1 = map(int, start.split(":"))
    h2, m2 = map(int, end.split(":"))
    return pd.Series((t >= h1 * 60 + m1) & (t <= h2 * 60 + m2), index=df.index)


def first_bar_of_day(df: pd.DataFrame) -> pd.Series:
    _note("intraday", "first_bar_of_day")
    d = df.index.normalize()
    return pd.Series(d != np.roll(d, 1), index=df.index) | (pd.Series(np.arange(len(df)) == 0, index=df.index))


def last_bar_of_day(df: pd.DataFrame) -> pd.Series:
    """True for the last bar of each session — decided by the CLOCK (bar end >= session close,
    or crossing midnight for 24h markets), so it never needs to peek at the next bar."""
    _note("intraday", "last_bar_of_day")
    from .. import config
    from ..data.sources import interval_seconds
    iv = df.attrs.get("interval")
    market = config.MARKETS.get(df.attrs.get("market", ""), None)
    if not iv or market is None:                     # no metadata: fall back to calendar change
        d = df.index.normalize()
        out = d != np.roll(d, -1)
        if len(out):
            out[-1] = True
        return pd.Series(out, index=df.index)
    bar = pd.Timedelta(seconds=interval_seconds(iv))
    day = df.index.normalize()
    if market.session_end:
        h, m = map(int, market.session_end.split(":"))
        close = day + pd.Timedelta(hours=h, minutes=m)
    else:
        close = day + pd.Timedelta(days=1)
    return pd.Series(df.index + bar >= close, index=df.index)


# ---------------------------------------------------------------- multi-timeframe
def htf(df: pd.DataFrame, interval: str, func: Callable[[pd.DataFrame], pd.Series]) -> pd.Series:
    """Compute `func` on a higher timeframe and map it back without look-ahead.

        daily_ema = htf(df, "1d", lambda d: ta.ema(d.close, 20))

    Each lower-timeframe bar only sees the *previous completed* higher-timeframe value.
    """
    from ..data.store import resample
    from .. import config
    _note("htf", interval)
    market = config.MARKETS.get(df.attrs.get("market", "NSE"), config.MARKETS["NSE"])
    big = resample(df, interval, market)
    val = func(big).shift(1)
    return val.reindex(df.index.union(val.index)).ffill().reindex(df.index)


def load(symbol: str, interval: str | None = None, start=None, end=None) -> pd.DataFrame:
    """Load another symbol from the local store (e.g. NIFTY as a market filter)."""
    from ..data import store
    _note("load", interval or "1d")
    return store.load(symbol, interval or "1d", start, end)
