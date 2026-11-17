"""Intraday strategies (use a minute timeframe; enable 'Square-off' in settings for NSE)."""
import numpy as np
import pandas as pd

from app.engine import Param, Signals, between_time, crossover, crossunder, strategy, ta


@strategy("Opening Range Breakout", "Intraday",
          range_minutes=Param(15, 5, 120, help="Length of the opening range"),
          exit_time=Param("15:10", help="Flat at this time"),
          sl_pct=Param(0.0, 0, 10, 0.1, help="Optional stop-loss % (0 = range low)"),
          allow_short=Param(True))
def orb(df, range_minutes, exit_time, sl_pct, allow_short):
    """Trade the first break of the opening range high (long) or low (short); flat by exit_time."""
    day = df.index.normalize()
    first = df.groupby(day).apply(lambda g: g.index[0]).reindex(day).to_numpy()
    in_range = (df.index - pd.DatetimeIndex(first)) < pd.Timedelta(minutes=range_minutes)
    hi = df.high.where(in_range).groupby(day).transform("max")
    lo = df.low.where(in_range).groupby(day).transform("min")
    after = ~in_range & between_time(df, "00:00", exit_time)
    # only the first breakout of each day
    up = crossover(df.close, hi) & after
    dn = crossunder(df.close, lo) & after
    up &= up.groupby(day).cumsum() == 1
    dn &= dn.groupby(day).cumsum() == 1
    t = df.index.hour * 60 + df.index.minute
    h, m = map(int, exit_time.split(":"))
    flat = pd.Series((t >= h * 60 + m), index=df.index)
    flat &= ~flat.groupby(day).shift(1, fill_value=False).astype(bool)
    exits = crossunder(df.close, lo) | flat
    sig = Signals(entries=up, exits=exits, overlays={"OR high": hi.where(~in_range), "OR low": lo.where(~in_range)},
                  sl=sl_pct or None)
    if allow_short:
        sig.short_entries, sig.short_exits = dn, crossover(df.close, hi) | flat
    return sig


@strategy("VWAP Cross", "Intraday", start=Param("09:30"), stop=Param("14:45"), allow_short=Param(False))
def vwap_cross(df, start, stop, allow_short):
    """Price crossing the session VWAP inside a trading window."""
    v = ta.vwap(df)
    window = between_time(df, start, stop)
    up, dn = crossover(df.close, v), crossunder(df.close, v)
    sig = Signals(entries=up & window, exits=dn, overlays={"VWAP": v})
    if allow_short:
        sig.short_entries, sig.short_exits = dn & window, up
    return sig


@strategy("VWAP + EMA Trend (intraday)", "Intraday", ema_len=Param(20, 5, 100), start=Param("09:30"), stop=Param("14:30"))
def vwap_ema(df, ema_len, start, stop):
    """Long when the fast EMA crosses above VWAP and price is above both; exit on cross back."""
    v, e = ta.vwap(df), ta.ema(df.close, ema_len)
    entries = crossover(e, v) & (df.close > e) & between_time(df, start, stop)
    return Signals(entries=entries, exits=crossunder(e, v), overlays={"VWAP": v, f"EMA {ema_len}": e})


@strategy("Previous Day High/Low Breakout", "Intraday", allow_short=Param(True), exit_time=Param("15:10"))
def pdh_pdl(df, allow_short, exit_time):
    """Break of yesterday's high (long) or low (short), flat by exit_time."""
    day = df.index.normalize()
    daily = df.groupby(day).agg(high=("high", "max"), low=("low", "min")).shift(1)
    pdh = pd.Series(daily.high.reindex(day).to_numpy(), index=df.index)
    pdl = pd.Series(daily.low.reindex(day).to_numpy(), index=df.index)
    t = df.index.hour * 60 + df.index.minute
    h, m = map(int, exit_time.split(":"))
    flat = pd.Series(t >= h * 60 + m, index=df.index)
    flat &= ~flat.groupby(day).shift(1, fill_value=False).astype(bool)
    up = crossover(df.close, pdh) & ~flat
    dn = crossunder(df.close, pdl) & ~flat
    sig = Signals(entries=up, exits=crossunder(df.close, pdh) | flat, overlays={"PDH": pdh, "PDL": pdl})
    if allow_short:
        sig.short_entries, sig.short_exits = dn, crossover(df.close, pdl) | flat
    return sig
