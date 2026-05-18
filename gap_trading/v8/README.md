# v8 — Walk-Forward L1 Logistic + Random Forest

## Purpose
Walk-forward version of v7: instead of a single train/OOS split, the model is retrained quarterly on all past data and evaluated on the next quarter. Tests whether the ML edge is consistent or a one-time artifact of the v7 train/OOS boundary.

## Method
- Data source: `v6/sim_cache.csv`
- Walk-forward expanding window: train on all data up to quarter Q, evaluate on Q+1
- OOS evaluation period: Jan 2025 – Mar 2026 (where enough training history exists)
- Two model types tested:
  - **L1 Logistic**: same as v7 (L1, liblinear, class_weight={0:1,1:2.5})
  - **Random Forest**: sklearn RandomForestClassifier, class_weight='balanced'
- Features: same as v7 (13 binary + continuous: entry_prem, dte, VIX_INDIA_pct, gap_normalized)

## Key Files
- `backtest_v8.ipynb` — full walk-forward training and evaluation notebook

## Results

### Walk-Forward OOS: Jan 2025 – Mar 2026

| Model | Trades | Win% | ROI | MaxDD |
|---|---|---|---|---|
| L1 Logistic | 24 | 25.0% | -42.3% | 47.1% |
| Random Forest | 8 | 25.0% | -6.7% | 22.0% |

### Context vs v9 (same period, in-sample combos)
| Version | Trades | Win% | ROI | MaxDD |
|---|---|---|---|---|
| v9 IS combos | 59 | 28.8% | -12.8% | 66.5% |
| v8 L1 WF (genuine OOS) | 24 | 25.0% | -42.3% | 47.1% |
| v8 RF WF (genuine OOS) | 8 | 25.0% | -6.7% | 22.0% |

## Key Findings
- Walk-forward OOS is worse than v7's single-split OOS — suggests the v7 train period (which included the quiet 2024 bull market) gave it an advantageous prior
- RF fires the least (8 trades) and loses the least in absolute terms (-6.7%)
- L1 fires more but loses badly in the Sep-Nov 2025 drawdown period
- 8 or 24 trades remain statistically insufficient for confidence
- The walk-forward approach confirmed there is no stable, consistent ML edge across rolling periods — the base win rate swings too much quarter to quarter (14%-34%) for any model to generalize

## Status
Archived. Superseded by v11 which bakes the regime gate into training rather than relying on the model to learn it.
