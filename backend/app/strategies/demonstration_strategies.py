import pandas as pd
from pydantic import BaseModel, Field
from typing import Tuple, List
import vectorbt as vbt
from base import BaseStrategy

# --- 1. Trend Strategy: EMA Crossover (Flexible) ---
class EMACrossParams(BaseModel):
    # Removed ge/le restrictions for user flexibility
    fast_window: int = Field(9, description="Fast EMA lookback window (e.g., 9)")
    slow_window: int = Field(26, description="Slow EMA lookback window (e.g., 26)")

class EMACrossover(BaseStrategy):
    strategy_id = 'EMA_CROSS'
    name = 'EMA Crossover'
    params_model = EMACrossParams

    def generate_signals(self, df: pd.DataFrame, params: EMACrossParams) -> Tuple[pd.Series, pd.Series, List[pd.Series]]:
        prices = df['close']
        
        # NOTE: VectorBT handles parameter validation/NaNs internally, allowing for wide ranges.
        ema_f = vbt.MA.run(prices, window=params.fast_window, ewm=True).ma.rename('EMA F')
        ema_s = vbt.MA.run(prices, window=params.slow_window, ewm=True).ma.rename('EMA S')
        
        entries, exits = self.get_crossover_signals(ema_f, ema_s)
        
        return entries, exits, [ema_f, ema_s]

# --- 2. Momentum Strategy: RSI Overbought/Oversold (Flexible) ---
class RSIClassicParams(BaseModel):
    # Removed ge/le restrictions for user flexibility
    window: int = Field(14, description="RSI period (e.g., 14)")
    oversold: int = Field(30, description="Oversold threshold (e.g., 30)")
    overbought: int = Field(70, description="Overbought threshold (e.g., 70)")

class RSIClassic(BaseStrategy):
    strategy_id = 'RSI_CLASSIC'
    name = 'RSI Overbought/Oversold'
    params_model = RSIClassicParams

    def generate_signals(self, df: pd.DataFrame, params: RSIClassicParams) -> Tuple[pd.Series, pd.Series, List[pd.Series]]:
        prices = df['close']
        rsi = vbt.RSI.run(prices, window=params.window).rsi.rename('RSI')
        
        entries = rsi.vbt.crossed_above(params.oversold)
        exits = rsi.vbt.crossed_below(params.overbought)
        
        return entries, exits, [rsi]

# --- 3. Volatility Strategy: Bollinger Bands Breakout (Flexible) ---
class BBandsBreakoutParams(BaseModel):
    # Removed ge/le restrictions for user flexibility
    window: int = Field(20, description="BBands period (e.g., 20)")
    std_dev: float = Field(2.0, description="Standard Deviation multiplier (e.g., 2.0)")

class BBandsBreakout(BaseStrategy):
    strategy_id = 'BBANDS_BREAKOUT'
    name = 'Bollinger Bands Breakout'
    params_model = BBandsBreakoutParams

    def generate_signals(self, df: pd.DataFrame, params: BBandsBreakoutParams) -> Tuple[pd.Series, pd.Series, List[pd.Series]]:
        prices = df['close']
        bb = vbt.BBANDS.run(prices, window=params.window, k=params.std_dev)
        
        # Buy: Price closes above Upper Band
        entries = prices.vbt.crossed_above(bb.upper)
        # Sell: Price closes below Lower Band
        exits = prices.vbt.crossed_below(bb.lower)
        
        return entries, exits, [bb.middle.rename('BB Middle'), bb.upper.rename('BB Upper'), bb.lower.rename('BB Lower')]