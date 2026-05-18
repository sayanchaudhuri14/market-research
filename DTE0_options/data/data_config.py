"""Path references and shared loaders for DTE0_options.

Two data formats are supported:
- Old format (Jan–Sep 2024): monthly folders, one file per (expiry, trade_date) with all strikes
  File: old_monthly_2024/2024{MON}/NIFTY-{expiry}-{trade_date}.csv
  Columns: datetime (HH:MM), strike_price, right, open, high, low, close, open_interest, volume

- New format (Oct 2024+): expiry-date folders, one file per (expiry, strike, right)
  File: nifty_expiry_data/nifty/{YYYY-MM-DD}/NIFTY_{strike}_{right}_{DD_MMM_YY}.csv
  Columns: timestamp (ISO), open, high, low, close, volume, oi

load_option_file() selects format automatically based on expiry date.
"""
from pathlib import Path
from datetime import date, timedelta
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent
_ROOT = _HERE.parent.parent                               # market-research/

OPTIONS_DATA_DIR = _ROOT / "options minutewise data"
OLD_DATA_DIR     = OPTIONS_DATA_DIR / "old_monthly_2024"
NEW_DATA_DIR     = OPTIONS_DATA_DIR / "nifty_expiry_data" / "nifty"

# Legacy aliases kept for backward compatibility
REAL_DATA_DIR  = OLD_DATA_DIR
NIFTY_SPOT_DIR = OLD_DATA_DIR / "2024Nifty"
EXPIRY_CSV     = OLD_DATA_DIR / "expiry.csv"

# Expiries from this date onwards use the new per-strike format
_NEW_FORMAT_CUTOFF = date(2024, 10, 3)

# ── Date helpers ──────────────────────────────────────────────────────────────
_MONTH_ABBR = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]

def d2dmy(d: date) -> str:
    return f"{d.day:02d}{_MONTH_ABBR[d.month-1]}{str(d.year)[2:]}"

def parse_dmy(s: str) -> date:
    s = s.strip()
    return date(int(s[5:]) + 2000, _MONTH_ABBR.index(s[2:5].upper()) + 1, int(s[:2]))

def _fmt_exp_underscore(d: date) -> str:
    """Format date as DD_MMM_YY for new-format filenames."""
    return f"{d.day:02d}_{_MONTH_ABBR[d.month-1]}_{str(d.year)[2:]}"

# ── Expiry calendars ───────────────────────────────────────────────────────────
def load_expiry_dates(year: int = 2024) -> list[date]:
    """Return NIFTY weekly expiry dates for the given year from old expiry.csv."""
    raw = pd.read_csv(EXPIRY_CSV, header=0)
    dates = []
    for s in raw.iloc[:, 0].dropna().astype(str):
        s = s.strip()
        if len(s) == 7 and s[:2].isdigit():
            try:
                d = parse_dmy(s)
                if d.year == year:
                    dates.append(d)
            except ValueError:
                pass
    return sorted(dates)

def load_all_expiry_dates() -> list[date]:
    """All expiry dates: Jan–Sep 2024 from expiry.csv + Oct 2024–Mar 2026 from folder names."""
    old = [d for d in load_expiry_dates(2024) if d < _NEW_FORMAT_CUTOFF]
    new = sorted([
        date.fromisoformat(f.name)
        for f in NEW_DATA_DIR.iterdir()
        if f.is_dir() and len(f.name) == 10 and f.name[4] == '-'
    ])
    return sorted(set(old + new))

# ── Trading day generator ─────────────────────────────────────────────────────
def generate_trading_days(start: date, end: date, holidays: set) -> list[date]:
    """All weekdays in [start, end] minus holidays."""
    days, d = [], start
    while d <= end:
        if d.weekday() < 5 and d not in holidays:
            days.append(d)
        d += timedelta(days=1)
    return days

# ── Option data loaders ───────────────────────────────────────────────────────
def _load_old_format(trade_date: date, expiry_date: date) -> pd.DataFrame | None:
    mon = _MONTH_ABBR[trade_date.month - 1]
    fp  = OLD_DATA_DIR / f"2024{mon}" / f"NIFTY-{d2dmy(expiry_date)}-{d2dmy(trade_date)}.csv"
    if not fp.exists():
        return None
    df = pd.read_csv(fp)
    df.columns = [c.strip() for c in df.columns]
    return df

def _load_new_format(trade_date: date, expiry_date: date) -> pd.DataFrame | None:
    expiry_dir = NEW_DATA_DIR / expiry_date.strftime('%Y-%m-%d')
    if not expiry_dir.exists():
        return None
    exp_str = _fmt_exp_underscore(expiry_date)
    files   = list(expiry_dir.glob(f"NIFTY_*_*_{exp_str}.csv"))
    if not files:
        return None
    dfs = []
    for fp in files:
        parts = fp.stem.split('_')          # NIFTY_27950_CE_03_OCT_24
        if len(parts) < 3:
            continue
        try:
            strike = int(parts[1])
        except ValueError:
            continue
        right = parts[2]
        try:
            df = pd.read_csv(fp, usecols=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
        except Exception:
            continue
        df['ts']      = pd.to_datetime(df['timestamp']).dt.tz_localize(None)
        df_day        = df[df['ts'].dt.date == trade_date].copy()
        if df_day.empty:
            continue
        df_day['datetime']      = df_day['ts'].dt.strftime('%H:%M')
        df_day['strike_price']  = strike
        df_day['right']         = right
        df_day.rename(columns={'oi': 'open_interest'}, inplace=True)
        dfs.append(df_day[['datetime', 'strike_price', 'right',
                            'open', 'high', 'low', 'close', 'open_interest', 'volume']])
    if not dfs:
        return None
    return (pd.concat(dfs)
              .sort_values(['datetime', 'strike_price', 'right'])
              .reset_index(drop=True))

def load_option_file(trade_date: date, expiry_date: date) -> pd.DataFrame | None:
    """Load 1-min options OHLCV for (trade_date, expiry_date).

    Routes to new per-strike format for expiries >= 2024-10-03,
    old monthly format for earlier expiries.
    Columns: datetime, strike_price, right, open, high, low, close, open_interest, volume
    """
    if expiry_date >= _NEW_FORMAT_CUTOFF:
        return _load_new_format(trade_date, expiry_date)
    return _load_old_format(trade_date, expiry_date)

# ── NIFTY spot loader (2024 only, for fallback ATM) ───────────────────────────
def load_nifty_spot(year: int = 2024) -> pd.DataFrame:
    """Load NIFTY 50 minute spot from old monthly CSVs (covers 2024 only).

    Returns DataFrame with columns: datetime (Timestamp), open, high, low, close, volume.
    """
    chunks = []
    for fp in sorted(NIFTY_SPOT_DIR.glob(f"Nifty-{year}*.csv")):
        df = pd.read_csv(fp, header=0,
                         names=["datetime","open","high","low","close","volume"],
                         skiprows=1)
        df["datetime"] = pd.to_datetime(df["datetime"], format="%Y-%m-%d %H:%M", errors="coerce")
        df.dropna(subset=["datetime"], inplace=True)
        chunks.append(df)
    if not chunks:
        return pd.DataFrame()
    return pd.concat(chunks).sort_values("datetime").reset_index(drop=True)

# ── Charge calculator ─────────────────────────────────────────────────────────
def compute_charges(
    legs_entry: list[dict],
    legs_exit:  list[dict],
    exchange: str = "NSE",
) -> float:
    """Return total charges (Rs) for a round-trip multi-leg options trade (Zerodha model)."""
    exc_rate = 0.00053 if exchange == "NSE" else 0.0005
    n_orders = len(legs_entry) + len(legs_exit)
    brokerage = 20.0 * n_orders
    stt = exc = stamp = sebi_turnover = 0.0
    for leg in legs_entry:
        val = leg["entry_price"] * leg["qty"]
        exc           += exc_rate * val
        sebi_turnover += val
        if leg["action"] == "SELL":
            stt += 0.000625 * val
        else:
            stamp += 0.00003 * val
    for leg in legs_exit:
        action = "BUY" if leg["action"] == "SELL" else "SELL"
        val = leg["exit_price"] * leg["qty"]
        exc           += exc_rate * val
        sebi_turnover += val
        if action == "SELL":
            stt += 0.000625 * val
        else:
            stamp += 0.00003 * val
    sebi  = (sebi_turnover / 1e7) * 10.0
    gst   = 0.18 * (brokerage + exc)
    return round(brokerage + stt + exc + stamp + sebi + gst, 2)
