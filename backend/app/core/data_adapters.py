import pandas as pd
from pathlib import Path
import asyncio
from typing import Tuple, Dict, Optional, List

SECURITIES: Dict[str, Tuple[str, str]] = {
    "HDFC BANK LTD": ("NSE:HDFCBANK-EQ", "HDFCBANK.csv"),
    "TATA CONSULTANCY SERVICES": ("NSE:TCS-EQ", "TCS.csv"),
    "RELIANCE INDUSTRIES LTD": ("NSE:RELIANCE-EQ", "RELIANCE.csv"),
    "INFOSYS LIMITED": ("NSE:INFY-EQ", "INFY.csv"),
    "HINDUSTAN UNILEVER LTD": ("NSE:HINDUNILVR-EQ", "HINDUNILVR.csv"),
    "NIFTY 50": ("NSE:NIFTY50-INDEX", "NIFTY50.csv"),
    "NIFTY BANK": ("NSE:NIFTYBANK-INDEX", "NIFTYBANK.csv"),
    "NIFTY IT": ("NSE:NIFTYIT-INDEX", "NIFTYIT.csv"),
    "NIFTY MIDCAP 100": ("NSE:NIFTYMIDCAP100-INDEX", "NIFTYMIDCAP100.csv"),
    "NIFTY FMCG": ("NSE:NIFTYFMCG-INDEX", "NIFTYFMCG.csv"),
}

def convert_resolution(res: str) -> str:
    """Converts user resolution (e.g., '15m') to Pandas offset alias (e.g., '15T')."""
    res = res.lower()
    if res.endswith("m") and not res.endswith("mo"): return res[:-1] + "T"
    if res.endswith("h"): return res[:-1] + "H"
    if res.endswith("d"): return res[:-1] + "D"
    if res.endswith("w"): return res[:-1] + "W"
    if res.endswith("mo"): return res[:-2] + "M"
    if res.endswith("y"): return res[:-1] + "Y"
    raise ValueError(f"Invalid resolution: {res}")

def _load_and_resample_data(
    ticker_name: str, 
    resolution: str, 
    start_date: str, 
    end_date: str
) -> pd.DataFrame:
    """Synchronous function to load and process data (run in a thread)."""
    PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
    CSV_ROOT = PROJECT_ROOT / "data"

    if ticker_name not in SECURITIES:
        raise ValueError(f"Ticker {ticker_name} not found in SECURITIES list.")
        
    csv_filename = SECURITIES[ticker_name][1]
    csv_path = CSV_ROOT / csv_filename

    if not csv_path.exists():
        raise FileNotFoundError(f"Data file not found at: {csv_path}")

    # 2. Load and clean DataFrame (synchronous part)
    df = pd.read_csv(csv_path)
    df['date_time'] = pd.to_datetime(df['date_time'], format="%d/%m/%Y %H:%M:%S")
    df = df.set_index("date_time")

    # 3. Resample and aggregate
    start_dt = pd.to_datetime(start_date, format="%d/%m/%Y %H:%M:%S")
    end_dt = pd.to_datetime(end_date, format="%d/%m/%Y %H:%M:%S")
    
    df = df.loc[start_dt:end_dt]
    rule = convert_resolution(resolution)
    
    df_resampled = df.resample(rule=rule).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum"
    }).dropna()
    
    # Ensure index is datetime and volume is integer
    df_resampled['volume'] = df_resampled['volume'].fillna(0).astype(int)
    
    return df_resampled.reset_index(names=['date_time'])


class DataAdapter:
    """Handles fetching raw market data."""
    
    def __init__(self, source: str = "csv"):
        self.source = source
        
    async def fetch_data_to_df(
        self, 
        ticker_name: str, 
        start_date: str, 
        end_date: str, 
        interval: str
    ) -> pd.DataFrame:
        """Runs the synchronous data loading/resampling in a separate thread."""
        if self.source == "csv":
            # Use asyncio.to_thread for the blocking I/O operation
            df = await asyncio.to_thread(
                _load_and_resample_data,
                ticker_name,
                interval,
                start_date,
                end_date
            )
            return df
        else:
            # Placeholder for future broker/DB logic
            raise NotImplementedError(f"Data source '{self.source}' not yet implemented.")

# Helper to get ticker list for frontend dropdown
def get_available_tickers() -> List[str]:
    return list(SECURITIES.keys())