from backend.app.services.cache_service import get_data, set_data, get_key_list
import pandas as pd

import asyncio

async def main():
    df = pd.read_csv("data/HDFCBANK.csv")
    df["date_time"] = pd.to_datetime(
        df["date_time"],
        format="%d/%m/%Y %H:%M:%S"
    ).dt.strftime("%d/%m/%Y %H:%M:%S")
    df = df.set_index("date_time")

    await set_data(df, "HDFC")      # ✅
    print(get_key_list())

    d = await get_data("HDFC")      # ✅
    if d is None:
        print("couldn't return anything")
    else:
        print(d.head())

asyncio.run(main())
