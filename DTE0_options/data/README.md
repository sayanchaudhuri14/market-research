# data/ — Data Loading Utilities

Shared data access layer for backtesting. Handles two different on-disk formats for NIFTY options tick data and provides the charge calculator used throughout the backtest notebooks.

---

## Files

| File | Purpose |
|---|---|
| `data_config.py` | All paths, loaders, helpers — single import for backtest notebooks |

---

## data_config.py

### Data Formats

Two formats exist on disk, selected automatically by expiry date:

**Old format** (Jan–Sep 2024, `old_monthly_2024/`):
- One CSV per `(expiry_date, trade_date)`, all strikes in one file
- Path: `old_monthly_2024/2024{MON}/NIFTY-{expiry}-{trade_date}.csv`
- Columns: `datetime (HH:MM), strike_price, right, open, high, low, close, open_interest, volume`

**New format** (Oct 2024+, `nifty_expiry_data/nifty/`):
- One CSV per `(expiry_date, strike, right)`
- Path: `nifty/{YYYY-MM-DD}/NIFTY_{strike}_{right}_{DD_MMM_YY}.csv`
- Columns: `timestamp (ISO), open, high, low, close, volume, oi`

Cutoff: `date(2024, 10, 3)` — expiries on or after this date use new format.

### Key Functions

| Function | Returns |
|---|---|
| `load_option_file(trade_date, expiry_date)` | DataFrame with minute OHLCV for all strikes, both formats auto-routed |
| `load_expiry_dates(year)` | List of NIFTY weekly expiry dates for a given year (2024 only, from CSV) |
| `load_all_expiry_dates()` | All expiries Jan 2024–Mar 2026 (old CSV + new folder names) |
| `generate_trading_days(start, end, holidays)` | All weekdays in range minus holidays |
| `load_nifty_spot(year)` | NIFTY 50 minute OHLCV (2024 only, for ATM fallback) |
| `compute_charges(legs_entry, legs_exit)` | Total Zerodha charges (Rs) for a round-trip multi-leg trade |
| `d2dmy(d)` | Format date as `DDMMMYY` (used in old-format filenames) |
| `parse_dmy(s)` | Parse `DDMMMYY` string back to `date` |

### Charge Model (`compute_charges`)

Zerodha brokerage for options:
- Brokerage: Rs 20 per order × (n_entry_legs + n_exit_legs)
- STT: 0.0625% of sell-side premium value
- Exchange: 0.053% of turnover (both sides)
- SEBI: Rs 10 per Rs 1 crore turnover
- Stamp: 0.003% of buy-side value (entry only)
- GST: 18% on (brokerage + exchange)

### ATM Source

Primary: Kite minute cache (`kite_minute_cache/`) at 09:25 open — same source used by live cron.  
Fallback: `load_nifty_spot()` from old monthly CSVs (2024 only).
