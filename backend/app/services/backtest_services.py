import pandas as pd
import vectorbt as vbt
from typing import Dict, Any, List
import asyncio

# ---------------- TIME UNIT CONFIG ---------------- #

TIME_UNIT_MAP =  {
    "HOUR": {
        "func": lambda s: s.dt.hour
    },
    "DAY_OF_WEEK": {
        "func": lambda s: s.dt.day_name()
    },
    "WEEK_OF_MONTH": {
        "func": lambda s: ((s.dt.day - 1) // 7) + 1
    },
    "MONTH": {
        "func": lambda s: s.dt.month_name()
    },
    "YEAR": {
        "func": lambda s: s.dt.year
    }
}

# ---------------- ALLOWED UNITS ---------------- #

def get_allowed_time_units(
    interval: str,
    duration_days: float,
    duration_months: float,
    duration_years: float
) -> List[str]:

    units: List[str] = []

    # Granularity
    if interval.endswith(("m", "h")):
        units.extend(["HOUR", "DAY_OF_WEEK"])
    elif interval.endswith("d"):
        units.append("DAY_OF_WEEK")

    # Duration based
    if duration_days >= 14:
        units.append("WEEK_OF_MONTH")
    if duration_months >= 1.5:
        units.append("MONTH")
    if duration_years >= 1:
        units.append("YEAR")

    return list(dict.fromkeys(units))


# ---------------- METRICS ---------------- #

def calculate_sub_portfolio_metrics(trades_df: pd.DataFrame) -> Dict[str, Any]:
    if trades_df.empty:
        return {
            "trades_count": 0,
            "total_return_pct": 0.0,
            "win_rate_pct": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown_pct": 0.0
        }

    total_trades = len(trades_df)
    total_return = trades_df["return"].sum()
    win_rate = (trades_df["return"] > 0).mean() * 100

    try:
        temp_returns = pd.Series(
            trades_df["return"].values,
            index=trades_df["entry_time"]
        )

        portfolio = vbt.Portfolio.from_returns(
            temp_returns,
            freq="1D",
            init_cash=1
        )

        sharpe = portfolio.sharpe_ratio()
        max_dd = portfolio.max_drawdown()

    except Exception:
        sharpe, max_dd = 0.0, 0.0

    return {
        "trades_count": total_trades,
        "total_return_pct": round(total_return * 100, 2),
        "win_rate_pct": round(win_rate, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(max_dd * 100, 2)
    }


# ---------------- GROUPING ---------------- #

def analyze_trades_by_time_unit(
    trades_df: pd.DataFrame,
    time_unit: str
) -> Dict[str, Dict[str, Any]]:

    accessor = TIME_UNIT_MAP[time_unit]["func"]
    trades_df = trades_df.copy()
    trades_df["group_key"] = accessor(trades_df["entry_time"])

    result: Dict[str, Dict[str, Any]] = {}

    for label, group_df in trades_df.groupby("group_key"):
        result[str(label)] = calculate_sub_portfolio_metrics(group_df)

    return result


# ---------------- ORCHESTRATOR ---------------- #

async def run_time_slice_analysis(
    trades_df: pd.DataFrame,
    interval: str,
    start_date: str,
    end_date: str
) -> Dict[str, Dict[str, Any]]:

    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    duration_days = (end_dt - start_dt).days
    duration_months = duration_days / 30.44
    duration_years = duration_days / 365

    allowed_units = get_allowed_time_units(
        interval,
        duration_days,
        duration_months,
        duration_years
    )

    tasks = {
        unit: asyncio.to_thread(analyze_trades_by_time_unit, trades_df, unit)
        for unit in allowed_units
    }

    results = await asyncio.gather(*tasks.values())

    return dict(zip(allowed_units, results))

def format_timedelta(td):
    if pd.isna(td):
        return None

    total_seconds = int(td.total_seconds())
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds:
        parts.append(f"{seconds}s")

    return " ".join(parts)
