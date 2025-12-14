from fastapi import APIRouter, Query
from typing import Any, Dict
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

@router.post("/backtest", response_model=Dict[str,Any])
async def run_backtest_sync(
    ticker_name: str = Query(default="NIFTY 50", description="Trading symbol or index name (e.g. 'NIFTY 50', 'RELIANCE')"),
    start_date: str = Query(default="01/12/2024 09:15:00", description="Start datetime in format DD/MM/YYYY HH:MM:SS"),
    end_date: str = Query(default="10/04/2025 15:30:00", description="End datetime in format DD/MM/YYYY HH:MM:SS"),
    interval: str = Query(default="15m", description="Candle interval (e.g. '5m', '15m', '1h', '1d')"),
    strategy_name: str = Query(default="EMA Crossover", description="Strategy name (e.g. 'EMA Crossover', 'RSI')"),
    params: str = Query({"short_window":5, "long_window":12}, description='Strategy parameters as a JSON string. Example for EMA Crossover: {"short_window": 13, "long_window": 24}'),
    initial_cash: float = Query(100000.0, description="Enter cash amount eg. 100000"),
    fees: float = Query(0.05, description="% commision on each transection eg. 0.05%"),
    slippage: float = Query(0.0, description="slippage % eg. 0.0%"),
):
    fees /= 100
    slippage /= 100

    params = json.loads(params)

    # -------- DATA -------- #
    df = await _load_and_resample_data(
        ticker_name,
        interval,
        start_date,
        end_date
    )
    print("backtest: data loaded")
    print("\n\nDataFrame Head")
    print(df.head())
    print("\n\nDataFrame Tail")
    print(df.tail())
    print("\nDataFrame Shape: ", df.shape)

    # -------- STRATEGY -------- #
    strategy_fn = STRATEGY_REGISTRY[strategy_name]
    print("backtest: strategy loaded")
    result = strategy_fn(df, **params)

    portfolio = await asyncio.to_thread(
        vbt.Portfolio.from_signals,
        df["close"],
        result["entries"],
        result["exits"],
        freq=pd.Timedelta(interval),
        init_cash=initial_cash,
        fees=fees,
        slippage=slippage
    )
    print("backtest: Portfolio Created")

    # -------- BACKTEST METRICS -------- #
    backtest_metrics = portfolio.stats().to_dict()
    calendar_period = (
    pd.to_datetime(end_date, dayfirst=True)
    - pd.to_datetime(start_date, dayfirst=True)
)
    # print("\nCalender Period", calendar_period)

    backtest_metrics["Calendar Period"] = format_timedelta(calendar_period)


    DURATION_KEYS = [
        "Avg Winning Trade Duration",
        "Avg Losing Trade Duration",
        "Max Drawdown Duration",
        "Period"
    ]

    for key in DURATION_KEYS:
        if key in backtest_metrics:
            backtest_metrics[key] = format_timedelta(backtest_metrics[key])

    # print("Backtest Metrics")
    # print(backtest_metrics)

    # print("Portfolio trades:: ", portfolio.trades)
    # # -------- TRADES -------- #
    # trades_df = portfolio.trades.records.copy()
    # trades_df.columns = trades_df.columns.str.lower().str.replace(" ", "_")

    # # keep only closed trades
    # trades_df = trades_df[trades_df["status"] == "Closed"]
    # print("\n\n\nTrade Readables")
    # print(trades_df)

    # # map entry index → datetime
    # if trades_df["entry_time"].isna().any(): # Check the entry_time column provided by records_dt
    #     raise ValueError("Invalid entry_time detected after parsing")



    # # -------- TIME SLICE -------- #
    # time_slice_analysis = await run_time_slice_analysis(
    #     trades_df=trades_df,
    #     interval=interval,
    #     start_date=start_date,
    #     end_date=end_date
    # )

    return {
        "backtest_result": backtest_metrics,
        # "time_slice_analysis": time_slice_analysis
    }
