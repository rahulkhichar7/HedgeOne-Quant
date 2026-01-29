import streamlit as st
import pandas as pd
import altair as alt
import requests
import json
from datetime import datetime

# --- CONFIGURATION ---
BASE_URL = "http://localhost:8000/api/v1"  # Adjust to your FastAPI server address
st.set_page_config(page_title="HedgeOne Quant", layout="wide")

# --- UTILS FOR API CALLS ---
def fetch_get(endpoint, params=None):
    try:
        response = requests.get(f"{BASE_URL}{endpoint}", params=params)
        return response.json()
    except Exception as e:
        st.error(f"Error fetching {endpoint}: {e}")
        return None

def fetch_post(endpoint, params=None):
    try:
        response = requests.post(f"{BASE_URL}{endpoint}", params=params)
        return response.json()
    except Exception as e:
        st.error(f"Error posting to {endpoint}: {e}")
        return None

# --- INITIAL LOAD (METADATA) ---
tickers_data = fetch_get("/data/asset/tickers")
tickers = tickers_data.get("tickers", ["TATA CONSULTANCY SERVICES"]) if tickers_data else []

indicator_meta = fetch_get("/data/asset/indicators/metadata") or {}
strategy_meta = fetch_get("/data/asset/strategies/metadata") or {}

# --- SESSION STATE ---
if 'chart_data' not in st.session_state:
    st.session_state.chart_data = None
if 'signals' not in st.session_state:
    st.session_state.signals = None
if 'indicators' not in st.session_state:
    st.session_state.indicators = []

# --- TOP SECTION: DATA CONTROLS [cite: 18-20, 89-90] ---
st.title("HedgeOne Quant - Backend Integrated")

with st.container():
    c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
    with c1:
        selected_ticker = st.selectbox("Ticker", tickers, index=tickers.index("TATA CONSULTANCY SERVICES") if "TATA CONSULTANCY SERVICES" in tickers else 0)
    with c2:
        # Defaults aligned to Docu [cite: 20]
        start_dt = st.text_input("Start (DD/MM/YYYY HH:MM:SS)", "01/12/2024 09:15:00")
        end_dt = st.text_input("End (DD/MM/YYYY HH:MM:SS)", "10/04/2025 15:30:00")
    with c3:
        interval = st.selectbox("Interval", ["5m", "15m", "1h", "1d", "1w", "1mo"], index=1)
    with c4:
        st.write("") # Spacer
        if st.button("Load Data to Cache", type="primary"):
            # Required step before running analysis [cite: 88]
            res = fetch_post("/data/cache/load", params={"ticker_name": selected_ticker})
            if res:
                st.success(res.get("message", "Loaded"))
                # Fetch OHLCV for chart
                ohlcv = fetch_get("/data/data", params={
                    "ticker_name": selected_ticker, "start_date": start_dt, 
                    "end_date": end_dt, "interval": interval
                })
                st.session_state.chart_data = pd.DataFrame(ohlcv.get("data", []))

# --- SIDEBAR: PANELS [cite: 27-37] ---
with st.sidebar:
    st.header("Analysis")
    
    # Indicators Panel
    with st.expander("Indicators"):
        selected_ind = st.selectbox("Select Indicator", list(indicator_meta.keys()))
        if selected_ind:
            st.write(indicator_meta[selected_ind].get("details", ""))
            ind_params = {}
            for inp in indicator_meta[selected_ind].get("inputs", []):
                ind_params[inp['name']] = st.number_input(f"{selected_ind}: {inp['name']}", value=inp['default'])
            
            if st.button("Apply Indicator"):
                res = fetch_get("/data/core/indicators/run", params={
                    "ticker_name": selected_ticker, "start_date": start_dt, "end_date": end_dt,
                    "interval": interval, "indicator_name": selected_ind, "params": json.dumps(ind_params)
                })
                if res: st.session_state.indicators.append(res)

    # Strategies Panel
    with st.expander("Strategies"):
        selected_strat = st.selectbox("Select Strategy", list(strategy_meta.keys()))
        if selected_strat:
            st.write(strategy_meta[selected_strat].get("details", ""))
            strat_params = {}
            for inp in strategy_meta[selected_strat].get("inputs", []):
                strat_params[inp['name']] = st.number_input(f"{selected_strat}: {inp['name']}", value=inp['default'])
            
            if st.button("Run Strategy (Practice)"):
                res = fetch_get("/data/core/strategies/run", params={
                    "ticker_name": selected_ticker, "start_date": start_dt, "end_date": end_dt,
                    "interval": interval, "strategy_name": selected_strat, "params": json.dumps(strat_params)
                })
                if res: st.session_state.signals = res

    if st.button("Run Full Backtest"):
        # Explicit params for backtest [cite: 118-120]
        bt_res = fetch_post("/backtest/backtest", params={
            "ticker_name": selected_ticker, "start_date": start_dt, "end_date": end_dt,
            "interval": interval, "strategy_name": selected_strat, "params": json.dumps(strat_params),
            "initial_cash": 100000.0, "fees": 0.05, "slippage": 0.0
        })
        st.session_state.backtest_results = bt_res

# --- MAIN UI: CHARTS & STATS ---
if st.session_state.chart_data is not None:
    df = st.session_state.chart_data
    df['date_time'] = pd.to_datetime(df['date_time'])
    
    # Altair Candlestick
    base = alt.Chart(df).encode(x='date_time:T')
    
    # Buy/Sell Signals Overlay [cite: 38-42]
    chart = base.mark_rule().encode(
        alt.Y('low:Q', scale=alt.Scale(zero=False)),
        alt.Y2('high:Q'),
        color=alt.condition("datum.open <= datum.close", alt.value("#06982d"), alt.value("#ae1325"))
    )
    
    if st.session_state.signals:
        sig_df = df.copy()
        sig_df['entry'] = st.session_state.signals['entries']
        sig_df['exit'] = st.session_state.signals['exits']
        
        entries = base.transform_filter(alt.datum.entry == True).mark_point(
            shape='triangle-up', size=100, color='green', filled=True
        ).encode(y='low:Q')
        
        exits = base.transform_filter(alt.datum.exit == True).mark_point(
            shape='triangle-down', size=100, color='red', filled=True
        ).encode(y='high:Q')
        
        chart = chart + entries + exits

    st.altair_chart(chart.properties(width=1000, height=400), use_container_width=True)

# --- BACKTEST VISUALIZATION [cite: 50-86] ---
# --- BACKTEST VISUALIZATION ---
if 'backtest_results' in st.session_state:
    st.divider()
    res = st.session_state.backtest_results
    stats = res.get("backtest_result", {})
    
    # Helper function to safely round values
    def fmt(val):
        try:
            return f"{float(val):.2f}"
        except (ValueError, TypeError):
            return "0.00"

    # Metrics Layout
    m1, m2, m3, m4 = st.columns(4)
    
    # Display rounded metrics
    m1.metric("Win Rate", f"{fmt(stats.get('Win Rate [%]', 0))}%")
    m2.metric("Total Return", f"{fmt(stats.get('Total Return [%]', 0))}%")
    m3.metric("Trades", int(stats.get("Total Trades", 0)))
    m4.metric("Max Drawdown", f"{fmt(stats.get('Max Drawdown [%]', 0))}%")

    # Time Slice Analysis [cite: 54-68, 70-76]
    ts_analysis = res.get("time_slice_analysis", {})
    if ts_analysis:
        unit = st.selectbox("Analyze by Time Slice", list(ts_analysis.keys()))
        slice_data = pd.DataFrame.from_dict(ts_analysis[unit], orient='index').reset_index()
        slice_data.columns = ['Label', 'trades_count', 'total_return_pct', 'win_rate_pct']
        
        sort_by = st.radio("Sort By", ["Win Rate", "Trades Executed"], horizontal=True)
        sort_col = "win_rate_pct" if sort_by == "Win Rate" else "trades_count"
        slice_data = slice_data.sort_values(sort_col, ascending=False)
        
        st.altair_chart(alt.Chart(slice_data).mark_bar().encode(
            x=alt.X('Label:N', sort=None),
            y='win_rate_pct:Q',
            tooltip=['trades_count', 'total_return_pct', 'win_rate_pct']
        ).properties(title=f"Win Rate by {unit}"), use_container_width=True)