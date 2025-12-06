import pandas as pd
import json
import uuid
import asyncio
from typing import Optional, Dict, Any
from ..core.config import settings
from fastapi import HTTPException
from io import StringIO 

# Using a simple in-memory cache for development until Redis is set up
CACHE: Dict[str, Any] = {}

class CachingService:
    """
    Handles caching and session management.
    Uses an in-memory dict for development.
    """
    
    def __init__(self):
        # In a real setup, connect to Redis here:
        # self.r = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT)
        pass 

    # --- 1. Data Caching (OHLCV DataFrames) ---
    def _generate_data_key(self, ticker: str, interval: str, start: str, end: str) -> str:
        return f"data:{ticker}:{interval}:{start}:{end}"  #a unique hash for the OHLCV data request.

    async def set_data(self, df: pd.DataFrame, ticker: str, interval: str, start: str, end: str):
        key = self._generate_data_key(ticker, interval, start, end)
        df_json = await asyncio.to_thread(df.to_json, orient='split')
        CACHE[key] = df_json

        # Serialize the DataFrame using a stable format (e.g., records)
        # Use to_thread for potentially large serialization/deserialization tasks

# Serialization = converting a Python object into a format that can be stored or sent.
# Deserialization = converting stored/sent data back into a Python object.

    async def get_data(self, ticker: str, interval: str, start: str, end: str) -> Optional[pd.DataFrame]:
        """Retrieves a processed DataFrame from the cache."""
        key = self._generate_data_key(ticker, interval, start, end)
        df_json = CACHE.get(key)
        
        if df_json:
            # Deserialize the DataFrame from the JSON string
            # Use to_thread for the blocking deserialization
            df = await asyncio.to_thread(pd.read_json, StringIO(df_json), orient='split')
            return df
        return None

    # --- 2. Analysis Session Caching (Frontend State) ---
    def create_session(self, initial_data_key: str, ticker: str, interval: str, start: str, end: str) -> str:
        """Creates a new session ID and stores the initial data key and parameters."""
        session_id = str(uuid.uuid4())
        session_data = {
            "data_key": initial_data_key, 
            "ticker": ticker,
            "interval": interval,
            "start_date": start,
            "end_date": end,
            "indicators": {}, 
            "strategy": {}
        }
        
        self.set_session(session_id, session_data)
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves session state."""
        session_json = CACHE.get(f"session:{session_id}")
        if session_json:
            # Load the JSON string back into a Python dict
            return json.loads(session_json)
        raise HTTPException(status_code=404, detail="Session expired or not found.")

    def set_session(self, session_id: str, data: Dict[str, Any]):
        """Updates session state (used for persisting intermediate choices)."""
        CACHE[f"session:{session_id}"] = json.dumps(data)
        
    def update_session(self, session_id: str, updates: Dict[str, Any]):
        """Helper to safely update existing session fields."""
        session_data = self.get_session(session_id)
        if session_data:
            session_data.update(updates)
            self.set_session(session_id, session_data)
        else:
            raise HTTPException(status_code=404, detail="Session expired during update.")

# Method to store the large trade record JSON for analysis
    def set_trade_records(self, session_id: str, trades_json: str):
        CACHE[f"trades:{session_id}"] = trades_json

    def get_trade_records(self, session_id: str) -> str:
        trades_json = CACHE.get(f"trades:{session_id}")
        if not trades_json:
            raise HTTPException(status_code=404, detail="Trade records not found. Please run backtest first.")
        return trades_json