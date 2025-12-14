# Indicators/__init__.py
from .momentum import ema_crossover, rsi_strategy

STRATEGY_REGISTRY = {
    "EMA Crossover": ema_crossover,
    "RSI": rsi_strategy
}
