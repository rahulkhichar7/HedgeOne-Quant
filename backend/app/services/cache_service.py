import pandas as pd
import json
from io import StringIO
import asyncio
from typing import Dict, Any, Optional


CACHE: Dict[str,Any] = {}

def generate_key(ticker):
    return f"data:{ticker}"

def get_key_list():
    return list(CACHE.keys())

async def set_data(df, ticker):
    key = generate_key(ticker)
    df_json = await asyncio.to_thread(df.to_json,
                                      orient = 'split'
                                      )
    CACHE[key] = df_json
    return {"message":f"Data loaded successfully with key: {key}"}

# Serialization = converting a Python object into a format that can be stored or sent.
# Deserialization = converting stored/sent data back into a Python object.

async def get_data(ticker):
    key = generate_key(ticker)
    keys = get_key_list()

    if key not in keys:
        print("Ticker is not in CACHE")
        return None

    df_json = CACHE.get(key)
    if df_json:
        df = await asyncio.to_thread(pd.read_json,
                                     StringIO(df_json),
                                     orient = 'split')
        return df
    else:
        print("Couldn't get dataframe")
        return
        
async def delete_data(ticker):
    key = generate_key(ticker=ticker)
    CACHE.pop(key,None)
    return {"message":f"data cleared from cache for : {ticker}"}



