"""
Central configuration: paths, secrets (.env), markets and trading-cost presets.

Everything that is a "number you may want to tweak" lives here, so the rest of
the code never hard-codes it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# ------------------------------------------------------------------ paths
BACKEND_DIR = Path(__file__).resolve().parent.parent          # .../backend
PROJECT_DIR = BACKEND_DIR.parent                               # .../HedgeOne-Quant
FRONTEND_DIR = PROJECT_DIR / "frontend"
STRATEGIES_DIR = BACKEND_DIR / "strategies"

load_dotenv(BACKEND_DIR / ".env")

DATA_DIR = Path(os.getenv("HEDGEONE_DATA_DIR", PROJECT_DIR / "data"))
STORE_DIR = DATA_DIR / "store"        # parquet candles:  store/<source>/<symbol>__<interval>.parquet
REPORTS_DIR = DATA_DIR / "reports"    # saved deep-backtest reports (json)
TOKENS_DIR = DATA_DIR / "tokens"      # broker access tokens (never commit)
for _d in (STORE_DIR, REPORTS_DIR, TOKENS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

SYMBOLS_FILE = Path(__file__).resolve().parent / "data" / "symbols.json"

# ------------------------------------------------------------------ secrets
# Upstox analytics token (read-only, valid one year): https://account.upstox.com/developer/apps
UPSTOX_ANALYTICS_TOKEN = os.getenv("UPSTOX_ANALYTICS_TOKEN", "")

# All timestamps are stored as *naive* local time of this zone (IST).
TIMEZONE = os.getenv("HEDGEONE_TZ", "Asia/Kolkata")


# ------------------------------------------------------------------ markets
@dataclass(frozen=True)
class Market:
    """Trading-calendar facts used for resampling and for annualising metrics."""
    name: str
    session_start: str | None      # "09:15" (None = trades 24/7)
    session_end: str | None        # "15:30"
    trading_days: int              # per year, for Sharpe/Sortino/CAGR annualisation
    default_costs: str             # key in COST_PRESETS
    utc_aligned: bool = False      # crypto candles align to UTC boundaries

    @property
    def session_minutes(self) -> int:
        if not self.session_start:
            return 24 * 60
        h1, m1 = map(int, self.session_start.split(":"))
        h2, m2 = map(int, self.session_end.split(":"))
        return (h2 * 60 + m2) - (h1 * 60 + m1)


MARKETS: dict[str, Market] = {
    "NSE": Market("NSE", "09:15", "15:30", 252, "nse_intraday"),
    "CRYPTO": Market("CRYPTO", None, None, 365, "delta_futures", utc_aligned=True),
}


# ------------------------------------------------------------------ costs
@dataclass(frozen=True)
class CostPreset:
    """Per-side costs. fees_pct and slippage_pct are in PERCENT (0.03 = 0.03 %)."""
    label: str
    fees_pct: float
    fixed_fee: float = 0.0       # currency per order
    slippage_pct: float = 0.0
    note: str = ""


# Approximations — verify against your broker's current charge sheet and edit here.
COST_PRESETS: dict[str, CostPreset] = {
    "zero": CostPreset("No costs", 0.0, 0.0, 0.0, "Idealised, useful only for debugging logic."),
    "nse_intraday": CostPreset(
        "NSE equity intraday", 0.03, 0.0, 0.01,
        "≈ brokerage ₹20 cap + STT 0.025% (sell) + exchange + SEBI + stamp + GST, averaged per side."),
    "nse_delivery": CostPreset(
        "NSE equity delivery", 0.12, 0.0, 0.01,
        "Dominated by STT 0.1% on both sides + stamp duty + DP charge."),
    "nse_futures": CostPreset(
        "NSE futures", 0.02, 0.0, 0.01, "Brokerage + STT 0.02% (sell) + exchange + GST, averaged."),
    "delta_futures": CostPreset(
        "Delta Exchange India futures (taker)", 0.059, 0.0, 0.02, "0.05% taker + 18% GST."),
    "coindcx_spot": CostPreset(
        "CoinDCX spot (taker)", 0.25, 0.0, 0.05, "Spot taker fee + GST; TDS not modelled."),
}


@dataclass
class BacktestSettings:
    """Defaults for a backtest run; every field can be overridden from the UI/API."""
    init_cash: float = 100_000.0
    cost_preset: str | None = None          # None -> market default
    fees_pct: float | None = None           # override preset
    fixed_fee: float | None = None
    slippage_pct: float | None = None
    size_pct: float = 100.0                 # % of equity per trade
    execution: str = "next_open"            # "next_open" (realistic) | "close" (same bar)
    square_off: bool = False                # NSE: flatten before session end, no overnight
    square_off_time: str = "15:15"
    no_entry_after: str = "15:00"
    sl_pct: float | None = None             # override strategy stop-loss  (percent)
    tp_pct: float | None = None             # override strategy take-profit (percent)
    trailing: bool | None = None
    extra: dict = field(default_factory=dict)
