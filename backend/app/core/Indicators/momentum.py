import vectorbt as vbt
import pandas as pd


def ema(df: pd.DataFrame, window: int):
    close = df["close"]
    ema = vbt.MA.run(close, window=window, ewm=True).ma

    return {
        "EMA": ema.round(2).tolist()
    }


def rsi(df: pd.DataFrame, window: int):
    close = df["close"]
    rsi = vbt.RSI.run(close, window=window).rsi

    return {
        "RSI": rsi.round(2).tolist()
    }
