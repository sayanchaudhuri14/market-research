# Overnight Drift Strategy — v2

Buy top 10 NIFTY 50 stocks (by 20-session overnight momentum) at 3:20 PM. Sell at 9:25 AM next morning. Only trade when the S&P 500 closed non-negative the previous night.

---

## Files

| File | Purpose |
|------|---------|
| `backtest.ipynb` | Full historical backtest. Change `STARTING_CAPITAL` and run all cells. |
| `daily_signal.ipynb` | Run at 3:00 PM daily — outputs TRADE or SKIP + buy list. |

---

## How to run

1. Open `backtest.ipynb`
2. Set `STARTING_CAPITAL` in cell 1 (the only cell you need to edit)
3. Run all cells — results table shows CAGR for fixed capital, compounding, and NIFTY index fund, both pre-tax and after-tax

---

## Charges modeled

| Charge | Rate |
|--------|------|
| STT | 0.10% of sell-side value |
| Stamp duty | 0.015% of buy-side value |
| Exchange + SEBI + GST | ~0.007% of capital |
| Brokerage | Rs 0 (delivery / CNC is free on Zerodha and AngelOne) |
| DP debit charge | Rs 23.6 per scrip sold (Rs 236 flat for 10 stocks) |
| **Total per session** | **Rs 236 + 0.1222% of capital** |

Break-even capital for fixed mode: ~Rs 2.7L. Compounding works at any capital.

---

## What v2 fixed vs v1

| v1 problem | v2 fix |
|------------|--------|
| Survivorship bias — current NIFTY 50 used for all history | Point-in-time constituents from NSE rebalancing notices (2019–2026) |
| VIX filter — skipped profitable high-fear days | Removed |
| Kite API dependency, daily token refresh | yfinance only — no login needed |
| Percentage cost double-counted in charge model | Fixed — 0.1222% not 0.2444% |
| Brokerage modeled as Rs 20/order | Fixed — delivery (CNC) is free |
