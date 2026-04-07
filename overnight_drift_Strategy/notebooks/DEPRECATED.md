# Notebooks — Deprecated

These notebooks were part of the v1 research phase. They are kept for reference only.
**Do not use for live trading decisions. Use the `v2/` folder instead.**

---

## 01_data_audit.ipynb
**Purpose:** Verified OHLC data quality from the Kite API cache — date ranges, missing sessions, open price sanity checks.  
**Why deprecated:** v2 fetches directly from yfinance with `auto_adjust=True`. No local cache to audit. Data quality is yfinance's responsibility.

## 02_signal_analysis.ipynb
**Purpose:** Validated that the overnight momentum signal has predictive power — autocorrelation, quintile analysis, Information Coefficient.  
**Why deprecated:** Signal validity was confirmed. The IC and quintile results supported building the strategy. This notebook is a one-time validation artifact — the conclusion is baked into v2.

## 03_backtest.ipynb
**Purpose:** First full backtest (2021–2026) using Kite OHLC cache.  
**Why deprecated:** Used the **current** NIFTY 50 composition for the entire historical period — i.e., survivorship bias. Showed ~16% XIRR which is inflated by ~6–7% due to this flaw. Replaced by `v2/backtest.ipynb` which uses point-in-time constituents.

## 04_live_signal.ipynb
**Purpose:** Daily-use notebook using Kite API — authenticated session, live LTP fetch, signal generation.  
**Why deprecated:** Requires Kite login and access token refresh every day. Replaced by `v2/daily_signal.ipynb` which uses yfinance — no login needed, two cells, runs in 30 seconds.

## 05_custom_backtest.ipynb
**Purpose:** First honest backtest — yfinance data, user-set date range, point-in-time constituents, no Kite dependency.  
**Why deprecated:** No filter applied. Equal-weight benchmark and bottom-10 comparisons included but no US filter. Superseded by `06_custom_backtest_withVIX.ipynb` and then `v2/backtest.ipynb`.  
**Key finding from this notebook:** After adding point-in-time constituents, real XIRR dropped from 16.7% (biased) to 9.46% (honest). Confirmed survivorship bias was the main driver of inflated v1 results.

## 06_custom_backtest_withVIX.ipynb
**Purpose:** Tested India VIX filter and US S&P 500 filter. Key discovery notebook.  
**Why deprecated:** VIX filter was shown to be harmful (skipped profitable days). US filter was shown to be powerful (+45% XIRR, 76% win rate, Sharpe 6.24). Freshness filter (drop Mondays) also tested and rejected — Mondays have 73.7% win rate, same as other days.  
**Keep this notebook** if you want to re-run filter experiments. Do not use for live decisions.  
**Key findings:**
- VIX filter: skip. It hurts.
- US S&P 500 filter: use it. p-value = 0.000, win rate 74.3% vs 38.4% on skip days.
- Monday staleness: not a problem. Do not drop Mondays.

## 07_daily_signal.ipynb
**Moved to `v2/daily_signal.ipynb`.** This file in the notebooks folder is the same notebook — edit the v2 copy going forward.
