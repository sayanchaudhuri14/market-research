# v9 — v4.3 Combos on sim_cache + VIX/Gap Gate + DTE/Expiry Analysis

## Purpose
Apple-to-apple comparison: reproduce the exact v4.3 combo filter (top-10 bearish combos from v2_reliable_signals.csv) on the sim_cache, so v4.3, v7, and v8 can all be evaluated on identical underlying trade outcomes. Also tested VIX and gap_normalized gates as post-filters, and discovered the structural impact of the Sep 2025 NIFTY expiry change.

## Method
- Data source: `v6/sim_cache.csv` (402 rows, Jan 2024 – Mar 2026)
- Signal filter: top-10 DOWN combos from `v2/v2_reliable_signals.csv` (same as cron/v4.3)
- Capital-compounding backtest engine (SL=15%, TP=40%, LOT_SIZE=75, BASE=5, MAX=25, DTE0_MAX=10)
- **Gate features** added from `v2/v2_aligned_dataset.csv`:
  - `VIX_INDIA_pct` = rolling 252-day percentile rank of VIX India level
  - `gap_normalized` = gap_pct / 20-day realized vol of NIFTY
  - VIX gate: VIX_INDIA_pct ≤ 0.65
  - Gap gate: |gap_normalized| ∈ [0.10, 0.80]
- **Expiry change**: `EXPIRY_CHANGE = date(2025, 9, 2)` — NIFTY weekly expiry moved Thursday → Tuesday

## Key Files
- `backtest_v9.ipynb` — full backtest notebook (combo filter → VIX/gap gates → DTE analysis)

---

## Results — Full Period 2024-01 to 2026-03 (In-Sample Combos)

| Version | Trades | Win% | ROI | MaxDD |
|---|---|---|---|---|
| v9 no gate | 120 | 31.7% | +147.7% | 34.2% |
| v9 + Gap gate | 92 | 30.4% | +119.1% | 36.0% |
| v9 + VIX gate | 56 | 30.4% | +44.3% | 56.8% |
| v9 + Both gates | 45 | 28.9% | +20.5% | 54.8% |

**All in-sample** — combos were selected on the same 2024-2026 data.

## Results — OOS Slices (Combos Still In-Sample)

### Jul 2025 – Mar 2026 (v7-equivalent window)
| Version | Trades | Win% | ROI | MaxDD |
|---|---|---|---|---|
| v9 no gate | 34 | 26.5% | -57.9% | 77.3% |
| v9 + VIX gate | 27 | 25.9% | -54.8% | 77.3% |
| v9 + Both gates | 22 | 27.3% | -39.0% | 65.0% |
| v7 L1 genuine OOS | 10 | 40.0% | +8.4% | 21.0% |

### Jan 2025 – Mar 2026 (v8-equivalent window)
| Version | Trades | Win% | ROI | MaxDD |
|---|---|---|---|---|
| v9 no gate | 59 | 28.8% | -12.8% | 66.5% |
| v9 + Both gates | 27 | 25.9% | -59.3% | 70.2% |
| v8 L1 walk-forward | 24 | 25.0% | -42.3% | 47.1% |
| v8 RF walk-forward | 8 | 25.0% | -6.7% | 22.0% |

## Year-by-Year (v9 no gate, in-sample)
| Year | Trades | Win% | PnL (Rs) |
|---|---|---|---|
| 2024 | 61 | 34.4% | +4,01,027 |
| 2025 | 48 | 27.1% | -69,306 |
| 2026 | 11 | 36.4% | -36,274 |

---

## Expiry Change Analysis (MOST IMPORTANT FINDING)

On **Sep 2, 2025**, NIFTY weekly options expiry moved from **Thursday to Tuesday**. This is a structural break that completely changed which DTE values the strategy trades on.

### DTE Distribution Before vs After

| Regime | DTE values | Days of week |
|---|---|---|
| Thursday expiry (before Sep 2) | 0, 1, 2, 6 | Thu=0, Wed=1, Tue=2, Fri=6 |
| Tuesday expiry (after Sep 2) | 0, 4, 5, 6 | Tue=0, Wed=6, Thu=5, Fri=4 |

DTE=1 and DTE=2 — the historically best performers — **no longer exist** under the new system.

### Win Rate by DTE

| Regime | DTE | N | Win% |
|---|---|---|---|
| Thursday (old) | 0 | 25 | 28.0% |
| Thursday (old) | 1 | 19 | 31.6% |
| Thursday (old) | **2** | 29 | **51.7%** ← was best |
| Thursday (old) | 6 | 18 | 16.7% |
| Tuesday (new) | **0** | 11 | **45.5%** ← now best |
| Tuesday (new) | 4 | 6 | **0.0%** ← worst |
| Tuesday (new) | 5 | 7 | 14.3% |
| Tuesday (new) | 6 | 5 | 20.0% |

### Weekday Win Rates After Sep 2025

| Day | DTE | N | Win% |
|---|---|---|---|
| Tuesday | 0 | 11 | **45.5%** |
| Wednesday | 6 | 5 | 20.0% |
| Thursday | 5 | 7 | 14.3% |
| **Friday** | **4** | **6** | **0.0%** |

Friday under the new regime: **6 trades, 6 losses, 0 wins.**

### Combo Win Rate Collapsed After the Change

```
Combo win rate BEFORE Sep 2 2025 : 34.1%  (91 trades)
Combo win rate AFTER  Sep 2 2025 : 24.1%  (29 trades)  ← below breakeven
```

### DTE=0 Filter Backtest (Sep 2025 – Mar 2026)

| Version | Trades | Win% | ROI | MaxDD |
|---|---|---|---|---|
| **DTE=0 only (Tuesday)** | **11** | **45.5%** | **+28.5%** | **5.9%** |
| DTE≠0 (Thu/Fri/Wed) | 18 | 11.1% | -83.2% | 83.2% |

The separation is extreme. The 18 non-DTE=0 trades after the expiry change destroyed 83% of capital with only 2 wins. The 11 DTE=0 trades made +28.5% with a maximum drawdown of only 5.9%.

Note: DTE=0 trades are automatically capped at 10 lots (DTE0_MAX_LOTS), which limits both upside and downside — contributing to the low MaxDD.

### Why the Sep 2025 Streak Was So Damaging

The VIX gate offered no protection because VIX India was at a **1-year low** during Sep 2025 (VIX_INDIA_pct = 0.00–0.12, absolute level 10–12). Every combo-fired day in Sep 2025 passed the VIX gate. The damage came from:
1. A bull trend regime — gap-up days continued upward instead of reversing
2. The combo firing on DTE=4 (Friday) and DTE=5 (Thursday) — the two worst days under Tuesday expiry
3. Full 25-lot sizing on these high-DTE trades (vs 10-lot cap on DTE=0) amplified losses

---

## Key Findings (All)

1. **VIX gate does not help in-sample or on the Sep 2025 OOS period.** Sep 2025 had ultra-low VIX — the gate passes every trade in that period. The gate only helps in high-VIX environments (like Mar 2026).

2. **The expiry change (Sep 2, 2025) is the single biggest structural break.** The strategy was tuned on Thursday-expiry dynamics (DTE=0,1,2,6). Under Tuesday expiry it fires on DTE=4 (Fri) and DTE=5 (Thu) which have near-zero win rates.

3. **The fix is a DTE filter, not a VIX filter.** Post Sep 2, 2025: trade only on Tuesday (DTE=0). Skip Thursday (DTE=5) and Friday (DTE=4). This converts an -83% losing subset into a +28.5% winning subset.

4. **In-sample ROI (+147.7%) is almost entirely a 2024 artefact** under Thursday expiry where DTE=2 had a 51.7% win rate. That DTE no longer exists.

5. **v7 (genuine OOS) remains the best positive OOS result** in the Jul-Mar window: 10 trades, 40%, +8.4% — it achieved this by being highly selective and firing less on the bad DTE days.

---

## Recommended Action

Add a one-line DTE gate to `cron/v4.3/entry.py`:
```python
if trade_date >= date(2025, 9, 2) and dte != 0:
    skip  # only trade on Tuesday expiry day under new weekly regime
```

## Status
Active reference notebook. Contains the most complete comparison of all filters. The DTE=0 finding is the most actionable result from this entire research series.
