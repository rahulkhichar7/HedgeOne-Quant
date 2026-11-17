"""
Technical indicators — formulas follow TradingView's Pine built-ins (ta.*) so values
match what you see there (EMA/RMA seeded with an SMA, Wilder smoothing for RSI/ATR/ADX,
population stdev for Bollinger Bands, ...).

Two layers:
  1. plain functions (sma, ema, rsi, ...)   -> use them inside strategies:  ta.rsi(df.close, 14)
  2. @indicator registrations at the bottom -> what the UI shows in "Indicators"
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Param, indicator

# ======================================================================
# Core smoothing
# ======================================================================


def _seeded_ewm(s: pd.Series, n: int, alpha: float) -> pd.Series:
    """Pine-style recursive average: first value = SMA(n), then alpha*x + (1-alpha)*prev."""
    s = s.astype(float)
    out = pd.Series(np.nan, index=s.index)
    first = s.first_valid_index()
    if first is None:
        return out
    i0 = s.index.get_loc(first)
    vals = s.to_numpy()
    if len(vals) - i0 < n:
        return out
    seed_pos = i0 + n - 1
    tmp = pd.Series(np.nan, index=s.index)
    tmp.iloc[seed_pos] = np.nanmean(vals[i0:seed_pos + 1])
    tmp.iloc[seed_pos + 1:] = vals[seed_pos + 1:]
    return tmp.ewm(alpha=alpha, adjust=False, ignore_na=True).mean().where(tmp.notna().cumsum() > 0)


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return _seeded_ewm(s, n, 2.0 / (n + 1))


def rma(s: pd.Series, n: int) -> pd.Series:
    """Wilder's moving average (a.k.a. SMMA), used by RSI / ATR / ADX."""
    return _seeded_ewm(s, n, 1.0 / n)


def wma(s: pd.Series, n: int) -> pd.Series:
    w = np.arange(1, n + 1, dtype=float)
    return s.rolling(n, min_periods=n).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)


def hma(s: pd.Series, n: int) -> pd.Series:
    return wma(2 * wma(s, max(n // 2, 1)) - wma(s, n), max(int(np.sqrt(n)), 1))


def dema(s: pd.Series, n: int) -> pd.Series:
    e = ema(s, n)
    return 2 * e - ema(e, n)


def tema(s: pd.Series, n: int) -> pd.Series:
    e1 = ema(s, n); e2 = ema(e1, n); e3 = ema(e2, n)
    return 3 * (e1 - e2) + e3


def vwma(close: pd.Series, volume: pd.Series, n: int) -> pd.Series:
    return sma(close * volume, n) / sma(volume, n)


def stdev(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).std(ddof=0)


def zscore(s: pd.Series, n: int) -> pd.Series:
    return (s - sma(s, n)) / stdev(s, n)


def change(s: pd.Series, n: int = 1) -> pd.Series:
    return s.diff(n)


def true_range(df: pd.DataFrame) -> pd.Series:
    pc = df.close.shift(1)
    tr = pd.concat([df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1).max(axis=1)
    tr.iloc[0] = df.high.iloc[0] - df.low.iloc[0]
    return tr


# ======================================================================
# Momentum / oscillators
# ======================================================================
def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    up, dn = rma(d.clip(lower=0), n), rma(-d.clip(upper=0), n)
    r = 100 - 100 / (1 + up / dn)
    return r.where(dn != 0, 100.0).where(up.notna())


def macd(s: pd.Series, fast=12, slow=26, signal=9) -> dict[str, pd.Series]:
    m = ema(s, fast) - ema(s, slow)
    sig = ema(m, signal)
    return {"macd": m, "signal": sig, "hist": m - sig}


def stoch(df: pd.DataFrame, k=14, smooth_k=1, d=3) -> dict[str, pd.Series]:
    ll, hh = df.low.rolling(k).min(), df.high.rolling(k).max()
    raw = 100 * (df.close - ll) / (hh - ll)
    kk = sma(raw, smooth_k) if smooth_k > 1 else raw
    return {"k": kk, "d": sma(kk, d)}


def stoch_rsi(s: pd.Series, rsi_len=14, stoch_len=14, k=3, d=3) -> dict[str, pd.Series]:
    r = rsi(s, rsi_len)
    ll, hh = r.rolling(stoch_len).min(), r.rolling(stoch_len).max()
    kk = sma(100 * (r - ll) / (hh - ll), k)
    return {"k": kk, "d": sma(kk, d)}


def cci(df: pd.DataFrame, n=20) -> pd.Series:
    tp = (df.high + df.low + df.close) / 3
    m = sma(tp, n)
    arr = tp.to_numpy()
    md = np.full(len(arr), np.nan)
    if len(arr) >= n:
        win = np.lib.stride_tricks.sliding_window_view(arr, n)
        md[n - 1:] = np.abs(win - win.mean(axis=1, keepdims=True)).mean(axis=1)
    return (tp - m) / (0.015 * pd.Series(md, index=tp.index))


def willr(df: pd.DataFrame, n=14) -> pd.Series:
    hh, ll = df.high.rolling(n).max(), df.low.rolling(n).min()
    return -100 * (hh - df.close) / (hh - ll)


def roc(s: pd.Series, n=9) -> pd.Series:
    return 100 * (s / s.shift(n) - 1)


def mom(s: pd.Series, n=10) -> pd.Series:
    return s - s.shift(n)


def mfi(df: pd.DataFrame, n=14) -> pd.Series:
    tp = (df.high + df.low + df.close) / 3
    mf = tp * df.volume
    pos = mf.where(tp.diff() > 0, 0.0).rolling(n).sum()
    neg = mf.where(tp.diff() < 0, 0.0).rolling(n).sum()
    return 100 - 100 / (1 + pos / neg)


def trix(s: pd.Series, n=18) -> pd.Series:
    e = ema(ema(ema(np.log(s), n), n), n)
    return 10000 * e.diff()


def awesome(df: pd.DataFrame, fast=5, slow=34) -> pd.Series:
    hl2 = (df.high + df.low) / 2
    return sma(hl2, fast) - sma(hl2, slow)


def ultimate(df: pd.DataFrame, f=7, m=14, s=28) -> pd.Series:
    pc = df.close.shift(1)
    bp = df.close - pd.concat([df.low, pc], axis=1).min(axis=1)
    tr = pd.concat([df.high, pc], axis=1).max(axis=1) - pd.concat([df.low, pc], axis=1).min(axis=1)
    avg = lambda n: bp.rolling(n).sum() / tr.rolling(n).sum()  # noqa: E731
    return 100 * (4 * avg(f) + 2 * avg(m) + avg(s)) / 7


def aroon(df: pd.DataFrame, n=14) -> dict[str, pd.Series]:
    up = df.high.rolling(n + 1).apply(lambda x: x.argmax(), raw=True) / n * 100
    dn = df.low.rolling(n + 1).apply(lambda x: x.argmin(), raw=True) / n * 100
    return {"up": up, "down": dn}


# ======================================================================
# Trend / volatility
# ======================================================================
def atr(df: pd.DataFrame, n=14) -> pd.Series:
    return rma(true_range(df), n)


def adx(df: pd.DataFrame, n=14, smooth=14) -> dict[str, pd.Series]:
    up, dn = df.high.diff(), -df.low.diff()
    plus = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    minus = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    tr = rma(true_range(df), n)
    pdi, mdi = 100 * rma(plus, n) / tr, 100 * rma(minus, n) / tr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi)
    return {"adx": rma(dx, smooth), "plus_di": pdi, "minus_di": mdi}


def bbands(s: pd.Series, n=20, mult=2.0) -> dict[str, pd.Series]:
    m, sd = sma(s, n), stdev(s, n)
    return {"upper": m + mult * sd, "middle": m, "lower": m - mult * sd}


def keltner(df: pd.DataFrame, n=20, mult=2.0, atr_len=10) -> dict[str, pd.Series]:
    m, a = ema(df.close, n), atr(df, atr_len)
    return {"upper": m + mult * a, "middle": m, "lower": m - mult * a}


def donchian(df: pd.DataFrame, n=20) -> dict[str, pd.Series]:
    up, lo = df.high.rolling(n).max(), df.low.rolling(n).min()
    return {"upper": up, "middle": (up + lo) / 2, "lower": lo}


def supertrend(df: pd.DataFrame, n=10, mult=3.0) -> dict[str, pd.Series]:
    """Returns line and direction (+1 up-trend, -1 down-trend)."""
    a = atr(df, n).to_numpy()
    hl2 = ((df.high + df.low) / 2).to_numpy()
    c = df.close.to_numpy()
    upper, lower = hl2 + mult * a, hl2 - mult * a
    st = np.full(len(c), np.nan)
    d = np.ones(len(c))
    for i in range(1, len(c)):
        if np.isnan(a[i - 1]):
            continue
        if not np.isnan(lower[i - 1]):
            lower[i] = lower[i] if (lower[i] > lower[i - 1] or c[i - 1] < lower[i - 1]) else lower[i - 1]
            upper[i] = upper[i] if (upper[i] < upper[i - 1] or c[i - 1] > upper[i - 1]) else upper[i - 1]
        prev_st = st[i - 1]
        if np.isnan(prev_st):
            d[i] = 1
        elif prev_st == upper[i - 1]:
            d[i] = 1 if c[i] > upper[i] else -1
        else:
            d[i] = -1 if c[i] < lower[i] else 1
        st[i] = lower[i] if d[i] == 1 else upper[i]
    return {"supertrend": pd.Series(st, index=df.index), "direction": pd.Series(d, index=df.index)}


def psar(df: pd.DataFrame, start=0.02, inc=0.02, maximum=0.2) -> pd.Series:
    h, l = df.high.to_numpy(), df.low.to_numpy()
    n = len(h)
    out = np.full(n, np.nan)
    if n < 2:
        return pd.Series(out, index=df.index)
    up = h[1] >= h[0]
    sar, ep, af = (l[0], h[0], start) if up else (h[0], l[0], start)
    for i in range(1, n):
        sar = sar + af * (ep - sar)
        if up:
            sar = min(sar, l[i - 1], l[i - 2] if i >= 2 else l[i - 1])
            if l[i] < sar:
                up, sar, ep, af = False, ep, l[i], start
            elif h[i] > ep:
                ep, af = h[i], min(af + inc, maximum)
        else:
            sar = max(sar, h[i - 1], h[i - 2] if i >= 2 else h[i - 1])
            if h[i] > sar:
                up, sar, ep, af = True, ep, h[i], start
            elif l[i] < ep:
                ep, af = l[i], min(af + inc, maximum)
        out[i] = sar
    return pd.Series(out, index=df.index)


def ichimoku(df: pd.DataFrame, tenkan=9, kijun=26, senkou=52, displacement=26) -> dict[str, pd.Series]:
    mid = lambda n: (df.high.rolling(n).max() + df.low.rolling(n).min()) / 2  # noqa: E731
    t, k = mid(tenkan), mid(kijun)
    return {"tenkan": t, "kijun": k,
            "span_a": ((t + k) / 2).shift(displacement - 1),
            "span_b": mid(senkou).shift(displacement - 1)}


def vwap(df: pd.DataFrame) -> pd.Series:
    """Session VWAP, resets every day."""
    tp = (df.high + df.low + df.close) / 3
    day = df.index.normalize()
    pv = (tp * df.volume).groupby(day).cumsum()
    vv = df.volume.groupby(day).cumsum()
    return (pv / vv.replace(0, np.nan))


def obv(df: pd.DataFrame) -> pd.Series:
    return (np.sign(df.close.diff()).fillna(0) * df.volume).cumsum()


def ad_line(df: pd.DataFrame) -> pd.Series:
    rng = (df.high - df.low).replace(0, np.nan)
    return (((df.close - df.low) - (df.high - df.close)) / rng * df.volume).fillna(0).cumsum()


def cmf(df: pd.DataFrame, n=20) -> pd.Series:
    rng = (df.high - df.low).replace(0, np.nan)
    mfv = ((df.close - df.low) - (df.high - df.close)) / rng * df.volume
    return mfv.rolling(n).sum() / df.volume.rolling(n).sum()


def hist_vol(s: pd.Series, n=20, periods_per_year=252) -> pd.Series:
    return np.log(s / s.shift(1)).rolling(n).std() * np.sqrt(periods_per_year) * 100


def pivots_daily(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Classic floor pivots from the previous day's H/L/C."""
    day = df.index.normalize()
    d = df.groupby(day).agg(high=("high", "max"), low=("low", "min"), close=("close", "last")).shift(1)
    p = (d.high + d.low + d.close) / 3
    lv = {"P": p, "R1": 2 * p - d.low, "S1": 2 * p - d.high, "R2": p + (d.high - d.low), "S2": p - (d.high - d.low)}
    return {k: pd.Series(v.reindex(day).to_numpy(), index=df.index) for k, v in lv.items()}


# ======================================================================
# UI registrations  (name, category, overlay?, params)
# ======================================================================
SRC = ["close", "open", "high", "low", "hl2", "hlc3", "ohlc4"]


def src(df: pd.DataFrame, name: str = "close") -> pd.Series:
    if name in df:
        return df[name]
    return {"hl2": (df.high + df.low) / 2, "hlc3": (df.high + df.low + df.close) / 3,
            "ohlc4": (df.open + df.high + df.low + df.close) / 4}[name]


_L = lambda d, lo=1, hi=500: Param(d, lo, hi)          # noqa: E731
_S = Param("close", options=SRC)

# ---- moving averages (overlay)
indicator("SMA", "Moving Averages", length=_L(20), source=_S)(lambda df, length, source: sma(src(df, source), length))
indicator("EMA", "Moving Averages", length=_L(20), source=_S)(lambda df, length, source: ema(src(df, source), length))
indicator("WMA", "Moving Averages", length=_L(20), source=_S)(lambda df, length, source: wma(src(df, source), length))
indicator("HMA (Hull)", "Moving Averages", length=_L(20), source=_S)(lambda df, length, source: hma(src(df, source), length))
indicator("DEMA", "Moving Averages", length=_L(20), source=_S)(lambda df, length, source: dema(src(df, source), length))
indicator("TEMA", "Moving Averages", length=_L(20), source=_S)(lambda df, length, source: tema(src(df, source), length))
indicator("SMMA (RMA)", "Moving Averages", length=_L(20), source=_S)(lambda df, length, source: rma(src(df, source), length))
indicator("VWMA", "Moving Averages", length=_L(20))(lambda df, length: vwma(df.close, df.volume, length))
indicator("VWAP (session)", "Moving Averages")(lambda df: vwap(df))

# ---- bands / channels (overlay)
indicator("Bollinger Bands", "Volatility", length=_L(20), mult=Param(2.0, 0.1, 10, 0.1), source=_S)(
    lambda df, length, mult, source: bbands(src(df, source), length, mult))
indicator("Keltner Channels", "Volatility", length=_L(20), mult=Param(2.0, 0.1, 10, 0.1), atr_length=_L(10))(
    lambda df, length, mult, atr_length: keltner(df, length, mult, atr_length))
indicator("Donchian Channels", "Volatility", length=_L(20))(lambda df, length: donchian(df, length))
indicator("SuperTrend", "Trend", atr_length=_L(10), factor=Param(3.0, 0.1, 20, 0.1))(
    lambda df, atr_length, factor: {"supertrend": supertrend(df, atr_length, factor)["supertrend"]})
indicator("Parabolic SAR", "Trend", start=Param(0.02, 0.001, 1, 0.01), increment=Param(0.02, 0.001, 1, 0.01),
          maximum=Param(0.2, 0.01, 1, 0.01))(lambda df, start, increment, maximum: psar(df, start, increment, maximum))
indicator("Ichimoku Cloud", "Trend", tenkan=_L(9), kijun=_L(26), senkou=_L(52), displacement=_L(26))(
    lambda df, tenkan, kijun, senkou, displacement: ichimoku(df, tenkan, kijun, senkou, displacement))
indicator("Pivot Points (daily)", "Trend")(lambda df: pivots_daily(df))

# ---- oscillators (own pane)
indicator("RSI", "Momentum", overlay=False, levels=[30, 50, 70], length=_L(14), source=_S)(
    lambda df, length, source: rsi(src(df, source), length))
indicator("MACD", "Momentum", overlay=False, levels=[0], fast=_L(12), slow=_L(26), signal=_L(9), source=_S)(
    lambda df, fast, slow, signal, source: macd(src(df, source), fast, slow, signal))
indicator("Stochastic", "Momentum", overlay=False, levels=[20, 80], k=_L(14), smooth_k=_L(1), d=_L(3))(
    lambda df, k, smooth_k, d: stoch(df, k, smooth_k, d))
indicator("Stochastic RSI", "Momentum", overlay=False, levels=[20, 80], rsi_length=_L(14), stoch_length=_L(14),
          k=_L(3), d=_L(3))(lambda df, rsi_length, stoch_length, k, d: stoch_rsi(df.close, rsi_length, stoch_length, k, d))
indicator("CCI", "Momentum", overlay=False, levels=[-100, 0, 100], length=_L(20))(lambda df, length: cci(df, length))
indicator("Williams %R", "Momentum", overlay=False, levels=[-80, -20], length=_L(14))(lambda df, length: willr(df, length))
indicator("Rate of Change", "Momentum", overlay=False, levels=[0], length=_L(9))(lambda df, length: roc(df.close, length))
indicator("Momentum", "Momentum", overlay=False, levels=[0], length=_L(10))(lambda df, length: mom(df.close, length))
indicator("TRIX", "Momentum", overlay=False, levels=[0], length=_L(18))(lambda df, length: trix(df.close, length))
indicator("Awesome Oscillator", "Momentum", overlay=False, levels=[0])(lambda df: awesome(df))
indicator("Ultimate Oscillator", "Momentum", overlay=False, levels=[30, 70], fast=_L(7), middle=_L(14), slow=_L(28))(
    lambda df, fast, middle, slow: ultimate(df, fast, middle, slow))
indicator("Aroon", "Trend", overlay=False, levels=[30, 70], length=_L(14))(lambda df, length: aroon(df, length))
indicator("ADX / DMI", "Trend", overlay=False, levels=[20, 25], length=_L(14), smoothing=_L(14))(
    lambda df, length, smoothing: adx(df, length, smoothing))
indicator("ATR", "Volatility", overlay=False, length=_L(14))(lambda df, length: atr(df, length))
indicator("Historical Volatility", "Volatility", overlay=False, length=_L(20))(lambda df, length: hist_vol(df.close, length))
indicator("Z-Score", "Statistics", overlay=False, levels=[-2, 0, 2], length=_L(20))(lambda df, length: zscore(df.close, length))
indicator("Standard Deviation", "Statistics", overlay=False, length=_L(20))(lambda df, length: stdev(df.close, length))

# ---- volume (own pane)
indicator("Volume", "Volume", overlay=False)(lambda df: df.volume)
indicator("OBV", "Volume", overlay=False)(lambda df: obv(df))
indicator("Accumulation/Distribution", "Volume", overlay=False)(lambda df: ad_line(df))
indicator("Chaikin Money Flow", "Volume", overlay=False, levels=[0], length=_L(20))(lambda df, length: cmf(df, length))
indicator("Money Flow Index", "Volume", overlay=False, levels=[20, 80], length=_L(14))(lambda df, length: mfi(df, length))
