import pandas as pd
import vectorbt as vbt
from typing import Dict, Any, List
import asyncio


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
    total_return = returns.sum()
    win_rate = (returns > 0).mean() * 100

    return {
        "trades_count": int(len(trades)),
        "total_return_pct": round(total_return * 100, 2),
        "win_rate_pct": round(win_rate, 2)
    }


# ================= GROUP ANALYSIS ================= #

def analyze_unit(trades_df: pd.DataFrame, label: str):
    df = trades_df.copy()

    # 🔒 ENSURE DATETIME
    df["entry_time"] = pd.to_datetime(df["entry_time"], errors="coerce")

    accessor = TIME_UNITS[label]
    df["group"] = accessor(df["entry_time"])

    output = {}

    for k, g in df.groupby("group"):
        key = f"Week {k}" if label == "Week of Month" else str(k)
        output[key] = calculate_metrics(g)

    return output


# ================= ORCHESTRATOR ================= #

async def run_time_slice_analysis(
    trades_df: pd.DataFrame,
    interval: str,
    start_date: str,
    end_date: str
) -> Dict[str, Dict[str, Any]]:

    start = pd.to_datetime(start_date, dayfirst=True)
    end = pd.to_datetime(end_date, dayfirst=True)
    duration_days = (end - start).days

    enabled_units: List[str] = []

    if interval.endswith(("m", "h")):
        enabled_units += ["Hour", "Days of Week"]

    if duration_days >= 7:
        enabled_units.append("Week of Month")
    if duration_days >= 30:
        enabled_units.append("Month")
    if duration_days >= 365:
        enabled_units.append("Year")

    tasks = {
        unit: asyncio.to_thread(analyze_unit, trades_df, unit)
        for unit in enabled_units
    }

    results = await asyncio.gather(*tasks.values())

    return dict(zip(enabled_units, results))


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
