# NIFTY First-Hour Direction — Research Summary

**Project:** Predict NIFTY 50's first-hour direction using overnight global signals, then trade weekly PE options on high-conviction bearish days.

**Status as of April 2026:** Signal edge validated. v4 research framework built — 8 versions (v2 baseline + v4.1–v4.7) each isolating one logical improvement. Paper trading automated on EC2 in two versions (v2 and v4.3).

---

## File Structure (Current)

```
market-research/
├── gap_trading/
│   ├── SUMMARY.md                      ← this file
│   ├── run_everyday.ipynb              ← morning signal check (manual, pre-9:25 AM)
│   ├── analyse_today.ipynb             ← post-trade review (after 11:15 AM)
│   ├── kite_access_token.txt           ← gitignored
│   ├── kite_minute_cache/              ← NIFTY 1-min cache (gitignored)
│   │
│   ├── cron/                           ← EC2 paper trading automation
│   │   ├── v2/                         ← v2 baseline (NKD=F D-1 close)
│   │   │   ├── entry.py, exit.py       ← 9:25 AM entry / 9:27 AM exit monitor
│   │   │   ├── config.py               ← all params
│   │   │   ├── kite_auth.py, kite_data.py
│   │   │   ├── v2_reliable_signals.csv
│   │   │   └── README.md
│   │   └── v4.3/                       ← v4.3 (^N225 trade-day open)
│   │       ├── entry.py                ← uses N225 open at 5:30 IST for SGX signal
│   │       ├── exit.py, config.py, kite_auth.py, kite_data.py
│   │       ├── v2_reliable_signals.csv
│   │       └── README.md
│   │
│   ├── v2/                             ← Phase 2: signal combos + backtests
│   │   ├── v2_india_global.ipynb       ← main combo analysis
│   │   ├── v2_aligned_dataset.csv      ← 741 sessions × 45 features (Apr 2021–Apr 2026)
│   │   ├── v2_reliable_signals.csv     ← 69 significant combos [SOURCE OF TRUTH]
│   │   └── backtesting_2024_options/   ← real 2024 options data backtest [CANONICAL]
│   │       ├── backtest_2024.ipynb     ← reference: 55 trades, 40% WR, 348% XIRR
│   │       └── grid_search_sl_tp.py    ← XIRR-bisection + metrics helpers
│   │
│   └── v4/                             ← Phase 5: incremental signal experiments
│       ├── _engine.py                  ← shared simulation + metrics + JSON export
│       ├── _bs_engine.py               ← Black-Scholes put pricer
│       ├── _make_notebooks.py          ← generates all v4.x notebooks
│       ├── compare_versions.ipynb      ← delta table across all versions
│       ├── v2_backtest/                ← v2 baseline in v4 format
│       ├── v4.1/                       ← NKD=F → ^N225 (D-1 close)
│       ├── v4.2/                       ← include Mondays
│       ├── v4.3/                       ← ^N225 trade-day open (5:30 IST)
│       ├── v4.4/                       ← India VIX regime filter
│       ├── v4.5/                       ← rebuild signals on 11:15 outcome (dir_120)
│       ├── v4.6/                       ← NASDAQ divergence confirmation
│       └── v4.7/                       ← first-10-min NIFTY direction filter
```

---

## Data Sources

### Zerodha Kite Connect API
- **Instrument:** NIFTY 50 index (token: 256265)
- **Data:** Minute-level OHLCV, 9:15 AM – 3:30 PM IST
- **Cached as:** `.pkl` files in `kite_minute_cache/`

### yfinance (Global Indices — overnight signals)
| Ticker | Market | v2 | v4.3+ |
|---|---|---|---|
| `^GSPC` | S&P 500 | D-1 close return | D-1 close return |
| `NKD=F` | Nikkei futures (SGX proxy) | D-1 close return | **replaced** |
| `^N225` | Nikkei 225 cash index | — | **trade-day Open (5:30 IST)** |
| `^GDAXI` | DAX (Germany) | D-1 close return | D-1 close return |
| `^VIX` | CBOE VIX | D-1 close return | D-1 close return |
| `^NSEI` | NIFTY 50 | prev close + gap | prev close + gap |
| `^INDIAVIX` | India VIX | unused in live | used in v4.4 filter |

**Date alignment rule:** For each India session on date T, use the most recent global date strictly before T (max 5-day gap).

### NSE Real Options Data
- **Coverage:** Full year 2024, all weekly expiries
- **Format:** `NIFTY-{EXPIRY_DDMMMYY}-{TRADE_DDMMMYY}.csv`
- **Granularity:** 1-minute candles, 09:15–15:29
- **Size:** ~2.6 GB, 1,400+ files (gitignored)

---

## Phase 2 — V2 Signal Analysis [ACTIVE SIGNALS]

### Signal Definitions
| Signal | Definition |
|---|---|
| Gap Up | NIFTY open > prev close by >0.15% |
| Gap Up Strong | NIFTY open > prev close by >0.50% |
| Gap Down | NIFTY open < prev close by >0.15% |
| Prev India UP/DOWN | Yesterday's NIFTY return positive/negative |
| US UP/DOWN | S&P 500 daily return positive/negative |
| SGX UP/DOWN | Nikkei signal positive/negative (see version differences) |
| DAX UP | DAX daily return positive |
| VIX Rising | VIX daily change > 3% |
| VIX Falling | VIX daily change < 0 |
| VIX Spike | VIX daily change > 5% |

### Top Bearish Combos (source: `v2_reliable_signals.csv`)
| Signal | P(DOWN) | Edge | N |
|---|---|---|---|
| Gap Up + Prev India DOWN + US UP + SGX UP | **74.6%** | +20.1% | 67 |
| Gap Up + Prev India DOWN + SGX UP + DAX UP | **74.1%** | +19.6% | 54 |
| Gap Up + Prev India DOWN + SGX UP + VIX Falling | **72.7%** | +18.2% | 44 |

### Core Insight
NIFTY systematically **fades gap-ups** in the first hour. The bearish signal fires when: NIFTY gapped up at 9:15, the previous Indian session was down, and Asian/US markets rose overnight — meaning the gap-up is purely technical and likely to reverse.

---

## Phase 4d — Canonical Backtest (`backtesting_2024_options/`) [REFERENCE]

**Full real data: entry = 9:25 AM option open, exit = 11:15 AM (candle SL/TP checks).**

| Metric | Value |
|---|---|
| Trades (2024) | 55 |
| Win rate | 40.0% |
| TP hit rate | 36.4% |
| XIRR | ~348% |
| Max drawdown | ~40% |
| Capital | Rs 3,000 starting, 75-lot size |

---

## Phase 5 — V4 Research Framework [CURRENT]

### Design
- One version per hypothesis — only Cell 3 (signal building) changes between versions
- All versions use same 2024 real options data → directly comparable
- Results exported to `results/*.json` per run
- Shared engine in `_engine.py`: simulate_trades(), compute_metrics(), save_results()
- `INITIAL_CAPITAL = 3000.0` fixed across all versions for comparability

### Version Map
| Version | Key Change | Hypothesis |
|---|---|---|
| v2_backtest | Baseline | v2 signals as-is, full charge model |
| v4.1 | NKD=F → ^N225 D-1 close | NKD=F adds USD/JPY noise; cash index cleaner |
| v4.2 | Include Mondays | Monday skip was never empirically tested |
| v4.3 | ^N225 trade-day Open | Fresher signal: 4 hrs of live Tokyo action before entry |
| v4.4 | India VIX regime filter | High VIX → skip (hypothesis: VIX spike = hostile days) |
| v4.5 | Rebuild signals on dir_120 | Signals fitted on 60-min target but trade exits at 11:15 |
| v4.6 | NASDAQ divergence filter | Require NASDAQ confirmation of bearish signal |
| v4.7 | First-10-min NIFTY filter | If NIFTY still extending gap at 9:25 — skip |

### Notable Results (2024 backtest)
| Version | XIRR | Key Finding |
|---|---|---|
| v2_backtest | ~348% | Baseline |
| v4.3 | ~413% | Best improvement: live N225 open adds predictive value |
| v4.1 | ~360% | Modest improvement from cleaner index |
| v4.2 | ~370% | Mondays are fine to include |
| v4.4 | ~203% | **Backfires** — high VIX days are the best days for puts |
| v4.6 | ~low | **Backfires** — NASDAQ was bullish in H2 2024, kills 40+ trades |

### Charge Model (all versions)
```python
BROKERAGE_PER_ORDER = 20.0      # Rs 20 per F&O order (buy + sell = Rs 40)
STT_SELL_RATE       = 0.000625  # 0.0625% on sell-side premium
STAMP_BUY_RATE      = 0.00003   # 0.003% on buy-side premium
EXCHANGE_RATE       = 0.00053   # 0.053% of total turnover
SEBI_RATE           = 0.000001  # 0.0001% of total turnover
GST_RATE            = 0.18      # 18% on (brokerage + exchange + SEBI)
```

---

## Two-Price Workflow (Critical)

| Price | When | Used For |
|---|---|---|
| **NIFTY_OPEN_915** | 09:15 market open | Gap % calculation only |
| **NIFTY_PRICE_925** | 09:25 (10 min after open) | ATM strike selection + entry price |

The 09:25 ATM can differ from 09:15 ATM by 50–150 pts on volatile days. Always compute strike from 09:25 price.

---

## Config Reference (must stay in sync across all files)

```python
GAP_THRESHOLD        = 0.0015   # 0.15%
GAP_LARGE_THRESHOLD  = 0.0050   # 0.50%
VIX_RISING_THRESHOLD = 0.03     # 3%
BASE_RATE            = 54.5     # 54.5% of sessions close DOWN from open
STRIKE_STEP          = 50
LOT_SIZE             = 75
EXPIRY_CHANGE_DATE   = date(2025, 9, 2)   # before: Thursday; after: Tuesday

ENTRY_TIME           = "09:25"
EXIT_TIME            = "11:15"
SL_PCT               = 0.15     # 15% of entry price
TP_PCT               = 0.40     # 40% of entry price
BASE_LOTS            = 2
DTE0_LOTS            = 5
MAX_LOTS             = 10
INITIAL_CAPITAL      = 3000.0   # fixed starting capital for all backtests
```

---

## EC2 Paper Trading Setup

Two independent versions run simultaneously, each in its own folder with its own logs:

```
/home/ec2-user/
├── cron_v2/     ← gap_trading/cron/v2/   (NKD=F D-1 close)
└── cron_v43/    ← gap_trading/cron/v4.3/ (^N225 trade-day open)
```

Cron entries (Asia/Kolkata timezone):
```cron
25 9 * * 2-5  cd /home/ec2-user/cron_v2  && python entry.py >> logs/cron_v2.log  2>&1
27 9 * * 2-5  cd /home/ec2-user/cron_v2  && python exit.py  >> logs/exit_v2.log  2>&1
25 9 * * 2-5  cd /home/ec2-user/cron_v43 && python entry.py >> logs/cron_v43.log 2>&1
27 9 * * 2-5  cd /home/ec2-user/cron_v43 && python exit.py  >> logs/exit_v43.log 2>&1
```

---

## Key Findings Summary

| Finding | Detail |
|---|---|
| Signal edge | Real. 74.6% P(DOWN) on top combo, 0/10,000 Monte Carlo coin-toss simulations beat it. |
| OLD timing (09:15–10:15) | -65.7% net, 23.3% WR — losing strategy. |
| NEW timing (09:25–11:15) | +148.9% net, 40.0% WR, 266% XIRR — winning strategy. |
| Key structural fix | 10-min entry delay eliminates gap-momentum SL hits. TP hits doubled. |
| Best v4 improvement | v4.3 (+65% XIRR vs baseline): ^N225 trade-day open gives fresher Asian signal. |
| Worst v4 change | v4.4 (India VIX filter): high-VIX days are the best put days — filtering them backfires. |
| Starting capital | Fixed at Rs 3,000 across all backtests. If first trade costs more, refill mechanism handles it. |
| Expiry schedule | Thursday through Sep 1 2025; Tuesday from Sep 2 2025 onward. |
| Lot size | 75 units per lot. |
| Breakeven WR | ~27% at SL=15%, TP=40% — current 40% WR has meaningful buffer. |

---

## NSE Event Calendar (skip these days)

| Date | Event |
|---|---|
| Feb 1 (annual) | Union Budget |
| Election results days | General + state elections |
| RBI MPC announcement days | ~6 per year (Feb, Apr, Jun, Aug, Oct, Dec) |
