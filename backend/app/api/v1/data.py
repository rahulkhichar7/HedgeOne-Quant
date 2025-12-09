import json
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any
from pathlib import Path

from ...schemas.data_models import OHLCVData, DataFetchResponse
from ...services.data_service import DataService
from ...core.data_adapters import get_available_tickers

router = APIRouter()
data_service = DataService()

# --- Path to Strategy Metadata ---
STRATEGIES_INFO_PATH = Path(__file__).parent.parent.parent / "strategies" / "info.json"


@router.get("/tickers", response_model=List[str])
async def get_available_tickers_list():
    """Returns a list of all available stock/index names."""
    return get_available_tickers()


@router.get("/data", response_model=DataFetchResponse)
async def get_ohlcv_data(
    ticker_name: str = Query(..., description="e.g. 'NIFTY 50'"),
    start_date: str = Query(..., description="e.g. '01/01/2020 09:15:00'"),
    end_date: str = Query(..., description="e.g. '31/12/2023 15:30:00'"),
    interval: str = Query(..., description="e.g. '15m', '1d'")
):
    """Fetch OHLCV data, check cache, and create a session."""
    try:
        data_list, data_key = await data_service.get_historical_data(
            ticker_name, start_date, end_date, interval
        )

        session_id = data_service.caching_service.create_session(
            data_key, ticker_name, interval, start_date, end_date
        )

        return DataFetchResponse(session_id=session_id, data=data_list)

    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Data processing failed: {e}")


@router.get("/strategies/metadata", response_model=Dict[str, Any])
async def get_strategies_metadata():
    """Returns strategy configuration from JSON."""
    try:
        with open(STRATEGIES_INFO_PATH, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Strategy metadata file not found.")
