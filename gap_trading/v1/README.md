# v1 — Correlation Exploratory Analysis

## Purpose
First-pass exploration of whether global market signals (US, Japan, Europe, VIX) have any predictive relationship with the NIFTY opening gap. No trading system yet — pure statistical analysis.

## Method
- Pulled daily OHLCV for NIFTY, S&P 500, NASDAQ, Nikkei, DAX, Hang Seng, FTSE, VIX US, VIX EU, VIX India via Kite and yfinance
- Computed pairwise correlations between prior-night global returns and NIFTY next-day gap
- Analyzed conditional stats: win rates by direction of each global index
- Plotted composite signal scores

## Key Files
- `global_india_correlation.ipynb` — main analysis notebook
- `aligned_dataset.csv` — merged daily dataset (global + NIFTY gap)
- `correlation_summary.csv` — pairwise correlation table
- `conditional_stats.csv` — win rate by signal direction
- `pairs_summary.csv` — top signal pairs

## Key Findings
- SGX Nifty (now BSE Sensex futures), Nikkei, and DAX direction show the strongest correlation with NIFTY gap direction
- VIX US spike shows a moderate inverse relationship with NIFTY gap-up continuation
- No single signal alone is reliable enough; pairs/triplets needed
- These findings motivated v2's systematic signal combination search

## Status
Exploratory only. Superseded by v2.
