import pandas as pd
import numpy as np
import vectorbt as vbt
from typing import List, Dict, Any, Tuple
import asyncio
import json
from datetime import datetime

# --- Project Imports ---
from ..schemas.data_models import TimeSliceAnalysisResult

# --- Constants for analysis ---
# Define the order and labels for standard groupings
TIME_UNIT_MAP = {
    # Time unit accessors using pandas datetime properties
    "HOUR": {"func": lambda s: s.dt.hour, "name": "Hour of Day (0-23)"},
    "DAY_OF_WEEK": {"func": lambda s: s.dt.day_name(), "name": "Day of Week"},
    "WEEK_OF_MONTH": {"func": lambda s: s.dt.day.apply(lambda day: (day - 1) // 7 + 1).astype(int), "name": "Week of Month"},
    "WEEK_OF_YEAR": {"func": lambda s: s.dt.isocalendar().week.astype(int), "name": "Week of Year"},
    "MONTH": {"func": lambda s: s.dt.month_name(), "name": "Month Name"},
    # "YEAR": {"func": lambda s: s.dt.year, "name": "Year"} # Add if multiple years are relevant
}

class AnalysisService:
    """
    Service for performing deep, custom post-backtest analysis 
    on trade results (timeline attribution analysis).
    """

    def _get_allowed_time_units(self, interval: str, backtest_duration_days: float, backtest_duration_months: float) -> List[str]:
        """Determines which time units are relevant based on the data interval and duration."""
        allowed_units = []
        
        # 1. GRANULARITY CHECK (Based on Interval)
        if interval.endswith('m') or interval.endswith('h'):
            # Intraday
            allowed_units.extend(["HOUR", "DAY_OF_WEEK"])
        elif interval.endswith('d'):
            # Daily
            allowed_units.extend(["DAY_OF_WEEK"])

        # 2. DURATION CHECK (Upper Bounds)
        
        # Week of Month (Requires at least 2 weeks of data)
        if backtest_duration_days >= 14: 
            allowed_units.append("WEEK_OF_MONTH")

        # Week of Year (Requires at least 4 weeks/1 month of data)
        if backtest_duration_days >= 28:
            allowed_units.append("WEEK_OF_YEAR")
            
        # Month Name (Requires more than one month of data)
        if backtest_duration_months > 1.5:
            allowed_units.append("MONTH")

        # Ensure unique list and return in a sensible order
        return [unit for unit in TIME_UNIT_MAP.keys() if unit in allowed_units]

    def _calculate_sub_portfolio_metrics(self, sub_trades_df: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculates key metrics (Sharpe, Returns, Win Rate) for a sub-set of trades 
        using a filtered DataFrame of trade records.
        """
        if sub_trades_df.empty:
            return {
                "trades_count": 0, "total_return_pct": 0.0, "win_rate_pct": 0.0,
                "sharpe_ratio": 0.0, "max_drawdown_pct": 0.0
            }

        total_trades = len(sub_trades_df)
        total_return = sub_trades_df['return'].sum()
        
        # Win Rate: Count of trades where return > 0
        winning_trades = (sub_trades_df['return'] > 0).sum()
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0

        sub_returns = sub_trades_df['return']

        try:
            # Create a simple Series for VBT from_returns calculation (indexed by entry time)
            temp_returns = pd.Series(sub_returns.values, index=sub_trades_df['entry_time'])
            # Since frequency is lost, we assume '1D' for annualized metrics calculation
            temp_portfolio = vbt.Portfolio.from_returns(temp_returns, freq='1D', init_cash=1) 
        except Exception:
            return {
                "trades_count": total_trades, "total_return_pct": round(total_return * 100, 2), "win_rate_pct": round(win_rate, 2),
                "sharpe_ratio": 0.0, "max_drawdown_pct": 0.0
            }

        return {
            "trades_count": total_trades,
            "total_return_pct": round(total_return * 100, 2),
            "win_rate_pct": round(win_rate, 2),
            
            # Use temp portfolio for Annualized Metrics
            "sharpe_ratio": round(temp_portfolio.sharpe_ratio(), 2),
            "max_drawdown_pct": round(temp_portfolio.max_drawdown() * 100, 2),
        }

    def _analyze_trades_by_time_unit(self, trades_df: pd.DataFrame, time_unit: str) -> List[Dict[str, Any]]:
        """
        Groups trades by their entry time and calculates metrics for each group.
        """
        if trades_df.empty:
            return []

        # 1. Extract the grouping key (e.g., Day Name, Month Number) from entry_time
        group_accessor = TIME_UNIT_MAP[time_unit]["func"]
        trades_df['group_key'] = group_accessor(trades_df['entry_time'])

        # 2. Group the DataFrame by the calculated key
        grouped_records = trades_df.groupby('group_key')

        results_list = []
        for group_label, group_data_df in grouped_records:
            
            # 3. Calculate Metrics directly from the filtered DataFrame
            metrics = self._calculate_sub_portfolio_metrics(group_data_df)
            
            results_list.append({
                "label": str(group_label), 
                **metrics
            })
            
        return results_list
        
    async def run_time_slice_analysis(
        self, 
        trades_records_json: str, # NOW ACCEPTS JSON OF TRADES DF
        interval: str, 
        start_date: str, 
        end_date: str,   
    ) -> Dict[str, TimeSliceAnalysisResult]:
        """
        Orchestrates the timeline analysis by running multiple groupings 
        in background threads.
        """
        
        # 1. Deserialize the trade records DataFrame (STABLE)
        trades_records_df = await asyncio.to_thread(pd.read_json, trades_records_json, orient='split')
        trades_records_df['entry_time'] = pd.to_datetime(trades_records_df['entry_time'], utc=True)
        
        # 2. Calculate Duration (Unchanged)
        try:
            start_dt = pd.to_datetime(start_date, format="%d-%m-%Y")
            end_dt = pd.to_datetime(end_date, format="%d-%m-%Y")
            duration = end_dt - start_dt
            backtest_duration_days = duration.days
            backtest_duration_months = backtest_duration_days / 30.44
        except Exception:
            backtest_duration_days = 90
            backtest_duration_months = 3
        
        # 3. Determine allowed units
        allowed_units = self._get_allowed_time_units(
            interval, backtest_duration_days, backtest_duration_months
        )
        
        # 4. Create parallel tasks
        tasks = {}
        for unit in allowed_units:
            # Pass the deserialized DataFrame to the synchronous function
            task = asyncio.to_thread(self._analyze_trades_by_time_unit, trades_records_df, unit)
            tasks[unit] = task

        # 5. Wait for results
        results = await asyncio.gather(*tasks.values())
        
        final_results = {}
        for unit, unit_results in zip(allowed_units, results):
            final_results[unit] = TimeSliceAnalysisResult(
                time_unit=TIME_UNIT_MAP[unit]["name"],
                results=unit_results
            )

        return final_results
        
    def generate_plotting_data(self, trades_records_json: str, unit_label: str) -> Dict[str, Any]:
        """
        Generates a Plotly JSON structure to visualize the trade execution 
        of a specific time slice (e.g., all trades that started on a Tuesday).
        """
        # 1. Deserialize the trade records DataFrame (STABLE)
        trades_records_df = pd.read_json(trades_records_json, orient='split')
        trades_records_df['entry_time'] = pd.to_datetime(trades_records_df['entry_time'], utc=True)
        
        # Determine which accessor to use based on the label type
        def get_matching_accessor(label: str):
            # Check if label is a month name
            if label in trades_records_df['entry_time'].dt.month_name().unique():
                return lambda s: s.dt.month_name()
            # Check if label is a day name
            elif label in trades_records_df['entry_time'].dt.day_name().unique():
                return lambda s: s.dt.day_name()
            # Check if label is numeric (Week of Month/Year)
            elif str(label).isdigit():
                # Default to Week of Month accessor if numeric
                return lambda s: s.dt.day.apply(lambda day: (day - 1) // 7 + 1).astype(str)
            else:
                return None
                
        accessor = get_matching_accessor(unit_label)
        
        if accessor:
            # Filter trades based on the label
            trades_to_plot_df = trades_records_df[accessor(trades_records_df['entry_time']) == unit_label]
        else:
             # Default to an empty set if filtering fails
             trades_to_plot_df = trades_records_df[trades_records_df.index.isin([])]

        
        if trades_to_plot_df.empty:
            return {"error": f"No trades found for entry label: {unit_label}"}

        # We need the full price series for the equity curve calculation, 
        # but we use the filtered DataFrame for plotting markers.
        sub_trades_df = trades_to_plot_df

        # 1. Extract Trade Markers for plotting
        signals = []
        for _, trade in sub_trades_df.iterrows():
            # Entry marker
            signals.append({
                'time': trade['entry_time'].isoformat(),
                'price': trade['entry_price'],
                'signal_type': 'ENTRY',
                'pnl': trade['pnl']
            })
            # Exit marker
            signals.append({
                'time': trade['exit_time'].isoformat(),
                'price': trade['exit_price'],
                'signal_type': 'EXIT',
                'pnl': trade['pnl']
            })
            
        # 2. Extract Sub-Equity Curve
        sub_returns = sub_trades_df['return']
        
        try:
            # Create a simple Series for VBT from_returns calculation (indexed by entry time)
            temp_returns = pd.Series(sub_returns.values, index=sub_trades_df['entry_time'])
            temp_portfolio = vbt.Portfolio.from_returns(temp_returns, freq='1D', init_cash=1) 
            sub_equity_curve_series = temp_portfolio.equity().iloc[:, 0]
        except Exception:
            sub_equity_curve_series = pd.Series([1.0] * len(sub_returns), index=sub_returns.index)

        # Convert Series to Plotly JSON format 
        # FIX: Use .tolist() on the index to get Python datetime objects
        sub_equity_curve_data = list(zip(sub_equity_curve_series.index.tolist(), sub_equity_curve_series.values))


        return {
            "title": f"Sub-Portfolio Trades Started on: {unit_label}",
            "trade_signals": signals,
            "sub_equity_curve": {"name": f"Equity ({unit_label} trades)", "data": sub_equity_curve_data},
            "metrics": self._calculate_sub_portfolio_metrics(sub_trades_df)
        }