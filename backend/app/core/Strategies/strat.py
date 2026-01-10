import vectorbt as vbt
import pandas as pd

def _result(entries, exits, indicators):
    return {
        "entries": entries.fillna(False).tolist(),
        "exits": exits.fillna(False).tolist(),
        "indicators": {k: v.round(2).tolist() for k, v in indicators.items()}
    }

def ema_crossover(df, short_window, long_window):
    close = df["close"]
    fast = vbt.MA.run(close, window=short_window, ewm=True).ma
    slow = vbt.MA.run(close, window=long_window, ewm=True).ma
    return _result(
        (fast >= slow) & (fast.shift() < slow.shift()),
        (fast <= slow) & (fast.shift() > slow.shift()),
        # fast.ma_crossed_above(slow),
        # slow.ma_crossed_below(fast),
        {"ema_fast": fast, "ema_slow": slow}
    )

def sma_crossover(df, short_window, long_window):
    close = df["close"]
    fast = vbt.MA.run(close, window=short_window).ma
    slow = vbt.MA.run(close, window=long_window).ma
    return _result(
        (fast >= slow) & (fast.shift() < slow.shift()),
        (fast <= slow) & (fast.shift() > slow.shift()),
          {"sma_fast": fast, "sma_slow": slow})

def rsi_strategy(df, window, oversold, overbought):
    rsi = vbt.RSI.run(df["close"], window).rsi
    return _result(rsi < oversold, rsi > overbought, {"rsi": rsi})

def macd_strategy(df, fast, slow, signal):
    macd = vbt.MACD.run(df["close"], fast, slow, signal)
    return _result(macd.macd > macd.signal, macd.macd < macd.signal,
                   {"macd": macd.macd, "signal": macd.signal})

def bollinger_strategy(df, window, std):
    bb = vbt.BBANDS.run(df["close"], window, std)
    return _result(df["close"] < bb.lower, df["close"] > bb.upper,
                   {"upper": bb.upper, "lower": bb.lower})

def vwap_strategy(df):
    vwap = vbt.VWAP.run(df["high"], df["low"], df["close"], df["volume"]).vwap
    return _result(df["close"] > vwap, df["close"] < vwap, {"vwap": vwap})

def adx_strategy(df, window, threshold):
    adx = vbt.ADX.run(df["high"], df["low"], df["close"], window).adx
    return _result(adx > threshold, adx < threshold, {"adx": adx})

def stochastic_strategy(df, k_window, d_window):
    stoch = vbt.STOCH.run(df["high"], df["low"], df["close"], k_window, d_window)
    return _result(stoch.percent_k < 20, stoch.percent_k > 80, {"%K": stoch.percent_k})

def cci_strategy(df, window):
    cci = vbt.CCI.run(df["high"], df["low"], df["close"], window).cci
    return _result(cci < -100, cci > 100, {"cci": cci})

def roc_strategy(df, window):
    roc = vbt.ROC.run(df["close"], window).roc
    return _result(roc > 0, roc < 0, {"roc": roc})

def williams_r_strategy(df, window):
    wr = vbt.WILLR.run(df["high"], df["low"], df["close"], window).willr
    return _result(wr < -80, wr > -20, {"willr": wr})

def atr_breakout(df, window):
    atr = vbt.ATR.run(df["high"], df["low"], df["close"], window).atr
    return _result(df["close"] > df["close"].shift() + atr,
                   df["close"] < df["close"].shift() - atr,
                   {"atr": atr})

def donchian_strategy(df, window):
    dc = vbt.DONCHIAN.run(df["high"], df["low"], window)
    return _result(df["close"] > dc.upper, df["close"] < dc.lower,
                   {"upper": dc.upper, "lower": dc.lower})

def momentum_strategy(df, window):
    mom = df["close"].diff(window)
    return _result(mom > 0, mom < 0, {"momentum": mom})

def ema_rsi_strategy(df, ema_window, rsi_window):
    ema = vbt.MA.run(df["close"], ema_window, ewm=True).ma
    rsi = vbt.RSI.run(df["close"], rsi_window).rsi
    return _result((df["close"] > ema) & (rsi < 40),
                   (df["close"] < ema) & (rsi > 60),
                   {"ema": ema, "rsi": rsi})

def mean_reversion_strategy(df, window):
    sma = vbt.MA.run(df["close"], window).ma
    return _result(df["close"] < sma * 0.98,
                   df["close"] > sma * 1.02,
                   {"sma": sma})

def price_channel_strategy(df, window):
    high = df["high"].rolling(window).max()
    low = df["low"].rolling(window).min()
    return _result(df["close"] > high, df["close"] < low,
                   {"high": high, "low": low})

def rsi_divergence_strategy(df, window):
    rsi = vbt.RSI.run(df["close"], window).rsi
    return _result(rsi.diff() > 0, rsi.diff() < 0, {"rsi": rsi})

def ema_pullback_strategy(df, window):
    ema = vbt.MA.run(df["close"], window, ewm=True).ma
    return _result(df["close"] > ema, df["close"] < ema, {"ema": ema})

def supertrend_strategy(df, window, multiplier):
    st = vbt.SUPERTREND.run(df["high"], df["low"], df["close"], window, multiplier)
    return _result(st.trend == 1, st.trend == -1, {"supertrend": st.supertrend})
