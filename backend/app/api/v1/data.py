import json
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any
from pathlib import Path

from ...schemas.data_models import OHLCVData
from ...services.data_service import DataService
from ...core.data_adapters import get_available_tickers # Import the helper

router = APIRouter()
data_service = DataService()

# --- Utility to load Strategy Metadata ---
# Navigate from api/v1/ to the strategies/ directory
STRATEGIES_INFO_PATH = Path(__file__).parent.parent.parent / "strategies" / "info.json"

@router.get("/tickers", response_model=List[str])
async def get_available_tickers_list():
    """Returns a list of all available stock/index names for the UI dropdown."""
    return get_available_tickers()

@router.get("/data", response_model=List[OHLCVData])
async def get_ohlcv_data(
    ticker_name: str = Query(..., description="The symbol name (e.g., 'NIFTY 50')"),
    start_date: str = Query(..., description="Start date (e.g., '01/01/2020 09:15:00')"),
    end_date: str = Query(..., description="End date (e.g., '31/12/2023 15:30:00')"),
    interval: str = Query(..., description="Time resolution (e.g., '15m', '1d')")
):
    """
    Fetches, cleans, and resamples historical OHLCV data. 
    This is the first step in the UI workflow.
    """
    try:
        data = await data_service.get_historical_data(ticker_name, start_date, end_date, interval)
        return data
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Catch unexpected errors during I/O/resampling
        raise HTTPException(status_code=500, detail=f"Data processing failed: {e}")

@router.get("/strategies/metadata", response_model=Dict[str, Any])
async def get_strategies_metadata():
    """Returns the full strategy configuration used by the frontend to build dynamic forms."""
    try:
        with open(STRATEGIES_INFO_PATH, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Strategy metadata file not found.")