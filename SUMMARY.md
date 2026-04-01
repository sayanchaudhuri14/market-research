# NIFTY First-Hour Direction — Research Summary

**Project:** Predict NIFTY 50's first-hour direction (9:15–10:15 AM) using overnight global signals, then trade weekly options on high-conviction days.

**Period covered:** April 2021 – March 2026  
**Backtest period:** March 2023 – March 2026 (3 trading years, ~756 trading days)  
**Total tradeable signal days found:** 162 (~54/year, ~4-5/month)

---

## Data Sources

### Zerodha Kite Connect API
- **Instrument:** NIFTY 50 index (token: 256265)
- **Data:** Minute-level OHLCV, 9:15 AM – 3:30 PM IST
- **Chunk limit:** 59 days per API call → fetched in chunks, cached as `.pkl` files in `v2/kite_minute_cache/`
- **Date range fetched:** ~April 2021 – March 2026
- **Total rows:** ~3.5 lakh minute candles

### yfinance (Global Indices)
| Ticker | Market | Purpose |
|---|---|---|
| `^GSPC` | S&P 500 (US) | US overnight return |
| `NKD=F` | Nikkei futures (SGX proxy) | Asia overnight direction |
| `^GDAXI` | DAX (Germany) | Europe overnight direction |
| `^VIX` | CBOE VIX | Global fear/risk sentiment |
| `^NSEI` | NIFTY 50 | Previous India close + gap |
| `^INDIAVIX` | India VIX | Implied volatility level |

**Date alignment rule:** For each India session on date T, use the most recent global trading date strictly before T (max 5 calendar day gap). US closes at ~1:30 AM IST = same calendar day as India session → Friday US close correctly maps to Monday India open.

---

## V1 Analysis (`v1/`)

**Goal:** Baseline exploration — do global markets predict NIFTY's next-day direction?

**Key findings:**
- S&P 500 daily return has ~55–58% directional correlation with NIFTY next morning
- SGX Nikkei futures showed the strongest single-signal correlation
- VIX level alone is a weak predictor; VIX *change* (daily %) is more meaningful
- Base rate established: **54.5% of NIFTY first-hour sessions close DOWN** from open
- Individual signals weak in isolation; combinations needed

**Output:** `v1/v1_aligned_dataset.csv` — 740 sessions × ~20 features

---

## V2 Analysis (`v2/`)

**Goal:** Systematic combination analysis — find statistically significant multi-signal combinations.

### Dataset
- **File:** `v2/v2_aligned_dataset.csv`
- **Rows:** 740 sessions (April 2021 – March 2026)
- **Features (45 columns):** india_date, india_open, gap_pct, prev_india_ret, SP500_ret, SGX_ret, DAX_ret, VIX_US_ret, VIX_INDIA_level, dir_60, ret_60, and derived binary signals

### Signal Definitions (thresholds)
| Signal | Definition |
|---|---|
| Gap Up | NIFTY open > prev close by >0.15% |
| Gap Up Strong | NIFTY open > prev close by >0.50% |
| Gap Down | NIFTY open < prev close by >0.15% |
| Prev India UP/DOWN | Yesterday's NIFTY return > or < 0 |
| US UP/DOWN | S&P 500 daily return > or < 0 |
| SGX UP/DOWN | Nikkei futures return > or < 0 |
| DAX UP | DAX daily return > 0 |
| VIX Rising | VIX daily change > 3% |
| VIX Falling | VIX daily change < 0 |
| VIX Spike | VIX daily change > 5% |

### Methodology
- All 2–4 signal combinations tested (13 binary signals → ~800+ combinations)
- Statistical filter: p-value < 0.05, N ≥ 40 occurrences
- **69 reliable combinations** passed the filter → saved to `v2/v2_reliable_signals.csv`

### Top Bearish Signals (Buy PUT)
*Predict NIFTY first hour DOWN*

| Signal | P(DOWN) | Edge | N | Significance |
|---|---|---|---|---|
| Gap Up + Prev India DOWN + US UP + SGX UP | **73.8%** | +19.3% | 65 | ** |
| Gap Up + Prev India DOWN + SGX UP + DAX UP | **73.1%** | +18.5% | 52 | ** |
| Gap Up + Prev India DOWN + SGX UP | **71.8%** | +17.3% | 71 | ** |

*Without gap (pre-market only):*

| Signal | P(DOWN) | Edge | N |
|---|---|---|---|
| SGX UP + DAX UP + VIX Falling | 65.9% | +11.4% | 135 |
| Prev India DOWN + US UP + SGX UP + DAX UP | 65.8% | +11.3% | 79 |
| US UP + SGX UP + DAX UP + VIX Falling | 64.1% | +9.5% | 128 |

### Top Bullish Signals (Buy CALL)
*Predict NIFTY first hour UP*

| Signal | P(UP) | Edge | N | Significance |
|---|---|---|---|---|
| Gap Down + US UP | **76.2%** | +21.7% | 42 | ** |
| Gap Down + SGX UP | **65.9%** | +11.4% | 44 | * |

*Without gap (pre-market only):*

| Signal | P(UP) | Edge | N |
|---|---|---|---|
| Prev India DOWN + US UP + SGX DOWN | 68.9% | +14.4% | 45 |
| Prev India DOWN + SGX DOWN | 63.2% | +8.7% | 76 |

### Key Insight
Bearish signals are far more abundant and stronger than bullish. NIFTY systematically **fades gap-ups** in the first hour — when global markets have already moved up overnight, the bullish information is fully priced in at open and the first hour reverses. Gap-up bearish days are the highest-conviction trades.

---

## Options Backtesting (`backtesting/`)

### Setup
| Parameter | Value |
|---|---|
| Instrument | NIFTY 50 weekly options |
| Strike | 1-OTM (ATM ± 50 points) |
| Lot size | 75 units |
| Expiry | Nearest Thursday |
| Entry | 9:15 AM (NIFTY open price) |
| Exit window | 9:15 – 10:15 AM |
| Pricing model | Black-Scholes with India VIX as IV proxy |
| IV skew | ×1.30 (DTE≤2), ×1.15 (DTE≤4), ×1.05 (DTE>4) |
| Risk-free rate | 6.5% |
| Brokerage | Rs 80/trade |

*Note: Real historical intraday options data for expired contracts is unavailable via Kite API. Black-Scholes approximation is used for the backtest only. Live trading uses actual market prices.*

### Signal Selection for Backtest
- **BEARISH days:** Top-3 bearish combos from v2_reliable_signals.csv
- **BULLISH days:** Top-3 bullish combos from v2_reliable_signals.csv
- **CONFLICT days** (both bear and bull fire): skipped, no trade
- **Neutral days:** skipped, no trade

### Audit Fixes Applied
Four critical bugs were identified and fixed before final results:

| Bug | Before | After |
|---|---|---|
| Gap Strong threshold | 0.40% (mismatched training) | 0.50% (matches training) |
| VIX Rising threshold | >0% (any move) | >3% (matches training) |
| Thursday expiry | Next Thursday (DTE=7) | Same-day Thursday (DTE=0) |
| Backtest window | 3×365=1095 calendar days | 252×3=756 trading days |

---

## Grid Search Results (`backtesting/grid_search_results/`)

**Grid:** Stop Loss 30–60% × Profit Target 10–40% (49 combinations)  
**Additional targeted runs:** TP extended to 55%

### Full Grid Summary (selected rows)
| SL | TP | Win% | Total P&L | Avg/trade | SL hits | TP hits | Time exits |
|---|---|---|---|---|---|---|---|
| 40% | 10% | 80.2% | Rs +27,553 | Rs +170 | 13 | 129 | 20 |
| 40% | 25% | 68.5% | Rs +77,403 | Rs +478 | 16 | 93 | 53 |
| **40%** | **40%** | **64.2%** | **Rs +1,13,260** | **Rs +699** | **18** | **66** | **78** |
| 40% | 55% | 61.7% | Rs +1,20,510 | Rs +744 | 19 | 41 | 102 |

### Recommended Parameters: **SL = 40%, TP = 40%**

**Why not TP = 55% despite higher total P&L:**
- At TP=55%, only 25% of trades actually hit target (41/162) vs 41% at TP=40% (66/162)
- The Rs 7,000 extra gain over 3 years is marginal and likely overfitted to this dataset
- At TP=40%, the strategy is more repeatable and psychologically easier to execute
- 41% TP hit rate means nearly every other trade exits cleanly — builds confidence

---

## Final Backtest Performance (SL=40%, TP=40%, 1 lot)

### Overall
| Metric | Value |
|---|---|
| Period | March 2023 – March 2026 (2.93 years) |
| Total tradeable days | 162 |
| Win rate | 64.2% |
| Directional accuracy | 61.7% |
| Total P&L (1 lot) | **Rs +1,13,260** |
| Average P&L per trade | Rs +699 |
| SL hits | 18 (11.1%) |
| TP hits | 66 (40.7%) |
| Time exits at 10:15 | 78 (48.1%) |

### By Signal Type
| Segment | Trades | Win% | Total P&L |
|---|---|---|---|
| BEARISH only | 71 | 66.2% | Rs +63,509 |
| BULLISH only | 91 | 62.6% | Rs +49,750 |

### Expected Annual Returns (1 lot, rolling capital)
| Metric | Value |
|---|---|
| Tradeable days per year | ~54 |
| Expected P&L per year | ~Rs 37,000–40,000 |
| Capital required | ~Rs 25,000–30,000 (covers margin + buffer) |
| **CAGR on deployed capital** | **~130–150%** |

*These are backtest estimates using Black-Scholes pricing. Actual results will differ due to real option bid-ask spreads (~Rs 2–5/unit = Rs 150–375/lot slippage per trade), liquidity, and whether the statistical edge holds out-of-sample.*

---

## Daily Workflow — `run_everyday.ipynb`

**Location:** Project root  
**Purpose:** Replace all analysis notebooks with a single action-oriented daily tool

### Two-Phase Structure

**Phase 1 — Pre-market (before 9:15 AM)**
Run Cells 1 → 2 → 3 → 4.
- Fetches global data automatically (yfinance)
- Computes all non-gap signals
- Checks top-3 bearish + top-3 bullish combos (gap combos excluded)
- Outputs: BEARISH / BULLISH / NEUTRAL / CONFLICT

**Phase 2 — Post-open (at/after 9:15 AM)**
Enter actual NIFTY open in Cell 5, run Cell 6.
- Updates gap signals (Gap Up / Gap Up Strong / Gap Down)
- Re-checks all 6 combos including gap-based ones
- Outputs: final signal + exact strike to buy + SL/TP levels

### Execution Guide (from Cell 6 output)
```
Strike     : 1-OTM weekly expiry (nearest Thursday)
BEARISH    : Buy PE (ATM − 50)
BULLISH    : Buy CE (ATM + 50)
Stop Loss  : Exit if premium falls 40% from entry price
Profit Tgt : Exit if premium rises 40% from entry price  
Hard exit  : Close by 10:15 AM regardless of P&L
Lot size   : 1 lot = 75 units
```

### Key Config (must stay in sync with backtest)
```python
GAP_LARGE_THRESHOLD  = 0.0050   # 0.50%
VIX_RISING_THRESHOLD = 0.03     # 3%
STOP_LOSS_PCT        = 0.40
PROFIT_TARGET_PCT    = 0.40
BASE_RATE            = 54.5
```

---

## Automation Path

Full automation is possible using **Zerodha Kite Connect API** (Rs 2,000/month):

| Time | Action |
|---|---|
| 8:45 AM | Script fetches global data, computes pre-market signal |
| 9:15 AM | Script fetches NIFTY open via Kite historical (1-min candle) |
| 9:15 AM | If signal fires: lookup option instrument token, place BUY order |
| 9:15 AM | On fill: place GTT two-leg order (SL trigger + TP limit) |
| 10:14 AM | Force-close any open NIFTY option position |

**One manual step remains:** Kite Connect access tokens expire at midnight. A login URL must be clicked each morning (~30 seconds). Full browser automation is possible but fragile and against Zerodha ToS.

---

## File Structure

```
03_Market_Research/
├── run_everyday.ipynb              ← daily use, run this every morning
├── SUMMARY.md                      ← this file
│
├── v1/
│   ├── v1_india_global.ipynb       ← baseline analysis
│   └── v1_aligned_dataset.csv
│
├── v2/
│   ├── v2_india_global.ipynb       ← full combination analysis
│   ├── v2_aligned_dataset.csv      ← 740 sessions × 45 features
│   ├── v2_reliable_signals.csv     ← 69 statistically significant combos
│   └── kite_minute_cache/          ← NIFTY minute data (.pkl files)
│
└── backtesting/
    ├── backtest_options.ipynb      ← interactive backtest notebook
    ├── py_backtest.py              ← backtest module (used by grid search)
    ├── grid_search.py              ← 49-combination SL/TP grid search
    ├── backtest_trade_log.csv      ← 162 trades with full details
    └── grid_search_results/
        ├── grid_search_full.csv    ← all 49 combinations
        ├── grid_top10.csv          ← top 10 by total P&L
        └── grid_search_heatmaps.png
```

---

## Limitations & Honest Caveats

1. **Black-Scholes pricing in backtest** — real option prices differ due to bid-ask spreads, liquidity, and actual IV. Treat P&L figures as directional estimates, not exact.

2. **In-sample only** — all signal discovery and backtesting uses the same 2021–2026 dataset. True out-of-sample performance is unknown until you trade it live.

3. **Signal decay** — India-global correlations can change. VIX regimes, RBI policy shifts, or NIFTY decoupling from US markets would reduce edge. Re-run v2 analysis every 6 months with fresh data.

4. **Low trade frequency** — ~54 trades/year means high variance. A 6-month period with bad luck could show losses even if the long-run edge holds.

5. **Bearish bias** — the strategy has more and stronger bearish signals than bullish. In a sustained bull market with no gap-ups, trade frequency could drop significantly.

6. **Thursday expiry risk** — on expiry day (DTE=0), option premiums are highly sensitive to NIFTY moves and decay extremely fast. Both SL and TP can trigger within minutes.

---

## Recommended Starting Protocol

| Phase | Duration | Action |
|---|---|---|
| Paper trade | 1 month | Follow every signal, record what you would have done |
| Live 1 lot | 3 months | Trade real money, 1 lot only |
| Validate | After 3 months | Check if win rate is within 5% of backtested 64% |
| Scale | Month 4+ | Move to 2–3 lots if validation passes |
| Re-train | Every 6 months | Refresh v2 dataset, re-check if top-3 signals still hold |
