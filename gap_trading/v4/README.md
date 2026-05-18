# v4 — Sub-version Backtests (v4.1 through v4.7)

## Purpose
Systematic comparison of different combo selections and signal configurations, all tested on real 2024 option data. v4.3 is the version that was deployed to production (cron/v4.3).

## Strategy (all sub-versions)
- Buy ATM-50 PUT at 9:25 AM on gap-up days matching bearish combo signals
- SL = -15% of entry premium
- TP = +40% of entry premium
- Hard exit at 11:15 AM
- Strike: ATM - 50 (1-OTM PUT), LOT_SIZE = 75
- Lot sizing: capital-compounding, BASE=5, MAX=25, DTE0_MAX=10
- Starting capital: Rs 2,00,000

## Sub-version Summary
| Version | Signal source | Key change |
|---|---|---|
| v4.1 | v2 top-10 bearish combos | Baseline — same as v2 deployed logic |
| v4.2 | v2 top-10 bearish combos | Minor config tweak (entry timing) |
| v4.3 | v2 top-10 bearish combos | **Deployed to production** — uses ^N225 open for SGX signal |
| v4.4 | Modified combo set | Alternative combo ranking |
| v4.5 | v4.5-specific reliable signals | Rebuilt signal file (v45_reliable_signals.csv) |
| v4.6 | Extended combo set | Larger combo pool |
| v4.7 | Alternative signals | Different signal definitions |

## v4.3 — Production Version
v4.3 is the live cron system. It uses:
- `v2_reliable_signals.csv` top-10 DOWN combos
- ^N225 open price fetched via yfinance for SGX UP/DOWN signal (live-consistent)
- Deployed on EC2 via cron (see `cron/v4.3/`)

Backtest reference (from v9/backtest_v9.ipynb on real sim_cache):
- Full period 2024-2026 (IN-SAMPLE): 120 trades, 31.7% win, +147.7% ROI, 34.2% MaxDD
- Jul 2025-Mar 2026 slice (combos still in-sample): 34 trades, 26.5% win, -57.9% ROI, 77.3% MaxDD

## Key Files
- `v4.X/backtest.ipynb` — real options backtest for each sub-version
- `v4.X/backtest_BS.ipynb` — Black-Scholes simulation version
- `v4.X/results/` — JSON trade logs and pkl trade caches
- `_engine.py`, `_bs_engine.py` — shared backtest engines
- `compare_versions.ipynb` — side-by-side comparison of all sub-versions

## Status
v4.3 is live in production (cron/v4.3). Other sub-versions archived. Superseded analytically by v6-v11 which use sim_cache for faster iteration.
