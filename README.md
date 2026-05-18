# NIFTY Options Research

Three independent research threads on NIFTY, all using real market data. Two are live on EC2 today.

---

## Projects

### 1. Gap PUT Strategy (`gap_trading/`)

The core idea: NIFTY systematically fades gap-ups in the first hour. When global markets close up overnight, that move is priced in at the 9:15 open — and the first 2 hours tend to reverse. Buying a 1-OTM PUT at 9:25 AM (10 minutes after open, not at open) captures that reversal.

Entry triggers on combinations of overnight global signals: S&P 500, Nikkei 225 open, DAX, VIX, India close, gap size. 741 sessions × 13 binary features → 69 statistically significant bearish combos (binomial test, p < 0.05). The strategy skips ~75% of days and breakeven is 27.3% win rate.

**In-sample results** (Jan 2024 – Mar 2026, combos selected on same data): 120 trades, 31.7% win rate, +147.7% ROI, 34.2% max drawdown. The in-sample number is inflated — the same data was used to select and evaluate the combos.

**Genuine OOS results** (combos fixed, evaluated on unseen data):

| Version | Period | Trades | Win% | ROI | MaxDD |
|---|---|---|---|---|---|
| v4.3 (no filter) | Jul 2025–Mar 2026 | 34 | 26.5% | -57.9% | 77.3% |
| v7 L1 logistic | Jul 2025–Mar 2026 | 10 | 40.0% | +8.4% | 21.0% |
| **v11 (VIX + gap gates)** | **Jul 2025–Feb 2026** | **17** | **47.1%** | **+88.0%** | **15.4%** |

v11 applies VIX and gap-size gates *before* training the model, so the model learns only from regime-appropriate days. It is the best genuine OOS result but has only 17 trades — statistically under-powered.

**Currently live**: v4.3 on EC2 (Tue–Fri). v4.3.2 running in parallel on Tuesday-only since Sep 2025, when NIFTY weekly expiry shifted from Thursday to Tuesday. v11 model exists (pkl) but not yet deployed.

---

### 2. DTE0 Weekly Options (`DTE0_options/`)

Multi-leg NIFTY options strategies (Bear Call Spread, Bull Put Spread, Batman, Strip, Iron Condor, Long Straddle) entered at 9:25 AM and monitored until SL/TP or 15:20 hard exit. 10 strategy + DTE combinations running live simultaneously, each with Rs 1,00,000 starting capital and a 15% drawdown circuit-breaker.

**Grid search**: 400 combinations (4 strategies × 5 DTEs × 5 SL levels × 4 TP levels) backtested on real NSE 1-minute options data, Jan 2024 – Mar 2026. The top 30 results are entirely Bear Call Spread. BPS, Batman, Strip, and Iron Condor have no backtest support.

**Live paper trading** (Apr 23 – May 15, 2026): BCS DTE1/2/3/4 all positive. BPS paused at -12% to -18% DD within 3 weeks. Batman down -33% on a single stop-loss. Strip outperforming everything at +33.7% in 2 trades — but too few data points to conclude.

**Structural finding**: On Sep 2, 2025, NIFTY weekly expiry moved from Thursday to Tuesday. This completely changed which DTE values the strategy trades on. Under Thursday expiry, Wednesday (DTE=2) had a 51.7% win rate — the best day. Under Tuesday expiry, Friday (DTE=4) has a 0% win rate across 6 trades; Tuesday expiry day (DTE=0) has 45.5%. The same strategy on the same signals produces opposite results depending on which day of the week it fires.

**History note**: The original backtest had a sign bug (`-(piv @ wt)` instead of `nc - (piv @ wt)`) that inverted all P&L, making losses appear as profits. Results like "BCS +400%, Strip +826%" were fabricated. All results in this repo are from the corrected version with a 9-test verification suite.

---

### 3. Overnight Drift Strategy (`overnight_drift_Strategy/`) — Closed

Buy the top 10 NIFTY 50 stocks by rolling 20-session overnight return at 3:20 PM, sell the next morning at 9:25 AM. The phenomenon is real and academically documented.

**Why it was closed**: Two bugs found and fixed. First, survivorship bias — the initial backtest used the current 2026 NIFTY 50 composition for the full 2021–2026 history, inflating XIRR to ~16%. Replaced with point-in-time constituents from NSE rebalancing notices. Second, a lookahead bug in the S&P 500 filter: the backtest was reading the US session that closes *after* the India buy (2:30 AM IST vs 3:15 PM IST buy), making it effectively "trade when the US goes up tonight." That filter appeared to boost win rate to 74% with p < 0.0001. After fixing the alignment, no statistically significant edge remained, and the honest pre-tax XIRR of ~9.5% fell below a NIFTY index fund after 20% STCG. Closed April 2026.

---

## Data

| Source | Used for |
|---|---|
| NSE real 1-min options OHLCV | Gap PUT backtest, DTE0 grid search (~2.6 GB, gitignored) |
| Zerodha Kite Connect API | Live prices, NIFTY spot, option LTPs |
| yfinance daily | `^GSPC`, `^N225`, `^GDAXI`, `^VIX`, `^NSEI` — global signal features |
| NSE bhav copy + rebalancing notices | Point-in-time NIFTY 50 constituents (overnight drift) |

---

## Live Systems (EC2, Asia/Kolkata)

```
# Gap PUT strategy — v4.3 (Tue–Fri)
25 9 * * 2-5  python3 .../cron/v4.3/entry.py
27 9 * * 2-5  python3 .../cron/v4.3/exit.py

# Gap PUT strategy — v4.3.2 (Tuesday only, DTE=0 gate)
25 9 * * 2    python3 .../cron/v4.3.2/entry.py
27 9 * * 2    python3 .../cron/v4.3.2/exit.py

# DTE0 weekly options (Tue–Fri)
25 9 * * 2-5  python3 .../DTE0_options/curr_live/cron/paper_trader.py
```

Kite authentication is fully automated — TOTP via pyotp, no browser. Token shared across systems to avoid session conflicts.

---

## Stack

Python · Jupyter · Zerodha Kite Connect · yfinance · pandas · NumPy · scikit-learn · pyotp · EC2
