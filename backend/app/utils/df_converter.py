import pandas as pd
import vectorbt as vbt
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime
import numpy as np

# --- Project Imports (assuming these schemas exist) ---
from ..schemas.data_models import PlotLine, SignalMarker, PerformanceMetrics
from ..schemas.strategy_models import BacktestRequest, BacktestResult

# ====================================================================
# I. PANDAS / SERIES TO PYDANTIC CONVERSION
# ====================================================================

def series_to_plot_line(series: pd.Series, name: str) -> PlotLine:
    """Converts a single Pandas Series (indicator, equity) to a PlotLine model."""
    if series.empty:
        return PlotLine(name=name, data=[])
    
    # Use .tolist() on the index to get Python datetime objects (most stable method)
    times = series.index.tolist()
    values = series.values.tolist()
    
    # Zip times and values into a list of tuples for efficient JSON transfer
    data = list(zip(times, values))
    
    return PlotLine(name=name, data=data)

def signals_to_markers(
    price_series: pd.Series, 
    signal_series: pd.Series, 
    signal_type: str
) -> List[SignalMarker]:
    """Converts a boolean signal Series to a list of SignalMarker models."""
    if signal_series.empty:
        return []

    # Filter price series to only include times where the signal is True
    active_times = signal_series[signal_series].index
    
    markers = []
    for time in active_times:
        try:
            markers.append(SignalMarker(
                time=time,
                price=price_series.loc[time],
                signal_type=signal_type,
                pnl=0.0 # PNL is typically calculated on the trade, not the signal
            ))
        except KeyError:
            # Skip if signal time does not align perfectly with price index
            continue 
            
    return markers

# ====================================================================
# II. VECTORBT PORTFOLIO TO PYDANTIC RESULT
# ====================================================================

def portfolio_to_result(
    portfolio: vbt.Portfolio, 
    df: pd.DataFrame, 
    indicator_series: List[pd.Series], 
    config: Dict[str, Any]
) -> BacktestResult:
    """
    Converts a complete vbt.Portfolio object into the BacktestResult Pydantic model.
    """
    
    # 1. Performance Metrics
    stats = portfolio.stats()
    
    metrics = PerformanceMetrics(
        total_return=stats.get('Total Return [%]', 0.0),
        max_drawdown=stats.get('Max Drawdown [%]', 0.0),
        sharpe_ratio=stats.get('Sharpe Ratio', 0.0),
        win_rate=stats.get('Win Rate [%]', 0.0),
        trades_count=stats.get('Total Trades', 0)
    )

    # 2. Plotting Data
    
    # --- Indicator Lines ---
    # Convert all indicator series provided by the strategy
    indicator_lines = [series_to_plot_line(s, s.name) for s in indicator_series]

    # --- Signals ---
    # We assume portfolio signals are single column series (iloc[:, 0])
    entries = portfolio.entry_signal.iloc[:, 0].copy()
    exits = portfolio.exit_signal.iloc[:, 0].copy()
    
    entry_markers = signals_to_markers(df['close'], entries, 'ENTRY')
    exit_markers = signals_to_markers(df['close'], exits, 'EXIT')
    all_signals = entry_markers + exit_markers
    
    # --- Equity Curve ---
    # Portfolio equity starts at 1.0 (or initial cash). We use the values directly.
    equity_curve = series_to_plot_line(
        portfolio.equity().iloc[:, 0].rename('Equity Curve'), 
        'Equity Curve'
    )
    
    # 3. Final Result Construction
    return BacktestResult(
        metrics=metrics,
        indicator_lines=indicator_lines,
        signals=all_signals,
        equity_curve=equity_curve,
        strategy_used=config.get('strategy_id', 'UNKNOWN'),
        parameters=config.get('params', {})
    )