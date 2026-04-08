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
| DP charge | Rs 153.40 flat/session | Rs 13 (CDSL base) + 18% GST = Rs 15.34/scrip × 10 stocks |
| STT (buy) | 0.10% of buy value | **Both sides charged** — Finance Act (No. 2) 2004 |
| STT (sell) | 0.10% of sell value | Both sides charged |
| Stamp duty | 0.015% of buy value | Buy side only |
| Exchange + SEBI + IPFT + GST | ~0.007% | Both sides |
| **Total percentage** | **0.2225% of capital** | Per round-trip |
| STCG tax | 20% | On net profits (strategy) |
| LTCG tax | 10% | On net profits (NIFTY index fund) |

**Total per session: Rs 153.40 + 0.2225% of capital**

| Capital | Total cost | As % of capital |
|---------|-----------|-----------------|
| Rs 0.5L | Rs 265 | 0.530% |
| Rs 1L | Rs 376 | 0.376% |
| Rs 2L | Rs 598 | 0.299% |
| Rs 3L | Rs 821 | 0.274% |
| Rs 5L | Rs 1,266 | 0.253% |
| Rs 10L | Rs 2,378 | 0.238% |

**Break-even capital (fixed mode): ~Rs 0.9L.** Above this the strategy is profitable even withdrawing profits each session. Compounding works at any capital.

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
Four bugs found and fixed:

**Bug 1 — PCT doubled:** Code had `PCT_COST_OF_CAPITAL = PCT_COST_OF_TURNOVER * 2`. The `* 2` was wrong — the variable was already expressed as a fraction of capital. Charged 0.2444% instead of the correct value.

**Bug 2 — Wrong brokerage:** Code assumed Rs 20/order for delivery. Both Zerodha and AngelOne charge Rs 0 for equity delivery (CNC). Flat cost is DP charge only.

**Bug 3 — Missing buy-side STT:** STT for equity delivery is 0.10% on **both** buyer and seller (Finance Act No. 2, 2004 schedule). Code only modeled sell-side STT → PCT_COST understated by 0.10% per session. Correct PCT_COST = 0.2225%.

**Bug 4 — Wrong DP rate:** DP charge modeled as Rs 20 + GST = Rs 23.60/scrip. Actual Zerodha CDSL rate is Rs 13 + 18% GST = Rs 15.34/scrip → flat cost Rs 153.40, not Rs 236.

Bugs 3 and 4 partially offset: higher STT raises costs, lower DP lowers them. Net result: break-even ~Rs 0.9L (vs initial inflated estimate of Rs 2.7L).

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
