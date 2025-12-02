import pandas as pd
import vectorbt as vbt
from typing import Dict, Any, List, Tuple
import asyncio

# --- Project Imports ---
# Access to Pydantic models for I/O validation
from ..schemas.strategy_models import BacktestRequest, BacktestResult, StrategyConfig 
# Access to the data fetching logic
from ..core.data_adapters import DataAdapter 
# Access to the converter utility
from ..utils.df_converter import portfolio_to_result 
# Access to the automatically built strategy registry
from ..strategies import registry 
from ..strategies.base import BaseStrategy

class VectorBTEngine:
    """
    Central service for executing vectorbt strategies and portfolio backtests.
    Handles data fetching, signal generation, and result serialization.
    """
    def __init__(self):
        # Initialize dependencies
        self.data_adapter = DataAdapter()

    async def run_strategy_backtest(self, request: BacktestRequest) -> BacktestResult:
        """
        Executes a single backtest run based on the request parameters.
        """
        # --- 1. Fetch Data (I/O Bound, runs in a separate thread) ---
        # The data adapter returns a Pandas DataFrame indexed by 'date_time'.
        df = await self.data_adapter.fetch_data_to_df(
            request.ticker, 
            request.start_date, 
            request.end_date, 
            request.interval
        )
        
        if df.empty:
            raise ValueError("No historical data available for the specified parameters.")

        # --- 2. Select and Validate Strategy ---
        strategy_id = request.strategy_config.strategy_id
        
        if strategy_id not in registry.STRATEGY_REGISTRY:
            raise ValueError(f"Strategy ID '{strategy_id}' not found in registry.")
            
        StrategyClass: Type[BaseStrategy] = registry.STRATEGY_REGISTRY[strategy_id]
        strategy_instance = StrategyClass()
        
        # Validate and cast parameters using the strategy's specific Pydantic model
        params_model = strategy_instance.params_model(**request.strategy_config.params)
        
        # --- 3. Generate Signals and Indicators (CPU Bound) ---
        # Note: We rely on the BaseStrategy contract to return three items.
        # This execution is generally fast due to VectorBT's Numba acceleration.
        entries, exits, indicator_series = await asyncio.to_thread(
            strategy_instance.generate_signals, 
            df, 
            params_model
        )
        
        # --- 4. Run VectorBT Portfolio ---
        portfolio = await asyncio.to_thread(
            vbt.Portfolio.from_signals,
            df['close'], 
            entries, 
            exits, 
            # Freq is needed for accurate annual metrics (Sharpe ratio, etc.)
            freq=pd.Timedelta(request.interval), # Convert interval string (e.g., '15m') to Timedelta
            init_cash=request.initial_cash, 
            fees=request.fees, 
            slippage=request.slippage,
        )
        
        # --- 5. Convert Results to Pydantic Model ---
        # The converter handles the complex Pandas/VectorBT to JSON transformation.
        result = portfolio_to_result(
            portfolio, 
            df, 
            indicator_series, 
            request.strategy_config.model_dump()
        )
        
        # --- 6. Cache Trade List for Analysis Service ---
        # In a production system, you would save the full trade list DataFrame 
        # (or portfolio object) to Redis/DB here using a unique Backtest ID (Job ID).
        # self.caching_service.save_backtest_result(job_id, portfolio) 
        
        return result