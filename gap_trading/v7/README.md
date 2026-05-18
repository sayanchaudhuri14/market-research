# v7 — L1 Logistic Regression on sim_cache (Genuine OOS)

## Purpose
First ML model on top of the sim_cache. Trained on Jan 2024 – Jun 2025 data, evaluated on a genuine OOS period: Jul 2025 – Mar 2026 (dates the model never saw during training).

## Method
- Data source: `v6/sim_cache.csv` (402 rows)
- Features: 13 binary signals + continuous features (entry_prem, dte, VIX_INDIA_pct rolling rank, gap_normalized)
- Model: L1 LogisticRegressionCV (penalty='l1', solver='liblinear', class_weight={0:1, 1:2.5}, cv=5, scoring='roc_auc')
- Signal threshold: trade only when model P(win) > some cutoff
- Train period: Jan 2024 – Jun 2025
- OOS period: Jul 2025 – Mar 2026

## Key Files
- `backtest_v7.ipynb` — full training + OOS evaluation notebook
- `v7_model.pkl` — serialized trained model (also copied to cron/v7/)

## Results

### Genuine OOS: Jul 2025 – Mar 2026
| Metric | Value |
|---|---|
| Trades | 10 |
| Win rate | 40.0% |
| ROI | +8.4% |
| Max drawdown | 21.0% |
| Breakeven | 27.3% |

**This is the only version with a positive ROI in the Jul 2025–Mar 2026 OOS window.**

### Context vs v9 (same period, in-sample combos)
| Version | Trades | Win% | ROI | MaxDD |
|---|---|---|---|---|
| v7 L1 (genuine OOS) | 10 | 40.0% | +8.4% | 21.0% |
| v9 no filter (IS combos) | 34 | 26.5% | -57.9% | 77.3% |

v7 achieved positive OOS by being highly selective (10 trades vs 34), filtering out the brutal Sep 2025 drawdown period.

## Caveats
- 10 OOS trades is statistically insufficient (~50 needed for significance)
- The model's AUC on OOS data was modest (~0.65)
- L1 regularization helped but cannot overcome regime risk
- The Sep 2025 losing streak (9 consecutive stop-losses in the market) was avoided primarily by the model's low firing rate, not genuine alpha

## Status
Deployed to cron/v7 as an experimental parallel system. Best performing genuine-OOS model in the series, but insufficient trade count to declare statistical edge. Superseded analytically by v11 which bakes the gate into training.
