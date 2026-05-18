# v3 — New Signal Exploration

## Purpose
Experimental version exploring additional signals beyond the original 13 used in v2. Investigated whether composite/derived signals or alternative data sources could improve the combo win rates.

## Method
- Extended `v2_aligned_dataset.csv` with additional derived signals in `v3_aligned_dataset.csv`
- Added new signal candidates to `v3_new_signals.csv`
- Ran comparison scripts (`v3_backtest_compare.py`, `metrics_summary.py`) against v2 baselines

## Key Files
- `v3_aligned_dataset.csv` — extended dataset with new signals
- `v3_new_signals.csv` — candidate new signals and their stats
- `v3_analysis.py` — signal analysis script
- `v3_backtest_compare.py` — comparison against v2
- `metrics_summary.py` — summary metrics

## Outcome
The new signals did not materially improve over v2's top combos. The core set of 13 binary signals from v2 proved robust enough. v3 was not deployed.

## Status
Dead end. Archived for reference. v2 signals remain canonical.
