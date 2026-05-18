# NIFTY Gap PUT Strategy — Research Overview

## Strategy
Buy the ATM-50 PUT option at 9:25 AM on NIFTY gap-up days that match bearish signal combinations from global overnight markets. Exit at TP (+40%), SL (-15%), or 11:15 AM hard stop.

- **Strike**: ATM - 50 (1-OTM PUT)
- **Entry**: 9:25 AM market open
- **SL / TP**: -15% / +40% of entry premium
- **Hard exit**: 11:15 AM
- **Breakeven win rate**: 27.3%
- **Lot size**: 75 (NIFTY), BASE=5 lots, MAX=25 lots, DTE0 cap=10 lots
- **Starting capital**: Rs 2,00,000 (compounding)

## Version Map

| Version | What it does | Status |
|---|---|---|
| [v1](v1/README.md) | Global-India correlation exploration | Archived |
| [v2](v2/README.md) | Signal combination search; produced top-10 combos | Active dependency |
| [v3](v3/README.md) | New signal exploration | Archived (dead end) |
| [v4](v4/README.md) | Sub-version backtests v4.1-v4.7; v4.3 deployed | v4.3 live in production |
| [v5](v5/README.md) | Bonferroni-corrected train/test split | Archived |
| [v6](v6/README.md) | **sim_cache.csv** — real option simulation cache | Active dependency |
| [v7](v7/README.md) | L1 logistic on sim_cache; genuine OOS +8.4% | Experimental cron |
| [v8](v8/README.md) | Walk-forward L1/RF; OOS -42% / -6.7% | Archived |
| [v9](v9/README.md) | v4.3 combos on sim_cache + VIX/gap gate analysis | Archived |
| [v10](v10/README.md) | Gate analysis + wider TP resim (dead end) | Archived |
| [v11](v11/README.md) | Gate baked into training; OOS +88%, 47.1% win | Best result — not yet deployed |
| [backtest-merged](backtest-merged/README.md) | Canonical v2 + v4.3 reference notebooks | Reference |
| [cron](cron/) | Live EC2 trading systems | Production |

## Key Data Files (cross-version dependencies)

| File | Used by |
|---|---|
| `v2/v2_aligned_dataset.csv` | v9, v10, v11 (gate features: VIX, gap_pct, prev_india_ret) |
| `v2/v2_reliable_signals.csv` | cron/v4.3, v9 (top-10 bearish/bullish combos) |
| `v6/sim_cache.csv` | v7, v8, v9, v10 (402-row option outcome cache, SL=15%/TP=40%) |
| `v10/sim_cache_v10.csv` | v10 Phase 2 only (wider TP, not used downstream) |

## Results Summary (Key OOS Numbers)

| Version | Period | Type | Trades | Win% | ROI | MaxDD |
|---|---|---|---|---|---|---|
| v4.3 / v9 IS | 2024–2026 | In-sample | 120 | 31.7% | +147.7% | 34.2% |
| v7 L1 | Jul–Mar 2026 | **Genuine OOS** | 10 | 40.0% | +8.4% | 21.0% |
| v8 L1 WF | Jan–Mar 2026 | Genuine OOS | 24 | 25.0% | -42.3% | 47.1% |
| v8 RF WF | Jan–Mar 2026 | Genuine OOS | 8 | 25.0% | -6.7% | 22.0% |
| v9 both gates | Jul–Mar 2026 | IS combos | 22 | 27.3% | -39.0% | 65.0% |
| **v11 both gates** | **Jul–Mar 2026** | **Genuine OOS** | **17** | **47.1%** | **+88.0%** | **15.4%** |

## Key Conclusions (as of May 2026)

1. **The base win rate is regime-dependent**: swings from 14% (Q4 2024) to 34% (Q1 2025). No model can profitably trade through all regimes without a filter.

2. **The VIX gate is real**: skipping when VIX_INDIA_pct (rolling 252d rank) > 0.65 consistently avoids losing months. It is mechanistically justified — expensive options + elevated uncertainty = poor PUT buying conditions.

3. **Gate-before-training beats gate-as-post-filter**: v11 (gate applied before training) achieved +88% OOS vs v9+gates (-39% on the same period). The model must be trained on the same distribution it will trade.

4. **The Sep 2025 drawdown is the key challenge**: 9 consecutive gap-up days in Jul-Sep 2025 where NIFTY reversed — triggering stop-losses on all combo-fired days. The v11 both-gates model filtered most of this period out.

5. **Statistical insufficiency persists**: the best OOS result (v11, 17 trades) needs ~50 trades for statistical significance. Approximately 2 more years of live trading needed before definitive conclusions.

6. **Recommended deployment**: Add VIX gate to cron/v4.3 as a skip condition. Optionally run v11 both-gates model (pkl exists) as a parallel system. Collect live OOS trades.

## Live Systems (cron/)
- `cron/v2/` — original v2 combo system (legacy)
- `cron/v4.3/` — **current production** (v4.3 top-10 combos, ^N225 SGX signal)
- `cron/v7/` — experimental L1 model parallel system
