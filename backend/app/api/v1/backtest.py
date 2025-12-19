from fastapi import APIRouter, Query
from typing import Dict, Any
import vectorbt as vbt
import pandas as pd
import json
import asyncio

from ...core.Strategies import STRATEGY_REGISTRY
from ...services.backtest_services import (
    run_time_slice_analysis,
    format_timedelta
)
from ...services.data_services import _load_and_resample_data

router = APIRouter()


@router.post("/backtest", response_model=Dict[str, Any])
async def run_backtest(
    ticker_name: str = Query("NIFTY 50"),
    start_date: str = Query("01/12/2024 09:15:00"),
    end_date: str = Query("10/04/2025 15:30:00"),
    interval: str = Query("15m"),
    strategy_name: str = Query("EMA Crossover"),
    params: str = Query('{"short_window":5,"long_window":12}'),
    initial_cash: float = Query(100000.0),
    fees: float = Query(0.05),
    slippage: float = Query(0.0),
):
    print("\n========== BACKTEST START ==========")
    print("Ticker:", ticker_name)
    print("Interval:", interval)
    print("Start:", start_date)
    print("End:", end_date)

    fees /= 100
    slippage /= 100
    params = json.loads(params)

    # ---------- DATA ----------
    print("\n[DATA] Loading data...")
    df = await _load_and_resample_data(
        ticker_name, interval, start_date, end_date
    )

    print("[DATA] Loaded")
    print("[DATA] DF shape:", df.shape)
    print("[DATA] DF columns:", df.columns.tolist())
    print("[DATA] Index type:", type(df.index))
    print("[DATA] Index dtype:", df.index.dtype)
    print("[DATA] Index sample:", df.index[:5])
    print("[DATA] Index first:", df.index[0])
    print("[DATA] Index last :", df.index[-1])

    # ---------- STRATEGY ----------
    print("\n[STRATEGY] Running:", strategy_name)
    strategy_fn = STRATEGY_REGISTRY[strategy_name]
    signals = strategy_fn(df, **params)

    print("[STRATEGY] Signals created")
    print("[STRATEGY] Entries count:", sum(signals["entries"]))
    print("[STRATEGY] Exits count  :", sum(signals["exits"]))

    portfolio = await asyncio.to_thread(
        vbt.Portfolio.from_signals,
        close=df["close"],
        entries=signals["entries"],
        exits=signals["exits"],
        init_cash=initial_cash,
        fees=fees,
        slippage=slippage,
        freq=pd.Timedelta(interval)
    )
    print("[PORTFOLIO] Created")

    # ---------- STATS ----------
    print("\n[STATS] Computing stats...")
    stats = portfolio.stats().to_dict()
    print("[STATS] Total Trades:", stats.get("Total Trades"))
    print("[STATS] Win Rate:", stats.get("Win Rate [%]"))
    print("[STATS] Total Fees Paid:", stats.get("Total Fees Paid"))

    calendar_period = (
        pd.to_datetime(end_date, dayfirst=True)
        - pd.to_datetime(start_date, dayfirst=True)
    )
    stats["Calendar Period"] = format_timedelta(calendar_period)

    for k in [
        "Avg Winning Trade Duration",
        "Avg Losing Trade Duration",
        "Max Drawdown Duration",
        "Period"
    ]:
        if k in stats:
            stats[k] = format_timedelta(stats[k])

    # ---------- TRADES ----------
    print("\n[TRADES] Extracting trades...")
    trades_df = pd.DataFrame(portfolio.trades.records)

    print("[TRADES] Trades DF shape:", trades_df.shape)
    print("[TRADES] Trades DF columns:", trades_df.columns.tolist())

    if trades_df.empty:
        print("[TRADES] No trades found")
        return {
            "backtest_result": stats,
            "time_slice_analysis": {}
        }

    # Map entry_idx → real datetime
    print("\n[TRADES] Mapping trade indices to timestamps...")
    price_index = df.index
    print("[TRADES] Price index sample:", price_index[:5])

    trades_df["entry_time"] = price_index.to_series().iloc[
        trades_df["entry_idx"]
    ].values
    trades_df["exit_time"] = price_index.to_series().iloc[
        trades_df["exit_idx"]
    ].values

    print("[TRADES] Raw entry_time sample:",
          trades_df["entry_time"].head(5).tolist())

    trades_df["entry_time"] = pd.to_datetime(trades_df["entry_time"], utc=False)
    trades_df["exit_time"] = pd.to_datetime(trades_df["exit_time"], utc=False)

    print("[TRADES] entry_time dtype:", trades_df["entry_time"].dtype)
    print("[TRADES] Parsed entry_time sample:",
          trades_df["entry_time"].head(5).tolist())

    print("[TRADES] Unique entry hours:",
          trades_df["entry_time"].dt.hour.unique())
    print("[TRADES] Unique entry weekdays:",
          trades_df["entry_time"].dt.day_name().unique())

    trades_df = trades_df.dropna(subset=["entry_time"])
    print("[TRADES] Trades after dropna:", len(trades_df))

    print("\n[TIME SLICE] Starting time-slice analysis...")
    # ---------- TIME SLICE ----------
    time_slice = await run_time_slice_analysis(
        trades_df=trades_df,
        interval=interval,
        start_date=start_date,
        end_date=end_date
    )

    print("[TIME SLICE] Completed")
    print("========== BACKTEST END ==========\n")

    return {
        "backtest_result": stats,
        "time_slice_analysis": time_slice
    }
