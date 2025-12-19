import pandas as pd
from pathlib import Path
import asyncio
from typing import Tuple, Dict, Optional, List, Any
from ..services.cache_service import get_data
import json

ASSET_PATH = Path(__file__).parent.parent.parent / "app" / "core" / "assets"

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

async def _read_csv(ticker_name:str):
    PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
    CSV_ROOT = PROJECT_ROOT / "data"

    securities = get_ticker_file()
    if ticker_name not in securities.keys():
        raise ValueError(f"Ticker {ticker_name} not found in Securities list.")
        
    csv_filename = securities[ticker_name][1]
    csv_path = CSV_ROOT / csv_filename

    if not csv_path.exists():
        raise FileNotFoundError(f"Data file not found at: {csv_path}")

    # 2. Load and clean DataFrame (synchronous part)
    df = pd.read_csv(csv_path)
    df['date_time'] = pd.to_datetime(df['date_time'], format="%d/%m/%Y %H:%M:%S")
    df = df.set_index("date_time")
    return df


async def _load_and_resample_data(ticker_name: str, resolution: str, start_date: str, end_date: str) -> pd.DataFrame:

    """Synchronous function to load and process data (run in a thread)."""

    # 3. Resample and aggregate
    df = await get_data(ticker=ticker_name)
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
    
    return df_resampled



async def fetch_data_to_df(
    ticker_name: str, 
    start_date: str, 
    end_date: str, 
    interval: str
) -> Dict[str,Any]:

    df = await _load_and_resample_data(
        ticker_name,
        interval,
        start_date,
        end_date
    )

    df = df.astype("str")
    records = df.to_dict(orient="records")
    return {"data": records}

def get_available_tickers() -> List[str]:
    try:
        with open(ASSET_PATH/"tickers.json", 'r') as f:
            tickers = list(dict(json.load(f)).keys())
            return tickers
    except Exception as e:
        print(f"Error duing loading ticker file: {e}")

def get_ticker_file()->Dict[str,List[str]]:
    try:
        with open(ASSET_PATH/"tickers.json", 'r') as f:
            tickers = json.load(f)
            return dict(tickers)
    except Exception as e:
        print(f"Error duing loading ticker file: {e}")

def get_available_indicators() -> List[str]:
    try:
        with open(ASSET_PATH/"indicators.json", 'r') as f:
            indicators = list(dict(json.load(f)).keys())
            return indicators
    except Exception as e:
        print(f"Error duing loading indicator file: {e}")

def get_available_strategies() -> List[str]:
    try:
        with open(ASSET_PATH/"strategies.json", 'r') as f:
            strategies = list(dict(json.load(f)).keys())
            return strategies
    except Exception as e:
        print(f"Error duing loading strategies file: {e}")

def get_strategies_metadata() -> Dict[str,Any]:
    try:
        with open(ASSET_PATH/"strategies.json", 'r') as f:
            strategies = json.load(f)
            return strategies
    except Exception as e:
        print(f"Error duing loading strategies metadata file: {e}")

def get_indicators_metadata() -> Dict[str,Any]:
    try:
        with open(ASSET_PATH/"indicators.json", 'r') as f:
            indicators = json.load(f)
            return indicators
    except Exception as e:
        print(f"Error duing loading indicators metadata file: {e}")
        