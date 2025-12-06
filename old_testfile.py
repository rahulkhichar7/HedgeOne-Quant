import pandas as pd
import numpy as np
import vectorbt as vbt
import asyncio
import json
import plotly.graph_objects as go # <-- NEW IMPORT
from datetime import datetime
from backend.app.services.analysis_service import AnalysisService
from backend.app.schemas.data_models import TimeSliceAnalysisResult
from typing import Dict, Any, Tuple

# --- NEW FUNCTION: Plotting Visualization ---
def plot_analysis_slice(original_prices: pd.Series, plotting_data: Dict[str, Any]):
    """
    Consumes the JSON output from generate_plotting_data and creates a Plotly figure.
    This simulates the rendering job the Next.js frontend will perform.
    """
    
    fig = go.Figure()
    
    # 1. Price Series (Candlestick/Line) for Context
    fig.add_trace(go.Scatter(
        x=original_prices.index, 
        y=original_prices.values, 
        mode='lines', 
        name='Price'
    ))
    
    # 2. Sub-Equity Curve (Rendered in a separate subplot/panel is typical)
    # We will plot the equity curve data on the main chart for simplicity in the test
    equity_data = plotting_data['sub_equity_curve']['data']
    equity_times = [item[0] for item in equity_data]
    equity_values = [item[1] for item in equity_data]

    fig.add_trace(go.Scatter(
        x=equity_times,
        y=equity_values,
        mode='lines',
        name=plotting_data['sub_equity_curve']['name'],
        yaxis='y2', # Use a secondary y-axis for scale separation
        line=dict(color='yellow', width=2)
    ))

    # 3. Trade Signals (Markers)
    entry_signals = [s for s in plotting_data['trade_signals'] if s['signal_type'] == 'ENTRY']
    exit_signals = [s for s in plotting_data['trade_signals'] if s['signal_type'] == 'EXIT']
    
    fig.add_trace(go.Scatter(
        x=[s['time'] for s in entry_signals],
        y=[s['price'] for s in entry_signals],
        mode='markers',
        marker=dict(symbol='triangle-up', size=10, color='green'),
        name='Entries'
    ))
    
    fig.add_trace(go.Scatter(
        x=[s['time'] for s in exit_signals],
        y=[s['price'] for s in exit_signals],
        mode='markers',
        marker=dict(symbol='triangle-down', size=10, color='red'),
        name='Exits'
    ))

    # 4. Layout Configuration
    fig.update_layout(
        title={'text': f"Deep Attribution Plot: {plotting_data['title']} (Return: {plotting_data['metrics']['total_return_pct']:.2f}%)", 'font': {'size': 20}},
        xaxis_title="Time",
        yaxis=dict(title='Price', showgrid=False),
        yaxis2=dict(title='Equity Curve', overlaying='y', side='right', showgrid=True), # Secondary Y-axis
        template="plotly_dark",
        height=600
    )
    fig.show()


# --- NEW STABLE SERIALIZATION HELPER (UNCHANGED) ---
def serialize_portfolio(portfolio: vbt.Portfolio, known_freq: str) -> str:
    """
    Manually serializes the necessary components of the Portfolio object 
    by accessing the raw NumPy structured array, ensuring reliable column names 
    and using the *known frequency* (known_freq) instead of portfolio.freq.
    """
    # 1. Access the raw NumPy structured array (Most stable data structure)
    trade_records = portfolio.trades.records
    
    # 2. Convert the raw structured array into a regular Pandas DataFrame
    trades_df = pd.DataFrame(trade_records) 
    
    time_index = portfolio.close.index
    
    # --- FIX: ROBUST INDEX MAPPING using numpy array indices ---
    
    # Ensure 'entry_idx' and 'exit_idx' are treated as integers for indexing
    if 'entry_idx' not in trades_df.columns or 'exit_idx' not in trades_df.columns:
        raise RuntimeError("VBT records array missing 'entry_idx' or 'exit_idx'. Cannot map trades.")
        
    # Map the integer index columns (stable in the NumPy array) to the datetime index
    trades_df['entry_time'] = time_index[trades_df['entry_idx'].values]
    trades_df['exit_time'] = time_index[trades_df['exit_idx'].values]

    # 3. Final Data Cleanup for serialization
    
    # Check for essential columns 
    if 'return' not in trades_df.columns and 'exit_price' in trades_df.columns:
        trades_df['return'] = trades_df['exit_price'] / trades_df['entry_price'] - 1
        
    if 'pnl' not in trades_df.columns:
        trades_df['pnl'] = (trades_df['exit_price'] - trades_df['entry_price']) * trades_df['size']

    # Convert times to ISO string format for safe JSON transfer
    trades_df['entry_time'] = trades_df['entry_time'].dt.strftime('%Y-%m-%d %H:%M:%S%z').fillna('')
    trades_df['exit_time'] = trades_df['exit_time'].dt.strftime('%Y-%m-%d %H:%M:%S%z').fillna('')
    
    # 4. Serialize the DataFrame using the stable 'split' format
    columns_to_keep = ['entry_time', 'exit_time', 'return', 'pnl', 'entry_price', 'exit_price']
    final_trades_df = trades_df[[c for c in columns_to_keep if c in trades_df.columns]].copy()
    
    trades_json = final_trades_df.to_json(orient='split', date_format='iso')
    
    # 5. Create a composite JSON structure
    composite_data = {
        'trades_records_json': trades_json,
        'freq': known_freq
    }
    
    return json.dumps(composite_data)

# --- 1. SIMULATE REAL-WORLD BACKTEST OUTPUT (MODIFIED TO RETURN PRICES) ---
def create_simulated_portfolio_data(
    ticker_name: str, 
    resolution: str, 
    start_date: str, 
    end_date: str
) -> Tuple[vbt.Portfolio, pd.Series]: # <<< MODIFIED RETURN TYPE
    """
    Simulates the full data loading and backtesting process for the RELIANCE example.
    Returns: (Portfolio, PriceSeries)
    """
    
    # 1. Simulate Data Loading and Resampling 
    start_dt = pd.to_datetime(start_date, format="%d-%m-%Y")
    end_dt = pd.to_datetime(end_date, format="%d-%m-%Y")
    
    # Generate dates/times only during market hours (9:15 AM to 3:30 PM, Mon-Fri)
    dates = pd.date_range(start_dt, end_dt, freq='30T', inclusive='left')
    market_dates = dates[
        (dates.time >= pd.to_datetime('09:15').time()) &
        (dates.time <= pd.to_datetime('15:30').time()) &
        (dates.day_of_week < 5) # Monday=0 to Friday=4
    ]
    
    # Simulate realistic price movements
    prices = pd.Series(
        np.cumsum(np.random.normal(0, 0.5, len(market_dates))) + 2500, 
        index=market_dates
    )

    # 2. Build EMA Indicators (EMA 9 & 26)
    ema_fast = vbt.MA.run(prices, window=9, ewm=True)
    ema_slow = vbt.MA.run(prices, window=26, ewm=True)

    # 3. Define Entry/Exit Signals
    entries = ema_fast.ma_crossed_above(ema_slow)
    exits = ema_fast.ma_crossed_below(ema_slow)

    # 4. Run Backtest
    portfolio = vbt.Portfolio.from_signals(
        close=prices,
        entries=entries,
        exits=exits,
        init_cash=10000,
        fees=0.0005,
        slippage=0.0,
        freq='30min'
    )
    return portfolio, prices # <<< RETURN PRICES

# --- 2. DEFINE TEST CASE FUNCTION (MODIFIED CALL) ---
async def run_analysis_test():
    print("--- Starting Analysis Service Test (RELIANCE EMA 30min) ---")
    
    # 2a. Setup the test environment and input parameters
    TICKER = "RELIANCE INDUSTRIES LTD"
    INTERVAL = '30m' 
    START_DATE = '01-11-2024' 
    END_DATE = '01-11-2025' 
    
    # Unpack the returned Portfolio and Prices
    portfolio, original_prices = create_simulated_portfolio_data(
        TICKER, INTERVAL, START_DATE, END_DATE
    )
    
    # FIX: Use the stable manual serialization helper
    portfolio_composite_json = serialize_portfolio(portfolio, known_freq=INTERVAL)
    
    # We must now extract ONLY the trades_records_json portion to pass to the service
    trades_records_json = json.loads(portfolio_composite_json)['trades_records_json']

    # Print basic check statistics
    print(f"Data Points: {portfolio.close.shape[0]}")
    print(f"Total Return: {portfolio.total_return() * 100:.2f}%")
    print(f"Total Trades: {portfolio.trades.count()}")
    
    analysis_service = AnalysisService()

    # 2b. Run the core time-slice analysis (all parallel tasks)
    print(f"\nRunning deep attribution analysis for interval {INTERVAL}...")
    full_analysis_results = await analysis_service.run_time_slice_analysis(
        trades_records_json=trades_records_json, # Passing the stable trades JSON
        interval=INTERVAL,
        start_date=START_DATE,
        end_date=END_DATE
    )

    # 2c. Output the results
    for unit_name, result_data in full_analysis_results.items():
        print(f"\n===== ANALYSIS BY: {result_data.time_unit} ({unit_name}) =====")
        # Sort by Trades Count for sanity check, then by Total Return
        sorted_results = sorted(result_data.results, key=lambda x: (x['trades_count'], x['total_return_pct']), reverse=True)
        
        # Output Top 3 slices
        for i, slice_data in enumerate(sorted_results[:3]):
            print(f"  {i+1}. Slice '{slice_data['label']}': Return: {slice_data['total_return_pct']:.2f}%, Trades: {slice_data['trades_count']}, Win Rate: {slice_data['win_rate_pct']:.2f}%")

        # 2d. Run Plotting Data Generator for the best slice
        if unit_name == "DAY_OF_WEEK" or unit_name == "WEEK_OF_MONTH":
            max_profit_slice = sorted_results[0]
            
            # The plotting data function also needs the stable trades JSON
            plotting_data = analysis_service.generate_plotting_data(trades_records_json, max_profit_slice['label'])
            
            print(f"\n--- Plotting Data Check for Max Profit Slice: {max_profit_slice['label']} ---")
            print(f"Plotting Data Title: {plotting_data['title']}")
            print(f"Self-Check Return: {plotting_data['metrics']['total_return_pct']:.2f}%")
            print(f"Total Signals (Entries+Exits): {len(plotting_data['trade_signals'])}")
            print("----------------------------------------------------------------")

            # 2e. VISUALIZATION (NEW STEP)
            plot_analysis_slice(original_prices, plotting_data)


# --- Execute the test ---
# This line is required to run the async test function
# asyncio.run(run_analysis_test()) 
print("\nTest function redefined with plotting. Please call 'await run_analysis_test()' to execute and view the chart.")