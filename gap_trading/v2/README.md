# v2 — Signal Combination Analysis + First Backtest

## Purpose
Systematic search for binary signal combinations (pairs + triplets) that predict NIFTY PUT option TP hits. This produced the **top-10 bearish combos** that became the basis of all downstream versions (v4.3 cron, v9 backtest).

## Method
- Built `v2_aligned_dataset.csv` with 13 binary signals per day (2023-2026):
  - Gap Up / Gap Up Strong / Gap Down
  - Prev India UP / DOWN
  - US UP / DOWN
  - SGX UP / DOWN
  - DAX UP
  - VIX Rising / VIX Falling / VIX Spike
- Enumerated all pairs (78) and triplets (286) → 374 combinations
- Computed win rate edge vs base for each combo
- Selected top-10 bullish and top-10 bearish combos by edge_pp
- Backtested using simulated option prices (Black-Scholes first, then real 2024 option data)
- Grid searched SL/TP parameters

## Key Files
- `v2_aligned_dataset.csv` — master daily dataset (india_date column), used by all downstream versions
- `v2_reliable_signals.csv` — **top-10 bearish and bullish combos with N, edge_pp, p-value**; loaded by cron/v4.3 and v9
- `v2_pairs_analysis.csv`, `v2_triplets_analysis.csv` — full combo tables
- `v2_pairs_significance.csv`, `v2_triplets_significance.csv` — p-value tables
- `backtesting_true_data/backtest_real_data.ipynb` — backtest on real 2024 option prices
- `backtest_outputs/` — xlsx reports for 1-OTM, 2-OTM, 5-OTM strikes

## Top-10 Bearish Combos (from v2_reliable_signals.csv)
| Rank | Signal | N | Edge_pp |
|---|---|---|---|
| 1 | Gap Up + Prev India DOWN + US UP + SGX UP | 67 | +20.0pp |
| 2 | Gap Up + Prev India DOWN + SGX UP + DAX UP | 54 | +19.4pp |
| 3 | Gap Up + Prev India DOWN + SGX UP + VIX Falling | 44 | +18.1pp |
| 4 | Gap Up + Prev India DOWN + SGX UP | 73 | +17.9pp |
| 5 | Gap Up + Prev India DOWN + US UP + DAX UP | 58 | +16.0pp |
| 6 | Gap Up + SGX UP + DAX UP + VIX Falling | 100 | +15.3pp |
| 7 | Gap Up + DAX UP + VIX Falling | 111 | +13.8pp |
| 8 | Gap Up + SGX UP + VIX Falling | 126 | +13.6pp |
| 9 | Gap Up + SGX UP + DAX UP | 154 | +13.5pp |
| 10 | Gap Up + US UP + SGX UP + DAX UP | 138 | +13.4pp |

## Critical Caveat
**In-sample selection bias:** the combos were selected on the full 2023-2026 dataset and then backtested on the same data. ~374 tests at p<0.05 → ~19 false positives by chance. The true OOS edge is unknown from v2 alone. This was addressed in v5 (Bonferroni + train/test split) and v9 (apple-to-apple OOS comparison).

## Status
Superseded as a standalone system. Key outputs (`v2_aligned_dataset.csv`, `v2_reliable_signals.csv`) remain active dependencies for cron/v4.3, v9, and v11.
