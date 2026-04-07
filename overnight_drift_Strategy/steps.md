# Overnight Drift Strategy — Implementation Guide for Claude Code

## Context & Purpose

This is a new, standalone trading strategy to be built in a separate folder alongside an existing NIFTY options system. The developer already has:
- Zerodha Kite Connect API credentials (in `.env` as `api_key` and `api_secret`)
- A working Kite authentication flow with cached access tokens
- Familiarity with NIFTY 50 data, yfinance, and pandas

This guide tells you everything you need to know before writing a single line of code.

---

## The Strategy — Full Rationale

### What is the Overnight Drift?

Stock returns decompose into two sessions:
- **Intraday:** Open → Close (3:25 PM)
- **Overnight:** Close → next Open (3:25 PM to 9:15 AM next day)

Across decades of academic research (Lou, Polk & Skouras 2019; NY Fed Staff Report 917 2020; Elm Wealth 2022), nearly all long-run equity index gains accrue overnight, not intraday. The intraday session is flat to negative on average.

The **cross-sectional** version of this anomaly is the exploitable one: stocks that have *persistently* shown positive overnight returns in the recent past tend to continue showing them in the near future. This is a momentum effect, but applied only to the overnight session. It is distinct from and complementary to day-level price momentum.

### Why It Works in India

India's NSE introduced a pre-open call auction in 2010. Post-2010, price discovery for large-cap stocks shifted almost entirely into the opening gap (driven by overnight global cues — US markets, SGX Nifty, etc.) rather than the intraday session. This structurally strengthened the overnight drift for NIFTY 50 constituents specifically.

The overnight return for a stock on any given day is:
```
overnight_return[t] = (open[t] / close[t-1]) - 1
```

A stock's trailing 20-session mean overnight return is its **score**. Stocks with high scores (persistent gappers) are the longs. Stocks with low or negative scores are ignored (no shorting — cash equity only, and shorting individual stocks intraday only in India).

### Trade Logic

- **Universe:** NIFTY 50 constituents (50 large-cap, liquid stocks)
- **Signal:** Rank all 50 stocks by trailing 20-session mean overnight return
- **Entry:** Buy top 10 ranked stocks at 3:20–3:25 PM (near-close, market order)
- **Exit:** Sell all positions at 9:25 AM next morning (after initial gap settles)
- **Hold time:** ~18 hours. No intraday risk.
- **Filters:** Only trade when S&P 500 previous close was non-negative (global tailwind). Skip RBI MPC days, Budget day, election result days, days after major crashes (India VIX > 20).

### Why 9:25 AM Exit (Not 9:15 AM)

The first 10 minutes after open are chaotic — bid-ask spreads are widest, institutional orders are still being placed, and momentum can extend the gap briefly before settling. Selling at 9:25 AM captures the gap while avoiding the opening auction chaos. This mirrors the existing strategy in the companion folder.

### Expected Edge

- Mean overnight return of top-quintile NIFTY 50 stocks: approximately 0.10–0.18% per session (estimate based on academic literature applied to India)
- Annualized (250 sessions): approximately 28–50% on a long-only portfolio, before transaction costs
- Brokerage per round trip (Zerodha): Rs 20 flat per order (equity delivery is free; intraday MIS is Rs 20). Clarification below.
- Net after brokerage (10 stocks × 2 orders × Rs 20 = Rs 400 per day): significant at small capital; negligible above Rs 5L deployed

**Important:** This is a *long-only cash equity* strategy. No options, no F&O, no leverage. Capital is at risk overnight (gap-down risk exists) but position is diversified across 10 stocks.

---

## Folder Structure to Create

```
overnight-drift/
│
├── STEPS.md                        ← this file
├── .env                            ← symlink or copy from parent folder (api_key, api_secret)
│
├── data/
│   ├── nifty50_constituents.csv    ← list of NIFTY 50 symbols with NSE instrument tokens
│   ├── ohlc_cache/                 ← daily OHLC .pkl files per stock (keyed by symbol)
│   └── access_token_cache.json     ← shared with parent folder or duplicated
│
├── notebooks/
│   ├── 01_data_audit.ipynb         ← Phase 1: verify data, compute overnight returns
│   ├── 02_signal_analysis.ipynb    ← Phase 2: signal persistence, autocorrelation
│   ├── 03_backtest.ipynb           ← Phase 3: walk-forward backtest
│   └── 04_live_signal.ipynb        ← Phase 4: daily live signal generation
│
├── scripts/
│   ├── fetch_ohlc.py               ← fetch and cache daily OHLC for all 50 stocks
│   ├── compute_signal.py           ← compute overnight scores, output ranked list
│   ├── run_morning.py              ← run at 9:25 AM — output sell instructions
│   └── run_evening.py              ← run at 3:15 PM — output buy instructions
│
├── config.py                       ← all constants in one place
└── utils.py                        ← shared helpers (Kite auth, data loading, etc.)
```

---

## config.py — All Constants

```python
# Universe
NIFTY50_SYMBOLS = [
    # Full list of NSE symbols — populated from nifty50_constituents.csv
    # Examples: "RELIANCE", "HDFCBANK", "INFY", "ICICIBANK", "TCS", ...
]

# Signal
LOOKBACK_SESSIONS = 20          # trailing sessions for mean overnight return score
TOP_N = 10                      # number of stocks to long

# Execution timing
ENTRY_TIME = "15:20"            # buy near close
EXIT_TIME = "09:25"             # sell after open settles

# Risk / filters
VIX_MAX = 20.0                  # skip days when India VIX > this
US_FILTER = True                # only trade when S&P 500 prev close return >= 0

# Sizing
CAPITAL = 200000                # Rs — adjust to actual capital
EQUAL_WEIGHT = True             # True = equal Rs per stock
WEIGHT_PER_STOCK = CAPITAL / TOP_N   # Rs per position

# Costs
BROKERAGE_PER_ORDER = 20        # Rs (Zerodha flat fee, intraday MIS)
# Note: Equity delivery (CNC) is free on Zerodha. If using MIS for same-day
# intraday-style, Rs 20 per executed order. Confirm order type choice.
STT_SELL_RATE = 0.001           # 0.1% STT on sell side (equity delivery)
# Total transaction cost estimate per round trip per stock:
# Buy: Rs 20 brokerage + exchange fees (~0.003%) + STT on sell side 0.1%
# Approximate: ~0.12% per round trip total

# Kite API
INSTRUMENT_TOKEN_NIFTY = 256265     # NIFTY 50 index
KITE_CACHE_DIR = "data/ohlc_cache"
CONSTITUENTS_FILE = "data/nifty50_constituents.csv"

# Skip rules (update as calendar is known)
SKIP_DATES = [
    # "2025-02-01",  # Budget
    # Add known RBI MPC dates, election result days here
]
```

---

## utils.py — Shared Helpers

Build the following functions:

### 1. `get_kite_session()`
Load `api_key` and `api_secret` from `.env`. Load cached access token from `data/access_token_cache.json`. If token is stale (older than 1 day), raise an error asking the user to re-authenticate manually via the Kite login URL. Do not auto-refresh — Zerodha tokens require manual re-auth each day.

```python
def get_kite_session() -> KiteConnect:
    # Load .env
    # Load token from cache
    # Validate token age (must be from today)
    # Return authenticated KiteConnect object
```

### 2. `get_nifty50_instruments()`
Read `data/nifty50_constituents.csv`. Return a dict mapping `symbol -> instrument_token`. The CSV must have columns: `symbol`, `instrument_token`, `name`. This file must be created once manually or fetched from Kite's instrument dump.

### 3. `fetch_daily_ohlc(kite, instrument_token, symbol, from_date, to_date)`
Call `kite.historical_data(instrument_token, from_date, to_date, "day")`. Returns a DataFrame with columns: `date, open, high, low, close, volume`. Cache result as a `.pkl` file in `data/ohlc_cache/{symbol}.pkl`. On subsequent calls, load from cache and only fetch missing dates (incremental update).

### 4. `load_all_ohlc(symbols)`
Load cached OHLC for all symbols. Return a dict `symbol -> DataFrame`. Align all DataFrames to the same date index (use only trading days where all stocks have data).

### 5. `compute_overnight_returns(ohlc_dict)`
For each symbol, compute: `overnight_return[t] = open[t] / close[t-1] - 1`. Return a wide DataFrame: rows = dates, columns = symbols, values = overnight return.

### 6. `compute_scores(overnight_df, lookback=20)`
Rolling mean of overnight_df over `lookback` sessions. Return wide DataFrame of same shape. The value at row `t` is the mean of the last 20 overnight returns ending at `t`. This is the signal score.

### 7. `rank_stocks(scores_df, date, top_n=10)`
For a given date, return the top `top_n` symbols sorted by score descending. This is the buy list.

---

## Script Details

### `scripts/fetch_ohlc.py`

Purpose: Fetch and cache daily OHLC for all 50 NIFTY stocks from Kite. Should be run once historically to bootstrap the cache, then daily to append.

Steps:
1. Authenticate via `get_kite_session()`
2. Load instrument list from `nifty50_constituents.csv`
3. For each symbol, check what dates are already cached
4. Fetch missing dates from Kite `historical_data()` with `interval="day"`
5. Append to cache `.pkl`
6. Print a summary: symbol, date range fetched, total rows in cache

**Important Kite API note:** Kite's `historical_data()` for equity (not index) requires the **instrument token** (integer), not the symbol string. The constituents CSV must have the correct token for each stock. Fetch the full instrument dump from `kite.instruments("NSE")` once and cross-reference by `tradingsymbol`.

Historical data rate limits: Kite allows ~3 requests/second. Add `time.sleep(0.4)` between calls.

### `scripts/compute_signal.py`

Purpose: Given cached OHLC, compute today's ranked buy list and print it.

Steps:
1. Load all OHLC from cache
2. Compute overnight returns for all stocks across full history
3. Compute rolling 20-session score
4. For today (or latest available date), rank stocks
5. Print top 10 with their score and yesterday's close price
6. Check filters: India VIX level (fetch from Kite), US S&P 500 previous close (fetch from yfinance `^GSPC`)
7. Output: BUY LIST or SKIP (with reason)

Output format:
```
=== OVERNIGHT DRIFT SIGNAL — 2026-04-07 ===
Filter: US positive ✓ | India VIX 14.2 ✓

BUY LIST (enter at 3:20-3:25 PM):
Rank  Symbol       Score    Prev Close   Rs Allocation
1     HDFCBANK     +0.18%   1,712.50     20,000
2     RELIANCE     +0.16%   1,243.00     20,000
...
10    WIPRO        +0.09%   298.00       20,000

Total capital to deploy: Rs 2,00,000
```

### `scripts/run_morning.py`

Purpose: Run at 9:25 AM after open. Fetch today's open prices and compute overnight returns realized. Compare to expected. Print sell instructions.

Steps:
1. Authenticate via `get_kite_session()`
2. Load yesterday's buy list (save it as `data/current_positions.json` from the evening run)
3. Fetch today's open price for each held stock (use `kite.ltp()` or `kite.quote()` at 9:25 AM)
4. Compute realized overnight return per stock
5. Print sell instructions with P&L
6. Update trade log CSV

Output format:
```
=== SELL SIGNAL — 2026-04-07 09:25 AM ===
Symbol     Entry     Exit      Overnight Return   P&L (Rs)
HDFCBANK   1,712.50  1,727.60  +0.88%            +177
RELIANCE   1,243.00  1,249.90  +0.56%            +89
...
TOTAL P&L (Rs): +763
TOTAL RETURN: +0.38%
```

### `scripts/run_evening.py`

Purpose: Run at 3:15 PM. Generate today's buy list. Save to `data/current_positions.json`. Output buy instructions.

This is just `compute_signal.py` wrapped with timing logic and JSON output saving.

---

## Notebooks

### `01_data_audit.ipynb`

Goal: Verify data quality before any signal work.

Cells:
1. Load all cached OHLC. Print date range per stock. Flag any stocks with missing > 5 sessions.
2. Compute overnight returns. Plot histogram — should be roughly normal, centered near 0, with fat tails.
3. Plot mean overnight return per stock (bar chart, all 50). Compare to mean intraday return per stock.
4. Key check: is mean overnight return > mean intraday return for the majority of stocks? This validates the anomaly exists in your dataset. If not, something is wrong with open price data (check for adjusted vs unadjusted prices).
5. Check for corporate action contamination: large overnight returns (>5%) on ex-dividend or split dates will inflate scores. Flag and optionally exclude them.

**Critical note on open prices:** Kite's historical daily OHLC `open` field is the actual first trade price of the session, not the pre-open auction call price. For most NIFTY 50 stocks, these are very close (within 5 pts). This is fine. Do NOT use the pre-open indicative price.

### `02_signal_analysis.ipynb`

Goal: Validate that the score signal has predictive power.

Cells:
1. Compute rolling 20-session scores for all stocks, all dates.
2. **Autocorrelation test:** For each stock, compute the autocorrelation of overnight_return at lag 1, 5, 10, 20. Plot as heatmap. Expect positive autocorrelation at lag 1–5 for most stocks. This is the theoretical basis of the strategy.
3. **Quintile backtest:** Each session, sort stocks into 5 quintiles by score. Compute next-session overnight return for each quintile. Plot quintile means as a bar chart. Expect monotonic increase from Q1 (low score) to Q5 (high score). This is the key validation plot.
4. **Information Coefficient (IC):** Compute Spearman rank correlation between score and next-day overnight return, for every session. Plot rolling 60-session mean IC. Expect positive mean IC (0.03–0.10 is reasonable). IC > 0.05 consistently = strong signal.
5. **Day-of-week effect:** Does the overnight drift differ by weekday? Monday nights may behave differently. Split and compare.

### `03_backtest.ipynb`

Goal: Walk-forward backtest. Train on 2021–2023, test on 2024 strictly.

Methodology:
- For each date in the test period (2024):
  - Compute score using only data up to and including the previous session (no lookahead)
  - Select top 10 stocks
  - Record the overnight return those 10 stocks actually delivered the next morning
  - Deduct transaction costs: 0.12% per round trip per stock
- Aggregate: mean daily return, Sharpe ratio, max drawdown, annual return

Metrics to report:
| Metric | Value |
|---|---|
| Total sessions | N |
| Sessions with signal (filters passed) | N |
| Mean daily overnight return (gross) | X% |
| Mean daily overnight return (net) | X% |
| Annualized return (net) | X% |
| Sharpe ratio | X |
| Max drawdown | X% |
| Win rate (sessions positive) | X% |
| Mean positive session | X% |
| Mean negative session | X% |

Also backtest the **comparison cases:**
- Equally weight all 50 stocks every day (buy-and-hold overnight index)
- Random 10 stocks each day
- Buy bottom 10 by score (should underperform)

The edge is only real if top-10 beats the equal-weight baseline by a meaningful margin.

**Walk-forward discipline:** Do not use any 2024 data to select parameters. The `LOOKBACK_SESSIONS = 20` parameter must be set before looking at test results and not changed after.

### `04_live_signal.ipynb`

Goal: Daily-use notebook. Run each trading day.

Structure:
- **Cell 1:** Authenticate and fetch today's data
- **Cell 2:** Check filters (India VIX, US S&P 500)
- **Cell 3:** Compute signal and display buy list
- **Cell 4 (run at 9:25 AM):** Fetch open prices, compute overnight P&L
- **Cell 5:** Update trade log

This notebook replaces the scripts for daily use if the developer prefers notebooks over terminal.

---

## Data Bootstrapping — Step by Step

### Step 1: Get NIFTY 50 Constituent List with Instrument Tokens

```python
from kiteconnect import KiteConnect
import pandas as pd

kite = KiteConnect(api_key="YOUR_KEY")
kite.set_access_token("YOUR_TOKEN")

# Fetch all NSE instruments
instruments = kite.instruments("NSE")
df = pd.DataFrame(instruments)

# NIFTY 50 symbols as of April 2026 (verify this list — index composition changes)
nifty50 = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS",
    "BHARTIARTL", "SBIN", "KOTAKBANK", "LT", "AXISBANK",
    "ASIANPAINT", "MARUTI", "SUNPHARMA", "TITAN", "NESTLEIND",
    "WIPRO", "ULTRACEMCO", "BAJFINANCE", "POWERGRID", "NTPC",
    "HCLTECH", "JSWSTEEL", "TATASTEEL", "INDUSINDBK", "TECHM",
    "ADANIENT", "ADANIPORTS", "COALINDIA", "BAJAJFINSV", "HINDALCO",
    "GRASIM", "BRITANNIA", "CIPLA", "DRREDDY", "EICHERMOT",
    "APOLLOHOSP", "HEROMOTOCO", "BPCL", "TATACONSUM", "DIVISLAB",
    "BAJAJ-AUTO", "SHRIRAMFIN", "SBILIFE", "HDFCLIFE", "TRENT",
    "BEL", "ONGC", "IOC", "M&M", "HINDUNILVR"
]

# Get tokens
nse_df = df[df["exchange"] == "NSE"][["tradingsymbol", "instrument_token", "name"]]
constituents = nse_df[nse_df["tradingsymbol"].isin(nifty50)]
constituents.to_csv("data/nifty50_constituents.csv", index=False)
```

**Important:** Verify the symbol list against the current NSE NIFTY 50 index composition (check NSE website). The composition changes ~4 times a year. The list above is approximate.

### Step 2: Fetch Historical OHLC

Fetch 5 years of daily OHLC (April 2021 – April 2026) for all 50 stocks. At ~3 requests/second, this takes roughly 20 minutes. Run once. After that, only daily incremental fetches are needed.

Kite `historical_data()` call:
```python
data = kite.historical_data(
    instrument_token=token,
    from_date="2021-04-01",
    to_date="2026-04-06",
    interval="day",
    continuous=False,
    oi=False
)
```

Returns list of dicts with keys: `date, open, high, low, close, volume`. Convert to DataFrame and cache as pickle.

### Step 3: Validate Open Price Quality

Before building signal, spot-check 5–10 stocks. For each stock, manually verify that `open` on 3–4 known dates matches NSE bhavcopy data. This catches any API quirks with adjusted prices or token mismatches.

---

## Transaction Cost Model

| Cost Item | Rate | Direction |
|---|---|---|
| Brokerage (equity intraday MIS) | Rs 20 flat | Per executed order |
| Brokerage (equity delivery CNC) | Rs 0 | Free on Zerodha |
| STT | 0.025% buy + 0.1% sell | On turnover |
| Exchange transaction charges | ~0.00325% | NSE |
| SEBI charges | 0.0001% | |
| GST on brokerage | 18% of brokerage | |
| Stamp duty | 0.015% | On buy side only |

**Recommendation:** Use **CNC (delivery) order type** if holding overnight is the intent. This is free brokerage. The trade is buy at 3:20 PM and sell next morning at 9:25 AM — this is technically an intraday trade on the second day (sold same day as open). Confirm with Zerodha whether this triggers intraday (MIS) STT or delivery STT. If selling on T+1 morning, it is delivery settlement and STT is 0.1% on sell side.

**Approximate total round-trip cost:** ~0.15% per stock.

At 0.15% cost and 10 stocks per day and 250 sessions per year:
- Annual cost drag: 0.15% × 250 = 37.5% of deployed capital
- This is why the signal must generate >0.15% per session per stock on average to be profitable

At the academic estimate of 0.15–0.18% mean overnight return for top-quintile large-cap Indian stocks, the net after costs is tight but positive. **This is why the signal quality validation in Notebooks 01 and 02 is critical before deploying capital.**

---

## Skip Rules

Do not trade on or around:
- RBI MPC announcement days (~6 per year: Feb, Apr, Jun, Aug, Oct, Dec — check exact dates each year)
- Union Budget day (Feb 1)
- General election result days
- Days after a major crash (India VIX > 20 the previous session)
- Days when Indian market is open but US was closed (overnight signal is absent)

Implement as a hard-coded `SKIP_DATES` list in `config.py` updated monthly, plus a runtime VIX check.

---

## Trade Log

Maintain `data/trade_log.csv` with the following columns:

```
date, symbol, entry_price, exit_price, qty, overnight_return_pct,
pnl_rs, transaction_cost_rs, net_pnl_rs, signal_score, rank,
vix_at_entry, us_prev_close_return, session_notes
```

After every 20 trades, compute rolling win rate and mean return. If rolling mean net return drops below -0.05% per session, pause and review. The signal may be breaking down.

---

## Common Failure Modes to Watch For

**1. Survivorship bias in constituent list**
The NIFTY 50 composition changes. If you train on current constituents going back 5 years, you include stocks that were added recently (likely after good performance) and exclude stocks that were removed (likely after bad performance). To be rigorous: use the point-in-time constituent list. For a first version, this is acceptable to skip — just know it inflates backtest returns modestly.

**2. Open price data artifacts**
On ex-dividend dates, the stock opens gap-down equal to the dividend. This looks like a large negative overnight return but is mechanical, not signal. Filter: if the overnight return magnitude exceeds 4% on a date where the stock has a known dividend, exclude that session from the score calculation.

**3. Corporate actions — splits and bonuses**
Stock splits create artificial large overnight moves. Kite provides adjusted OHLC when using `continuous=False` for most cases, but verify.

**4. Illiquidity at 3:20 PM**
NIFTY 50 stocks are highly liquid even at 3:20 PM. This is not a concern. But avoid placing all 10 orders as market orders simultaneously — stagger by 2 minutes or use limit orders at last traded price.

**5. Score concentration**
If the same 8–9 stocks appear in the buy list every day, the portfolio is effectively undiversified. Monitor turnover. If top-10 changes by fewer than 3 stocks per session on average, consider expanding to top-15.

---

## Suggested Build Order

1. `utils.py` — authentication and data loading functions
2. `data/nifty50_constituents.csv` — bootstrap the instrument token list
3. `scripts/fetch_ohlc.py` — fetch and cache 5 years of history
4. `notebooks/01_data_audit.ipynb` — validate data quality
5. `notebooks/02_signal_analysis.ipynb` — validate signal exists
6. `notebooks/03_backtest.ipynb` — walk-forward backtest, confirm edge
7. `config.py` — finalize all constants post-validation
8. `scripts/compute_signal.py` — daily signal generator
9. `scripts/run_evening.py` + `scripts/run_morning.py` — daily workflow
10. `notebooks/04_live_signal.ipynb` — combined daily-use notebook
11. Paper trade for 20–30 sessions before deploying capital

---

## Daily Operational Workflow (Post-Build)

**3:15 PM — Evening run**
```bash
python scripts/run_evening.py
```
Outputs buy list. Buy the listed stocks between 3:20–3:25 PM via Zerodha Kite web or app. Note actual fill prices in trade log.

**9:25 AM — Morning run**
```bash
python scripts/run_morning.py
```
Outputs sell instructions and overnight P&L. Sell all positions via Zerodha Kite web or app.

**Once per week**
```bash
python scripts/fetch_ohlc.py
```
Refresh OHLC cache with latest data.

---

## Notes for Claude Code

- Use Python 3.10+
- Dependencies: `kiteconnect`, `pandas`, `numpy`, `yfinance`, `python-dotenv`, `scipy`, `matplotlib`, `seaborn`, `openpyxl`
- All file paths should be relative to the `overnight-drift/` root directory
- Do not hardcode API keys anywhere — always load from `.env`
- The `.env` file format: `api_key=xxx` and `api_secret=yyy` and `access_token=zzz` (access token changes daily and is set manually)
- All DataFrames should use `pd.Timestamp` for date index, timezone-naive (IST implied)
- Use `pickle` protocol 4 for cache files for compatibility
- Print progress bars using `tqdm` for long fetch loops
- All scripts should be runnable from command line with no arguments (all config from `config.py`)
- Notebooks should be self-contained — import from `utils.py` and `config.py` using relative paths
- When computing overnight returns, always use the formula `open[t] / close[t-1] - 1`, never `(open[t] - close[t-1]) / close[t-1]` — they are equivalent but the former is cleaner
- Align all stock DataFrames to a common trading calendar before computing cross-sectional ranks — missing data on a date for one stock should not corrupt the ranking for others