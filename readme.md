# HedgeOne Quant

A local quant research terminal. It downloads market data from **Fyers**, **Delta Exchange India** and **CoinDCX**
and stores it on your disk. You write strategies in **plain Python** in VS Code, then apply them to a
**TradingView-style chart** where every trade is shaded green or red. One click backtests the strategy on **vectorbt**
(open-source, 1.2+), and **Deep backtest** produces a full report page you can save as a PDF.

```
 ┌───────────────────────────────── browser: http://127.0.0.1:8000 ─────────────────────────────────┐
 │  symbol · interval · dates                                                          ⬇ Data   ⇆   │
 │ ┌──────────────────────────────────────────────────────────────┐ ┌─────────────────────────────┐ │
 │ │ candles + strategy lines                                     │ │ Strategy | Indicators |     │ │
 │ │ ░░ green zone = winning trade   ▓▓ red zone = losing trade   │ │ Results | Trades | Reports  │ │
 │ │ RSI / MACD panes …                                           │ │  params · settings          │ │
 │ │ Equity vs buy & hold                                         │ │  ▶ Apply  Backtest  Deep ↗  │ │
 │ │ Drawdown                                                     │ │                             │ │
 │ └──────────────────────────────────────────────────────────────┘ └─────────────────────────────┘ │
 └──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Quick start (Windows)

```bat
cd HedgeOne-Quant\backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          &:: then put your Fyers keys in .env
python run.py
```

Open **http://127.0.0.1:8000**. The API docs are at http://127.0.0.1:8000/docs.

> You need Python **3.11 or newer** (vectorbt 1.2 requires it). The first backtest after a restart takes a few
> seconds because numba compiles vectorbt's engine; after that it's fast.

**First run:**
1. Click **⬇ Data**, pick a symbol (e.g. `BTCUSD`, which uses Delta Exchange and needs no key), choose `5m`
   and a date range, then click **Start download**.
2. For NSE symbols, open **Fyers login** in the same dialog once a day, log in, and paste the redirect URL.
3. Already have your old HedgeOne CSVs? Use **Import CSV** and give it the file path (the old
   `date_time,open,high,low,close,volume` format works as-is).
4. Pick a strategy on the right and press **Apply**, **Backtest** or **Deep backtest ↗**.

---

## 2. Folder structure

```
HedgeOne-Quant/
├── backend/
│   ├── run.py                  ← start the server (auto-reloads when you edit code)
│   ├── cli.py                  ← same features from the terminal (download, backtest, deep …)
│   ├── requirements.txt
│   ├── .env.example            ← copy to .env (Fyers keys)
│   ├── strategies/             ← ★ YOUR STRATEGIES — every .py here is auto-loaded
│   │   ├── __init__.py         (auto-discovery + hot reload)
│   │   ├── trend.py            10 trend strategies
│   │   ├── mean_reversion.py   7 mean-reversion strategies
│   │   ├── momentum.py         6 momentum strategies
│   │   ├── breakout.py         6 breakout / volatility strategies
│   │   ├── intraday.py         4 intraday strategies (ORB, VWAP, PDH/PDL)
│   │   └── my_strategies.py    template + example with a daily filter + custom indicator
│   └── app/
│       ├── main.py             FastAPI app, serves the frontend
│       ├── export.py           standalone (offline) HTML export of research reports
│       ├── config.py           paths, .env, markets (NSE / CRYPTO), cost presets, backtest defaults
│       ├── api/
│       │   ├── common.py       NaN-safe JSON, error mapping
│       │   ├── data.py         /api/symbols, /download, /candles, /import-csv, /fyers/…
│       │   ├── engine.py       /api/strategies, /indicators, /apply, /backtest, /deep, /reports
│       │   └── research.py     /api/research/optimize, /research/universe, /dev/backtest, research reports + HTML export
│       ├── data/
│       │   ├── sources.py      Fyers · Delta Exchange India · CoinDCX · CSV  (one class each)
│       │   ├── store.py        Parquet store, merge/update, session-aligned resampling, jobs
│       │   └── symbols.json    symbol catalog (edit or add from the UI)
│       └── engine/
│           ├── __init__.py     the toolkit you import in strategies
│           ├── base.py         @strategy, @indicator, Param, Signals, crossover, htf(), …
│           ├── indicators.py   39 indicators (TradingView formulas) — also usable as ta.*
│           ├── backtest.py     vectorbt simulation, costs, fills, stops, metrics
│           ├── analysis.py     deep analysis, insights, report storage
│           ├── replay.py       bar replay: look-ahead check + exact point-in-time mode
│           ├── research.py     parameter optimizer, universe test, developer-mode train/test
│           └── runner.py       run(symbol, interval, …, mode) — used by API and CLI
├── frontend/                   plain HTML / CSS / JS (no build step)
│   ├── index.html              the terminal
│   ├── report.html             the report page (Download PDF)
│   ├── optimize.html · universe.html   research report pages (PDF + offline HTML export)
│   ├── css/style.css · css/report.css
│   ├── js/app.js               terminal controller
│   ├── js/chart.js             chart stack, trade-zone drawing, synced panes, legend
│   ├── js/replay.js            bar replay controller (playback, intrabar, practice trading)
│   ├── js/report.js · js/svg.js  report page + small SVG charts
│   ├── js/optimize.js · js/universe.js · js/research.js   research pages + shared helpers
│   ├── js/api.js · js/ui.js    fetch wrapper, shared formatting
│   └── vendor/lightweight-charts.standalone.js   (TradingView Lightweight Charts v4.1, Apache-2.0)
├── data/                       (git-ignored, created automatically)
│   ├── store/<source>/<SYMBOL>__<interval>.parquet
│   ├── reports/<id>.json
│   ├── reports/optimize/<id>.json · reports/universe/<id>.json
│   └── tokens/fyers_token.json
├── docs/versions/              your old version notes (v1–v4)
└── Arbitrage/                  untouched
```

**Where to put new code:**

| You want to… | Edit |
|---|---|
| add or modify a strategy | `backend/strategies/*.py` (any new file works), then click ⟳ in the UI |
| add an indicator to the chart list | `@indicator` in `app/engine/indicators.py` or in any strategy file |
| add a symbol | UI → Data → Add symbol, or `app/data/symbols.json` |
| add a data source (e.g. Zerodha) | subclass `DataSource` in `app/data/sources.py`, register it in `SOURCES` |
| change fees / slippage / trading calendar | `app/config.py` (`COST_PRESETS`, `MARKETS`) |
| add a metric | `metrics()` in `app/engine/backtest.py` (it appears in the UI automatically) |
| add an analysis / insight | `app/engine/analysis.py` (`breakdowns()`, `insights()`) |
| change the UI | `frontend/js/app.js`, `frontend/css/style.css` |

---

## 3. Writing a strategy (raw Python)

```python
# backend/strategies/my_strategies.py
from app.engine import strategy, Param, Signals, ta, crossover, crossunder

@strategy("My EMA Cross", "My Strategies",
          fast=Param(9, 2, 100, help="fast EMA"),
          slow=Param(21, 3, 300))
def my_ema_cross(df, fast, slow):
    f = ta.ema(df.close, fast)
    s = ta.ema(df.close, slow)
    return Signals(
        entries=crossover(f, s),          # buy when the fast line crosses above
        exits=crossunder(f, s),           # sell on the cross back
        overlays={"EMA fast": f, "EMA slow": s},   # drawn on the chart
    )
```

Save the file and click **⟳** next to the strategy search box. It shows up in the library, the parameter form is
built from your `Param`s, and **Apply** draws the lines, buy/sell markers and green/red trade zones.

**What you get inside a strategy**

| | |
|---|---|
| `df` | pandas DataFrame: `open, high, low, close, volume`, DatetimeIndex in IST, at the timeframe selected in the UI |
| `ta.*` | `sma ema wma hma dema tema rma vwma rsi macd stoch stoch_rsi cci willr roc mom mfi trix awesome ultimate aroon atr adx bbands keltner donchian supertrend psar ichimoku vwap obv ad_line cmf zscore stdev hist_vol pivots_daily` |
| signals | `crossover(a, b)`, `crossunder`, `cross`, `rising(s, n)`, `falling`, `highest(s, n)`, `lowest`, `bars_since(cond)`, `state_to_events(cond)` |
| time | `between_time(df, "09:30", "14:45")`, `first_bar_of_day(df)`, `last_bar_of_day(df)` |
| multi-timeframe | `htf(df, "1d", lambda d: ta.ema(d.close, 20))`: higher-timeframe value with **no look-ahead** |
| other symbols | `load("NIFTY 50", "1d")` (e.g. for a market filter or a pairs trade) |

**`Signals(...)` fields**

| field | meaning |
|---|---|
| `entries`, `exits` | long entry / exit (boolean Series) |
| `short_entries`, `short_exits` | optional short side (long↔short reversal is supported) |
| `overlays={name: series}` | lines on the price chart |
| `panes={"RSI": {"RSI": rsi}}` | separate synced panes under the chart |
| `levels={"RSI": [30, 70]}` | dashed guide lines in a pane |
| `sl=1.5, tp=4, trailing=True` | stop-loss / take-profit in **percent**, simulated intrabar by vectorbt using high/low |

A strategy file that fails to import doesn't crash the app. The UI shows the traceback above the strategy list.

---

## 4. The three buttons

| Button | What happens | Where you see it |
|---|---|---|
| **▶ Apply** | runs the strategy and simulates the trades | strategy lines and panes, Buy/Short markers, exit dots with %, **dim green / red zone across every trade** plus a box from entry price to exit price. Hover a zone to see entry, exit, P&L, MAE/MFE and exit reason. "Raw signals" toggle shows every signal bar vs the actual fills. |
| **Backtest** | Apply + full metrics | **Results** tab (KPIs + 37 metrics), **Equity vs buy & hold** pane, **Drawdown** pane, **Trades** tab (sortable; click a row to zoom to the trade) |
| **Deep backtest ↗** | Backtest + full analysis, saved as a report | a link to `report.html?id=…` (also listed in **Reports**). The page has the price chart with trade zones, equity and drawdown, an insights section ("where it works / fails"), all metrics, a monthly returns heatmap, yearly vs buy & hold, breakdowns by **time of day, hour, weekday, week of month, month, year, holding period, side and exit reason**, return distribution, MAE/MFE scatter, holding time vs result, rolling win rate, cumulative P&L, worst drawdowns, the full trade list and the strategy source. **Download PDF** prints it (A4 landscape, light theme); choose "Save as PDF". |

**Insights** are plain-English findings generated from the trades, for example:
- *Weak hour (entry): 12:00. 6 trades, win rate 33%, P&L −1.45% of capital. Consider filtering out this hour.*
- *Winners turning into losers. 14 of 23 losing trades were up at least 0.48% before closing red. A trailing stop could save these.*
- *Stop-loss hint. 90% of winning trades never went more than 0.88% against you.*
- *Losers held too long*, *Costs eat the edge*, *The short side loses*, *Profit concentration*, *Small sample*, *Too good to be true?*

---

## 4b. Bar Replay ⏪

Replay the market from any point, bar by bar, like TradingView's replay but stricter about the future.

**Start:** click **⏪ Replay** in the chart toolbar, then click the candle to start from (everything to its right is
hidden). You can also pick a date or press 🎲 for a random bar.

| Control | |
|---|---|
| ▶ / ⏸ | play / pause (**Space**) |
| ⏴ ⏵ | step back / forward one bar (**← / →**, **Shift+→** = 10 bars) |
| speed | 0.5 – 100 steps per second |
| **Bar / Intrabar** | *Intrabar* builds each candle from your finer stored data (e.g. a 15m candle grows minute by minute: open → highs/lows → close, volume accumulating). It's available when you've stored a finer interval than the chart's. |
| Pause on trade | stops automatically whenever the strategy opens or closes a trade |
| slider | scrub to any bar |
| ⤺ | pick a new start bar |
| ✕ | exit (**Esc**) |
| **Practice: Buy / Sell / Close** | trade by hand at the current price (**B / S / C**). Your trades are drawn with a blue outline and tracked with P&L (fees from your cost preset). |

Everything works during replay: pick any strategy and press **Apply**, or add, edit and remove indicators. The
replay reloads and keeps your position in time. **Backtest** and **Deep backtest** in replay mode only use data
**up to the replay cursor**, and the Results tab says so.

**How the future stays hidden:**
1. The chart, legend, indicator values, panes, equity curve, markers and the trade list are cut at the cursor, so no
   future value is ever drawn, not even in the crosshair legend.
2. A trade appears only once it would have been known. Fills at a bar's open show when that bar opens, and
   stop-loss / take-profit exits show when the bar closes. A still-open trade is drawn up to the cursor with its
   live P&L.
3. **Look-ahead check.** When replay starts, the backend reruns the strategy and every indicator with the future cut
   off at several points and compares signals, plotted lines and the simulated equity. The badge shows
   **✓ past data only** when it all matches. All 34 built-in strategies and 39 indicators pass.
4. If your own code peeks ahead (`shift(-1)`, normalising by the whole series' mean or max, `df.close.iloc[-1]` …), the
   badge turns **⚠ exact mode** and a message names the series and bar where it happened. In exact mode the strategy
   **goes live at the replay start**: for every new bar it's run only on the bars so far, and its decision for that bar
   is frozen. You see exactly what it would have done live, which is usually much worse than its backtest.

API: `POST /api/replay/prepare` (data + look-ahead check), `POST /api/replay/step` (exact point-in-time mode).

---

## 4c. Research workflow: developer mode → optimize → train vs test → universe 🧪

The recommended loop for building a strategy that holds up on data it has never seen:

1. **🧪 Dev mode** (top bar). Set a **Train** and a **Test** period (or click **70/30** / **80/20** to split the stored data).
   While dev mode is on, the chart, **Apply**, indicators, replay, **Deep (train)** and the optimizer only ever see the
   **train** period. The test period stays hidden (🔒).
2. **⚙ Optimize ↗** (Strategy tab). For every parameter choose **Fixed**, **Range** (from / to / step) or **List**
   (also *Both* for true/false). Pick what to rank by (Sharpe, Calmar, return, profit factor …), a minimum trade count,
   and an optional constraint such as `fast < slow`. The live counter shows how many combinations will run (limit 20,000).
   A new tab opens with the report: best parameters, a heatmap of any two parameters (look for broad green
   plateaus, not single bright cells), one-parameter sensitivity, top-10 equity curves, risk vs return, the full sortable
   table, and notes on over-fitting. **↩ Use in terminal** (or *Use* on any row) loads those values into the strategy form.
3. **Train vs test** (the Backtest button in dev mode). Runs the strategy once over the whole span (so indicators are
   warmed up), then trades the train and test periods separately from fresh capital. The chart reveals the test
   period (orange shading), and Results shows train vs test side by side, the difference, and a verdict
   (*holds up / partly / does not hold up*). The terminal counts how often you looked at the test period — if you keep
   tuning until the test looks good, the test has become training data.
4. **🌐 Universe test ↗** (disabled in dev mode; *Next: universe test* in the train/test results switches dev mode off
   for you). Tick any mix of stocks, indices and crypto. The report has a comparison table, interactive equity and
   drawdown overlays, an **equal-weight portfolio** of the selection, metric bars, risk vs return, yearly returns,
   correlation of daily returns, and a full individual analysis for each security (with a *Deep report ↗* button).
   Tick / untick securities (or use All · Stocks · Indices · Crypto · Profitable · Top 5 …) and every comparison follows.

Both research reports have **⬇ PDF** (print → Save as PDF; the universe PDF can add a page per selected security) and
**⬇ HTML**, which downloads one self-contained file (data, charts and scripts inlined) that works offline, keeps every
checkbox and chart interactive, and can be e-mailed or archived. Past runs are listed in the **Reports** tab.

All research runs use exactly the same simulation as **Backtest** (same costs, fills, stops and settings), so any row of
an optimizer table matches what you get when you backtest those parameters on their own.

---

## 5. How the backtest stays realistic

| Topic | What HedgeOne does |
|---|---|
| **Fills** | Signals are computed on the bar **close** and filled at the **next bar's open** (no look-ahead). You can switch to same-bar-close in Backtest settings. |
| **Costs** | Per-side fees and slippage from a market preset (`config.COST_PRESETS`): NSE intraday / delivery / futures, Delta futures, CoinDCX spot, or zero. You can override any number in the UI. *Presets are approximations; check them against your broker's current charges.* |
| **Annualisation** | Sharpe, Sortino, CAGR and volatility use the **real trading calendar**: NSE = 252 days × session bars (09:15–15:30), crypto = 365 × 24h. The old code assumed 24/7 trading and inflated intraday Sharpe by about 2.4×. |
| **Resampling** | NSE intraday bars are anchored at **09:15** (1h = 09:15, 10:15 … like TradingView). Crypto bars align to UTC like the exchanges. Weekly bars start on Monday. |
| **Intraday square-off** | Optional: flat at 15:15, no new entries after 15:00, never holds overnight. "Last bar of the day" is decided by the clock (bar end ≥ 15:30), never by peeking at the next bar. |
| **Stops** | SL / TP / trailing are simulated by vectorbt using each bar's high and low. |
| **Exit reason** | Every trade is tagged *Signal / Stop loss / Take profit / Trailing stop / Square-off / Reversal / Open*. |
| **MAE / MFE** | Max adverse / favourable excursion for each trade, from the bar highs and lows while the trade was open. |
| **Indicators** | Same formulas as TradingView's Pine built-ins (EMA/RMA seeded with an SMA, Wilder RSI/ATR/ADX, population stdev in Bollinger Bands), so values match the TradingView chart. |

---

## 6. Data sources

| Source | Markets | Auth | Intervals | Notes |
|---|---|---|---|---|
| **Fyers** (API v3) | NSE stocks, indices, F&O | `FYERS_CLIENT_ID`, `FYERS_SECRET_KEY` in `.env` + daily login | 1m … 4h, 1d | 100-day chunks intraday, 366 days daily; token saved in `data/tokens/` |
| **Delta Exchange India** | crypto futures (BTCUSD, ETHUSD …) | none | 1m … 1w | `api.india.delta.exchange/v2/history/candles`, 2,000 candles/request |
| **CoinDCX** | crypto spot (`B-BTC_USDT`, `I-BTC_INR` …) | none | 1m … 1M | `public.coindcx.com/market_data/candles`, 1,000 candles/request |
| **CSV** | anything | none | any | `date_time, open, high, low, close, volume` (DD/MM/YYYY or ISO or epoch) |

- All timestamps are stored as **naive IST** (`HEDGEONE_TZ`), so the chart shows Indian wall-clock time.
- Download the **finest** interval you need once (e.g. `1m` or `5m`). The app builds every higher timeframe from it.
- Downloading again **merges** into the stored file. **Data → Stored → Update** fetches only what's new.
- Downloads run in the background, and the dialog shows live progress.

---

## 7. Built-in library

**34 strategies**

| Category | Strategies |
|---|---|
| **Trend** | EMA Crossover, SMA Crossover (Golden Cross), Triple EMA Alignment, MACD Crossover, SuperTrend, Parabolic SAR, ADX / DMI Trend, Ichimoku Cloud Breakout, Hull MA Turn, Aroon Crossover |
| **Mean Reversion** | RSI Mean Reversion, Bollinger Mean Reversion, Z-Score Reversion, Stochastic Reversal, Williams %R Reversal, CCI Reversal, Connors RSI-2 |
| **Momentum** | RSI Momentum (50 cross), Rate of Change, TRIX Signal, Trend Pullback (EMA + RSI), MACD Zero-Line Cross, Awesome Oscillator Zero Cross |
| **Breakout** | Donchian Breakout (Turtle), Bollinger Squeeze Breakout, Keltner Channel Breakout, ATR Volatility Breakout, Chandelier Exit Trend, Breakout with ATR Stops |
| **Intraday** | Opening Range Breakout, VWAP Cross, VWAP + EMA Trend, Previous Day High/Low Breakout |
| **My Strategies** | My MA Crossover + Daily Filter (template) |

Most of these have an `allow_short` switch. All of them use **event-based** signals (crosses), not "every bar
the condition is true", and none use future data. Donchian and price-channel breakouts compare against the
*previous* bars' high and low.

**39 indicators**

| Category | Indicators |
|---|---|
| **Moving Averages** | SMA, EMA, WMA, HMA (Hull), DEMA, TEMA, SMMA (RMA), VWMA, VWAP (session) |
| **Volatility** | Bollinger Bands, Keltner Channels, Donchian Channels, ATR, Historical Volatility |
| **Trend** | SuperTrend, Parabolic SAR, Ichimoku Cloud, Pivot Points (daily), Aroon, ADX / DMI |
| **Momentum** | RSI, MACD, Stochastic, Stochastic RSI, CCI, Williams %R, Rate of Change, Momentum, TRIX, Awesome Oscillator, Ultimate Oscillator |
| **Statistics** | Z-Score, Standard Deviation |
| **Volume** | Volume, OBV, Accumulation/Distribution, Chaikin Money Flow, Money Flow Index |

---

## 8. Terminal UI tips

- **Symbol search**: click the symbol name. A green dot means data is stored, and the intervals are listed next to it.
- **Interval / dates**: `1M 3M 1Y All` quick ranges. Changing them re-runs the last action automatically.
- **⇆**: docks the panel on the **right** or the **bottom**. Drag the splitter to resize, and drag a pane's bottom edge to resize panes.
- **Indicators tab**: click to add. Edit parameters and colour inline. Panes can be closed with ×.
- **Trades tab**: filter winners/losers, sort by any column, click a row to zoom to that trade.
- Everything you pick (symbol, interval, strategy parameters, settings, indicators, dock side) is remembered in your browser.

---

## 9. CLI

```bash
cd backend
python cli.py symbols
python cli.py download "RELIANCE INDUSTRIES LTD" 5m 2024-01-01
python cli.py update   "RELIANCE INDUSTRIES LTD" 5m
python cli.py import   "TATA CONSULTANCY SERVICES" 1m D:/old/TCS.csv
python cli.py stored
python cli.py strategies
python cli.py backtest "BTCUSD" 1h "SuperTrend" --params factor=2.5 allow_short=true
python cli.py deep     "RELIANCE INDUSTRIES LTD" 15m "Opening Range Breakout" --settings square_off=true
python cli.py fyers-login
```

From a notebook:

```python
import sys; sys.path.insert(0, "backend")
import strategies; strategies.load_all()
from app.engine.runner import run
res = run("BTCUSD", "1h", "2025-01-01", None, "EMA Crossover", {"fast": 12, "slow": 26}, mode="backtest")
```

---

## 10. API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | strategy / indicator counts, strategy load errors |
| GET / POST | `/api/symbols` | catalog (+ stored intervals) / add a symbol |
| GET | `/api/sources` | sources, supported intervals, login status |
| POST | `/api/download` → GET `/api/jobs/{id}` | background download + progress |
| POST | `/api/update?symbol=&interval=` | fetch only new candles |
| POST | `/api/import-csv` | import a CSV from a path |
| GET | `/api/inventory` | everything stored on disk |
| GET | `/api/candles?symbol=&interval=&start=&end=` | OHLCV |
| GET / POST | `/api/fyers/login-url`, `/api/fyers/token` | Fyers login |
| GET | `/api/strategies`, `/api/indicators` | library (+ params, source code) |
| POST | `/api/strategies/reload` | re-import `backend/strategies/*.py` |
| POST | `/api/indicator` | compute one indicator |
| POST | `/api/apply`, `/api/backtest`, `/api/deep` | `{symbol, interval, start, end, strategy, params, settings}` |
| GET / DELETE | `/api/reports`, `/api/reports/{id}` | saved reports |

---

## 11. What changed from the previous version

- **Rebuilt backend**: clean `data / engine / api` layers, one registry with a `@strategy` decorator (no more
  duplicated `strategies.json`), strategies live in their own folder and hot-reload.
- **Fixed bugs that affected results**: Sharpe annualisation (assumed 24/7 trading), same-bar fills,
  price-channel / Donchian breakouts that could never trigger, a crash on zero-trade backtests, a crash when data
  wasn't pre-loaded into the cache, NaN breaking JSON responses, hourly NSE bars anchored at 09:00 instead of 09:15,
  deprecated pandas frequency aliases. Mislabelled strategies (ADX "trend" with no direction, "RSI Divergence",
  "EMA Pullback") were replaced with correct ones.
- **Indicators no longer depend on vectorbt classes that don't exist in open-source vectorbt** (ADX, SUPERTREND,
  VWAP … crashed before). All 39 are implemented in pandas/numpy and match TradingView formulas.
- **New**: three data sources with a Parquet store, cost presets, intraday square-off, stops, long/short,
  exit reasons, MAE/MFE, a deep analysis with insights, a report page with PDF export, a TradingView-style terminal, and a CLI.
- Time-slice analysis (hour / weekday / week / month / year) from the old version is kept and extended.

**Roadmap items from `docs/versions/v4.txt` that are now done:** strategy categories, cumulative P&L graph,
trade P&L view, backtest report + export, 30+ strategies and indicators with parameters, saving tested strategies
with results (reports).
Replay mode (bar replay + practice trading) is done too.
**Still open / next ideas:** parameter optimisation and walk-forward (vectorbt can broadcast a parameter grid),
running one strategy across many symbols, combining strategies (AND/OR/vote), portfolio-level backtests, replay
mode, Telegram/email reports, options strategies.

---

## Disclaimer

HedgeOne-Quant is a research and software project. Backtests, indicators and signals don't guarantee future
results and aren't investment advice. Check data quality, costs and assumptions yourself before trading real capital.
