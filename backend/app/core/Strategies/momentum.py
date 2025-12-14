import vectorbt as vbt
import pandas as pd

def ema_crossover(df: pd.DataFrame, short_window: int, long_window: int):
    close = df["close"]
    fast_ema = vbt.MA.run(close, window=short_window, ewm=True).ma
    slow_ema = vbt.MA.run(close, window=long_window, ewm=True).ma

    # Mark only crossover points
    entries = (fast_ema > slow_ema) & (fast_ema.shift(1) <= slow_ema.shift(1))
    exits   = (fast_ema < slow_ema) & (fast_ema.shift(1) >= slow_ema.shift(1))

    return {
        "entries": entries.fillna(False).tolist(),
        "exits": exits.fillna(False).tolist(),
        "indicators": {
            "ema_fast": fast_ema.round(2).tolist(),
            "ema_slow": slow_ema.round(2).tolist()
        }
    }

def rsi_strategy(df: pd.DataFrame, window: int, overbought: int, oversold: int):
    close = df["close"]
    rsi = vbt.RSI.run(close, window=window).rsi

    # Entry when oversold, exit when overbought
    entries = rsi < oversold
    exits   = rsi > overbought

    return {
        "entries": entries.fillna(False).tolist(),
        "exits": exits.fillna(False).tolist(),
        "indicators": {
            "rsi": rsi.round(2).tolist()
        }
    }
