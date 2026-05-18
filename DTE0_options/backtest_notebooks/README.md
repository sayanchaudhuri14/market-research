# backtest_notebooks — Grid Search and Strategy Analysis

All historical backtesting for the DTE0 options project. Uses real NIFTY options tick data (open prices bar-by-bar), Kite 9:25 AM spot as ATM source, real broker charges, bid-ask slippage, compounding lot sizing, and a 15% DD circuit-breaker.

---

## Files

| File | Purpose |
|---|---|
| `grid_search.ipynb` | **Primary research notebook** — 400-combo grid search across 4 strategies × 5 DTEs × 5 SL × 4 TP |
| `strategy_analysis.ipynb` | 10 deployed strategies analysed with fixed SL/TP from paper_trader.py (not yet re-run after sign fix) |
| `_patch_nb.py` / `_patch2_nb.py` | One-off patching scripts used during the sign bug fix — not needed going forward |
| `_strip_backtest.py` | Standalone strip strategy backtest script |
| `gs_cache/` | Cached precomputed series per strategy+DTE (pkl files) and grid search results |

---

## Grid Search Setup

- **Data**: Jan 2024 – Mar 2026 (old monthly format Jan–Sep 2024; per-strike expiry folders Oct 2024+)
- **Entry**: 9:25 AM, Tue–Fri only (Mon excluded to match live cron)
- **ATM source**: Kite minute cache (9:25 open) as primary; NIFTY spot fallback
- **Strategies tested**: Bear Call Spread, Bull Put Spread, Batman, Iron Condor (5 DTEs × 5 SL × 4 TP each = 100 combos per strategy = 400 total)
- **Realism**: slippage Rs 8/unit/leg round-trip, real brokerage + STT + exchange + GST + SEBI, monthly lot recalc, 15% DD pause (4 weeks)

### Sign Bug (critical history)
The original backtest computed `-(piv @ wt)` instead of `nc - (piv @ wt)` for PnL, inverting the sign. SL almost never fired, TP fired on losing trades. Fabricated results: BCS +400%, Strip +826%, BPS +446%. 

Fixed version uses `pnl_arr = nc - (piv @ wt)`. A 9-test suite (sign checks, SL/TP firing, lot sizing, charges) was added and must pass before any run.

---

## Grid Search Results (corrected)

Top 30 results are entirely **Bear Call Spread**. No BPS, Batman, Strip, or Iron Condor appears.

| Rank | Strategy | DTE | SL | TP | WR | ROI | MaxDD |
|---|---|---|---|---|---|---|---|
| 1 | Bear Call Spread | 3 | 50% | 100% | 53.7% | +144.7% | 44.7% |
| 2 | Bear Call Spread | 3 | 50% | 75% | 58.3% | +101.1% | 49.0% |
| 3 | Bear Call Spread | 4 | 75% | 75% | 63.8% | +93.0% | 78.6% |
| 4 | Bear Call Spread | 2 | 50% | 100% | 54.5% | +81.5% | 42.2% |
| 7 | Bear Call Spread | 3 | 100% | 100% | 63.0% | +61.4% | 54.5% |

Full results in `gs_cache/results.csv`. Heatmap saved as `gs_cache/heatmap.png`.

**All results are in-sample** (Jan 2024–Mar 2026). The grid search parameters were then deployed live — live data from Apr 2026 onward is the true OOS test.

---

## gs_cache/

Pre-computed intraday PnL series per strategy+DTE combination. Delete to rebuild (takes ~3s with cache). Each pkl contains a list of dicts with `trade_date`, `expiry`, `pnl_arr`, `nc`, `ml`, `n_legs`, `expiry_pnl`, `charges`.
