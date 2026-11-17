"""Mean-reversion strategies (buy weakness, sell strength)."""
from app.engine import Param, Signals, crossover, crossunder, strategy, ta


@strategy("RSI Mean Reversion", "Mean Reversion",
          length=Param(14, 2, 50), oversold=Param(30, 5, 50), exit_level=Param(60, 40, 95),
          trend_filter=Param(0, 0, 400, help="Only buy above this SMA (0 = off)"))
def rsi_reversion(df, length, oversold, exit_level, trend_filter):
    """Buy when RSI climbs back above the oversold level; exit when RSI reaches the exit level."""
    r = ta.rsi(df.close, length)
    entries = crossover(r, oversold)
    over = {}
    if trend_filter:
        sma = ta.sma(df.close, trend_filter)
        entries &= df.close > sma
        over[f"SMA {trend_filter}"] = sma
    return Signals(entries=entries, exits=crossover(r, exit_level), overlays=over,
                   panes={"RSI": {"RSI": r}}, levels={"RSI": [oversold, exit_level]})


@strategy("Bollinger Mean Reversion", "Mean Reversion", length=Param(20, 5, 100), mult=Param(2.0, 0.5, 4, 0.1))
def bollinger_reversion(df, length, mult):
    """Buy when price closes back inside the lower band; exit at the middle band."""
    bb = ta.bbands(df.close, length, mult)
    return Signals(entries=crossover(df.close, bb["lower"]), exits=crossover(df.close, bb["middle"]),
                   overlays={"BB upper": bb["upper"], "BB mid": bb["middle"], "BB lower": bb["lower"]})


@strategy("Z-Score Reversion", "Mean Reversion", length=Param(20, 5, 200), entry_z=Param(2.0, 0.5, 4, 0.1),
          exit_z=Param(0.0, -2, 2, 0.1), allow_short=Param(False))
def zscore_reversion(df, length, entry_z, exit_z, allow_short):
    """Buy when the z-score recovers from below -entry_z, exit when it reaches exit_z."""
    z = ta.zscore(df.close, length)
    sig = Signals(entries=crossover(z, -entry_z), exits=crossover(z, exit_z),
                  panes={"Z-Score": {"Z": z}}, levels={"Z-Score": [-entry_z, exit_z, entry_z]})
    if allow_short:
        sig.short_entries, sig.short_exits = crossunder(z, entry_z), crossunder(z, -exit_z)
    return sig


@strategy("Stochastic Reversal", "Mean Reversion", k=Param(14, 3, 50), d=Param(3, 1, 20),
          lower=Param(20, 5, 40), upper=Param(80, 60, 95))
def stoch_reversal(df, k, d, lower, upper):
    """%K crosses above %D in the oversold zone; exit on the bearish cross in the overbought zone."""
    st = ta.stoch(df, k, 3, d)
    entries = crossover(st["k"], st["d"]) & (st["k"] < lower)
    exits = crossunder(st["k"], st["d"]) & (st["k"] > upper)
    return Signals(entries=entries, exits=exits, panes={"Stochastic": {"%K": st["k"], "%D": st["d"]}},
                   levels={"Stochastic": [lower, upper]})


@strategy("Williams %R Reversal", "Mean Reversion", length=Param(14, 3, 50))
def willr_reversal(df, length):
    """Buy when %R leaves the oversold zone (-80), exit when it leaves overbought (-20)."""
    w = ta.willr(df, length)
    return Signals(entries=crossover(w, -80), exits=crossunder(w, -20),
                   panes={"Williams %R": {"%R": w}}, levels={"Williams %R": [-80, -20]})


@strategy("CCI Reversal", "Mean Reversion", length=Param(20, 5, 100), level=Param(100, 50, 300))
def cci_reversal(df, length, level):
    """Buy when CCI crosses back above -level, exit when it drops back below +level."""
    c = ta.cci(df, length)
    return Signals(entries=crossover(c, -level), exits=crossunder(c, level),
                   panes={"CCI": {"CCI": c}}, levels={"CCI": [-level, 0, level]})


@strategy("Connors RSI-2", "Mean Reversion", rsi_len=Param(2, 2, 10), buy_below=Param(10, 1, 30),
          trend_len=Param(200, 20, 400), exit_len=Param(5, 2, 50))
def connors_rsi2(df, rsi_len, buy_below, trend_len, exit_len):
    """Larry Connors: in an up-trend (close > SMA200) buy extreme RSI(2) dips, exit above SMA(5)."""
    r = ta.rsi(df.close, rsi_len)
    trend, ex = ta.sma(df.close, trend_len), ta.sma(df.close, exit_len)
    entries = (r < buy_below) & (df.close > trend)
    entries &= ~entries.shift(1, fill_value=False)
    return Signals(entries=entries, exits=crossover(df.close, ex),
                   overlays={f"SMA {trend_len}": trend, f"SMA {exit_len}": ex},
                   panes={"RSI": {f"RSI {rsi_len}": r}}, levels={"RSI": [buy_below]})
