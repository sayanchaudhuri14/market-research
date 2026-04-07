# Scripts — Deprecated

These scripts were built for v1 — they depend on the Kite API, a local OHLC cache,
and daily manual token refresh. **All superseded by `v2/daily_signal.ipynb`.**

---

## fetch_ohlc.py
**Purpose:** Fetched and cached daily OHLC for all 50 NIFTY stocks from Kite's historical data API. Stored as `.pkl` files in `data/ohlc_cache/`.  
**Why deprecated:** v2 uses yfinance directly. No cache, no Kite dependency, no token needed. The cache is now stale and not maintained.

## compute_signal.py
**Purpose:** Loaded the Kite cache, computed overnight scores, applied VIX and US filters, printed the buy list.  
**Why deprecated:** VIX filter removed (shown to hurt returns). Logic consolidated into `v2/daily_signal.ipynb` — two cells, no terminal needed.

## run_evening.py
**Purpose:** Ran at 3:15 PM — generated buy list, saved `data/current_positions.json`.  
**Why deprecated:** Terminal script workflow replaced by the notebook. The v2 daily signal notebook is faster and shows more context (scores, quantities, S&P 500 value).

## run_morning.py
**Purpose:** Ran at 9:25 AM — fetched open prices via Kite LTP, computed overnight P&L, updated trade log.  
**Why deprecated:** This required a live Kite session. For now, P&L tracking is manual — check Zerodha Kite Holdings at 9:25 AM, sell all, note the return. A v2 morning script can be added later if needed using yfinance intraday data.
