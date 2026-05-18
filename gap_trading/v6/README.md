# v6 — Real Option Simulation Cache (sim_cache)

## Purpose
Built the **sim_cache.csv** — a pre-computed table of all 402 tradeable days from Jan 2024 to Mar 2026 with actual option trade outcomes. This cache eliminates the need to re-run the full option simulation for every backtest iteration. It is the shared data foundation for v7, v8, v9, v10, and v11.

## Strategy Parameters
- Strike: ATM - 50 (1-OTM PUT), bought at 9:25 AM open
- SL = -15% of entry premium
- TP = +40% of entry premium
- Hard exit at 11:15 AM if neither SL nor TP hit
- Breakeven win rate: 27.3% (= 0.15 / (0.15 + 0.40))
- Lot size: 75 (NIFTY)

## sim_cache.csv Structure
402 rows × 20 columns:

| Column | Description |
|---|---|
| date | Trading date |
| win | True if TP hit, False if SL/time exit |
| exit_reason | Target Hit / Stop Loss / 11:15 exit |
| entry_prem | PUT premium at 9:25 AM (Rs) |
| exit_prem | PUT premium at exit (Rs) |
| dte | Days to expiry at entry |
| Gap Up, Gap Up Strong, ... | 13 binary signals (same as v2) |

## Base Win Rate (2024-2026)
- All 402 days: **24.9%** win rate
- Quarterly range: 14.3% – 34.4%
- Significant regime dependence — Q4 2024 was 14.3%, Q1 2025 was 32.6%

## Key Files
- `sim_cache.csv` — **the main cache** (402 rows, 2024-01-02 to 2026-03-24)
- `backtest_v6.ipynb` — notebook that built the cache and ran initial diagnostics

## Downstream Dependencies
sim_cache.csv is loaded by:
- `v7/backtest_v7.ipynb` — L1 logistic regression
- `v8/backtest_v8.ipynb` — walk-forward L1/RF
- `v9/backtest_v9.ipynb` — v4.3 combo filter + gate analysis
- `v10/backtest_v10.ipynb` — gate analysis (Path B: uses v6 cache)

## Status
Active. sim_cache.csv is the canonical data source for all downstream analysis. Do not modify it without re-running all dependent notebooks.
