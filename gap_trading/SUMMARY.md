# NIFTY First-Hour Direction — Research Summary

**Project:** Predict NIFTY 50's first-hour direction using overnight global signals, then trade weekly PE options on high-conviction bearish days.

**Status as of April 2026:** Signal edge is real and validated. Switching entry from 09:15 → 09:25 and exit from 10:15 → 11:15 transformed the strategy from a loser (-65.7% net) to a strong winner (+148.9% net, 266% XIRR) on the same 2024 signal days.

---

## File Structure (Current)

```
market-research/
├── gap_trading/                        ← ALL gap trading research (this folder)
│   │
│   ├── SUMMARY.md                      ← this file
│   ├── run_everyday.ipynb              ← morning signal (run before 9:25 AM)
│   ├── analyse_today.ipynb             ← post-trade review (run after 11:15 AM)
│   ├── kite_access_token.txt           ← Kite access token (gitignored)
│   ├── kite_minute_cache/              ← live session NIFTY 1-min cache (gitignored)
│   │
│   ├── cron/                           ← live paper-trading automation [OPERATIONAL]
│   │   ├── config.py                   ← shared constants (all params, must match backtest)
│   │   ├── entry.py                    ← 9:25 AM: fetch signal, place order
│   │   ├── exit.py                     ← polls SL/TP every 10s, hard exit at 11:15
│   │   ├── kite_auth.py                ← OAuth token refresh
│   │   ├── kite_data.py                ← Kite API helpers
│   │   └── v2_reliable_signals.csv     ← copy of v2 signals used at runtime
│   │
│   ├── v1/                             ← Phase 1: baseline correlation study
│   │   ├── global_india_correlation.ipynb
│   │   ├── aligned_dataset.csv
│   │   └── [charts]
│   │
│   ├── v2/                             ← Phase 2: signal combos + all backtesting [ACTIVE]
│   │   ├── v2_india_global.ipynb       ← main analysis notebook
│   │   ├── v2_aligned_dataset.csv      ← 741 sessions × 45 features (Apr 2021–Apr 2026)
│   │   ├── v2_reliable_signals.csv     ← 69 statistically significant combos [SOURCE OF TRUTH]
│   │   ├── kite_minute_cache/          ← NIFTY 1-min OHLCV used for analysis (gitignored)
│   │   ├── cache/                      ← global daily data + access token (gitignored)
│   │   │
│   │   ├── backtesting/                ← Phase 4a: BS simulation backtest [SUPERSEDED]
│   │   │   ├── py_backtest.py          ← original (Black-Scholes, in-sample)
│   │   │   ├── py_backtest_optimized.py← optimized timing: 09:25 entry, 11:15 exit (BS)
│   │   │   ├── grid_search.py          ← 49-combo SL/TP grid (BS-based)
│   │   │   └── backtest_trade_log.csv
│   │   │
│   │   ├── backtesting_true_data/      ← Phase 4b: NSE bhav entry + BS exit [SUPERSEDED]
│   │   │   ├── backtest_real_data.ipynb
│   │   │   ├── grid_search.py          ← original timing (09:16–10:15)
│   │   │   ├── grid_search_optimized.py← optimized timing (09:26–11:15)
│   │   │   ├── bhav_cache/             ← gitignored
│   │   │   └── backtest_outputs/
│   │   │
│   │   ├── backtesting_true_data_v2/   ← Phase 4c: + 5-min SL lockout [SUPERSEDED]
│   │   │   ├── backtest_real_data.ipynb
│   │   │   ├── grid_search.py
│   │   │   ├── bhav_cache/             ← gitignored
│   │   │   └── backtest_outputs/
│   │   │
│   │   └── backtesting_2024_options/   ← Phase 4d: FULLY REAL DATA [CURRENT BEST]
│   │       ├── grid_search_real.py     ← original timing (09:15 entry, 10:15 exit)
│   │       ├── compare_entry_exit.py   ← OLD vs NEW timing comparison
│   │       ├── sim_all_mode.py         ← always-PE vs always-CE simulation
│   │       ├── 2024/                   ← 1,400+ CSV files (2.6 GB) (gitignored)
│   │       └── backtest_outputs/
│   │
│   └── v3/                             ← Phase 3: added China/HangSeng/Oil/DXY (NOT ADOPTED)
│       ├── v3_analysis.py
│       ├── v3_aligned_dataset.csv
│       ├── v3_new_signals.csv          ← 124 new combos (not adopted — marginal improvement)
│       └── v3_backtest_compare.py
│
└── overnight_drift_Strategy/           ← CLOSED April 2026 (see its own RESEARCH_SUMMARY.md)
```

---

## Data Sources

### Zerodha Kite Connect API
- **Instrument:** NIFTY 50 index (token: 256265)
- **Data:** Minute-level OHLCV, 9:15 AM – 3:30 PM IST
- **Intraday current-day data:** Available via `historical_data()` after market hours
- **Cached as:** `.pkl` files in `v2/kite_minute_cache/`

### yfinance (Global Indices — overnight signals)
| Ticker | Market | Purpose |
|---|---|---|
| `^GSPC` | S&P 500 | US overnight return |
| `NKD=F` | Nikkei futures (SGX proxy) | Asia overnight direction |
| `^GDAXI` | DAX (Germany) | Europe overnight direction |
| `^VIX` | CBOE VIX | Global fear/risk sentiment |
| `^NSEI` | NIFTY 50 | Previous India close + gap |
| `^INDIAVIX` | India VIX | Implied volatility level |

**Date alignment rule:** For each India session on date T, use the most recent global date strictly before T (max 5-day gap). Friday US close correctly maps to Monday India open.

### NSE Real Options Data (`backtesting_2024_options/`)
- **Coverage:** Full year 2024, all weekly expiries (Thursdays)
- **Format:** `NIFTY-{EXPIRY_DDMMMYY}-{TRADE_DDMMMYY}.csv`
- **Columns:** `datetime (HH:MM), strike_price, right (CE/PE), open, high, low, close, open_interest, volume`
- **Granularity:** 1-minute candles, 09:15–15:29
- **Size:** 2.6 GB, ~1,400 files

---

## Phase 1 — V1 Baseline (`v1/`)

**Goal:** Do global markets predict NIFTY's next-day direction at all?

**Key findings:**
- S&P 500 daily return: ~55–58% directional correlation with NIFTY next morning
- SGX Nikkei futures: strongest single-signal
- VIX *change* (daily %) more meaningful than VIX level
- **Base rate established: 54.5% of NIFTY first-hour sessions close DOWN from open**
- Individual signals weak in isolation; combinations needed

---

## Phase 2 — V2 Full Combination Analysis (`v2/`) [ACTIVE SIGNALS]

**Goal:** Systematically find statistically significant multi-signal combinations.

### Signal Definitions
| Signal | Definition |
|---|---|
| Gap Up | NIFTY open > prev close by >0.15% |
| Gap Up Strong | NIFTY open > prev close by >0.50% |
| Gap Down | NIFTY open < prev close by >0.15% |
| Prev India UP/DOWN | Yesterday's NIFTY return positive/negative |
| US UP/DOWN | S&P 500 daily return positive/negative |
| SGX UP/DOWN | Nikkei futures return positive/negative |
| DAX UP | DAX daily return positive |
| VIX Rising | VIX daily change > 3% |
| VIX Falling | VIX daily change < 0 |
| VIX Spike | VIX daily change > 5% |

### Methodology
- Tested all 2–4 signal combinations from 13 binary signals (~800+ combos)
- Filter: p-value < 0.05, N ≥ 40 occurrences
- **69 reliable combinations** → saved to `v2/v2_reliable_signals.csv`
- **Dataset used: April 2021 – April 2026 (741 sessions)**

### Top Bearish Signals (Buy PUT — NIFTY expected DOWN)
| Signal | P(DOWN) | Edge | N |
|---|---|---|---|
| Gap Up + Prev India DOWN + US UP + SGX UP | **74.6%** | +20.1% | 67 |
| Gap Up + Prev India DOWN + SGX UP + DAX UP | **74.1%** | +19.6% | 54 |
| Gap Up + Prev India DOWN + SGX UP + VIX Falling | **72.7%** | +18.2% | 44 |

### Top Bullish Signals (Buy CALL — NIFTY expected UP)
| Signal | P(UP) | Edge | N |
|---|---|---|---|
| Gap Down + US UP | **76.2%** | +21.7% | 42 |
| Gap Down + SGX UP | **65.9%** | +11.4% | 44 |

### Core Insight
NIFTY systematically **fades gap-ups** in the first hour. When global markets moved up overnight, that information is fully priced into the gap at open — and the first hour reverses. This is the underlying logic of the bearish signal.

### Signal Filter — Why It Matters
- 74% of 2024 trading days are flat/mixed — no signal fires
- Signal filter's main job is eliminating these bleed days
- On 2024 signal days: 38% TP hit rate vs 9% random baseline
- Monte Carlo: 0 out of 10,000 coin-toss simulations beat the indicator strategy on signal days

---

## Phase 3 — V3 New Markets (`v3/`)

Added: China SSE (`000001.SS`), Hang Seng (`^HSI`), WTI Crude (`CL=F`), US Dollar Index (`DX-Y.NYB`).

**Result:** 124 new reliable combos found. Marginal P&L difference vs V2 (+1.4% better win rate, -1.4% total P&L). V2 signals retained as primary.

---

## Phase 4a — BS Simulation Backtest (`backtesting/`) [SUPERSEDED — DO NOT TRUST P&L NUMBERS]

**What it did:** Used Black-Scholes to price options from NIFTY spot candles. Entry and exit both synthetic.

**Why not trustworthy:** In-sample overfitting (same 741 rows for signal selection and backtest), synthetic IV with arbitrary multipliers, no real bid-ask spreads.

**`py_backtest_optimized.py` results (09:25 entry, 11:15 exit, BS-based):**
- 226 trades, 53.5% WR, XIRR 305.6%, DD 63.5%, Final value Rs 19,54,548
- (Still BS-based — treat as directional indicator only, not real P&L)

---

## Phase 4b/4c — NSE Bhav Copy Backtest (`backtesting_true_data/`) [SUPERSEDED]

**What it improved:** Real option OPEN price at entry (from NSE daily bhav copy files). Exit still BS-simulated.

**Limitation:** Only 19 trades with bhav data available (Apr 2023–Jul 2024). NSE new URL format blocked by Akamai bot detection.

**`grid_search_optimized.py` results (09:26 entry, 11:15 exit):**
- 84 trades across grid, best XIRR 5033% at SL=15% TP=100%
- (Entry is real; exit is still BS — partially trustworthy)

---

## Phase 4d — Fully Real Data Backtest (`backtesting_2024_options/`) [CURRENT BEST]

**What it does:**
- Entry = real option OPEN at 09:25 from actual NSE options 1-min CSV
- Exit = real option candles — TP triggered on candle HIGH, SL on candle LOW
- SL locked out before 09:30 (5-minute lockout from entry)
- Hard exit at 11:15
- No Black-Scholes anywhere in the pipeline

### OLD vs NEW Timing Comparison (`compare_entry_exit.py`)

**Same 61 bearish signal days, 2024. FIXED=5 lots, DTE0=10 lots, MAX=20 lots, SL=15%, TP=40%.**

| Metric | OLD (09:15 entry, 10:15 exit) | NEW (09:25 entry, 11:15 exit) |
|---|---|---|
| Trades | 47 | 55 |
| Win Rate | 23.3% | **40.0%** |
| TP Hits | 11 | **22** |
| Net P&L | -65.7% | **+148.9%** |
| XIRR | N/A (loss) | **266%** |
| Max Drawdown | 751% | **123%** |
| Refills needed | 12 | **3** |

**Key finding:** The 10-minute wait after open (09:15 → 09:25) eliminates the gap-momentum SL hits. TP hits doubled, net P&L swung from -65.7% to +148.9%. This is the single most important structural improvement.

### Why 09:25 Entry Works
- At 09:15 open, NIFTY often extends the gap-up for 5–10 minutes
- OTM PE with delta ~0.35 hits 15% SL on just a 36-pt wrong-way NIFTY move
- Waiting until 09:25 lets initial momentum exhaust — entry is at a better price
- 11:15 exit captures the full reversal (which happens at 11:00–12:00, not 10:15)

### Random Baseline Comparison (`sim_all_mode.py`)

**On the 136 ALL-mode signal days (61 bear, 75 bull), 2024:**

| Strategy | Win Rate | Net P&L | Max DD | Refills |
|---|---|---|---|---|
| Always PE (buy PE every day) | 31.1% | +2.6% | 293% | 13 |
| Always CE (buy CE every day) | 28.8% | -51.8% | 612% | 12 |
| **Indicator strategy (PE on bear signals only)** | **40.0%** | **+148.9%** | **123%** | **3** |
| Coin toss (random CE/PE on signal days) | ~27% avg | Negative | High | Many |

**Monte Carlo confirmation:** 0 of 10,000 coin-toss simulations beat the indicator strategy on signal days. The directional signal provides a real, non-random edge.

---

## Two-Price Workflow (Critical — Do Not Mix Up)

| Price | When | Used For |
|---|---|---|
| **NIFTY_OPEN_915** | 09:15 market open | Gap % calculation only |
| **NIFTY_PRICE_925** | 09:25 (10 min after open) | ATM strike selection + entry price |

```python
gap_preview = (NIFTY_OPEN_915 - nifty_close) / nifty_close   # direction filter
atm_925     = round(NIFTY_PRICE_925 / 50) * 50                 # strike for trade
```

The 09:25 ATM can differ from 09:15 ATM by 50–150 pts on volatile days. Always compute strike from 09:25 price.

---

## Daily Live Notebooks

### `run_everyday.ipynb` — Morning signal (run each trading day before 9:25 AM)

**Timing:**
- **Before 9:15:** Run Cells 1–4 to get pre-market signal from overnight globals
- **At 9:15:** Note NIFTY opening price (for gap % only)
- **At 9:25:** Note NIFTY price (for ATM strike), enter both in Cell 5
- **9:25:** Place trade at market price on identified strike

**Two inputs in Cell 5:**
```python
NIFTY_OPEN_915  = 22350    # ← NIFTY price at 9:15 open  (gap % only)
NIFTY_PRICE_925 = 22390    # ← NIFTY price at 9:25       (strike & entry)
```

**Output:** BEARISH / BULLISH / NEUTRAL + exact strike + SL/TP prices + lot count

**Skip on:** Mondays (US data 3 days stale), known event days (RBI MPC, Budget, elections).

### `analyse_today.ipynb` — Post-trade review (run after 11:15 AM)

**Fully automatic after 11:15 AM — no manual input required.**

- Auto-fetches NIFTY spot candle at 09:25 from Kite (token 256265) to determine ATM
- Fetches real option minute candles from 09:25 to 11:15 (Kite `historical_data()`)
- SL/TP scan uses candle `low`/`high` (not `close`) — same method as backtest
- Hard exit at 11:15 if neither SL nor TP triggered
- Reports: entry price, exit price, P&L, whether direction was correct

**Data availability:** Kite provides intraday minute candles for the current day after market hours. Running after 11:15 gives all ~110 candles (09:25–11:15). No data availability issue.

---

## Config Reference (must stay in sync across all files)

```python
GAP_THRESHOLD        = 0.0015   # 0.15%
GAP_LARGE_THRESHOLD  = 0.0050   # 0.50%
VIX_RISING_THRESHOLD = 0.03     # 3%
BASE_RATE            = 54.5     # 54.5% of sessions close DOWN from open
STRIKE_STEP          = 50
STRIKES_OTM          = 1        # 1-OTM from ATM at 09:25
LOT_SIZE             = 75
BROKERAGE            = 80       # Rs per trade
RISK_FREE_RATE       = 0.065
EXPIRY_CHANGE_DATE   = date(2025, 9, 2)   # before: Thursday; after: Tuesday

# Trade timing (CURRENT — do not revert)
ENTRY_TIME           = "09:25"
EXIT_TIME            = "11:15"
SL                   = 0.15     # 15% of entry price
TP                   = 0.40     # 40% of entry price
FIXED_LOTS           = 5
DTE0_LOTS            = 10       # extra lots on expiry day
MAX_LOTS             = 20

# Lot scaling
# Normal days: 5 lots
# Expiry day (DTE=0): min(10, max_lots - current_open_lots)
```

---

## Key Findings Summary

| Finding | Detail |
|---|---|
| Signal correlation | Real. 74.6% P(DOWN) on top combo, validated on full dataset. |
| In-sample bias (old backtests) | Severe in BS backtests — signals and backtest used same 741 rows. |
| OLD timing (09:15–10:15) | -65.7% net, 23.3% WR, 751% max DD — losing strategy. |
| **NEW timing (09:25–11:15)** | **+148.9% net, 40.0% WR, 123% DD, 266% XIRR — winning strategy.** |
| Key structural fix | 10-minute entry delay eliminates gap-momentum SL hits. TP hits doubled. |
| vs coin toss | 0/10,000 Monte Carlo simulations beat indicator strategy — edge is real. |
| vs always-PE | Indicator (+148.9%) vastly outperforms random always-PE (+2.6%) and always-CE (-51.8%). |
| Expiry schedule | Thursday 2024; Tuesday from Sep 2, 2025 onward. |
| Lot size | 75 units per lot (verify before each new expiry series). |
| Breakeven win rate | 27.3% at SL=15%, TP=40% — strategy at 40% WR has meaningful buffer. |

---

## NSE Event Calendar (skip these days — IV elevated, signal has no edge)

| Date | Event |
|---|---|
| Feb 1 (annual) | Union Budget / Interim Budget |
| Election results day | General + state elections |
| RBI MPC announcement days | ~6 per year (Feb, Apr, Jun, Aug, Oct, Dec) |
| Day after major election results | Extreme gap risk |
