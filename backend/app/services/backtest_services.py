import pandas as pd
import vectorbt as vbt
import asyncio
from typing import Dict, Any, List

from ..core.Strategies import STRATEGY_REGISTRY
from .data_services import _load_and_resample_data


# ================= TIME UNITS ================= #

TIME_UNITS = {
    "Hour": lambda s: s.dt.strftime("%H:00"),
    "Days of Week": lambda s: s.dt.day_name(),
    "Week of Month": lambda s: ((s.dt.day - 1) // 7) + 1,
    "Month": lambda s: s.dt.month_name(),
    "Year": lambda s: s.dt.year,
}


# ================= METRICS ================= #

def calculate_metrics(trades: pd.DataFrame) -> Dict[str, Any]:
    if trades.empty:
        return {
            "trades_count": 0,
            "total_return_pct": 0.0,
            "win_rate_pct": 0.0
        }

    returns = trades["return"]
    return {
        "trades_count": int(len(trades)),
        "total_return_pct": round(returns.sum() * 100, 2),
        "win_rate_pct": round((returns > 0).mean() * 100, 2),
    }


# ================= GROUP ANALYSIS ================= #

def analyze_unit(trades_df: pd.DataFrame, label: str):
    df = trades_df.copy()
    df["entry_time"] = pd.to_datetime(df["entry_time"], errors="coerce")

    accessor = TIME_UNITS[label]
    df["group"] = accessor(df["entry_time"])

    out = {}
    for k, g in df.groupby("group"):
        key = f"Week {k}" if label == "Week of Month" else str(k)
        out[key] = calculate_metrics(g)

    return out


# ================= TIME SLICE ================= #

async def run_time_slice_analysis(
    trades_df: pd.DataFrame,
    interval: str,
    start_date: str,
    end_date: str
) -> Dict[str, Dict[str, Any]]:

    start = pd.to_datetime(start_date, dayfirst=True)
    end = pd.to_datetime(end_date, dayfirst=True)
    duration_days = (end - start).days

    enabled: List[str] = []

    if interval.endswith(("m", "h")):
        enabled += ["Hour", "Days of Week"]
    if duration_days >= 7:
        enabled.append("Week of Month")
    if duration_days >= 30:
        enabled.append("Month")
    if start.year != end.year:
        enabled.append("Year")


    tasks = {
        unit: asyncio.to_thread(analyze_unit, trades_df, unit)
        for unit in enabled
    }

    results = await asyncio.gather(*tasks.values())
    return dict(zip(enabled, results))


# ================= UTILS ================= #

def format_timedelta(td):
    if pd.isna(td):
        return None

    sec = int(td.total_seconds())
    d, sec = divmod(sec, 86400)
    h, sec = divmod(sec, 3600)
    m, s = divmod(sec, 60)

    out = []
    if d: out.append(f"{d}d")
    if h: out.append(f"{h}h")
    if m: out.append(f"{m}m")
    if s: out.append(f"{s}s")

    return " ".join(out)


# ================= MAIN ORCHESTRATOR ================= #

async def run_full_backtest(
    ticker_name: str,
    start_date: str,
    end_date: str,
    interval: str,
    strategy_name: str,
    params: Dict[str, Any],
    initial_cash: float,
    fees: float,
    slippage: float,
    df:None,
) -> Dict[str, Any]:

    print("[BACKTEST] Starting")

    fees /= 100
    slippage /= 100

    # ---------- DATA ----------
    print("[DATA] Loading")
    if df is None:
        df = await _load_and_resample_data(ticker_name, interval, start_date, end_date)

    # ---------- STRATEGY ----------
    print("[STRATEGY] Running")
    strategy_fn = STRATEGY_REGISTRY[strategy_name]
    signals = strategy_fn(df, **params)

    # ---------- PORTFOLIO ----------
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

    # ---------- STATS ----------
    stats = portfolio.stats().to_dict()
    stats["Calendar Period"] = format_timedelta(
        pd.to_datetime(end_date, dayfirst=True)
        - pd.to_datetime(start_date, dayfirst=True)
    )

    for k in [
        "Avg Winning Trade Duration",
        "Avg Losing Trade Duration",
        "Max Drawdown Duration",
        "Period",
    ]:
        if k in stats:
            stats[k] = format_timedelta(stats[k])

    # ---------- TRADES ----------
    trades_df = pd.DataFrame(portfolio.trades.records)

    if trades_df.empty:
        print("[BACKTEST] No trades")
        return {
            "backtest_result": stats,
            "time_slice_analysis": {}
        }

    price_index = df.index
    trades_df["entry_time"] = price_index.to_series().iloc[
        trades_df["entry_idx"]
    ].values
    trades_df["exit_time"] = price_index.to_series().iloc[
        trades_df["exit_idx"]
    ].values

    trades_df["entry_time"] = pd.to_datetime(trades_df["entry_time"])
    trades_df["exit_time"] = pd.to_datetime(trades_df["exit_time"])
    trades_df = trades_df.dropna(subset=["entry_time"])

# 🔍 DEBUG: find weekend trades
    trades_df["weekday"] = trades_df["entry_time"].dt.day_name()
    trades_df["date"] = trades_df["entry_time"].dt.date

    weekend_trades = trades_df[
        trades_df["weekday"].isin(["Saturday", "Sunday"])
    ]

    if not weekend_trades.empty:
        print("\n[DEBUG] Weekend trades detected:")
        print(
            weekend_trades[
                ["entry_time", "exit_time", "weekday", "date", "return"]
            ]
        )


    # ---------- TIME SLICE ----------
    print("[TIME SLICE] Running")
    time_slice = await run_time_slice_analysis(
        trades_df, interval, start_date, end_date
    )

    print("[BACKTEST] Completed")

    return {
        "backtest_result": stats,
        "time_slice_analysis": time_slice
    }
