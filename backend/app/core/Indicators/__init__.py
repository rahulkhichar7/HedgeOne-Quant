from .indics import *

INDICATOR_REGISTRY = {
    "Simple Moving Average (SMA)": sma,
    "Exponential Moving Average (EMA)": ema,
    "Weighted Moving Average (WMA)": wma,
    "Relative Strength Index (RSI)": rsi,
    "Moving Average Convergence Divergence (MACD)": macd,
    "Bollinger Bands": bbands,
    "Average True Range (ATR)": atr,
    "Stochastic Oscillator": stoch,
    "Commodity Channel Index (CCI)": cci,
    "Williams %R": willr,
    "Rate of Change (ROC)": roc,
    "Momentum": momentum,
    "On Balance Volume (OBV)": obv,
    "Money Flow Index (MFI)": mfi,
    "Average Directional Index (ADX)": adx,
    "Parabolic SAR": psar,
    "Ichimoku Cloud": ichimoku,
    "Ultimate Oscillator": uo,
    "Chaikin Money Flow (CMF)": cmf,
    "Donchian Channels": donchian
}
