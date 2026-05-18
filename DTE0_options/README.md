# DTE0 Options — NIFTY Weekly Options Strategy Research

Research and live paper trading for NIFTY weekly options strategies. Entry at 9:25 AM, exit at SL/TP or 15:20 hard stop. All strategies trade multi-leg structures (spreads, combinations) on NIFTY index options.

**Starting capital**: Rs 1,00,000 per strategy  
**Lot size**: 75 units  
**Universe**: NIFTY weekly options (Tuesday expiry from Sep 2025)  
**Cron**: Tue–Fri 9:25 AM on EC2

---

## Folder Map

| Folder | Purpose |
|---|---|
| [strategies/](strategies/) | Shared strategy leg definitions used by both backtest and live (research copy) |
| [data/](data/) | Data loading utilities for backtesting — option files, NIFTY spot, expiry calendar |
| [backtest_notebooks/](backtest_notebooks/) | Grid search and strategy analysis notebooks — all historical research |
| [curr_live/](curr_live/) | **Live paper trading system** — deployed on EC2, running daily |
| [paper_trader/](paper_trader/) | Earlier/alternate paper trader version (superseded by curr_live/) |

---

## Key Findings (as of May 2026)

### The Sign Bug
The original backtest had a PnL sign inversion bug — it stored the negative of actual PnL, making losses appear as profits. Results like "BCS +400%, Strip +826%" were fabricated. The bug was caught, all tests were re-run with a verified sign-check suite.

### Grid Search Conclusion (corrected, Jan 2024–Mar 2026)
400 combinations tested (4 strategies × 5 DTEs × 5 SL × 4 TP). The top 30 by final capital are **entirely Bear Call Spread**. No BPS, Batman, Strip, or Iron Condor appears in the top 30.

Top results (in-sample):

| Rank | Strategy | DTE | SL | TP | WR | ROI |
|---|---|---|---|---|---|---|
| 1 | Bear Call Spread | 3 | 50% | 100% | 53.7% | +144.7% |
| 2 | Bear Call Spread | 3 | 50% | 75% | 58.3% | +101.1% |
| 3 | Bear Call Spread | 4 | 75% | 75% | 63.8% | +93.0% |
| 4 | Bear Call Spread | 2 | 50% | 100% | 54.5% | +81.5% |

**These are in-sample** — combos were selected on the same data they are evaluated on.

### Live Paper Trading Results (Apr 23 – May 15, 2026, ~3 weeks)

| Strategy | ROI | Trades | Status |
|---|---|---|---|
| STRIP DTE4 | +33.7% | 2 | Active (open pos) |
| BCS DTE1 | +15.2% | 3 | Active |
| BCS DTE4 | +12.4% | 2 | Active (open pos) |
| BCS DTE2 | +10.2% | 2 | Active |
| BCS DTE3 | -4.1% | 3 | Active |
| BPS DTE2 | -12.5% | 2 | **PAUSED** (DD hit) |
| BPS DTE4 | -16.0% | 2 | **PAUSED** |
| BPS DTE3 | -18.0% | 1 | **PAUSED** |
| Batman DTE2 | -33.1% | 2 | **PAUSED** (-Rs 46k SL) |
| Long Straddle DTE1 | -30.4% | 1 | **PAUSED** |

3 weeks / 1–3 trades per strategy is insufficient for conclusions. Directionally consistent with grid search (BCS works, others don't).

### What to Watch
BCS DTE2 and DTE3 with SL=50%, TP=100% are the grid search top picks. The live system is running SL=50%/TP=100% for DTE2/3 and SL=75%/TP=75% for DTE4 — close to optimal parameters. Collect 20+ trades per strategy before drawing conclusions.

---

## Cron (EC2)
```
25 9 * * 1-5  python3 /home/ec2-user/Gap_Trading_Strategy/options/paper_trader/paper_trader.py >> .../cron.log 2>&1
```
