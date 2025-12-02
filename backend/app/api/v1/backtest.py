from fastapi import APIRouter, Body, HTTPException
from typing import Dict, Any
import pandas as pd

from ...schemas.strategy_models import BacktestRequest, BacktestResult
from ...schemas.data_models import TimeSliceAnalysisResult
from ...services.vectorbt_engine import VectorBTEngine
from ...services.analysis_service import AnalysisService

router = APIRouter()
vbt_engine = VectorBTEngine()
analysis_service = AnalysisService()

@router.post("/backtest", response_model=BacktestResult)
async def run_backtest_sync(request: BacktestRequest = Body(...)):
    """
    Runs the full VectorBT backtest using the requested strategy and parameters.
    This is CPU-bound and run in a thread to keep FastAPI responsive.
    """
    try:
        # NOTE: Caching logic (using Redis/core/caching.py) should be implemented here 
        # before calling the engine, using the request JSON as the cache key.
        
        result = await vbt_engine.run_strategy_backtest(request)
        return result
    except ValueError as e:
        # Catch specific errors (e.g., strategy not found, data issues)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Catch all other exceptions (e.g., VectorBT error, Numba error)
        raise HTTPException(status_code=500, detail=f"Backtest execution failed: {type(e).__name__}: {str(e)}")


@router.post("/analysis/time_slice", response_model=TimeSliceAnalysisResult)
async def get_time_slice_analysis(
    # NOTE: The request body for analysis needs to include the Job ID 
    # OR the original BacktestRequest, plus the requested analysis unit (e.g., "WEEK")
    request_data: Dict[str, Any] = Body(...) 
):
    """
    Performs the in-depth, timeline-wise P&L analysis (Max Profit Day/Week/Month).
    This logic is complex and is run by the AnalysisService.
    """
    try:
        # Placeholder for complex implementation
        analysis_unit = request_data.get("time_unit", "DAY_OF_WEEK")
        
        # In a real scenario, the service would fetch the trade list from the cache 
        # based on a job ID provided in the request, then run analysis.
        
        # Example of calling the service (assuming it's ready to handle the logic)
        analysis_result = analysis_service.run_time_slice_analysis(analysis_unit)
        
        return TimeSliceAnalysisResult(
            time_unit=analysis_unit, 
            results=analysis_result
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")