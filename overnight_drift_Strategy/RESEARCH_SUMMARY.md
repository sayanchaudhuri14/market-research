# Overnight Drift Strategy — Research Summary

**Project:** Overnight Drift on NIFTY 50  
**Research period:** Jan 2019 – Apr 2026  
**Status: ACTIVE — viable at any capital, fixed mode break-even ~Rs 2.7L**

---

## Strategy

**Signal:** Rolling 20-session mean overnight return per stock  
`overnight_return[t] = open[t] / close[t-1] - 1`

**Filter:** Only trade when S&P 500 closed non-negative the previous night  
(S&P 500 closes ~2:30 AM IST — fully known before 3:20 PM entry)

**Entry:** Buy top 10 ranked NIFTY 50 stocks at 3:20–3:25 PM (CNC delivery)

**Exit:** Sell all at 9:25 AM next morning

**No VIX filter** — tested and shown to be harmful. High VIX days are profitable.

---

## Results (2019–2026, point-in-time constituents)

Run `v2/backtest.ipynb` with your capital to get exact CAGR figures. Capital-independent metrics:

| Metric | Value |
|--------|-------|
| Active sessions | ~120/year (~46% of all sessions) |
| Win rate (compounding) | ~76% on active days |
| Sharpe ratio | ~6+ on active sessions |
| Max drawdown | ~-4.6% |

CAGR depends on starting capital because flat charges (Rs 236/session) shrink as a fraction as capital grows. Compounding outperforms fixed at all capital levels.

---

## Cost Model

| Charge | Rate | Notes |
|--------|------|-------|
| Brokerage | **Rs 0** | Zerodha & AngelOne: delivery (CNC) is free |
| DP charge | Rs 236 flat/session | Rs 20 + GST per scrip × 10 stocks sold |
| STT | 0.10% of sell value | Sell side only |
| Stamp duty | 0.015% of buy value | Buy side only |
| Exchange + SEBI + GST | ~0.007% | Both sides |
| **Total percentage** | **0.1222% of capital** | Per round-trip |
| STCG tax | 20% | On net profits (strategy) |
| LTCG tax | 10% | On net profits (NIFTY index fund) |

**Total per session: Rs 236 + 0.1222% of capital**

| Capital | Total cost | As % of capital |
|---------|-----------|-----------------|
| Rs 1L | Rs 358 | 0.358% |
| Rs 2L | Rs 480 | 0.240% |
| Rs 3L | Rs 603 | 0.201% |
| Rs 5L | Rs 847 | 0.169% |
| Rs 10L | Rs 1,458 | 0.146% |

**Break-even capital (fixed mode): ~Rs 2.7L.** Above this the strategy is profitable even withdrawing profits each session. Compounding works at any capital — reinvestment grows the portfolio past break-even quickly.

---

## Why Win Rate Differs Between Fixed and Compounding

A session is a "win" when `gross return > cost fraction`. In fixed mode the cost fraction is constant (`0.1222% + Rs 236 / starting capital`). In compounding mode the cost fraction recalculates every session as the portfolio grows — as the portfolio exceeds starting capital, the flat charge shrinks as a %, so the win threshold drops and more sessions qualify. Compounding win rate is slightly higher than fixed for this reason. It is not a bug — both are correct.

---

## Why the US Filter Works

The S&P 500 and NIFTY 50 are correlated overnight. When the S&P 500 closes positive, Indian stocks open with a positive gap. The US close (2:30 AM IST) is fully known before entry (3:20 PM IST) — no lookahead.

- Skip days (S&P < 0): mean return ~-0.16%, win rate ~38%
- Trade days (S&P >= 0): mean return ~+0.21%, win rate ~74%
- t-test p-value = 0.000

---

## Research Journey

### v1 (Kite API, current constituents)
- Survivorship bias — used current NIFTY 50 for entire history → inflated XIRR ~16–17%
- Required Kite login + daily token refresh

### v1.5 (yfinance + point-in-time constituents, no filter)
- Honest XIRR without filter: ~9.5% pre-tax, ~7.6% after 20% STCG
- Below NIFTY index fund after tax — not viable without a filter

### v2 (US S&P 500 filter)
- Filter transforms the strategy — win rate jumps from ~50% to ~74% on active days
- VIX filter tested and rejected — skips profitable high-fear days
- Monday staleness tested and rejected — 73.7% win rate on Mondays, same as rest of week

### Apr 2026 Charge Model Audit
Two bugs found in the original cost model:

**Bug 1 — PCT doubled:** Code had `PCT_COST_OF_CAPITAL = PCT_COST_OF_TURNOVER * 2`. The `* 2` was wrong — the variable was already expressed as a fraction of capital, not turnover. Charged 0.2444% instead of the correct 0.1222%.

**Bug 2 — Wrong brokerage:** Code assumed Rs 20/order for delivery. Both Zerodha and AngelOne charge Rs 0 for equity delivery (CNC). Flat cost is Rs 236/session (DP only), not Rs 708.

Combined these inflated charges by ~300% of starting capital over the backtest, making the strategy appear unviable below Rs 30L when the actual fixed-mode break-even is Rs 2.7L.

---

## What Is Not Modeled

- **Exit slippage:** `open[t]` from yfinance is the pre-open auction price. Actual 9:25 AM fill may differ by 0.1–0.3%.
- **Entry slippage:** Actual 3:20 PM fill may differ slightly from the previous close.
- **Idle capital return:** Capital is idle on skip days and from 9:25 AM–3:20 PM on trade days. Parking in an overnight/liquid fund could add ~3–4%/year on the idle portion.

---

## Active Files

| File | Purpose |
|------|---------|
| `v2/backtest.ipynb` | Full historical backtest — set `STARTING_CAPITAL` and run all cells |
| `v2/daily_signal.ipynb` | Run at 3 PM — TRADE or SKIP decision + buy list |
| `v2/README.md` | Quick reference |
| `RESEARCH_SUMMARY.md` | This file |
| `notebooks/DEPRECATED.md` | v1 notebooks — what they were and why deprecated |
| `scripts/DEPRECATED.md` | v1 scripts — what they were and why deprecated |

---

*Research completed: April 2026*  
*Charge model audited and corrected: April 2026*  
*Data: yfinance (NSE OHLC + ^GSPC + ^NSEI), NSE rebalancing notices (2019–2026)*
