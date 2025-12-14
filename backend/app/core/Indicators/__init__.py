from .momentum import ema, rsi

INDICATOR_REGISTRY = {
    "Exponential Moving Average (EMA)": ema,
    "Relative Strength Index (RSI)": rsi
}
