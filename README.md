# NIFTY Gap Trading Research

Personal research project. The core idea: NIFTY systematically **fades gap-ups** in the first hour. When global markets close up overnight, that move is fully priced into the 9:15 open — and the first 2 hours tend to reverse. This repo is the full journey of finding, validating, and trading that edge.

---

## The Strategy

Buy a 1-OTM NIFTY PUT at **9:25 AM** on days when a specific combination of overnight global signals fires. Exit at **11:15 AM** (or on SL/TP, whichever comes first).

- **Entry**: 10 minutes after open, not at open — lets the gap-momentum exhaust before entering
- **SL**: 15% of entry premium
- **TP**: 40% of entry premium
- **Hard exit**: 11:15 AM

That 10-minute wait was the single most important finding. The same signals at 9:15 entry lost 65.7%. At 9:25 entry: +148.9%, 40% win rate, 266% XIRR on 2024 data.

---

## Signals

Built on 741 sessions of data (Apr 2021 – Apr 2026). Tested all 2–4 signal combinations from 13 binary features. 69 statistically significant bearish combos emerged.

The top one:
> **Gap Up + Prev India DOWN + US UP + SGX UP** → 74.6% P(NIFTY DOWN), Edge +20.1%, N=67

These aren't predictions — they're filters. 74% of days are flat/mixed and get skipped. The strategy only trades on the ~25% of days where the signal fires.

0 out of 10,000 Monte Carlo coin-toss simulations beat the indicator strategy on signal days.

---

## Repo Structure

```
gap_trading/
├── v2/                         Signal analysis + canonical 2024 backtest
│   ├── v2_india_global.ipynb   Full combo analysis (the main research notebook)
│   ├── v2_aligned_dataset.csv  741 sessions × 45 features
│   ├── v2_reliable_signals.csv 69 validated combos [source of truth]
│   └── backtesting_2024_options/
│       └── backtest_2024.ipynb Real options data, 55 trades, 40% WR, ~348% XIRR
│
├── v4/                         Incremental signal experiments
│   ├── _engine.py              Shared simulation engine (all versions)
│   ├── compare_versions.ipynb  Side-by-side delta table
│   ├── v2_backtest/            v2 baseline in v4 format
│   ├── v4.1/ → v4.7/           One hypothesis per version (see below)
│   └── results/*.json          Timestamped results per run
│
└── cron/                       EC2 paper trading automation
    ├── v2/                     Live: NKD=F D-1 close for SGX signal
    └── v4.3/                   Live: ^N225 trade-day open (5:30 IST) for SGX signal
```

---

## What v4 Tests

Each version changes exactly one thing vs the v2 baseline:

| Version | Change | Result |
|---------|--------|--------|
| v4.1 | Replace NKD=F with ^N225 D-1 close | +12% XIRR — cleaner signal, no USD/JPY noise |
| v4.2 | Include Mondays | +22% XIRR — Monday skip was never justified |
| **v4.3** | ^N225 trade-day open (5:30 IST) | **+65% XIRR — best improvement** |
| v4.4 | India VIX > 20 → skip | −145% XIRR — backfires badly, high-VIX days are the best put days |
| v4.5 | Rebuild signals on 11:15 outcome | Marginal change in combo ordering |
| v4.6 | Require NASDAQ confirmation | Nearly no trades — NASDAQ was bullish all H2 2024 |
| v4.7 | First-10-min NIFTY direction filter | Reduces trade count, modest improvement |

v4.3 is the current live version running on EC2.

---

## Live Paper Trading

Two versions run simultaneously on EC2 (Asia/Kolkata):

```
25 9 * * 2-5  python3 .../cron/v2/entry.py    # v2 baseline
27 9 * * 2-5  python3 .../cron/v2/exit.py
25 9 * * 2-5  python3 .../cron/v4.3/entry.py  # v4.3 live
27 9 * * 2-5  python3 .../cron/v4.3/exit.py
```

Authentication is fully automated (Kite Connect + TOTP via pyotp, no browser). Token shared between both versions to avoid session conflicts.

---

## Data

- **Global signals**: yfinance daily (`^GSPC`, `^N225`, `^GDAXI`, `^VIX`, `^NSEI`)
- **Live prices**: Zerodha Kite Connect API (NIFTY spot, option premiums, 9:15 candle)
- **Backtest options data**: NSE real 1-min option candles, full year 2024, ~2.6 GB (gitignored)
- **Expiry**: Thursday through Sep 1 2025 → Tuesday from Sep 2 2025 onward

---

## Stack

Python · Jupyter · yfinance · Zerodha Kite Connect · pandas · pyotp · EC2
