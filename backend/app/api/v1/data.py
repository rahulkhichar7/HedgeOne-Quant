import json
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any
from pathlib import Path
from ...services.data_services import (
    get_available_indicators,
    get_available_strategies,
    get_strategies_metadata,
    get_available_tickers,
    _read_csv,
    fetch_data_to_df,
    get_indicators_metadata,
    _load_and_resample_data
)
from ...services.cache_service import set_data, delete_data, get_key_list
from ...core.Strategies import STRATEGY_REGISTRY
from ...core.Indicators import INDICATOR_REGISTRY


router = APIRouter()

ASSET_PATH = Path(__file__).parent.parent.parent / "app" / "assets"

@router.get("/asset/tickers")
async def get_available_tickers_list():
    tickers = get_available_tickers()
    return {"tickers":tickers}

@router.get("/asset/indicators", response_model=Any)
async def get_available_indicators_list():
    indicators = get_available_indicators()
    return {"indicators": indicators}

@router.get("/asset/indicators/metadata", response_model=Any)
async def _get_indicators_metadata():
    return get_indicators_metadata()

@router.get(
    "/core/indicators/run",
    response_model=dict,
    summary="Run a technical indicator on historical price data",
    description=(
        "Computes a selected technical indicator on historical OHLCV data "
        "and returns the indicator values as a list."
    )
)
async def run_indicator(
    ticker_name: str = Query(default="TATA CONSULTANCY SERVICES", description="Trading symbol or index name"),
    start_date: str = Query(default="01/12/2024 09:15:00", description="Start datetime (DD/MM/YYYY HH:MM:SS)"),
    end_date: str = Query(default="06/12/2024 15:30:00", description="End datetime (DD/MM/YYYY HH:MM:SS)"),
    interval: str = Query(default="1d", description="Candle interval (e.g. '5m', '15m', '1h', '1d')"),
    indicator_name: str = Query(default="Exponential Moving Average (EMA)", description="Indicator name (e.g. 'EMA', 'RSI')"),
    params: str = Query(
        ...,
        description='Indicator parameters as JSON string. Example for EMA: {"window": 14}'
    )
):
    params = json.loads(params)

    df = await _load_and_resample_data(
        ticker_name=ticker_name,
        resolution=interval,
        start_date=start_date,
        end_date=end_date
    )

    indicator_fn = INDICATOR_REGISTRY[indicator_name]
    result = indicator_fn(df, **params)

    return {
        "indicator": indicator_name,
        "params": params,
        "values": result
    }


@router.get("/asset/strategies", response_model=Any)
async def get_available_strategies_list():
    strategies = get_available_strategies()
    return {"strategies":strategies}

@router.get("/asset/strategies/metadata", response_model=Any)
async def _get_strategies_metadata():
    return get_strategies_metadata()

@router.get("/core/strategies/run",response_model=dict,
            summary="Run a trading strategy on historical price data",
        description=(
            "Executes a selected trading strategy on historical OHLCV data "
            "and returns entry/exit signals along with all indicators used "
            "inside the strategy."
        )
)
async def run_strategy(
    ticker_name: str = Query(default="TATA CONSULTANCY SERVICES", description="Trading symbol or index name (e.g. 'NIFTY 50', 'RELIANCE')"),
    start_date: str = Query(default="01/12/2024 09:15:00", description="Start datetime in format DD/MM/YYYY HH:MM:SS"),
    end_date: str = Query(default="06/12/2024 15:30:00", description="End datetime in format DD/MM/YYYY HH:MM:SS"),
    interval: str = Query(default="1d", description="Candle interval (e.g. '5m', '15m', '1h', '1d')"),
    strategy_name: str = Query(default="EMA Crossover", description="Strategy name (e.g. 'EMA Crossover', 'RSI')"),
    params: str = Query(
    ...,
    description='Strategy parameters as a JSON string. Example for EMA Crossover: {"short_window": 13, "long_window": 24}'
)
):
    params = json.loads(params)

    df = await _load_and_resample_data(
        ticker_name=ticker_name,
        resolution=interval,
        start_date=start_date,
        end_date=end_date
    )

    strategy_fn = STRATEGY_REGISTRY[strategy_name]
    result = strategy_fn(df, **params)

    return {
        "strategy": strategy_name,
        "params": params,
        "entries": result["entries"],
        "exits": result["exits"],
        "indicators": result["indicators"]
    }

@router.post("/cache/load")
async def load_data(
    ticker_name: str = Query("TATA CONSULTANCY SERVICES", description="e.g. 'NIFTY 50'")
):
    df = await _read_csv(ticker_name=ticker_name)
    return await set_data(df=df, ticker= ticker_name)

@router.get("/cache/keys")
async def cache_keys():
    key_list = get_key_list()
    return {"keys": key_list}

@router.post("/cache/delete")
async def clear_cache(
    ticker_name: str = Query("TATA CONSULTANCY SERVICES", description="e.g. 'NIFTY 50'")
):
    return await delete_data(ticker=ticker_name)

@router.get("/data")
async def get_ohlcv_data(
    ticker_name: str = Query("TATA CONSULTANCY SERVICES", description="e.g. 'NIFTY 50'"),
    start_date: str = Query('01/12/2024 09:15:00', description="e.g. '01/12/2024 09:15:00'"),
    end_date: str = Query('06/12/2024 15:30:00', description="e.g. '01/10/2025 15:30:00'"),
    interval: str = Query('1d', description="e.g. '15m', '1d'")
):
    data = await fetch_data_to_df(ticker_name = ticker_name, start_date=start_date, end_date=end_date, interval=interval)
    return data # a json file with "data" as key