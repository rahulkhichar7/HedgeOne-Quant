from fastapi import APIRouter, Body, HTTPException, Query
from typing import Dict, Any

from ...schemas.strategy_models import BacktestRequest, BacktestResult, StrategyConfig
from ...schemas.data_models import TimeSliceAnalysisResult
from ...services.vectorbt_engine import VectorBTEngine
from ...services.analysis_service import AnalysisService
from ...core.caching import CachingService

router = APIRouter()
vbt_engine = VectorBTEngine()
analysis_service = AnalysisService()
caching_service = CachingService()


# ----------------- STEP 3: Run Backtest -----------------
@router.post("/backtest", response_model=BacktestResult)
async def run_backtest_sync(
    session_id: str = Query(..., description="Active session ID."),
    initial_cash: float = Query(10000.0),
    fees: float = Query(0.0005),
    slippage: float = Query(0.0)
):
    """Runs VectorBT backtest using cached data + strategy."""
    session_data = caching_service.get_session(session_id)

    if not session_data.get("strategy"):
        raise HTTPException(status_code=400, detail="Strategy configuration missing.")

    reconstructed_request = BacktestRequest(
        ticker=session_data["ticker"],
        interval=session_data["interval"],
        start_date=session_data["start_date"],
        end_date=session_data["end_date"],
        initial_cash=initial_cash,
        fees=fees,
        slippage=slippage,
        strategy_config=StrategyConfig(**session_data["strategy"])
    )

    try:
        return await vbt_engine.run_strategy_backtest(reconstructed_request, session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest execution failed: {type(e).__name__}: {str(e)}")


# ----------------- STEP 4: Time Slice Analysis -----------------
@router.post("/analysis/time_slice", response_model=Dict[str, TimeSliceAnalysisResult])
async def get_time_slice_analysis(
    session_id: str = Query(...),
    request_data: Dict[str, Any] = Body(default_factory=dict)
):
    """Performs in-depth P&L timeline analysis."""
    try:
        session_data = caching_service.get_session(session_id)
        trades_records_json = caching_service.get_trade_records(session_id)

        return await analysis_service.run_time_slice_analysis(
            trades_records_json=trades_records_json,
            interval=session_data["interval"],
            start_date=session_data["start_date"],
            end_date=session_data["end_date"]
        )

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis execution failed: {str(e)}")
