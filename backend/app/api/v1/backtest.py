from fastapi import APIRouter, Query
from typing import Dict, Any
import json

from ...services.backtest_services import run_full_backtest

router = APIRouter()


@router.post("/backtest", response_model=Dict[str, Any])
async def run_backtest(
    ticker_name: str = Query("NIFTY 50"),
    start_date: str = Query("01/12/2024 09:15:00"),
    end_date: str = Query("10/04/2025 15:30:00"),
    interval: str = Query("15m"),
    strategy_name: str = Query("EMA Crossover"),
    params: str = Query('{"short_window":5,"long_window":12}'),
    initial_cash: float = Query(100000.0),
    fees: float = Query(0.05),
    slippage: float = Query(0.0),
):
    params = json.loads(params)
    

    return await run_full_backtest(
        ticker_name=ticker_name,
        start_date=start_date,
        end_date=end_date,
        interval=interval,
        strategy_name=strategy_name,
        params=params,
        initial_cash=initial_cash,
        fees=fees,
        slippage=slippage,
    )
