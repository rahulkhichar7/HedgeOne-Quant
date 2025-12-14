from fastapi import APIRouter, Body, HTTPException, Query
from typing import Dict, Any

# from ...core.caching import CachingService

router = APIRouter()

# ----------------- STEP 3: Run Backtest -----------------
@router.post("/backtest", response_model=Any)
async def run_backtest_sync(
    session_id: str = Query(..., description="Active session ID."),
    initial_cash: float = Query(10000.0),
    fees: float = Query(0.0005),
    slippage: float = Query(0.0)
):
    return {"message":"yet to impliment"}

# ----------------- STEP 4: Time Slice Analysis -----------------
@router.post("/analysis/time_slice", response_model=Any)
async def get_time_slice_analysis(
    session_id: str = Query(...),
    request_data: Dict[str, Any] = Body(default_factory=dict)
):
    return {"message":"yet to impliment"}