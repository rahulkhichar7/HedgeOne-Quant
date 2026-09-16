# HedgeOne-Quant

> A quantitative research and algorithmic trading platform for market data analysis, technical indicators, strategy development, and historical backtesting.

---

## Overview

**HedgeOne-Quant** is a quantitative trading research platform designed to provide a structured environment for exploring financial market data, developing systematic trading strategies, computing technical indicators, and evaluating strategy performance through historical backtesting.

The project is built around a modular architecture that separates:

- Market data acquisition and processing
- Data caching and management
- Technical indicators
- Trading strategies
- Backtesting
- Plotting and visualization
- API services
- Research and experimentation

The core backend is implemented using **FastAPI**, while quantitative analysis and strategy research make extensive use of **Pandas, NumPy, VectorBT, Matplotlib, and Plotly**.

The API exposes dedicated routes for data, backtesting, user functionality, indicators, strategies, and cached datasets. The application entry point registers the major API routers under `/api/v1/data` and `/api/v1/backtest`. :contentReference[oaicite:1]{index=1}

---

## Key Objectives

HedgeOne-Quant aims to provide a foundation for systematic quantitative research with an emphasis on:

- 📊 Historical market-data analysis
- 📈 Technical indicator research
- 🧠 Rule-based trading strategy development
- 🔬 Strategy experimentation
- ⚙️ Automated backtesting
- 📉 Performance evaluation
- 🗃️ Efficient historical-data handling
- 🚀 API-driven quantitative workflows
- 🧪 Research through interactive notebooks

---

## Features

### 1. Market Data Management

The platform works with historical **OHLCV (Open, High, Low, Close, Volume)** market data.

A typical data record contains:

```text
date_time
open
high
low
close
volume
````

The backend defines structured data-transfer models for OHLCV data using Pydantic. 

The system supports configurable:

* Tickers
* Start dates
* End dates
* Candle intervals
* Historical datasets
* Data resampling

Supported research intervals include examples such as:

```text
5m
15m
1h
1d
```

---

### 2. Multiple Asset Classes

The project contains mappings for a range of financial instruments, including:

* Indian equities
* Indian market indices
* Cryptocurrency pairs

Examples include:

```text
NIFTY 50
NIFTY BANK
NIFTY IT
NIFTY MIDCAP 100
NIFTY FMCG

TATA CONSULTANCY SERVICES
RELIANCE INDUSTRIES LTD
INFOSYS LIMITED
HINDUSTAN UNILEVER LTD

BTCUSD
ETHUSD
SOLUSD
XRPUSD
LTCUSD
```

This allows the same research infrastructure to be applied across different instruments and markets. 

---

## 3. Technical Indicators

HedgeOne-Quant provides a registry-based architecture for technical indicators.

Indicators can be:

1. Registered in the indicator registry
2. Selected through the API
3. Configured using parameters
4. Executed against historical OHLCV data
5. Returned as structured indicator values

The API provides indicator discovery and metadata endpoints as well as an endpoint for executing an indicator on historical data. 

Example parameter format:

```json
{
  "window": 14
}
```

This architecture makes it possible to extend the platform with additional indicators without redesigning the entire API.

---

## 4. Trading Strategies

Trading strategies follow a similar registry-based architecture.

Strategies can receive:

* Historical OHLCV data
* Configurable parameters
* Selected time intervals
* Selected instruments
* Historical date ranges

A strategy returns information such as:

```text
entries
exits
indicators
```

The backend exposes strategy discovery, strategy metadata, and strategy execution functionality. 

This provides a flexible foundation for implementing strategies such as:

* Moving-average strategies
* Momentum strategies
* Mean-reversion strategies
* Indicator-based strategies
* Multi-condition strategies
* Custom quantitative research strategies

---

## 5. Historical Backtesting

The project integrates **VectorBT** for quantitative strategy research and backtesting.

A research example uses:

```python
import vectorbt as vbt
```

and constructs a portfolio from generated entry and exit signals.

Example:

```python
portfolio = vbt.Portfolio.from_signals(
    close=price,
    entries=entries,
    exits=exits,
    init_cash=100000,
    fees=0.0,
    slippage=0.0,
    freq=resolution
)
```

The research workflow evaluates strategy characteristics such as:

* Total return
* Win rate
* Sharpe ratio
* Entry signals
* Exit signals
* Parameter combinations
* Stop-loss configurations
* Take-profit configurations
* Trailing-stop configurations
* ATR-based configurations

The included research notebook demonstrates experimentation with historical TCS data and strategy parameter sweeps.

---

## 6. Data Resampling

Historical datasets can be loaded and resampled according to the requested research resolution.

For example:

```text
5m
15m
1h
1d
```

A typical workflow is:

```text
Raw Historical Data
        │
        ▼
Data Loading
        │
        ▼
Date Filtering
        │
        ▼
Resampling
        │
        ▼
OHLCV DataFrame
        │
        ▼
Indicator / Strategy
        │
        ▼
Backtest
```

The data service provides functions for loading and resampling historical datasets before they are passed to indicators or strategies. 

---

## 7. Data Caching

HedgeOne-Quant includes a caching layer for loaded market datasets.

The API provides operations to:

* Load data into cache
* Retrieve cached keys
* Delete cached datasets

Example cache keys follow the pattern:

```text
data:TATA CONSULTANCY SERVICES
data:RELIANCE INDUSTRIES LTD
```

The cache API is designed to reduce repeated data-loading operations during research and strategy execution. 

---

## 8. Fyers Integration

The project includes utilities for obtaining historical market data through **Fyers**.

The data utilities expose functionality related to:

```python
get_fyers_authcode()
get_historical_data_by_fyers()
save_to_csv()
```

This provides a path for acquiring and maintaining historical market datasets for quantitative research.

---

## Architecture

HedgeOne-Quant follows a modular backend architecture:

```text
HedgeOne-Quant
│
├── backend/
│   │
│   ├── app/
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── data
│   │   │       ├── backtest
│   │   │       └── user
│   │   │
│   │   ├── core/
│   │   │   ├── Strategies
│   │   │   └── Indicators
│   │   │
│   │   ├── services/
│   │   │   ├── data_services
│   │   │   ├── cache_service
│   │   │   ├── plotting_services
│   │   │   └── backtest_services
│   │   │
│   │   ├── schemas/
│   │   │   └── data_models
│   │   │
│   │   ├── utils/
│   │   │   └── data utilities
│   │   │
│   │   └── assets/
│   │
│   ├── main.py
│   ├── requirements.txt
│   └── start.sh
│
├── St_dev1.ipynb
│
└── README.md
```

The backend entry point creates a FastAPI application named:

```text
HedgeOne Quant API
```

and registers separate routers for data, backtesting, and user-related functionality. 

---

# Technology Stack

## Backend

| Technology        | Purpose                         |
| ----------------- | ------------------------------- |
| Python            | Core programming language       |
| FastAPI           | REST API framework              |
| Uvicorn           | ASGI application server         |
| Pydantic          | Data validation and API schemas |
| Pydantic Settings | Application configuration       |
| Pandas            | Data manipulation and analysis  |
| NumPy             | Numerical computation           |

## Quantitative Research

| Technology       | Purpose                           |
| ---------------- | --------------------------------- |
| VectorBT         | Strategy research and backtesting |
| Matplotlib       | Research visualization            |
| Plotly           | Interactive visualization         |
| Jupyter Notebook | Quantitative experimentation      |


---

# Installation

## 1. Clone the Repository

```bash
git clone <repository-url>
cd HedgeOne-Quant
```

---

## 2. Create a Virtual Environment

### Windows

```bash
python -m venv .venv
.venv\Scripts\activate
```

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

## 3. Install Dependencies

Navigate to the backend directory if required:

```bash
cd backend
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

The backend dependency set includes FastAPI, Uvicorn, VectorBT, Pandas, Pydantic, Plotly, Requests, Matplotlib, Fyers API, dotenv, and related packages. 

---

# Configuration

If API credentials are required, create a `.env` file in the appropriate project location.

Example:

```env
FYERS_CLIENT_ID=your_client_id
FYERS_SECRET_KEY=your_secret_key
FYERS_REDIRECT_URI=your_redirect_uri
FYERS_ACCESS_TOKEN=your_access_token
```

> Do not commit API keys, access tokens, passwords, or other secrets to Git.

The repository's ignore configuration already excludes environment files such as `.env` and virtual-environment directories.

---

# Running the Backend

From the project root, start the FastAPI application with Uvicorn.

```bash
uvicorn backend.main:app --reload
```

The API will normally become available at:

```text
http://127.0.0.1:8000
```

FastAPI's interactive documentation can then be accessed through:

```text
http://127.0.0.1:8000/docs
```

The application is defined as:

```python
app = FastAPI(title="HedgeOne Quant API")
```

and exposes versioned data and backtesting routes. 

---

# API Structure

The project organizes its API around versioned functional modules.

## Data API

```text
/api/v1/data
```

Used for market-data related operations.

Example functionality includes retrieving OHLCV data using:

```text
ticker
start date
end date
interval
```

The underlying data endpoint accepts parameters such as ticker name, date range, and candle interval. 

---

## Backtest API

```text
/api/v1/backtest
```

Provides functionality related to historical strategy evaluation and backtesting.

---

## Indicator API

Indicator-related operations include:

```text
/asset/indicators
/asset/indicators/metadata
/core/indicators/run
```

These endpoints allow available indicators to be discovered, metadata to be retrieved, and selected indicators to be executed against historical market data. 

---

## Strategy API

Strategy-related operations include:

```text
/asset/strategies
/asset/strategies/metadata
/core/strategies/run
```

A strategy can be selected by name and supplied with parameters before being executed against historical OHLCV data. 

---

## Cache API

Cache operations include:

```text
POST /cache/load
GET  /cache/keys
POST /cache/delete
```

These endpoints manage datasets loaded into the application's cache layer. 

---

# Quantitative Research Workflow

A typical HedgeOne-Quant research workflow is:

```text
1. Select Asset
       │
       ▼
2. Load Historical Data
       │
       ▼
3. Select Date Range
       │
       ▼
4. Select Timeframe
       │
       ▼
5. Resample / Prepare Data
       │
       ▼
6. Calculate Indicators
       │
       ▼
7. Generate Strategy Signals
       │
       ▼
8. Run Backtest
       │
       ▼
9. Analyze Performance
       │
       ▼
10. Iterate / Optimize
```

This architecture separates data preparation from indicator computation, strategy execution, and backtesting, allowing each component to be independently developed and tested.

---

# Example: Researching a Strategy

A strategy can be evaluated using historical price data:

```python
import vectorbt as vbt

ema_fast = vbt.MA.run(price, 9)
ema_slow = vbt.MA.run(price, 26)

entries = ema_fast.ma_crossed_above(ema_slow)
exits = ema_fast.ma_crossed_below(ema_slow)

portfolio = vbt.Portfolio.from_signals(
    close=price,
    entries=entries,
    exits=exits,
    init_cash=100000,
    fees=0.0,
    slippage=0.0,
    freq=resolution
)

print("Total Return:", portfolio.total_return())
print("Win Rate:", portfolio.stats()["Win Rate [%]"])
print("Sharpe Ratio:", portfolio.sharpe_ratio())
```

This type of workflow is already demonstrated in the project's quantitative research notebook.

---

# Research Notebook

The repository includes:

```text
St_dev1.ipynb
```

The notebook is used as a research and development environment for:

* Loading historical data
* Testing data services
* Testing cache services
* Exploring available tickers
* Testing indicators
* Testing strategies
* Running VectorBT portfolios
* Evaluating performance
* Performing parameter experiments

For example, the research environment loads historical TCS data and stores it in the caching layer before performing further analysis. 

---

# Extending HedgeOne-Quant

The architecture is intended to make quantitative components extensible.

## Adding a New Indicator

A new indicator should generally:

1. Implement the indicator calculation.
2. Register the indicator.
3. Define its metadata/parameters.
4. Expose it through the existing indicator API.

The registry-based design allows the API to dynamically locate the requested indicator function. 

---

## Adding a New Strategy

A new strategy should generally:

1. Implement the strategy logic.
2. Generate entry signals.
3. Generate exit signals.
4. Return required indicators.
5. Register the strategy.
6. Define strategy metadata and parameters.

The API then resolves the selected strategy from the strategy registry and executes it on the requested historical dataset. 

---

# Data Model

The core market-data model is based on OHLCV candles:

```text
┌─────────────────────────────┐
│         OHLCV Candle        │
├─────────────────────────────┤
│ date_time                   │
│ open                        │
│ high                        │
│ low                         │
│ close                       │
│ volume                      │
└─────────────────────────────┘
```

This standardized structure allows indicators and strategies to operate independently of the original data source.
---

# Disclaimer

HedgeOne-Quant is a **quantitative research and software-development project**.

Backtesting results, technical indicators, strategy signals, and research outputs are not guarantees of future market performance.

Nothing in this repository should be interpreted as financial, investment, or trading advice.

Users are responsible for independently evaluating strategies, assumptions, data quality, execution costs, and risks before using any strategy with real capital.

---