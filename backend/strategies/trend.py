"""Trend-following strategies."""
from app.engine import Param, Signals, crossover, crossunder, state_to_events, strategy, ta

SHORT = Param(False, help="Also take the opposite (short) side")


def _both(entries, exits, allow_short, **kw):
    """Long on entries / exit on exits; optionally mirror as shorts."""
    if allow_short:
        return Signals(entries=entries, exits=exits, short_entries=exits, short_exits=entries, **kw)
    return Signals(entries=entries, exits=exits, **kw)


@strategy("EMA Crossover", "Trend",
          fast=Param(9, 2, 200, help="Fast EMA length"), slow=Param(21, 3, 400, help="Slow EMA length"),
          allow_short=SHORT)
def ema_crossover(df, fast, slow, allow_short):
    """Buy when the fast EMA crosses above the slow EMA, exit on the cross back."""
    f, s = ta.ema(df.close, fast), ta.ema(df.close, slow)
    return _both(crossover(f, s), crossunder(f, s), allow_short,
                 overlays={f"EMA {fast}": f, f"EMA {slow}": s})


@strategy("SMA Crossover (Golden Cross)", "Trend",
          fast=Param(50, 2, 300), slow=Param(200, 5, 500), allow_short=SHORT)
def sma_crossover(df, fast, slow, allow_short):
    """Classic golden / death cross of two simple moving averages."""
    f, s = ta.sma(df.close, fast), ta.sma(df.close, slow)
    return _both(crossover(f, s), crossunder(f, s), allow_short, overlays={f"SMA {fast}": f, f"SMA {slow}": s})


@strategy("Triple EMA Alignment", "Trend", fast=Param(8, 2, 100), mid=Param(21, 3, 200), slow=Param(55, 5, 400))
def triple_ema(df, fast, mid, slow):
    """Enter when fast > mid > slow lines up; exit when the fast EMA loses the mid EMA."""
    f, m, s = ta.ema(df.close, fast), ta.ema(df.close, mid), ta.ema(df.close, slow)
    entries = state_to_events((f > m) & (m > s))
    return Signals(entries=entries, exits=crossunder(f, m),
                   overlays={f"EMA {fast}": f, f"EMA {mid}": m, f"EMA {slow}": s})


@strategy("MACD Crossover", "Trend", fast=Param(12, 2, 100), slow=Param(26, 3, 200), signal=Param(9, 2, 50),
          below_zero_only=Param(False, help="Only buy crosses that happen below the zero line"), allow_short=SHORT)
def macd_cross(df, fast, slow, signal, below_zero_only, allow_short):
    """MACD line crossing its signal line."""
    m = ta.macd(df.close, fast, slow, signal)
    up, dn = crossover(m["macd"], m["signal"]), crossunder(m["macd"], m["signal"])
    if below_zero_only:
        up &= m["macd"] < 0
    return _both(up, dn, allow_short, panes={"MACD": {"MACD": m["macd"], "Signal": m["signal"], "Hist": m["hist"]}},
                 levels={"MACD": [0]})


@strategy("SuperTrend", "Trend", atr_length=Param(10, 2, 100), factor=Param(3.0, 0.5, 10, 0.1), allow_short=SHORT)
def supertrend(df, atr_length, factor, allow_short):
    """Follow the SuperTrend direction flips."""
    st = ta.supertrend(df, atr_length, factor)
    d = st["direction"]
    return _both(crossover(d, 0), crossunder(d, 0), allow_short, overlays={"SuperTrend": st["supertrend"]})


@strategy("Parabolic SAR", "Trend", start=Param(0.02, 0.005, 0.2, 0.005), increment=Param(0.02, 0.005, 0.2, 0.005),
          maximum=Param(0.2, 0.05, 1.0, 0.05), allow_short=SHORT)
def psar(df, start, increment, maximum, allow_short):
    """Enter when price flips above the SAR dots, exit when it flips below."""
    sar = ta.psar(df, start, increment, maximum)
    return _both(crossover(df.close, sar), crossunder(df.close, sar), allow_short, overlays={"PSAR": sar})


@strategy("ADX / DMI Trend", "Trend", length=Param(14, 2, 100), adx_min=Param(20, 5, 60, help="Minimum ADX trend strength"),
          allow_short=SHORT)
def adx_trend(df, length, adx_min, allow_short):
    """+DI crossing above -DI while ADX confirms a trend; exit on the opposite DI cross."""
    a = ta.adx(df, length, length)
    strong = a["adx"] > adx_min
    up = crossover(a["plus_di"], a["minus_di"]) & strong
    dn = crossunder(a["plus_di"], a["minus_di"])
    sig = _both(up, dn, allow_short, panes={"ADX": {"ADX": a["adx"], "+DI": a["plus_di"], "-DI": a["minus_di"]}},
                levels={"ADX": [adx_min]})
    if allow_short:
        sig.short_entries = dn & strong
        sig.short_exits = crossover(a["plus_di"], a["minus_di"])
    return sig


@strategy("Ichimoku Cloud Breakout", "Trend", tenkan=Param(9, 2, 50), kijun=Param(26, 5, 100), senkou=Param(52, 10, 200))
def ichimoku_breakout(df, tenkan, kijun, senkou):
    """Close breaks above the cloud with Tenkan > Kijun; exit when close falls below Kijun."""
    ic = ta.ichimoku(df, tenkan, kijun, senkou, kijun)
    top = ic["span_a"].combine(ic["span_b"], max)
    entries = crossover(df.close, top) & (ic["tenkan"] > ic["kijun"])
    return Signals(entries=entries, exits=crossunder(df.close, ic["kijun"]),
                   overlays={"Tenkan": ic["tenkan"], "Kijun": ic["kijun"], "Span A": ic["span_a"], "Span B": ic["span_b"]})


@strategy("Hull MA Turn", "Trend", length=Param(55, 5, 300), allow_short=SHORT)
def hull_turn(df, length, allow_short):
    """Buy when the Hull MA turns up, exit when it turns down."""
    h = ta.hma(df.close, length)
    slope = h.diff()
    return _both(crossover(slope, 0), crossunder(slope, 0), allow_short, overlays={f"HMA {length}": h})


@strategy("Aroon Crossover", "Trend", length=Param(25, 5, 100))
def aroon_cross(df, length):
    """Aroon Up crossing above Aroon Down (new highs dominating new lows)."""
    a = ta.aroon(df, length)
    return Signals(entries=crossover(a["up"], a["down"]), exits=crossunder(a["up"], a["down"]),
                   panes={"Aroon": {"Up": a["up"], "Down": a["down"]}}, levels={"Aroon": [30, 70]})
