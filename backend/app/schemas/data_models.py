from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Dict, Any, Tuple

# ------------------------------------------------
# A. DATA TRANSFER MODELS (Used by /data endpoint)
# ------------------------------------------------

class OHLCVData(BaseModel):
    date_time: datetime = Field(..., description="The candlestick timestamp.")
    open: float
    high: float
    low: float
    close: float
    volume: int = Field(..., description="Volume, stored as integer.")

class DataFetchResponse(BaseModel):
    session_id: str = Field(..., description="Unique ID for the current analysis session.")
    data: List[OHLCVData]

# ------------------------------------------------
# B. PLOTTING MODELS (Used inside BacktestResult)
# ------------------------------------------------

class PlotLine(BaseModel):
    name: str = Field(..., description="Name of the indicator line or equity curve.")
    # (timestamp, value) pairs
    data: List[Tuple[datetime, float]] 

class SignalMarker(BaseModel):
    time: datetime
    price: float
    signal_type: str = Field(..., description="'ENTRY', 'EXIT', or custom marker.") #... shows field is required
    pnl: float = Field(0.0, description="P&L associated with this marker (for tooltips).")

class PerformanceMetrics(BaseModel):
    total_return: float = Field(..., description="Total return percentage.")
    max_drawdown: float = Field(..., description="Maximum drawdown percentage.")
    sharpe_ratio: float = Field(..., description="Annualized Sharpe Ratio.")
    win_rate: float = Field(..., description="Win rate percentage.")
    trades_count: int = Field(..., description="Total number of trades executed.")
    # Add other metrics here as you expand

# ------------------------------------------------
# C. ANALYSIS MODELS (Used by /analysis/time_slice endpoint)
# ------------------------------------------------

class AnalysisMetricResult(BaseModel):
    label: str = Field(..., description="The time slice label (e.g., 'Monday', 'January', '10').")
    trades_count: int
    total_return_pct: float
    win_rate_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float

class TimeSliceAnalysisResult(BaseModel):
    """Container for one type of attribution analysis (e.g., Day of Week)."""
    time_unit: str = Field(..., description="e.g., 'Day of Week', 'Month Name'.")
    results: List[AnalysisMetricResult]