import json
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any
from pathlib import Path

from ...schemas.data_models import OHLCVData, DataFetchResponse
from ...services.data_service import DataService
from ...core.data_adapters import get_available_tickers, get_available_strategies, get_available_indicators, get_strategies_metadata, DataAdapter

router = APIRouter()
data_service = DataService()

# --- Path to data
ASSET_PATH = Path(__file__).parent.parent.parent / "app" / "assets"


@router.get("/tickers")
async def get_available_tickers_list():
    return get_available_tickers()

@router.get("/indicators", response_model=List[str])
async def get_available_indicators_list():
    return get_available_indicators()

@router.get("/strategies", response_model=List[str])
async def get_available_strategies_list():
    return get_available_strategies()

@router.get("/strategies/metadata", response_model=Dict[str, Any])
async def _get_strategies_metadata():
    return get_strategies_metadata()

@router.get("/data")
async def get_ohlcv_data(
    ticker_name: str = Query(..., description="e.g. 'NIFTY 50'"),
    start_date: str = Query(..., description="e.g. '01/12/2024 09:15:00'"),
    end_date: str = Query(..., description="e.g. '01/10/2025 15:30:00'"),
    interval: str = Query(..., description="e.g. '15m', '1d'")
):
    adapter = DataAdapter()
    data = await adapter.fetch_data_to_df(ticker_name = ticker_name, start_date=start_date, end_date=end_date, interval=interval)
    return data # a json file with "data" as key