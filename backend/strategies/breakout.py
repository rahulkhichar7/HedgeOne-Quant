"""Breakout / volatility strategies."""
from app.engine import Param, Signals, crossover, crossunder, highest, lowest, strategy, ta


@strategy("Donchian Breakout (Turtle)", "Breakout", entry_len=Param(20, 5, 200), exit_len=Param(10, 2, 100),
          allow_short=Param(False))
def donchian_breakout(df, entry_len, exit_len, allow_short):
    """Buy a close above the previous N-bar high; exit below the previous M-bar low."""
    up = highest(df.high, entry_len).shift(1)          # previous bars only -> no look-ahead
    lo = lowest(df.low, exit_len).shift(1)
    sig = Signals(entries=crossover(df.close, up), exits=crossunder(df.close, lo),
                  overlays={f"High {entry_len}": up, f"Low {exit_len}": lo})
    if allow_short:
        dn = lowest(df.low, entry_len).shift(1)
        cover = highest(df.high, exit_len).shift(1)
        sig.short_entries, sig.short_exits = crossunder(df.close, dn), crossover(df.close, cover)
        sig.overlays[f"Low {entry_len}"] = dn
    return sig


@strategy("Bollinger Squeeze Breakout", "Breakout", length=Param(20, 5, 100), mult=Param(2.0, 0.5, 4, 0.1),
          squeeze_len=Param(120, 20, 500, help="Bandwidth must be at its lowest in this many bars"))
def bb_squeeze(df, length, mult, squeeze_len):
    """After a volatility squeeze (narrowest bands in N bars), buy the close above the upper band."""
    bb = ta.bbands(df.close, length, mult)
    width = (bb["upper"] - bb["lower"]) / bb["middle"]
    squeezed = (width <= lowest(width, squeeze_len) * 1.1).rolling(5).max().astype(bool)
    return Signals(entries=crossover(df.close, bb["upper"]) & squeezed, exits=crossunder(df.close, bb["middle"]),
                   overlays={"BB upper": bb["upper"], "BB mid": bb["middle"], "BB lower": bb["lower"]},
                   panes={"Bandwidth": {"Width %": width * 100}})


@strategy("Keltner Channel Breakout", "Breakout", length=Param(20, 5, 100), mult=Param(2.0, 0.5, 5, 0.1), atr_len=Param(10, 2, 50))
def keltner_breakout(df, length, mult, atr_len):
    """Close above the upper Keltner channel; exit back below the middle line."""
    k = ta.keltner(df, length, mult, atr_len)
    return Signals(entries=crossover(df.close, k["upper"]), exits=crossunder(df.close, k["middle"]),
                   overlays={"KC upper": k["upper"], "KC mid": k["middle"], "KC lower": k["lower"]})


@strategy("ATR Volatility Breakout", "Breakout", atr_len=Param(14, 2, 100), k=Param(1.5, 0.5, 5, 0.1),
          chandelier=Param(3.0, 1, 8, 0.5, help="Exit: close below highest-high minus this × ATR"))
def atr_breakout(df, atr_len, k, chandelier):
    """Bar closes more than k×ATR above the previous close; exit with a chandelier trailing stop."""
    a = ta.atr(df, atr_len)
    entries = df.close > df.close.shift(1) + k * a.shift(1)
    entries &= ~entries.shift(1, fill_value=False)
    trail = highest(df.high, 22) - chandelier * a
    return Signals(entries=entries, exits=crossunder(df.close, trail), overlays={"Chandelier": trail})


@strategy("Chandelier Exit Trend", "Breakout", length=Param(22, 5, 100), mult=Param(3.0, 1, 8, 0.5), allow_short=Param(True))
def chandelier_trend(df, length, mult, allow_short):
    """Flip long/short when price crosses the chandelier stop lines."""
    a = ta.atr(df, length)
    long_stop = highest(df.high, length) - mult * a
    short_stop = lowest(df.low, length) + mult * a
    up, dn = crossover(df.close, short_stop.shift(1)), crossunder(df.close, long_stop.shift(1))
    sig = Signals(entries=up, exits=dn, overlays={"Long stop": long_stop, "Short stop": short_stop})
    if allow_short:
        sig.short_entries, sig.short_exits = dn, up
    return sig


@strategy("Breakout with ATR Stops", "Breakout", lookback=Param(55, 5, 300), sl=Param(2.0, 0.2, 20, 0.1, help="Stop-loss %"),
          tp=Param(6.0, 0.5, 50, 0.5, help="Take-profit %"), trailing=Param(False))
def breakout_stops(df, lookback, sl, tp, trailing):
    """N-bar high breakout; exits come only from the stop-loss / take-profit (shows vectorbt stops)."""
    up = highest(df.high, lookback).shift(1)
    never = df.close != df.close     # all False
    return Signals(entries=crossover(df.close, up), exits=never, overlays={f"High {lookback}": up},
                   sl=sl, tp=tp, trailing=trailing)
