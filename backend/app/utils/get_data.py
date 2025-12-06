import datetime as dt
import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from fyers_apiv3 import fyersModel
import webbrowser
import time
import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_PATH = Path(__file__).parent.parent.parent.parent
load_dotenv(PROJECT_PATH/"backend"/".env")  #by default load_dotenv() just look at current dir

def unix_to_dt(unix_timestamp):
    dt_obj = dt.datetime.fromtimestamp(unix_timestamp)
    simple_dt = dt_obj.strftime("%d/%m/%Y %H:%M:%S")
    return simple_dt

def get_data_by_DEI(symbol, resolution, start_date, end_date):
    start_dt = dt.datetime.strptime(start_date, "%d/%m/%Y %H:%M:%S")
    end_dt = dt.datetime.strptime(end_date, "%d/%m/%Y %H:%M:%S")
    
    headers = {'Accept': 'application/json'}
    all_dfs = [] 

    current_end_dt = end_dt
    print(f"Initializing data fetch for {symbol} ({resolution})...")
    
    while current_end_dt > start_dt:
        start_ts = int(start_dt.timestamp())
        end_ts = int(current_end_dt.timestamp())
        
        # Ensure we don't request data before our desired start_time
        if end_ts < start_ts:
            break
            
        print(f"  Fetching chunk ending at: {current_end_dt.strftime('%d/%m/%Y %H:%M:%S')}")

        try:
            params = {
                'resolution': resolution,
                'symbol': symbol,
                'start': start_ts,
                'end': end_ts
            }
            
            r = requests.get('https://api.india.delta.exchange/v2/history/candles', params=params, headers=headers)
            r.raise_for_status()  # Raise an error for bad responses (4xx or 5xx)
            
            data = r.json().get('result', [])
            if not data:
                print("  No more data found in this range. Stopping.")
                break
                
            df_chunk = pd.DataFrame(data)
            all_dfs.append(df_chunk)
            oldest_ts_in_chunk = df_chunk['time'].min()
            current_end_dt = dt.datetime.fromtimestamp(oldest_ts_in_chunk - 1)

        except requests.exceptions.RequestException as e:
            print(f"API Error: {e}. Stopping fetch.")
            break
        except Exception as e:
            print(f"An unexpected error occurred: {e}. Stopping fetch.")
            break

    # --- 4. Final Processing ---
    if not all_dfs:
        print("No data was fetched.")
        return pd.DataFrame()

    print("All chunks fetched. Concatenating and cleaning data...")

    final_df = pd.concat(all_dfs)
    final_df = final_df.sort_values(by='time', ascending=True)
    final_df = final_df.drop_duplicates(subset='time')
    final_df['time'] = final_df['time'].apply(unix_to_dt)
    final_df = final_df.reset_index(drop=True)
    
    print(f"Successfully fetched {len(final_df)} total candles.")
    return final_df


def get_data_from_csv(csv_path, resolution, start_date, end_date):

    def convert_resolution(res):
        res = res.lower()
        if res.endswith("m") and not res.endswith("mo"):  # minutes
            return res[:-1] + "T"   # 15m -> 15T
        if res.endswith("h"):       # hours
            return res[:-1] + "H"   # 1h -> 1H
        if res.endswith("d"):       # days
            return res[:-1] + "D"
        if res.endswith("w"):       # weeks
            return res[:-1] + "W"
        if res.endswith("mo"):      # months
            return res[:-2] + "M"   # 1mo -> 1M
        if res.endswith("y"):       # years
            return res[:-1] + "Y"   # 1y -> 1Y

        raise ValueError(f"Invalid resolution: {res}")

    df = pd.read_csv(csv_path)
    df['date_time'] = pd.to_datetime(df['date_time'], format="%d/%m/%Y %H:%M:%S")
    df = df.set_index("date_time")

    start_dt = pd.to_datetime(start_date, format="%d/%m/%Y %H:%M:%S")
    end_dt   = pd.to_datetime(end_date,   format="%d/%m/%Y %H:%M:%S")

    df = df.loc[start_dt:end_dt]
    rule = convert_resolution(resolution)
    df = df.resample(rule=rule).agg({
        "open": "first",
        "high": "max",
        "low":  "min",
        "close": "last",
        "volume": "sum"
    }).dropna()
    df = df.reset_index()
    return df

def get_fyers_authcode():
    redirect_uri= "https://127.0.0.1/"  
    client_id = os.getenv("FYERS_CLIENT_ID")                     
    secret_key = os.getenv("FYERS_SECRET_KEY")                        
    grant_type = "authorization_code"                  
    response_type = "code"                            
    state = "sample"                              
    appSession = fyersModel.SessionModel(client_id = client_id, redirect_uri = redirect_uri,response_type=response_type,state=state,secret_key=secret_key,grant_type=grant_type)
    generateTokenUrl = appSession.generate_authcode()
    webbrowser.open(generateTokenUrl,new=1)

def get_historical_data_by_fyers(symbol, resolution, start_date, end_date):

    DATA_LIMIT_DAYS = {"1": 100, "5": 100, "15": 100, "30": 100, "45": 100, "60": 100, "D": 365}

    start_dt = dt.datetime.strptime(start_date, "%d-%m-%Y").date()
    end_dt = dt.datetime.strptime(end_date, "%d-%m-%Y").date()
    delta = dt.timedelta(days=DATA_LIMIT_DAYS.get(resolution, 100))
    date_ranges = []
    while start_dt < end_dt:
        next_dt = min(start_dt + delta, end_dt)
        date_ranges.append((start_dt.strftime("%Y-%m-%d"), next_dt.strftime("%Y-%m-%d")))
        start_dt = next_dt + dt.timedelta(days=1)


    client_id = os.getenv("FYERS_CLIENT_ID")
    secret_key = os.getenv("FYERS_SECRET_KEY")

    if client_id == None:
        print("Client ID is missing")
        return
    if secret_key == None:
        print("Secret Key is missing")
        return
    # print(client_id, secret_key)
    session = fyersModel.SessionModel(
        client_id = client_id,
        secret_key = secret_key,
        redirect_uri= "https://127.0.0.1/" ,
        response_type="code",
        state = "sample",
        grant_type = "authorization_code"
    )

    AUTH_CODE = os.getenv("FYERS_AUTH_CODE")
    # AUTH_CODE = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcHBfaWQiOiJDVjI2SExPOUpJIiwidXVpZCI6Ijg4NGQ4Y2RiNTU0NDRkY2VhOWVlOTYyNjBlZTk2MDNlIiwiaXBBZGRyIjoiIiwibm9uY2UiOiIiLCJzY29wZSI6IiIsImRpc3BsYXlfbmFtZSI6IkZBQzYyMzQ0Iiwib21zIjoiSzEiLCJoc21fa2V5IjoiNmU2ZTk3YzdhYTc1MDMyY2QxOTU1NGE0NjI1ZWQ1YWEyZmEyNWE2YTUyOTQ3NmI3MDkyZjI2ZDMiLCJpc0RkcGlFbmFibGVkIjoiTiIsImlzTXRmRW5hYmxlZCI6Ik4iLCJhdWQiOiJbXCJkOjFcIixcImQ6MlwiLFwieDowXCIsXCJ4OjFcIixcIng6MlwiXSIsImV4cCI6MTc2NDk0MTc5OCwiaWF0IjoxNzY0OTExNzk4LCJpc3MiOiJhcGkubG9naW4uZnllcnMuaW4iLCJuYmYiOjE3NjQ5MTE3OTgsInN1YiI6ImF1dGhfY29kZSJ9.qhjINXc4757edZGikNyPlPT9SnU60Y4kF96t2tsAQsY"
    if AUTH_CODE == None:
        print("Auth Code is missing")
        return
    
    session.set_token(AUTH_CODE)
    response = session.generate_token()
    access_token = response.get("access_token")
    # print(access_token)
    if access_token == None:
        print("Couldn't generate access token")
        print("Auth Code:: " ,AUTH_CODE)
        return

    fyers = fyersModel.FyersModel(
        token=access_token,
        is_async=False,
        client_id=os.getenv("FYERS_CLIENT_ID"),
        log_path=""
    )

    all_data = []
    for start, end in date_ranges:
        response = fyers.history({"symbol": symbol, 
                                  "resolution": resolution, 
                                  "date_format": "1", 
                                  "range_from": start, 
                                  "range_to": end})
        print(response)
        try:
            if response["candles"]:
                all_data.append(np.array(response["candles"]))
            else:
                raise Exception(f"Data not available for {start} to {end}")
        except Exception as e:
            print(f"Error accured while extracting data from response: {e}")
    df = pd.DataFrame(np.vstack(all_data), columns=["date_time", "open", "high", "low", "close", "volume"])
    df["date_time"] = pd.to_datetime(df["date_time"], unit="s")
    df["date_time"] = df["date_time"].dt.tz_localize('utc').dt.tz_convert('Asia/Kolkata')
    df["date_time"] = df["date_time"].dt.tz_localize(None)
    df["date_time"] = df["date_time"].dt.floor("min")
    df["volume"] = df["volume"].astype(int)

    return df

def save_to_csv(df:pd.DataFrame, symbol:str):
    df.set_index("date_time")
    path = PROJECT_PATH/"data"/f"{symbol}.csv"
    df.to_csv(path, index=None)
    print(f"Successfully saved to {path}")