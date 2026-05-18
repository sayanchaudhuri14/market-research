# v10 — Gate Analysis + Wider TP Exploration (Two-Phase)

## Purpose
Two parallel investigations:
- **Phase 1** (`backtest_v10.ipynb`): Test regime gates (VIX, gap_normalized, HMM) on top of the v7 ML model using the original SL=15%/TP=40% sim_cache (v6)
- **Phase 2** (`resim_v10.ipynb`): Re-simulate with wider TP (SL=10%, TP=60%) to test whether a wider profit target improves outcomes within the 105-minute window

Both phases used the same underlying backtest engine and trade logic.

## Phase 1 — Gate Analysis with v6 Cache

### Gates Tested
- **VIX gate**: VIX_INDIA_pct (rolling 252d rank) ≤ 0.65 — skip when India VIX is elevated
- **Gap gate**: |gap_pct / nifty_20d_realized_vol| ∈ [0.10, 0.80] — skip momentum days (>0.8) and no-catalyst days (<0.1)
- **HMM gate**: Hidden Markov Model regime classifier (2-state: favorable/unfavorable)

### Key Result Files (v6 cache)
- `results_v6_oos_no_gates.csv` — baseline no filter
- `results_v6_oos_vix_only.csv` — VIX gate only
- `results_v6_oos_gap_only.csv` — gap gate only
- `results_v6_oos_all3_gates.csv` — all three gates
- `results_v6_oos_all3_kelly.csv` — all three gates + Kelly sizing
- `results_v6_summary.csv` — summary table

### Conclusion
VIX gate is the most reliable single gate. The HMM gate added marginal value. The gap gate alone does not consistently improve.

## Phase 2 — Wider TP Resimulation (SL=10%, TP=60%)

### New sim_cache_v10.csv
- 402 tradeable days re-simulated with SL=10%, TP=60%
- Breakeven drops to 14.3% (vs 27.3% for original)
- Kelly odds = 6.0x (vs 2.67x)

### Base Win Rate Comparison
| Period | SL=15%/TP=40% (v6) | SL=10%/TP=60% (v10) |
|---|---|---|
| 2024-Q1 | 28.6% | 14.3% |
| 2024-Q2 | 28.9% | 17.8% |
| 2024-Q3 | 19.5% | 7.3% |
| 2024-Q4 | 14.3% | 9.5% |
| 2025-Q1 | 32.6% | 19.0% |
| Overall | 24.9% | ~14% |

### Conclusion — Phase 2 Failed
**Wider TP was worse in every quarter.** The 105-minute window (9:25 AM → 11:15 AM) is insufficient for a PUT option to gain 60% in normal conditions. Winning trades under the original SL=15%/TP=40% that would have hit TP at +40% now only reach +40% then reverse — or they hit the narrower 10% SL faster. Path B chosen: **stay with original SL=15%/TP=40% and focus on gates.**

## Key Files
- `backtest_v10.ipynb` — Phase 1 gate analysis + v7 model application
- `resim_v10.ipynb` — Phase 2 re-simulation with SL=10%/TP=60%
- `sim_cache_v10.csv` — wider-TP sim cache (kept for reference, not used downstream)
- `results_v6_*.csv` / `results_v10_*.csv` — gate analysis exports

## Bugs Fixed in backtest_v10.ipynb
- **KeyError 'india_date'**: merged df drops column after join → fixed to use 'date'
- **ValueError NaN in predict_proba**: rolling warmup NaN rows → fillna(median) before transform
- **Wrong BREAKEVEN/KELLY_ODDS when v10 cache selected**: added auto-detection from SIM_CACHE_PATH name

## Status
Archived. Phase 1 confirmed VIX gate value. Phase 2 confirmed wider TP is a dead end. The gate-first approach was carried forward into v11.
