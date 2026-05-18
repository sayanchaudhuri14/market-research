# NIFTY Gap Strategy — Live Paper Trading (v4.3.2)

Identical to v4.3 with one additional skip condition: the **DTE=0 gate**.

From Sep 2, 2025 onward (when NIFTY weekly expiry moved Thursday → Tuesday), the
strategy only trades on expiry day itself (DTE=0, i.e. Tuesday). All other days
in the new regime — Wednesday (DTE=6), Thursday (DTE=5), Friday (DTE=4) — are skipped.

Before Sep 2, 2025 the gate is inactive and all DTE values trade normally (identical to v4.3).

---

## Why DTE=0

Under Thursday expiry (pre-Sep 2025), the combo strategy fired on DTE=0/1/2/6. DTE=2 (Wednesday)
was historically the best at 51.7% win rate. Under Tuesday expiry the DTE distribution shifted:
DTE=4 (Friday) and DTE=5 (Thursday) replaced DTE=1 and DTE=2. These new DTEs have 0% and 14%
win rates — below the 27.3% breakeven.

| Regime | DTE=0 win% | Other DTEs |
|---|---|---|
| Thursday expiry (old) | 28% (one of four DTEs) | DTE=2 was best at 51.7% |
| Tuesday expiry (new) | **45.5%** | DTE=4=0%, DTE=5=14%, DTE=6=20% |

Backtest on Jul 2025 – Mar 2026 (sim_cache, in-sample combos):

| Version | Trades | Win% | ROI | MaxDD |
|---|---|---|---|---|
| v4.3 no filter | 34 | 26.5% | -57.9% | 77.3% |
| v4.3.2 DTE=0 gate | 12 | **50.0%** | **+33.1%** | **5.7%** |

See `v9/README.md` for full analysis.

---

## Change from v4.3

Single addition in `entry.py` after the expiry/DTE computation (step 7b):

```python
if today >= EXPIRY_CHANGE_DATE and dte != 0:
    skip  # only DTE=0 (Tuesday) traded under new expiry regime
```

All other logic — signals, combo matching, lot sizing, charges, exit monitoring — is unchanged.

---

## Files

| File | Purpose |
|------|---------|
| `entry.py` | 9:25 AM — signals + DTE gate + buy |
| `exit.py` | 9:27 AM — polls SL/TP until 11:15 hard exit |
| `config.py` | All parameters (unchanged from v4.3) |
| `kite_data.py` | Kite API helpers |
| `v2_reliable_signals.csv` | Top-10 bearish combo definitions |

---

## Cron setup (EC2, Asia/Kolkata timezone)

```cron
# v4.3.2 Entry: 9:25 AM Tue–Fri
25 9 * * 2-5  cd /path/to/cron_v432 && python entry.py >> logs/cron_v432.log 2>&1

# v4.3.2 Exit monitor: 9:27 AM Tue–Fri
27 9 * * 2-5  cd /path/to/cron_v432 && python exit.py >> logs/exit_v432.log 2>&1
```
