"""Momentum strategies."""
from app.engine import Param, Signals, crossover, crossunder, strategy, ta


@strategy("RSI Momentum (50 cross)", "Momentum", length=Param(14, 2, 50), level=Param(50, 30, 70), allow_short=Param(False))
def rsi_momentum(df, length, level, allow_short):
    """Buy when RSI crosses above 50 (momentum turns positive), exit below 50."""
    r = ta.rsi(df.close, length)
    up, dn = crossover(r, level), crossunder(r, level)
    sig = Signals(entries=up, exits=dn, panes={"RSI": {"RSI": r}}, levels={"RSI": [level]})
    if allow_short:
        sig.short_entries, sig.short_exits = dn, up
    return sig


@strategy("Rate of Change", "Momentum", length=Param(12, 2, 100), threshold=Param(0.0, -10, 10, 0.1))
def roc_momentum(df, length, threshold):
    """Buy when ROC crosses above the threshold, exit when it crosses back below."""
    r = ta.roc(df.close, length)
    return Signals(entries=crossover(r, threshold), exits=crossunder(r, threshold),
                   panes={"ROC": {"ROC": r}}, levels={"ROC": [threshold]})


@strategy("TRIX Signal", "Momentum", length=Param(15, 3, 60), signal=Param(9, 2, 30))
def trix_signal(df, length, signal):
    """TRIX crossing its EMA signal line."""
    t = ta.trix(df.close, length)
    s = ta.ema(t, signal)
    return Signals(entries=crossover(t, s), exits=crossunder(t, s),
                   panes={"TRIX": {"TRIX": t, "Signal": s}}, levels={"TRIX": [0]})


@strategy("Trend Pullback (EMA + RSI)", "Momentum", trend_len=Param(200, 20, 400), rsi_len=Param(14, 2, 50),
          pullback=Param(40, 20, 50), take=Param(70, 55, 90))
def trend_pullback(df, trend_len, rsi_len, pullback, take):
    """In an up-trend (close > EMA), buy when RSI recovers from a pullback; exit at RSI 'take' or trend loss."""
    e = ta.ema(df.close, trend_len)
    r = ta.rsi(df.close, rsi_len)
    entries = crossover(r, pullback) & (df.close > e)
    exits = crossover(r, take) | crossunder(df.close, e)
    return Signals(entries=entries, exits=exits, overlays={f"EMA {trend_len}": e},
                   panes={"RSI": {"RSI": r}}, levels={"RSI": [pullback, take]})


@strategy("MACD Zero-Line Cross", "Momentum", fast=Param(12, 2, 100), slow=Param(26, 3, 200), signal=Param(9, 2, 50))
def macd_zero(df, fast, slow, signal):
    """Buy when the MACD line crosses above zero (fast EMA above slow EMA), exit when it crosses below."""
    m = ta.macd(df.close, fast, slow, signal)
    return Signals(entries=crossover(m["macd"], 0), exits=crossunder(m["macd"], 0),
                   panes={"MACD": {"Hist": m["hist"], "MACD": m["macd"], "Signal": m["signal"]}}, levels={"MACD": [0]})


@strategy("Awesome Oscillator Zero Cross", "Momentum")
def ao_cross(df):
    """Bill Williams' AO crossing the zero line."""
    ao = ta.awesome(df)
    return Signals(entries=crossover(ao, 0), exits=crossunder(ao, 0), panes={"AO": {"AO": ao}}, levels={"AO": [0]})
