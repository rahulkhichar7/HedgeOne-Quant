import vectorbt as vbt
import pandas as pd


def sma(df: pd.DataFrame, window: int):
    out = vbt.MA.run(df["close"], window=window).ma
    return {"SMA": out.round(2).tolist()}


def ema(df: pd.DataFrame, window: int):
    out = vbt.MA.run(df["close"], window=window, ewm=True).ma
    return {"EMA": out.round(2).tolist()}


def wma(df: pd.DataFrame, window: int):
    out = vbt.MA.run(df["close"], window=window, wtype="wma").ma
    return {"WMA": out.round(2).tolist()}


def rsi(df: pd.DataFrame, window: int):
    out = vbt.RSI.run(df["close"], window=window).rsi
    return {"RSI": out.round(2).tolist()}


def macd(df: pd.DataFrame, fast: int, slow: int, signal: int):
    macd = vbt.MACD.run(df["close"], fast_window=fast, slow_window=slow, signal_window=signal)
    return {
        "MACD": macd.macd.round(2).tolist(),
        "Signal": macd.signal.round(2).tolist(),
        "Histogram": macd.hist.round(2).tolist()
    }


def bbands(df: pd.DataFrame, window: int, std: float):
    bb = vbt.BBANDS.run(df["close"], window=window, std=std)
    return {
        "Upper": bb.upper.round(2).tolist(),
        "Middle": bb.middle.round(2).tolist(),
        "Lower": bb.lower.round(2).tolist()
    }


def atr(df: pd.DataFrame, window: int):
    out = vbt.ATR.run(df["high"], df["low"], df["close"], window=window).atr
    return {"ATR": out.round(2).tolist()}


def stoch(df: pd.DataFrame, k: int, d: int):
    st = vbt.STOCH.run(df["high"], df["low"], df["close"], k_window=k, d_window=d)
    return {
        "%K": st.percent_k.round(2).tolist(),
        "%D": st.percent_d.round(2).tolist()
    }


def cci(df: pd.DataFrame, window: int):
    out = vbt.CCI.run(df["high"], df["low"], df["close"], window=window).cci
    return {"CCI": out.round(2).tolist()}


def willr(df: pd.DataFrame, window: int):
    out = vbt.WILLR.run(df["high"], df["low"], df["close"], window=window).willr
    return {"WILLR": out.round(2).tolist()}


def roc(df: pd.DataFrame, window: int):
    out = vbt.ROC.run(df["close"], window=window).roc
    return {"ROC": out.round(2).tolist()}


def momentum(df: pd.DataFrame, window: int):
    out = vbt.MOM.run(df["close"], window=window).mom
    return {"Momentum": out.round(2).tolist()}


def obv(df: pd.DataFrame):
    out = vbt.OBV.run(df["close"], df["volume"]).obv
    return {"OBV": out.round(2).tolist()}


def mfi(df: pd.DataFrame, window: int):
    out = vbt.MFI.run(
        df["high"], df["low"], df["close"], df["volume"], window=window
    ).mfi
    return {"MFI": out.round(2).tolist()}


def adx(df: pd.DataFrame, window: int):
    out = vbt.ADX.run(df["high"], df["low"], df["close"], window=window).adx
    return {"ADX": out.round(2).tolist()}


def psar(df: pd.DataFrame):
    out = vbt.PSAR.run(df["high"], df["low"]).psar
    return {"PSAR": out.round(2).tolist()}


def ichimoku(df: pd.DataFrame):
    ic = vbt.ICHIMOKU.run(df["high"], df["low"])
    return {
        "Tenkan": ic.tenkan.round(2).tolist(),
        "Kijun": ic.kijun.round(2).tolist(),
        "SpanA": ic.span_a.round(2).tolist(),
        "SpanB": ic.span_b.round(2).tolist()
    }


def uo(df: pd.DataFrame):
    out = vbt.UO.run(df["high"], df["low"], df["close"]).uo
    return {"UO": out.round(2).tolist()}


def cmf(df: pd.DataFrame, window: int):
    out = vbt.CMF.run(
        df["high"], df["low"], df["close"], df["volume"], window=window
    ).cmf
    return {"CMF": out.round(2).tolist()}


def donchian(df: pd.DataFrame, window: int):
    dc = vbt.DONCHIAN.run(df["high"], df["low"], window=window)
    return {
        "Upper": dc.upper.round(2).tolist(),
        "Lower": dc.lower.round(2).tolist(),
        "Middle": dc.middle.round(2).tolist()
    }
