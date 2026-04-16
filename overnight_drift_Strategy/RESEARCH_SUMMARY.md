# Overnight Drift Strategy — Post-Mortem

**Status: CLOSED — April 2026**
**Verdict: Strategy is not viable with equity delivery. Edge does not survive transaction costs.**

---

## What the strategy was

Buy the top 10 NIFTY 50 stocks (ranked by trailing 20-session mean overnight return) at 3:20 PM.
Sell the next morning at 9:25 AM. Hold time: ~18 hours.

```
overnight_return[t] = open[t] / close[t-1] - 1
score[t]            = rolling 20-session mean of overnight_return
buy list            = top 10 stocks by score, bought at 3:20 PM close
```

The phenomenon is real and academically documented — a cross-sectional overnight momentum
effect in large-cap equities. The problem is not the signal. The problem is costs.

---

## Research journey

### v1 — Survivorship bias
First backtest used the current (2026) NIFTY 50 composition for the entire 2021–2026 history.
Survivorship bias inflated XIRR to ~16–17%. Replaced by point-in-time constituents sourced from
NSE rebalancing notices.

### v1.5 — Honest baseline
With point-in-time constituents and no filter: XIRR ~9.5% pre-tax, ~7.6% after 20% STCG.
Below a NIFTY index fund after tax. Not viable without a filter.

### v2 — US filter (appeared to work)
Added an S&P 500 filter: only trade when the previous night's US close was non-negative.
Apparent results:
- Skip days (S&P < 0): mean return −0.16%, win rate 38%
- Trade days (S&P >= 0): mean return +0.21%, win rate 74%
- t-test p-value = 0.000

This looked like a genuine, powerful filter. It was not.

### Apr 2026 — Lookahead bug found in the filter

**The bug:** The backtest loop iterated over India exit days (`dt` = open day). It used
`sp_ret[sp_ret.index < dt]`, which picks the US session with calendar date `dt − 1`.
That US session closes at ~2:30 AM IST on `dt` — 11 hours **after** the India buy at
3:15 PM IST on `dt − 1`. The filter was reading data that did not exist at buy time.

**What this means:** The filter was effectively: "trade when the US goes up tonight."
Of course that predicts India's opening gap — it is the cause of it.
It is not tradeable information at 3:15 PM.

**Corrected alignment** — using `sp_ret[sp_ret.index < india_buy_date]` (the previous
India trading day, not the exit day):

| Signal | n | Mean return | Win rate (gross) | p-value |
|--------|---|-------------|------------------|---------|
| Trade days (S&P >= 0) | 994 | +0.179% | 70.5% | — |
| Skip days (S&P < 0) | 804 | +0.232% | 72.5% | — |
| **t-test** | | | | **0.1255** |

The filter has no statistical significance (p = 0.125). Skip days returned slightly more
than trade days. The filter was discarding 45% of sessions for no reason.

### Apr 2026 — Filter removed, full results

No-filter backtest (2019–2026, 1,798 sessions):

| Metric | Value |
|--------|-------|
| Active sessions | 1,796 / 1,798 |
| Gross mean return per session | **+0.2029%** |
| PCT_COST alone (STT both sides) | **0.2225%** |
| Net per session at any capital | **negative** |

---

## Why the strategy cannot work with equity delivery

The dominant cost is STT — Securities Transaction Tax, a government charge of 0.10% on
**both** buy and sell sides of equity delivery trades. Round trip STT alone is 0.20%.

The entire gross edge of +0.2029% is consumed by STT before any other charge is counted.
No capital level makes this profitable:

```
gross_mean (0.2029%) < PCT_COST alone (0.2225%)
→ net per session is negative at infinite capital
```

| Capital | Total cost/session | Net return/session |
|---------|-------------------|--------------------|
| Rs 2L   | 0.299%            | −0.096% |
| Rs 5L   | 0.253%            | −0.050% |
| Rs 10L  | 0.238%            | −0.035% |
| Rs 50L  | 0.226%            | −0.023% |
| ∞       | 0.2225%           | −0.019% |

### Charge model (Zerodha / AngelOne, equity delivery CNC)

| Charge | Rate | Notes |
|--------|------|-------|
| STT buy | 0.10% | Finance Act (No. 2) 2004 — both sides |
| STT sell | 0.10% | |
| Stamp duty | 0.015% | Buy side only |
| Exchange + IPFT + SEBI + GST | ~0.007% | Both sides |
| Brokerage | Rs 0 | Delivery (CNC) is free |
| DP debit charge | Rs 153.40 flat | Rs 13 + 18% GST × 10 stocks (CDSL) |
| **Total** | **0.2225% + Rs 153.40** | Per session |

---

## What was also found along the way (charge model bugs fixed)

During the April 2026 audit, four bugs were found and corrected in the cost model:

1. **PCT doubled** — `PCT_COST_OF_CAPITAL = PCT_COST_OF_TURNOVER * 2` was wrong. Charged 0.244% instead of 0.222%.
2. **Wrong brokerage** — Rs 20/order assumed. Delivery (CNC) is free on Zerodha and AngelOne.
3. **Missing buy-side STT** — Only sell-side STT was modeled. Finance Act 2004 charges both sides.
4. **Wrong DP rate** — Rs 20/scrip assumed. Actual Zerodha CDSL rate is Rs 13 + 18% GST = Rs 15.34/scrip.

These bugs partly offset each other. The corrected break-even capital is ~Rs 0.9L (was estimated at Rs 2.7L). But it is irrelevant — the strategy loses money at any capital because the % cost alone exceeds the % edge.

---

## Could it work differently?

**NIFTY futures (different instrument):** Futures STT is ~0.01% on sell side only (vs 0.20%
round-trip for equity delivery). Total round-trip cost drops to ~0.05%. At that cost level
the +0.20% gross edge survives. But stock-selection alpha would be lost — you would trade
the index, not individual stocks.

**A stronger filter:** The daily variance in overnight returns is large (std ~0.53%).
Some nights return +0.5%, some −0.5%. If a genuinely available signal could select only
the top-third of nights (mean ~+0.40%), that would clear the cost bar. No such signal was
found using correctly aligned data. The best tested signal (lagged S&P 500) had p = 0.717.

Neither path was pursued further. The gap fading system (separate research) has a stronger
and cleaner edge and is the active focus.

---

## What remains in this folder

```
overnight_drift_Strategy/
├── RESEARCH_SUMMARY.md          ← this file
├── data/
│   └── nifty50_constituents.csv ← point-in-time constituent list (2010–2026), useful reference
├── notebooks/
│   └── DEPRECATED.md            ← v1 notebook catalogue
├── scripts/
│   └── DEPRECATED.md            ← v1 script catalogue
└── v2/
    ├── backtest.ipynb           ← full honest backtest (2019–2026, no filter, correct costs)
    ├── daily_signal.ipynb       ← signal generator (kept for reference, not for live use)
    └── README.md                ← v2 file guide
```

All live trading scripts (`config.py`, `utils.py`, `scripts/*.py`, `v2/cron/`) have been deleted.
The v1 notebooks have been deleted. Only the research artifacts remain.

---

*Research started: early 2026*
*Closed: April 2026*
*Primary reason for closure: STT (0.20% round-trip) exceeds gross edge (0.20%). Not fixable within equity delivery.*
