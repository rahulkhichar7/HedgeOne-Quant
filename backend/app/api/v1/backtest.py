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

# --- ENDPOINT 1: Store Strategy Choice (UI Step 2) ---
@router.post("/session/{session_id}/update-strategy")
async def update_session_strategy(
    session_id: str, 
    strategy_config: StrategyConfig = Body(...)
):
    """
    Stores the user's chosen strategy parameters in the session cache. 
    """
    try:
        caching_service.update_session(session_id, {"strategy": strategy_config.model_dump()})
        return {"message": "Strategy configuration updated successfully."}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update session: {str(e)}")


# --- ENDPOINT 2: Run Backtest (UI Step 3) ---
@router.post("/backtest", response_model=BacktestResult)
async def run_backtest_sync(
    session_id: str = Query(..., description="Active session ID from the frontend."),
    initial_cash: float = Query(10000.0, description="Initial portfolio cash."),
    fees: float = Query(0.0005, description="Trading fees (0.05% default)."),
    slippage: float = Query(0.0, description="Trading slippage.")
):
    """
    Runs the full VectorBT backtest by retrieving data/parameters from the session
    and saves trade records to the cache for analysis.
    """
    # 1. Retrieve full state from session
    session_data = caching_service.get_session(session_id)
    
    if not session_data.get('strategy'):
        raise HTTPException(status_code=400, detail="Strategy configuration is missing from session.")

    # 2. Reconstruct the full BacktestRequest from the cache
    reconstructed_request = BacktestRequest(
        ticker=session_data['ticker'],
        interval=session_data['interval'],
        start_date=session_data['start_date'],
        end_date=session_data['end_date'],
        initial_cash=initial_cash,
        fees=fees,
        slippage=slippage,
        strategy_config=StrategyConfig(**session_data['strategy'])
    )

    # 3. Call engine (passing session_id so it can save the trades JSON)
    try:
        result = await vbt_engine.run_strategy_backtest(reconstructed_request, session_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest execution failed: {type(e).__name__}: {str(e)}")


# --- ENDPOINT 3: Run Time Slice Analysis (UI Step 4) ---
@router.post("/analysis/time_slice", response_model=Dict[str, TimeSliceAnalysisResult])
async def get_time_slice_analysis(
    session_id: str = Query(..., description="Active session ID from the frontend."),
    request_data: Dict[str, Any] = Body(default_factory=dict)
):
    """
    Performs the in-depth, timeline-wise P&L analysis using cached trade data 
    from the last backtest associated with the session.
    """
    try:
        # 1. Retrieve the session data (to get interval and dates)
        session_data = caching_service.get_session(session_id)
        
        # 2. Retrieve the raw trade records JSON string from the cache
        trades_records_json = caching_service.get_trade_records(session_id)
        
        # 3. Call AnalysisService with all necessary components
        analysis_results = await analysis_service.run_time_slice_analysis(
            trades_records_json=trades_records_json,
            interval=session_data['interval'],
            start_date=session_data['start_date'],
            end_date=session_data['end_date']
        )
        return analysis_results
        
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis execution failed: {str(e)}")