# v11 — Gate Baked into Training (VIX Gate + Both Gates)

## Purpose
Key design change from v10: instead of applying gates as a post-filter to the full combo universe, the gate is applied BEFORE model training. The model learns only from days that pass the gate, so it is not contaminated by unfavorable regime examples.

Two gate variants were trained and evaluated:
- **VIX gate only**: VIX_INDIA_pct ≤ 0.65
- **Both gates**: VIX_INDIA_pct ≤ 0.65 AND |gap_normalized| ∈ [0.10, 0.80]

## Method
- Data source: `v6/sim_cache.csv` + `v2/v2_aligned_dataset.csv` (for gate features)
- Gate applied first → filtered subset used for training AND for OOS evaluation
- Model: L1 LogisticRegressionCV (penalty='l1', solver='liblinear', Cs=[0.01,0.05,0.1,0.5,1.0,5.0], cv=5, scoring='roc_auc', class_weight={0:1,1:2.5})
- Train period: Jan 2024 – Jun 2025 (gate applied)
- OOS period: Jul 2025 onwards (split into Q3 2025, Q4 2025, Q1 2026)

## Key Files
- `backtest_v11.ipynb` — full notebook (gate diagnostic → training → OOS → export)
- `v11_model_vix.pkl` — trained model (VIX gate only)
- `v11_model_both.pkl` — trained model (both gates)
- `v11_summary.csv` — combined results summary
- `v11_train_both_gates.csv` — in-sample trade log (both gates)
- `v11_train_vix_gate.csv` — in-sample trade log (VIX gate only)
- `v11_oos_both_gates.csv` — OOS trade log (both gates)
- `v11_oos_vix_gate.csv` — OOS trade log (VIX gate only)

## Results — In-Sample (Jan 2024 – Jun 2025)

| Model | Trades | Win% | ROI | MaxDD |
|---|---|---|---|---|
| VIX gate IS | 11 | 54.5% | +105% (est) | moderate |
| Both gates IS | 21 | ~52% | large | **68.2%** |

**Warning**: training MaxDD of 68.2% for both-gates model is a red flag — the in-sample path had a deep drawdown even on filtered days.

## Results — Out-of-Sample (Jul 2025 – Mar 2026)

| Model | Trades | Win% | ROI | MaxDD |
|---|---|---|---|---|
| VIX gate OOS | 5 | 40.0% | +10.6% | 19.1% |
| Both gates OOS | 17 | 47.1% | +88.0% | 15.4% |

The **both-gates OOS** is the best result in the entire v6-v11 series:
- 47.1% win rate vs 27.3% breakeven
- +88% ROI from Rs 2,00,000 starting capital
- Only 15.4% max drawdown

### OOS Trade Log Summary (both gates, from v11_oos_both_gates.csv)
- Period: Jul 2025 – Feb 2026
- 17 trades, 8 wins (47.1%), 9 losses
- End capital: Rs 3,75,910 (from Rs 2,00,000)
- Notable winners: Aug 2025 (+Rs 66k), Jan 2026 (+Rs 77k), Jan 2026 (+Rs 45k)
- Notable losses: Jul 2025 (-Rs 19k, -Rs 17k), Sep 2025 (-Rs 24k), Feb 2026 (-Rs 31k)

### OOS Trade Log Summary (VIX gate only, from v11_oos_vix_gate.csv)
- Period: Jul 2025 – Jan 2026
- 5 trades, 2 wins (40.0%)
- End capital: Rs 2,21,284 (from Rs 2,00,000)
- Very sparse — VIX gate alone is too restrictive

## Key Findings
1. **Gate-before-training is superior to gate-as-post-filter** (v11 both-gates +88% OOS vs v9+both-gates -39% on similar period). The model trained on gated data is calibrated to the regime it will actually trade in.
2. **Both-gates OOS is the best result in the entire series** — 47.1% win rate, +88% ROI, 15.4% DD.
3. **Statistical caveat**: 17 OOS trades is still insufficient for significance (~50 needed). Need approximately 2 more years of live trading to confirm.
4. **Sep 2025 avoided well**: the both-gates model passed only Jul 29, Jul 30 in the Sep drawdown window (vs 9 consecutive losses in v9). The gate effectively filtered out the worst of Sep 2025.
5. **Training MaxDD (68.2%) is concerning** — suggests even on filtered days, the strategy can have severe in-sample drawdowns. Live deployment should use strict drawdown stop rules.

## Recommended Next Steps (as of May 2026)
- Add the VIX gate as a skip condition to the live cron/v4.3 system (minimal code change, most defensible intervention)
- Deploy v11 both-gates model (pkl file exists) as a parallel experimental cron alongside v4.3
- Collect 50+ live OOS trades before drawing statistical conclusions

## Status
Most recent completed version. Both models saved as pkl files. OOS results are the most promising in the series but statistically under-powered. The gate logic (VIX_INDIA_pct ≤ 0.65, |gap_normalized| ∈ [0.10, 0.80]) is the key deployable insight from this entire research series.
