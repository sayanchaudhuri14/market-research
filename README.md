# NIFTY Options Research

Three independent research threads on NIFTY, all using real market data. Two are live on EC2 today.

---

## Projects

### 1. Gap PUT Strategy (`gap_trading/`)

The core idea: NIFTY systematically fades gap-ups in the first hour. When global markets close up overnight, that move is priced in at the 9:15 open — and the first 2 hours tend to reverse. Buying a 1-OTM PUT at 9:25 AM (10 minutes after open, not at open) captures that reversal.

**The 10-minute delay was the biggest single finding.** Same signals at 9:15 entry: -65.7% ROI on 2024 data. At 9:25 entry: +148.9%, 40% win rate.

Entry triggers on combinations of overnight global signals: S&P 500, Nikkei 225 open, DAX, VIX, India close, gap size. 741 sessions × 13 binary features → 69 statistically significant bearish combos (binomial test, p < 0.05). The strategy skips ~75% of days. 0/10,000 Monte Carlo coin-flip simulations beat it on signal days.

**Currently live**: v4.3 running on EC2 (Tue–Fri, 9:25 AM IST). v4.3.2 running in parallel on Tuesday-only (expiry day) since Sep 2025, when NIFTY shifted from Thursday to Tuesday weekly expiry.

**Best research result**: v11 (L1 logistic + VIX + gap gates baked into training) — 47.1% win rate, +88% ROI, 15.4% max drawdown on 17 genuine OOS trades (Jul 2025 – Feb 2026). Not yet deployed.

---

### 2. DTE0 Weekly Options (`DTE0_options/`)

Multi-leg NIFTY options strategies (Bear Call Spread, Bull Put Spread, Batman, Strip, Iron Condor, Long Straddle) entered at 9:25 AM and monitored until SL/TP or 15:20 hard exit. 10 strategy + DTE combinations running live simultaneously, each with Rs 1,00,000 starting capital and a 15% drawdown circuit-breaker.

**Grid search**: 400 combinations (4 strategies × 5 DTEs × 5 SL levels × 4 TP levels) backtested on real NSE 1-minute options data, Jan 2024 – Mar 2026. The top 30 results are entirely Bear Call Spread. BPS, Batman, Strip, and Iron Condor have no backtest support.

**Live paper trading** (Apr 23 – May 15, 2026): BCS DTE1/2/3/4 all positive. BPS paused at -12% to -18% DD within 3 weeks. Batman down -33% on a single stop-loss. Strip outperforming everything at +33.7% in 2 trades — but too few data points to conclude.

**History note**: The original backtest had a sign bug (`-(piv @ wt)` instead of `nc - (piv @ wt)`) that inverted all P&L, making losses appear as profits. Results like "BCS +400%, Strip +826%" were fabricated. All results in this repo are from the corrected version with a 9-test verification suite.

---

### 3. Overnight Drift Strategy (`overnight_drift_Strategy/`) — Closed

Buy the top 10 NIFTY 50 stocks by rolling 20-session overnight return at 3:20 PM, sell the next morning at 9:25 AM. The phenomenon is real and academically documented.

**Why it was closed**: An S&P 500 filter appeared to boost the win rate to 74% with p < 0.0001 — until a lookahead bug was found. The backtest was reading the US session that closes *after* the India buy (2:30 AM IST vs 3:15 PM IST buy), making it effectively "trade when the US goes up tonight." After fixing the alignment, the corrected filter showed no statistically significant edge, and the pre-tax XIRR of ~9.5% fell below a NIFTY index fund after 20% STCG. Closed April 2026.

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
