# backtest-merged — Unified Backtest Notebooks

## Purpose
Consolidated backtest notebooks combining the v2 signal approach and v4.3 option simulation engine into single, self-contained notebooks. Used as a reference implementation and for cross-validating results between v2/v4.3 and the sim_cache-based v6+ series.

## Key Files
- `backtest_v2.ipynb` — v2 signal analysis reproduced with v4.3 option simulation engine
- `backtest_v43.ipynb` — **the canonical v4.3 backtest** with real option data, full compounding engine, and NSE helpers

## backtest_v43.ipynb — Canonical Reference
This notebook contains the authoritative implementation of:
- `simulate_trade_real()` — full option simulation (9:25 AM entry, ATM-50 PUT, SL/TP/time exit)
- `round_trip_charges()` — brokerage, STT, stamp duty, SEBI, GST
- `load_opt()` / `_load_old()` / `_load_new()` — option data loader (pre/post Nov 2024 cutoff)
- `next_expiry()`, `is_skip_day()` — NSE expiry calendar, holiday/event filters
- `spot_map` — NIFTY 9:25 AM spot price from minute_256265_*.pkl files
- `sgx_ret_v43` — ^N225 open return for SGX UP/DOWN signal (yfinance)

v6-v11 all reuse this simulation logic (or the sim_cache derived from it).

## Status
Reference only. The actual backtesting has moved to the versioned notebooks (v6-v11) which load from sim_cache rather than re-running the full simulation each time.
