from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from .data_models import PlotLine, SignalMarker, PerformanceMetrics, TimeSliceAnalysisResult # Import required models

# ------------------------------------------------
# A. REQUEST MODELS (Input to Strategies)
# ------------------------------------------------

class StrategyConfig(BaseModel):
    """Defines a single strategy and its parameters."""
    strategy_id: str = Field(..., description="The unique ID of the strategy to run (e.g., 'EMA_CROSS').")
    params: Dict[str, Any] = Field(..., description="Dictionary of parameters for the strategy (e.g., {'fast_window': 9}).")
    # For composite strategies (future use)
    merge_logic: Optional[str] = "AND_OR" 

class BacktestRequest(BaseModel):
    """The full request payload for a new backtest run (used by the engine)."""
    # Data parameters (retrieved from cache/session)
    ticker: str
    interval: str
    start_date: str
    end_date: str
    
    # Financial parameters (passed explicitly by the user, not stored in session data)
    initial_cash: float = Field(10000.0)
    fees: float = Field(0.0005)
    slippage: float = Field(0.0)
    
    # Strategy parameters (retrieved from session)
    strategy_config: StrategyConfig


# ------------------------------------------------
# B. RESPONSE MODELS (Output from /backtest endpoint)
# ------------------------------------------------

class BacktestResult(BaseModel):
    """The complete, structured output returned by the backtesting engine."""
    
    # 1. Performance Metrics
    metrics: PerformanceMetrics
    
    # 2. Plotting Data (Primary Chart)
    # NOTE: The full OHLCV data is returned by the /data endpoint, but we can include 
    # indicator lines and signals here for a full visualization packet.
    indicator_lines: List[PlotLine]    
    signals: List[SignalMarker]         
    equity_curve: PlotLine              # Time series data for equity curve
    
    # 3. Analysis Metadata
    strategy_used: str
    parameters: Dict[str, Any]