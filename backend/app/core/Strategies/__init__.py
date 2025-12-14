from .strat import *

STRATEGY_REGISTRY = {
    "EMA Crossover": ema_crossover,
    "SMA Crossover": sma_crossover,
    "RSI": rsi_strategy,
    "MACD": macd_strategy,
    "Bollinger Bands": bollinger_strategy,
    "VWAP": vwap_strategy,
    "ADX Trend": adx_strategy,
    "Stochastic Oscillator": stochastic_strategy,
    "CCI": cci_strategy,
    "ROC": roc_strategy,
    "Williams %R": williams_r_strategy,
    "ATR Breakout": atr_breakout,
    "Donchian Channel": donchian_strategy,
    "Momentum": momentum_strategy,
    "EMA + RSI": ema_rsi_strategy,
    "Mean Reversion": mean_reversion_strategy,
    "Price Channel": price_channel_strategy,
    "RSI Divergence": rsi_divergence_strategy,
    "EMA Pullback": ema_pullback_strategy,
    "SuperTrend": supertrend_strategy
}
