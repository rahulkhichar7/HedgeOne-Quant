import pandas as pd
import vectorbt as vbt
from typing import Dict, Any, List, Tuple, Type
import asyncio
from io import StringIO
from fastapi import HTTPException

# --- Project Imports ---
from ..schemas.strategy_models import BacktestRequest, BacktestResult 
from ..schemas.strategy_models import StrategyConfig 
from ..core.data_adapters import DataAdapter 
from ..utils.df_converter import portfolio_to_result 
from ..strategies import registry 
from ..strategies.base import BaseStrategy
from ..core.caching import CachingService 

class VectorBTEngine:
    """
    Central service for executing vectorbt strategies and portfolio backtests.
    Handles data fetching, signal generation, result serialization, and trade caching.
    """
    def __init__(self):
        self.data_adapter = DataAdapter()
        self.caching_service = CachingService()

    async def run_strategy_backtest(self, request: BacktestRequest, session_id: str) -> BacktestResult:
        """
        Executes a single backtest run and caches the trade records (JSON) for analysis.
        """
        
        # 1. --- Fetch Data from Cache (Check CachingService using data_key) ---
        session_data = self.caching_service.get_session(session_id)
        data_key = session_data['data_key']
        
        # Retrieve the OHLCV JSON string and deserialize it (runs in thread)
        df_json_str = self.caching_service.CACHE.get(data_key)
        if not df_json_str:
            raise HTTPException(status_code=404, detail="Data cache expired or missing. Please re-run data selection.")
            
        # Deserialization of the main OHLCV data into a DataFrame
        df = await asyncio.to_thread(pd.read_json, StringIO(df_json_str), orient='split')
        df['date_time'] = pd.to_datetime(df['date_time'])
        df = df.set_index('date_time')
        
        if df.empty:
            raise ValueError("No historical data available for the specified parameters.")

        # 2. --- Select and Run Strategy (CPU Bound) ---
        strategy_id = request.strategy_config.strategy_id
        
        if strategy_id not in registry.STRATEGY_REGISTRY:
            raise ValueError(f"Strategy ID '{strategy_id}' not found in registry.")
            
        StrategyClass: Type[BaseStrategy] = registry.STRATEGY_REGISTRY[strategy_id]
        strategy_instance = StrategyClass()
        
        params_model = strategy_instance.params_model(**request.strategy_config.params)
        
        entries, exits, indicator_series = await asyncio.to_thread(
            strategy_instance.generate_signals, 
            df, 
            params_model
        )
        
        # 3. --- Run VectorBT Portfolio ---
        portfolio = await asyncio.to_thread(
            vbt.Portfolio.from_signals,
            df['close'], 
            entries, 
            exits, 
            freq=pd.Timedelta(request.interval), 
            init_cash=request.initial_cash, 
            fees=request.fees, 
            slippage=request.slippage,
        )
        
        # 4. --- Convert Results for API Response ---
        result = portfolio_to_result(
            portfolio, 
            df, 
            indicator_series, 
            request.strategy_config.model_dump()
        )
        
        # 5. --- CRITICAL: Save Trade Records for AnalysisService ---
        # Get trades df from VBT and serialize to JSON string 
        trades_df = await asyncio.to_thread(lambda: portfolio.trades.records_readable.copy())
        
        # Serialize the JSON string to the cache under the session ID
        trades_records_json = await asyncio.to_thread(trades_df.to_json, orient='split', date_format='iso')
        
        self.caching_service.set_trade_records(session_id, trades_records_json)
        
        return result