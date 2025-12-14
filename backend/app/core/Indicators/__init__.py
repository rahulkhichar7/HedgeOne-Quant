from .momentum import ema, rsi

INDICATOR_REGISTRY = {
    "EMA": ema,
    "RSI": rsi
}
