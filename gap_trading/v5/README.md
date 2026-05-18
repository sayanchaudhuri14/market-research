# v5 — Walk-Forward Signal Backtest with Bonferroni Correction

## Purpose
Addressed the two critical flaws in v2/v4.3:
1. **In-sample selection bias** — combos selected on the same data they were evaluated on
2. **Multiple testing** — 374 combos at p<0.05 yields ~19 false positives by chance

## Method
- **Target = actual PUT option TP hit** (not NIFTY direction) — directly tied to P&L
- **Clean train/test split**: combos selected ONLY on 2024 data, evaluated OOS on 2025+2026
- **Bonferroni correction**: threshold = 0.05 / 377 = 0.000133 across all 377 combos
- Used ^N225 open for SGX signal (consistent with v4.3 cron)
- Sim source: real options data (same as v6 sim_cache)

## Key Files
- `backtest_v5.ipynb` — full walk-forward notebook
- `v5_selected_combos.csv` — combos that passed Bonferroni on 2024 training data

## Results
The Bonferroni threshold (p < 0.000133) was strict enough that only a handful of combos passed on the 2024 training set alone. The selected combos were then evaluated OOS on 2025 and 2026.

This version confirmed that much of the v2/v4.3 edge was in-sample artefact — the Bonferroni-selected combo set fires less frequently and with weaker OOS edge than the full top-10 list.

## Status
Methodology was sound. Results fed into the broader conclusion that the combo filter alone is insufficient without regime gates (addressed in v10/v11). Archived — v6 sim_cache approach replaced the re-simulation overhead.
