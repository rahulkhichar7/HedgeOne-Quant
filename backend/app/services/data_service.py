import pandas as pd
import asyncio
from typing import List, Tuple
from ..core.data_adapters import DataAdapter
from ..schemas.data_models import OHLCVData
from ..core.caching import CachingService 

class DataService:
    def __init__(self):
        self.data_adapter = DataAdapter()
        self.caching_service = CachingService()

    async def get_historical_data(self, ticker_name: str, start_date: str, end_date: str, interval: str) -> Tuple[List[OHLCVData], str]:
        
        # 1. Generate Key
        data_key = self.caching_service._generate_data_key(ticker_name, interval, start_date, end_date)
        
        # 2. CHECK CACHE
        df = await self.caching_service.get_data(ticker_name, interval, start_date, end_date)
        
        if df is None:
            # 3. READ CSV (SLOW PATH)
            df = await self.data_adapter.fetch_data_to_df(ticker_name, start_date, end_date, interval)
            
            # 4. SET CACHE (Async operation)
            await self.caching_service.set_data(df, ticker_name, interval, start_date, end_date)
            
        # 5. Convert DF to List[OHLCVData] 
        # (Using synchronous operation here, convert to async if the DF is massive)
        data_list = []
        df_reset = df.reset_index(names=['date_time'])
        for _, row in df_reset.iterrows():
            data_list.append(OHLCVData(
                date_time=row['date_time'], 
                open=row['open'], 
                high=row['high'], 
                low=row['low'], 
                close=row['close'], 
                volume=row['volume'] if 'volume' in row else 0
            ))
        
        # 6. Return the list and the unique key for the session
        return data_list, data_key
    

