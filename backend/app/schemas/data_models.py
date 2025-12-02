from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Tuple, Dict, Any

# --- OHLCV Data ---
# For raw data transfer (used in /data endpoint)
class OHLCVData(BaseModel):
    date_time: datetime = Field(..., description="The candlestick timestamp.")
    open: float
    high: float
    low: float
    close: float
    volume: int

# --- Plotting/Indicator Data ---
# Structure for a single line on the chart (e.g., EMA 9)
class PlotLine(BaseModel):
    name: str = Field(..., description="Name of the indicator line or equity curve.")
    data: List[Tuple[datetime, float]] # (timestamp, value) pairs

# Structure for Buy/Sell Markers
class SignalMarker(BaseModel):
    time: datetime
    price: float
    signal_type: str = Field(..., description="'ENTRY', 'EXIT', or 'STOP_LOSS'")

# Structure for Metrics
class PerformanceMetrics(BaseModel):
    total_return: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    # Add other key VectorBT stats as you expand

# Structure for Time-Slice Analysis (Timeline-wise result)
class TimeSliceAnalysisResult(BaseModel):
    time_unit: str = Field(..., description="e.g., 'Day of Week', 'Month', 'Interval'")
    results: List[Dict[str, Any]] # e.g., [{"label": "Monday", "total_return": 5.2}, ...]