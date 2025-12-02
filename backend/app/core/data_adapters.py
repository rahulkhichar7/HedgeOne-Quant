import pandas as pd
from pathlib import Path
import asyncio

class DataAdapter:
    PROJECT_ROOT = Path(__file__).parent.parent.parent.parent  #can be accessed using self as they are class variables
    CSV_PATH = PROJECT_ROOT/"data"

    def __init__(self, source = "csv"):
        self.source = source
        

    async def fetch_data(self, ticker: str, start_date: str, end_date: str, interval: str):
        file_name = ""
        file_path = self.CSV_PATH/file_name

        if not file_path.exists():
            raise FileNotFoundError(f"Data file not found at: {file_path}")

        df = await asyncio.to_thread(pd.read_csv, #here pass function & argument as seprate parameters, like first create a thread then function to exicute, then first argument ....
                                     file_path, 
                                     header=None)
        



