"""
YOUR strategies go here (or in any new .py file in this folder).

Workflow:
  1. write a function that takes `df` (+ your parameters) and returns Signals(...)
  2. decorate it with @strategy("Name", "Category", param=Param(default, min, max))
  3. save the file, click ⟳ in the UI -> it appears under "Strategies"

Cheat-sheet
  df.open / df.high / df.low / df.close / df.volume      pandas Series, DatetimeIndex (IST)
  ta.ema(s, n)  ta.sma  ta.rsi  ta.macd  ta.bbands  ta.atr  ta.supertrend  ta.vwap ...  (see app/engine/indicators.py)
  crossover(a, b)  crossunder(a, b)  rising(s, n)  highest(s, n)  lowest(s, n)  bars_since(cond)
  between_time(df, "09:30", "14:45")   first_bar_of_day(df)   last_bar_of_day(df)
  htf(df, "1d", lambda d: ta.ema(d.close, 20))     higher-timeframe value, no look-ahead
  load("NIFTY 50", "1d")                           another symbol from your local store

Signals(entries, exits, short_entries=None, short_exits=None,
        overlays={name: series},          # lines on the price chart
        panes={"Pane": {name: series}},   # separate indicator panes
        levels={"Pane": [30, 70]},        # guide lines in panes
        sl=1.5, tp=4.0, trailing=False)   # stops in percent
"""
from app.engine import Param, Signals, crossover, crossunder, htf, indicator, strategy, ta


@strategy("My MA Crossover + Daily Filter", "My Strategies",
          fast=Param(9, 2, 100, help="Fast EMA"),
          slow=Param(21, 3, 300, help="Slow EMA"),
          daily_len=Param(20, 5, 200, help="Only buy when price is above this daily EMA"),
          sl=Param(1.5, 0, 20, 0.1, help="Stop-loss % (0 = off)"))
def my_ma_cross(df, fast, slow, daily_len, sl):
    """Example: EMA crossover traded only in the direction of the daily trend, with a stop-loss."""
    f = ta.ema(df.close, fast)
    s = ta.ema(df.close, slow)
    daily = htf(df, "1d", lambda d: ta.ema(d.close, daily_len))     # yesterday's daily EMA
    entries = crossover(f, s) & (df.close > daily)
    exits = crossunder(f, s)
    return Signals(entries=entries, exits=exits,
                   overlays={f"EMA {fast}": f, f"EMA {slow}": s, f"Daily EMA {daily_len}": daily},
                   sl=sl or None)


# A custom indicator also shows up in the UI's indicator list:
@indicator("My Spread (EMA fast - slow)", "My Indicators", overlay=False, levels=[0],
           fast=Param(9, 2, 100), slow=Param(21, 3, 300))
def my_spread(df, fast, slow):
    return ta.ema(df.close, fast) - ta.ema(df.close, slow)
