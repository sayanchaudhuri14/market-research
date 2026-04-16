"""
_make_notebooks.py — Generates all v2/backtest and v4.x backtest notebooks.
Run once: py -3 _make_notebooks.py
"""

import json
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent   # gap_trading/

def nb(cells):
    """Minimal valid Jupyter notebook dict."""
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.12.0"}
        },
        "cells": cells
    }

def md(source):
    return {"cell_type": "markdown", "metadata": {}, "source": source}

def code(source):
    return {"cell_type": "code", "metadata": {}, "execution_count": None,
            "outputs": [], "source": source}

def write_nb(path, cells):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(nb(cells), f, indent=1, ensure_ascii=False)
    print(f"  wrote {path.relative_to(BASE.parent)}")


# ════════════════════════════════════════════════════════════════════
# CELL BLOCKS — reusable across versions
# ════════════════════════════════════════════════════════════════════

CELL2_IMPORTS = """\
import sys, os
from pathlib import Path

HERE    = Path(globals().get('__vsc_ipynb_file__', Path.cwd())).parent
V4_DIR  = HERE.parent if HERE.name.startswith('v4') else HERE.parent.parent / 'v4'
sys.path.insert(0, str(V4_DIR))

from _engine import (simulate_trades, compute_metrics, save_results,
                     sig_map, combo_fires, load_reliable_signals, print_summary)

import pandas as pd
import numpy  as np
import yfinance as yf
import pickle, warnings
from datetime import date, timedelta, time as dtime
from pathlib import Path
warnings.filterwarnings('ignore')
"""

CELL4_RUN = """\
# ── Parameters dict passed to engine ──────────────────────────────────────────
params = dict(
    SL_PCT          = SL_PCT,
    TP_PCT          = TP_PCT,
    BASE_LOTS       = BASE_LOTS,
    MAX_LOTS        = MAX_LOTS,
    DTE0_LOTS       = DTE0_LOTS,
    LOT_SIZE        = LOT_SIZE,
    BEAR_N          = BEAR_N,
    ENTRY_TIME      = ENTRY_TIME,
    EXIT_TIME       = EXIT_TIME,
    INITIAL_CAPITAL = INITIAL_CAPITAL,
)

df_log = simulate_trades(signal_days, params)
print(f"Simulation complete: {len(df_log)} trades executed.")
df_log
"""

CELL5_RESULTS = """\
metrics = compute_metrics(df_log, params)
print_summary(df_log, metrics, params)

version_meta = dict(
    version     = VERSION,
    key_change  = KEY_CHANGE,
    data_source = DATA_SRC,
)
out = save_results(metrics, params, version_meta, HERE / 'results')
print(f"\\nRun ID: {out.stem}")
"""

# ════════════════════════════════════════════════════════════════════
# SHARED DATA-LOADING BLOCK (Cell 3 baseline — used by v2/backtest
# and as the foundation for all v4.x versions)
# ════════════════════════════════════════════════════════════════════

DATA_DIR_SETUP = """\
# ── Paths ──────────────────────────────────────────────────────────────────────
# HERE.parent.parent == gap_trading/ for both v2/backtest and v4/v4.x layouts
GAP_TRADING     = HERE.parent.parent
DATA_2024       = GAP_TRADING / 'v2' / 'backtesting_2024_options' / '2024'
SIGNALS_CSV     = GAP_TRADING / 'v2' / 'v2_reliable_signals.csv'
NIFTY_SPOT_DIR  = DATA_2024 / '2024Nifty'
EXPIRY_CSV      = DATA_2024 / 'expiry.csv'
CACHE_FILE      = HERE / 'results' / f'trade_cache_{VERSION.replace(".", "_")}.pkl'
"""

HOLIDAYS_BLOCK = """\
# ── NSE holidays and event days (2024) ────────────────────────────────────────
NSE_HOLIDAYS = {
    date(2024,  1, 22), date(2024,  3, 25), date(2024,  3, 29),
    date(2024,  4, 14), date(2024,  4, 17), date(2024,  5,  1),
    date(2024,  6, 17), date(2024,  7, 17), date(2024,  8, 15),
    date(2024, 10,  2), date(2024, 11, 15), date(2024, 12, 25),
}
EVENT_DAYS = {
    date(2024,  2,  1),   # Union Budget
    date(2024,  2,  8),   # RBI MPC
    date(2024,  4,  5),   # RBI MPC
    date(2024,  6,  7),   # RBI MPC
    date(2024,  8,  8),   # RBI MPC
    date(2024, 10,  9),   # RBI MPC
    date(2024, 12,  6),   # RBI MPC
}
"""

EXPIRY_BLOCK = """\
# ── Expiry helpers ─────────────────────────────────────────────────────────────
expiry_df = pd.read_csv(EXPIRY_CSV)
expiry_df.columns = [c.strip() for c in expiry_df.columns]
# Column is 'ExpiryDate' in DDMMMYY format (e.g. '04JAN24')
_ecol = [c for c in expiry_df.columns if 'expiry' in c.lower() or 'date' in c.lower()][0]
expiry_dates = sorted(
    pd.to_datetime(expiry_df[_ecol].str.strip(), format='%d%b%y').dt.date.tolist()
)

def nearest_expiry(d):
    for e in expiry_dates:
        if e >= d:
            return e
    return expiry_dates[-1]

def expiry_folder(exp):
    return '2024' + exp.strftime('%b').capitalize()
"""

GLOBAL_DATA_BLOCK = """\
# ── Global market data (yfinance, daily) ──────────────────────────────────────
print("Fetching global market data ...", end=' ', flush=True)
START = '2023-12-15'
END   = '2025-01-10'
TICKERS = {'SP500': '^GSPC', 'SGX': 'NKD=F', 'DAX': '^GDAXI',
           'VIX': '^VIX', 'NIFTY': '^NSEI'}

raw = {}
for name, ticker in TICKERS.items():
    try:
        df = yf.download(ticker, start=START, end=END, progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC')
        raw[name] = df[['Close']].rename(columns={'Close': name})
    except Exception as e:
        print(f"  [warn] {name}: {e}")
        raw[name] = pd.DataFrame()

gdf = pd.concat([v for v in raw.values() if not v.empty], axis=1)
gdf.index = gdf.index.date
gdf = gdf.ffill()
print(f"done. {len(gdf)} rows.")
"""

SIGNAL_COMBO_BLOCK = """\
# ── Load signal combos ────────────────────────────────────────────────────────
bear_combos = load_reliable_signals(SIGNALS_CSV, bear_n=BEAR_N, base_rate=BASE_RATE)
print(f"Loaded {len(bear_combos)} bearish combos from {SIGNALS_CSV.name}")
for i, c in enumerate(bear_combos, 1):
    print(f"  {i:>2}. {c}")
"""

NIFTY_SPOT_CACHE_BLOCK = """\
# ── NIFTY spot 1-min data ─────────────────────────────────────────────────────
spot_cache = {}
for f in sorted(NIFTY_SPOT_DIR.glob('Nifty-2024*.csv')):
    try:
        s = pd.read_csv(f)
        s.columns = [c.strip().lower() for c in s.columns]
        s['datetime'] = pd.to_datetime(s['datetime'])
        s['date'] = s['datetime'].dt.date
        s['time'] = s['datetime'].dt.time
        for d, grp in s.groupby('date'):
            spot_cache[d] = grp.reset_index(drop=True)
    except Exception as e:
        print(f"  [warn] spot {f.name}: {e}")
print(f"Spot data loaded for {len(spot_cache)} days.")
"""

BUILD_SIGNAL_DAYS_BLOCK = """\
# ── Build signal_days dict ────────────────────────────────────────────────────
if CACHE_FILE.exists():
    with open(CACHE_FILE, 'rb') as f:
        signal_days = pickle.load(f)
    print(f"Loaded trade cache: {len(signal_days)} dates, "
          f"{sum(1 for v in signal_days.values() if v is not None)} with signal.")
else:
    signal_days = {}
    skipped = []
    LOT_SIZE_LOCAL = 75
    STRIKE_STEP    = 50

    all_dates = sorted([d for d in gdf.index if isinstance(d, date)
                        and date(2024,1,1) <= d <= date(2024,12,31)])

    for d in all_dates:
        # ── Skip conditions ────────────────────────────────────────────────
        if d.weekday() == 0:           # Monday
            skipped.append((d, 'Monday')); continue
        if d in NSE_HOLIDAYS:
            skipped.append((d, 'Holiday')); continue
        if d in EVENT_DAYS:
            skipped.append((d, 'EventDay')); continue

        # ── Global data row ────────────────────────────────────────────────
        prev_rows = [x for x in gdf.index if x < d]
        if len(prev_rows) < 2:
            skipped.append((d, 'NoGlobalData')); continue
        prev  = prev_rows[-1]
        prev2 = prev_rows[-2]

        def _ret(col, d1, d2):
            try:
                return float((gdf.loc[d1, col] - gdf.loc[d2, col]) / gdf.loc[d2, col])
            except Exception:
                return None

        sp500_ret = _ret('SP500', prev, prev2)
        sgx_ret   = _ret('SGX',   prev, prev2)
        dax_ret   = _ret('DAX',   prev, prev2)
        vix_ret   = _ret('VIX',   prev, prev2)
        pind_ret  = _ret('NIFTY', prev, prev2)

        # ── NIFTY open (9:15) for gap ──────────────────────────────────────
        spot = spot_cache.get(d)
        if spot is None:
            skipped.append((d, 'NoSpotData')); continue
        open_row = spot[spot['time'] == dtime(9, 15)]
        if open_row.empty:
            skipped.append((d, 'No915Open')); continue
        nifty_open = float(open_row.iloc[0]['open'])

        nifty_prev_close = float(gdf.loc[prev, 'NIFTY']) if prev in gdf.index else None
        if nifty_prev_close is None or nifty_prev_close <= 0:
            skipped.append((d, 'NoPrevClose')); continue

        gap = (nifty_open - nifty_prev_close) / nifty_prev_close

        # ── Compute signals ────────────────────────────────────────────────
        sigs = sig_map(gap, pind_ret, sp500_ret, sgx_ret, dax_ret, vix_ret)
        fired = [c for c in bear_combos if combo_fires(c, sigs)]

        if not fired:
            signal_days[d] = None; continue

        winning_combo = fired[0]

        # ── NIFTY 9:25 for strike ──────────────────────────────────────────
        row_925 = spot[spot['time'] == dtime(9, 25)]
        if row_925.empty:
            signal_days[d] = None; continue
        nifty_925 = float(row_925.iloc[0]['open'])
        atm    = round(nifty_925 / STRIKE_STEP) * STRIKE_STEP
        strike = atm - STRIKE_STEP   # 1-OTM put

        # ── Expiry ─────────────────────────────────────────────────────────
        exp = nearest_expiry(d)
        dte = (exp - d).days
        exp_str = exp.strftime('%d%b%y').upper()

        # ── Load option file ───────────────────────────────────────────────
        month_dir = DATA_2024 / expiry_folder(exp)
        opt_file  = month_dir / f"NIFTY-{exp_str}-{d.strftime('%d%b%y').upper()}.csv"
        if not opt_file.exists():
            signal_days[d] = None; continue

        try:
            opt = pd.read_csv(opt_file)
            opt.columns = [c.strip().lower() for c in opt.columns]
            opt['datetime'] = pd.to_datetime(opt['datetime'])
            opt['time']     = opt['datetime'].dt.time
            pe = opt[(opt['strike_price'] == strike) & (opt['right'].str.strip().str.upper() == 'PE')]
            if pe.empty:
                signal_days[d] = None; continue

            # Entry candle at 9:25
            entry_row = pe[pe['time'] == dtime(9, 25)]
            if entry_row.empty:
                entry_row = pe[pe['time'] >= dtime(9, 25)].head(1)
            if entry_row.empty:
                signal_days[d] = None; continue
            entry_price = float(entry_row.iloc[0]['open'])
            if entry_price <= 0:
                signal_days[d] = None; continue

            # Candles from 9:25 to 11:15
            candles = pe[(pe['time'] >= dtime(9, 25)) & (pe['time'] <= dtime(11, 15))].copy()
            candles = candles.reset_index(drop=True)

            signal_days[d] = {
                'entry_price':  entry_price,
                'candles':      candles,
                'dte':          dte,
                'strike':       strike,
                'combo':        winning_combo,
                'nifty_open':   nifty_open,
                'nifty_925':    nifty_925,
            }
        except Exception as e:
            print(f"  [warn] {d}: {e}")
            signal_days[d] = None

    # ── Save cache ─────────────────────────────────────────────────────────
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, 'wb') as f:
        pickle.dump(signal_days, f)

    valid = sum(1 for v in signal_days.values() if v is not None)
    print(f"Built trade cache: {len(signal_days)} dates, {valid} with valid signal+data.")
    print(f"  Skipped {len(skipped)} dates: "
          + ', '.join(f"{r}={sum(1 for _,x in skipped if x==r)}"
                      for r in dict.fromkeys(x for _,x in skipped)))
    print(f"  Cache saved: {CACHE_FILE}")
"""


# ════════════════════════════════════════════════════════════════════
# v2/backtest/backtest.ipynb  — BASELINE
# ════════════════════════════════════════════════════════════════════

def make_v2_backtest():
    cell0 = md("""\
# v2/backtest — Baseline

| | |
|---|---|
| **Version** | v2/backtest |
| **Key change** | Baseline — v2 signals, 2024 real options data, full charge model |
| **Data source** | 2024 real 1-min NSE option CSVs |
| **Lookahead** | None — all global signals use D-1 daily close |
| **Signals CSV** | `v2/v2_reliable_signals.csv` (top-10 bearish combos, original) |

Run Cell 1 → Cell 3 once to build the trade cache, then re-run Cell 4–5 freely to test different SL/TP.
""")

    cell1 = code("""\
# ╔══════════════════════════════════╗
# ║  EDIT THESE — re-run Cell 4+5   ║
# ╚══════════════════════════════════╝
VERSION    = 'v2_backtest'
KEY_CHANGE = 'Baseline — v2 signals, 2024 real options data, full charge model'
DATA_SRC   = 'real_2024_options'

SL_PCT    = 0.15    # stop loss  15%
TP_PCT    = 0.40    # target     40%
BASE_LOTS = 2
MAX_LOTS  = 10
DTE0_LOTS = 5
LOT_SIZE  = 75
BEAR_N    = 10      # top-N bearish combos
BASE_RATE = 54.5
ENTRY_TIME      = '09:25'
EXIT_TIME       = '11:15'
INITIAL_CAPITAL = 3000.0   # fixed starting capital for all versions (Rs)

print(f"Breakeven win rate: {SL_PCT/(SL_PCT+TP_PCT)*100:.1f}%")
""")

    cell2 = code(CELL2_IMPORTS)

    cell3 = code(
        DATA_DIR_SETUP +
        HOLIDAYS_BLOCK +
        EXPIRY_BLOCK +
        GLOBAL_DATA_BLOCK +
        SIGNAL_COMBO_BLOCK +
        NIFTY_SPOT_CACHE_BLOCK +
        BUILD_SIGNAL_DAYS_BLOCK
    )

    cell4 = code(CELL4_RUN)
    cell5 = code(CELL5_RESULTS)

    write_nb(BASE / 'v2/backtest/backtest.ipynb',
             [cell0, cell1, cell2, cell3, cell4, cell5])


# ════════════════════════════════════════════════════════════════════
# v4.1/backtest.ipynb  — NKD=F → ^N225
# ════════════════════════════════════════════════════════════════════

def make_v41():
    cell0 = md("""\
# v4.1 — Replace NKD=F with ^N225

| | |
|---|---|
| **Version** | v4.1 |
| **Key change** | SGX proxy: `NKD=F` (CME Nikkei USD futures) → `^N225` (Nikkei 225 cash index, JPY) |
| **Data source** | 2024 real 1-min NSE option CSVs |
| **Lookahead** | None — D-1 close used |
| **Baseline** | v2/backtest |

**Why**: NKD=F adds USD/JPY currency noise. ^N225 is the actual Nikkei 225 index
that SGX/GIFT Nifty futures track. GIFT Nifty itself has no yfinance daily series.

**One-line change in Cell 3**: `'SGX': 'NKD=F'` → `'SGX': '^N225'`
""")

    cell1 = code("""\
VERSION    = 'v4.1'
KEY_CHANGE = 'SGX proxy: NKD=F → ^N225 (Nikkei 225 cash, JPY-denominated)'
DATA_SRC   = 'real_2024_options'

SL_PCT    = 0.15
TP_PCT    = 0.40
BASE_LOTS = 2
MAX_LOTS  = 10
DTE0_LOTS = 5
LOT_SIZE  = 75
BEAR_N    = 10
BASE_RATE = 54.5
ENTRY_TIME      = '09:25'
EXIT_TIME       = '11:15'
INITIAL_CAPITAL = 3000.0   # fixed starting capital for all versions (Rs)

print(f"Breakeven win rate: {SL_PCT/(SL_PCT+TP_PCT)*100:.1f}%")
""")

    cell2 = code(CELL2_IMPORTS)

    # Cell 3: identical to baseline but SGX ticker changed
    cell3_src = (
        DATA_DIR_SETUP +
        HOLIDAYS_BLOCK +
        EXPIRY_BLOCK +
        GLOBAL_DATA_BLOCK.replace("'SGX': 'NKD=F'", "'SGX': '^N225'") +
        SIGNAL_COMBO_BLOCK +
        NIFTY_SPOT_CACHE_BLOCK +
        BUILD_SIGNAL_DAYS_BLOCK
    )
    cell3 = code(cell3_src)
    cell4 = code(CELL4_RUN)
    cell5 = code(CELL5_RESULTS)

    write_nb(BASE / 'v4/v4.1/backtest.ipynb',
             [cell0, cell1, cell2, cell3, cell4, cell5])


# ════════════════════════════════════════════════════════════════════
# v4.2/backtest.ipynb  — Include Mondays
# ════════════════════════════════════════════════════════════════════

def make_v42():
    cell0 = md("""\
# v4.2 — Include Monday sessions

| | |
|---|---|
| **Version** | v4.2 |
| **Key change** | Monday skip removed — Friday US close used for Monday signal |
| **Data source** | 2024 real 1-min NSE option CSVs |
| **Lookahead** | None — Friday US close is available at Monday 9:25 IST |
| **Baseline** | v2/backtest |

**Why**: Monday skip was never empirically tested. Friday S&P 500 close is 60 hours old
at Monday 9:25 IST but may still predict Monday India first-hour direction.

**One change in Cell 3**: Remove `if d.weekday() == 0: continue`
""")

    cell1 = code("""\
VERSION    = 'v4.2'
KEY_CHANGE = 'Include Monday sessions (Friday US close used as global signal)'
DATA_SRC   = 'real_2024_options'

SL_PCT    = 0.15
TP_PCT    = 0.40
BASE_LOTS = 2
MAX_LOTS  = 10
DTE0_LOTS = 5
LOT_SIZE  = 75
BEAR_N    = 10
BASE_RATE = 54.5
ENTRY_TIME      = '09:25'
EXIT_TIME       = '11:15'
INITIAL_CAPITAL = 3000.0   # fixed starting capital for all versions (Rs)
""")

    cell2 = code(CELL2_IMPORTS)

    # Remove Monday skip
    cell3_src = (
        DATA_DIR_SETUP +
        HOLIDAYS_BLOCK +
        EXPIRY_BLOCK +
        GLOBAL_DATA_BLOCK +
        SIGNAL_COMBO_BLOCK +
        NIFTY_SPOT_CACHE_BLOCK +
        BUILD_SIGNAL_DAYS_BLOCK
        .replace(
            "        if d.weekday() == 0:           # Monday\n"
            "            skipped.append((d, 'Monday')); continue\n",
            "        # v4.2: Monday skip REMOVED — Friday close used as-is\n"
        )
    )
    cell3 = code(cell3_src)

    cell4_monday_diag = CELL4_RUN + """\

# ── Monday diagnostic ─────────────────────────────────────────────────────────
if not df_log.empty:
    df_log['weekday'] = pd.to_datetime(df_log['date']).dt.day_name()
    mon = df_log[df_log['weekday'] == 'Monday']
    non = df_log[df_log['weekday'] != 'Monday']
    print(f"Monday trades : {len(mon):>3}  |  win% {(mon['pnl_rs']>0).mean()*100:.1f}%")
    print(f"Other  trades : {len(non):>3}  |  win% {(non['pnl_rs']>0).mean()*100:.1f}%")
"""

    cell4 = code(cell4_monday_diag)
    cell5 = code(CELL5_RESULTS)

    write_nb(BASE / 'v4/v4.2/backtest.ipynb',
             [cell0, cell1, cell2, cell3, cell4, cell5])


# ════════════════════════════════════════════════════════════════════
# v4.3/backtest.ipynb  — SGX live price at 9:25 IST
# ════════════════════════════════════════════════════════════════════

def make_v43():
    cell0 = md("""\
# v4.3 — Nikkei Live Open as SGX Signal

| | |
|---|---|
| **Version** | v4.3 |
| **Key change** | SGX signal: NKD=F D-1 close → ^N225 trade-day open (Tokyo open at 05:30 IST) |
| **Data source** | 2024 real 1-min NSE option CSVs + ^N225 daily OHLC from yfinance |
| **Lookahead** | None — Tokyo opens at 09:00 JST = 05:30 IST, ~4 hrs before 9:25 entry |
| **Baseline** | v2/backtest |

**Why**: yfinance 1h NKD=F bars are limited to the last 730 days (unavailable for 2024).
The best available "live" proxy is the `^N225` Open on the trade day — the Tokyo
market open (09:00 JST = 05:30 IST), observed ~4 hours before the 9:25 IST entry.

Signal change: `sgx_ret = (N225_open_today - N225_close_yesterday) / N225_close_yesterday`
vs baseline: `sgx_ret = (NKD=F_close_yesterday - NKD=F_close_day_before) / NKD=F_close_day_before`
""")

    cell1 = code("""\
VERSION    = 'v4.3'
KEY_CHANGE = 'SGX signal: ^N225 trade-day open (Tokyo 05:30 IST) vs D-1 NKD=F close'
DATA_SRC   = 'real_2024_options'

SL_PCT    = 0.15
TP_PCT    = 0.40
BASE_LOTS = 2
MAX_LOTS  = 10
DTE0_LOTS = 5
LOT_SIZE  = 75
BEAR_N    = 10
BASE_RATE = 54.5
ENTRY_TIME      = '09:25'
EXIT_TIME       = '11:15'
INITIAL_CAPITAL = 3000.0   # fixed starting capital for all versions (Rs)
""")

    cell2 = code(CELL2_IMPORTS)

    # Download ^N225 OHLC separately to get the trade-day Open
    live_sgx_block = """\
# ── ^N225 daily OHLC — trade-day Open as live SGX proxy ───────────────────────
# Tokyo opens 09:00 JST = 05:30 IST, ~4 hours before 9:25 IST entry.
# Using Open-today vs Close-yesterday gives the overnight Nikkei gap.
print("Fetching ^N225 OHLC for live open signal ...", end=' ', flush=True)
try:
    n225_ohlc = yf.download('^N225', start='2023-12-01', end='2025-01-15',
                             progress=False, auto_adjust=True)
    if isinstance(n225_ohlc.columns, pd.MultiIndex):
        n225_ohlc.columns = n225_ohlc.columns.get_level_values(0)
    if n225_ohlc.index.tz is None:
        n225_ohlc.index = n225_ohlc.index.tz_localize('UTC')
    n225_ohlc.index = n225_ohlc.index.date
    n225_open_map  = n225_ohlc['Open'].to_dict()    # trade-day Tokyo open
    n225_close_map = n225_ohlc['Close'].to_dict()   # D-1 close (for return)
    print(f"done. {len(n225_open_map)} days.")
except Exception as e:
    n225_open_map = {}; n225_close_map = {}
    print(f"FAILED ({e}) — will fall back to daily NKD=F return.")

print(f"Coverage: {len(n225_open_map)} days with ^N225 open data.")
"""

    build_v43_block = BUILD_SIGNAL_DAYS_BLOCK.replace(
        "        sgx_ret   = _ret('SGX',   prev, prev2)",
        """\
        # v4.3: use ^N225 trade-day Open vs D-1 Close as live SGX signal
        # (Tokyo open at 05:30 IST — observed 4 hrs before 9:25 entry)
        n225_open_today = n225_open_map.get(d)
        n225_close_prev = n225_close_map.get(prev)
        if n225_open_today and n225_close_prev and n225_close_prev > 0:
            sgx_ret = (n225_open_today - n225_close_prev) / n225_close_prev
        else:
            sgx_ret = _ret('SGX', prev, prev2)  # fallback to NKD=F daily"""
    )

    cell3 = code(
        DATA_DIR_SETUP +
        HOLIDAYS_BLOCK +
        EXPIRY_BLOCK +
        GLOBAL_DATA_BLOCK +
        live_sgx_block +
        SIGNAL_COMBO_BLOCK +
        NIFTY_SPOT_CACHE_BLOCK +
        build_v43_block
    )

    cell4 = code("""\
# ── v4.3 coverage diagnostic ───────────────────────────────────────────────────
live_days = sum(1 for v in signal_days.values()
                if v is not None and v.get('nifty_open') is not None)
print(f"Trades using live N225 open signal: checking cache coverage ...")
print(f"n225_open_map has {len(n225_open_map)} days  |  n225_close_map has {len(n225_close_map)} days")
""" + CELL4_RUN)
    cell5 = code(CELL5_RESULTS)

    write_nb(BASE / 'v4/v4.3/backtest.ipynb',
             [cell0, cell1, cell2, cell3, cell4, cell5])


# ════════════════════════════════════════════════════════════════════
# v4.4/backtest.ipynb  — India VIX regime filter
# ════════════════════════════════════════════════════════════════════

def make_v44():
    cell0 = md("""\
# v4.4 — India VIX Regime Filter

| | |
|---|---|
| **Version** | v4.4 |
| **Key change** | Skip trade if D-1 India VIX > threshold (high-fear regime filter) |
| **Data source** | 2024 real 1-min NSE option CSVs + ^INDIAVIX daily from yfinance |
| **Lookahead** | None — D-1 India VIX close |
| **Baseline** | v2/backtest |

**Why**: `^INDIAVIX` is the implied volatility of NIFTY options — the exact instrument
being traded. High India VIX → put premiums inflated → SL more likely on volatility spikes.
`VIX_INDIA_level` is already in `v2_aligned_dataset.csv` (93% coverage).

**Change**: Add skip condition `if vix_india_today > VIX_INDIA_HIGH_THRESH: continue`
Default threshold: 20.0 (configurable in Cell 1).
""")

    cell1 = code("""\
VERSION    = 'v4.4'
KEY_CHANGE = 'India VIX regime filter: skip if D-1 ^INDIAVIX > VIX_INDIA_HIGH_THRESH'
DATA_SRC   = 'real_2024_options'

SL_PCT    = 0.15
TP_PCT    = 0.40
BASE_LOTS = 2
MAX_LOTS  = 10
DTE0_LOTS = 5
LOT_SIZE  = 75
BEAR_N    = 10
BASE_RATE = 54.5
ENTRY_TIME      = '09:25'
EXIT_TIME       = '11:15'
INITIAL_CAPITAL = 3000.0   # fixed starting capital for all versions (Rs)

VIX_INDIA_HIGH_THRESH = 20.0   # skip trade days where D-1 India VIX > this
print(f"India VIX filter: skip if D-1 INDIAVIX > {VIX_INDIA_HIGH_THRESH}")
""")

    cell2 = code(CELL2_IMPORTS)

    vix_india_block = """\
# ── India VIX (^INDIAVIX) daily data ──────────────────────────────────────────
print("Fetching India VIX ...", end=' ', flush=True)
try:
    vix_india_df = yf.download('^INDIAVIX', start='2023-12-01', end='2025-01-15',
                                progress=False, auto_adjust=True)
    if isinstance(vix_india_df.columns, pd.MultiIndex):
        vix_india_df.columns = vix_india_df.columns.get_level_values(0)
    if vix_india_df.index.tz is None:
        vix_india_df.index = vix_india_df.index.tz_localize('UTC')
    vix_india_df.index = vix_india_df.index.date
    vix_india_map = vix_india_df['Close'].to_dict()
    print(f"done. {len(vix_india_map)} days.")
except Exception as e:
    vix_india_map = {}
    print(f"FAILED ({e}) — VIX filter will not apply (all days traded).")
"""

    build_v44 = BUILD_SIGNAL_DAYS_BLOCK.replace(
        "        # ── Compute signals ────────────────────────────────────────────────",
        """\
        # ── v4.4: India VIX regime filter ─────────────────────────────────────────
        vix_india_today = vix_india_map.get(prev)   # D-1 India VIX close
        if vix_india_today is not None and vix_india_today > VIX_INDIA_HIGH_THRESH:
            skipped.append((d, f'IndiaVIX>{VIX_INDIA_HIGH_THRESH}'))
            signal_days[d] = None
            continue

        # ── Compute signals ────────────────────────────────────────────────"""
    )

    cell3 = code(
        DATA_DIR_SETUP +
        HOLIDAYS_BLOCK +
        EXPIRY_BLOCK +
        GLOBAL_DATA_BLOCK +
        vix_india_block +
        SIGNAL_COMBO_BLOCK +
        NIFTY_SPOT_CACHE_BLOCK +
        build_v44
    )

    cell4 = code("""\
# ── VIX filter diagnostic ──────────────────────────────────────────────────────
vix_vals = [v for v in vix_india_map.values() if v is not None]
if vix_vals:
    print(f"India VIX 2024: min={min(vix_vals):.1f}  max={max(vix_vals):.1f}  "
          f"mean={sum(vix_vals)/len(vix_vals):.1f}")
    above = sum(1 for v in vix_vals if v > VIX_INDIA_HIGH_THRESH)
    print(f"Days with VIX > {VIX_INDIA_HIGH_THRESH}: {above} / {len(vix_vals)}")
""" + CELL4_RUN)

    cell5 = code(CELL5_RESULTS)

    write_nb(BASE / 'v4/v4.4/backtest.ipynb',
             [cell0, cell1, cell2, cell3, cell4, cell5])


# ════════════════════════════════════════════════════════════════════
# v4.5/backtest.ipynb  — dir_120 signals
# ════════════════════════════════════════════════════════════════════

def make_v45():
    cell0 = md("""\
# v4.5 — Rebuild Signals on dir_120 (11:15 Outcome)

| | |
|---|---|
| **Version** | v4.5 |
| **Key change** | Signals rebuilt against 11:15 outcome (dir_120) instead of dir_60 |
| **Prerequisite** | Run `signal_rebuild.ipynb` first → produces `v45_reliable_signals.csv` |
| **Data source** | 2024 real 1-min NSE option CSVs |
| **Lookahead** | None — global signals still use D-1 closes |
| **Baseline** | v2/backtest |

**Why**: v2 combos were statistically validated on `dir_60` (60-min return from open).
But the actual trade holds 110 min (9:25–11:15). Signals that predict the correct direction
at minute 60 may not hold at minute 120. This version retrains on the 11:15 outcome.

**One change**: `SIGNALS_CSV` points to `v45_reliable_signals.csv` (from signal_rebuild.ipynb).
""")

    cell1 = code("""\
VERSION    = 'v4.5'
KEY_CHANGE = 'Signal combos rebuilt on dir_120 (11:15 AM outcome) instead of dir_60'
DATA_SRC   = 'real_2024_options'

SL_PCT    = 0.15
TP_PCT    = 0.40
BASE_LOTS = 2
MAX_LOTS  = 10
DTE0_LOTS = 5
LOT_SIZE  = 75
BEAR_N    = 10
BASE_RATE = 54.5
ENTRY_TIME      = '09:25'
EXIT_TIME       = '11:15'
INITIAL_CAPITAL = 3000.0   # fixed starting capital for all versions (Rs)
""")

    cell2 = code(CELL2_IMPORTS)

    cell3_src = (
        DATA_DIR_SETUP.replace(
            "SIGNALS_CSV     = GAP_TRADING / 'v2' / 'v2_reliable_signals.csv'",
            "SIGNALS_CSV     = HERE / 'v45_reliable_signals.csv'  # rebuilt on dir_120"
        ) +
        """\
# ── Check prerequisite ────────────────────────────────────────────────────────
if not SIGNALS_CSV.exists():
    raise FileNotFoundError(
        f"v45_reliable_signals.csv not found at {SIGNALS_CSV}\\n"
        "Run signal_rebuild.ipynb first to generate it."
    )
print(f"Using signals: {SIGNALS_CSV}")
""" +
        HOLIDAYS_BLOCK +
        EXPIRY_BLOCK +
        GLOBAL_DATA_BLOCK +
        SIGNAL_COMBO_BLOCK +
        NIFTY_SPOT_CACHE_BLOCK +
        # v4.5: add explicit gap-up guard — dir_120 combos don't all include 'Gap Up',
        # but the trade thesis is a gap-fade, so only enter on gap-up days (gap > 0.15%).
        BUILD_SIGNAL_DAYS_BLOCK.replace(
            "        sigs = sig_map(gap, pind_ret, sp500_ret, sgx_ret, dax_ret, vix_ret)\n"
            "        fired = [c for c in bear_combos if combo_fires(c, sigs)]",
            "        sigs = sig_map(gap, pind_ret, sp500_ret, sgx_ret, dax_ret, vix_ret)\n"
            "        # v4.5: require gap-up day regardless of combo membership\n"
            "        if not sigs.get('Gap Up', False):\n"
            "            signal_days[d] = None; continue\n"
            "        fired = [c for c in bear_combos if combo_fires(c, sigs)]"
        )
    )

    cell3 = code(cell3_src)
    cell4 = code(CELL4_RUN)
    cell5 = code(CELL5_RESULTS)

    write_nb(BASE / 'v4/v4.5/backtest.ipynb',
             [cell0, cell1, cell2, cell3, cell4, cell5])


# ════════════════════════════════════════════════════════════════════
# v4.6/backtest.ipynb  — NASDAQ divergence signal
# ════════════════════════════════════════════════════════════════════

def make_v46():
    cell0 = md("""\
# v4.6 — NASDAQ Divergence Signal

| | |
|---|---|
| **Version** | v4.6 |
| **Key change** | Extra filter: only enter if NASDAQ also confirms bearish direction |
| **Data source** | 2024 real 1-min NSE option CSVs + ^IXIC daily from yfinance |
| **Lookahead** | None — D-1 NASDAQ close |
| **Baseline** | v2/backtest |

**Why**: v2 uses only S&P 500 for the US signal. NASDAQ is tech-heavy and often leads
broad market direction. On days where NASDAQ diverges from S&P (e.g., S&P up but
NASDAQ flat), the bearish fade signal may be less reliable.

**Change**: After bearish combo fires, additionally require `nasdaq_ret < NASDAQ_DIV_THRESH`.
Default: `NASDAQ_DIV_THRESH = 0.0` (NASDAQ must be non-positive on trade days).
This is a filter on top of existing v2 combos — it reduces trade count but may improve WR.
""")

    cell1 = code("""\
VERSION    = 'v4.6'
KEY_CHANGE = 'NASDAQ confirmation filter: only trade if NASDAQ also non-positive (D-1)'
DATA_SRC   = 'real_2024_options'

SL_PCT    = 0.15
TP_PCT    = 0.40
BASE_LOTS = 2
MAX_LOTS  = 10
DTE0_LOTS = 5
LOT_SIZE  = 75
BEAR_N    = 10
BASE_RATE = 54.5
ENTRY_TIME      = '09:25'
EXIT_TIME       = '11:15'
INITIAL_CAPITAL = 3000.0   # fixed starting capital for all versions (Rs)

NASDAQ_CONFIRM     = True   # require NASDAQ confirmation
NASDAQ_DIV_THRESH  = 0.0    # NASDAQ D-1 return must be < this to confirm bearish
""")

    cell2 = code(CELL2_IMPORTS)

    nasdaq_fetch = """\
# ── NASDAQ daily data ──────────────────────────────────────────────────────────
print("Fetching NASDAQ ...", end=' ', flush=True)
try:
    nq_df = yf.download('^IXIC', start='2023-12-01', end='2025-01-15',
                         progress=False, auto_adjust=True)
    if isinstance(nq_df.columns, pd.MultiIndex):
        nq_df.columns = nq_df.columns.get_level_values(0)
    if nq_df.index.tz is None:
        nq_df.index = nq_df.index.tz_localize('UTC')
    nq_df.index = nq_df.index.date
    nq_close = nq_df['Close'].to_dict()
    print(f"done. {len(nq_close)} days.")
except Exception as e:
    nq_close = {}
    print(f"FAILED ({e}) — NASDAQ filter will not apply.")
"""

    build_v46 = BUILD_SIGNAL_DAYS_BLOCK.replace(
        "        if not fired:",
        """\
        # ── v4.6: NASDAQ confirmation filter ──────────────────────────────────────
        if NASDAQ_CONFIRM and fired:
            prev_rows2 = [x for x in gdf.index if x < d]
            if len(prev_rows2) >= 2:
                p, p2 = prev_rows2[-1], prev_rows2[-2]
                nq_today  = nq_close.get(p)
                nq_yest   = nq_close.get(p2)
                if nq_today is not None and nq_yest is not None and nq_yest > 0:
                    nasdaq_ret = (nq_today - nq_yest) / nq_yest
                    if nasdaq_ret >= NASDAQ_DIV_THRESH:
                        skipped.append((d, 'NASDAQ_not_confirm'))
                        signal_days[d] = None
                        continue

        if not fired:"""
    )

    cell3 = code(
        DATA_DIR_SETUP +
        HOLIDAYS_BLOCK +
        EXPIRY_BLOCK +
        GLOBAL_DATA_BLOCK +
        nasdaq_fetch +
        SIGNAL_COMBO_BLOCK +
        NIFTY_SPOT_CACHE_BLOCK +
        build_v46
    )

    cell4 = code(CELL4_RUN)
    cell5 = code(CELL5_RESULTS)

    write_nb(BASE / 'v4/v4.6/backtest.ipynb',
             [cell0, cell1, cell2, cell3, cell4, cell5])


# ════════════════════════════════════════════════════════════════════
# v4.7/backtest.ipynb  — First-10-min direction
# ════════════════════════════════════════════════════════════════════

def make_v47():
    cell0 = md("""\
# v4.7 — 9:15→9:25 NIFTY Direction as Entry Filter

| | |
|---|---|
| **Version** | v4.7 |
| **Key change** | Only enter if NIFTY moved down (or flat) from 9:15 to 9:25 open |
| **Data source** | 2024 real 1-min NSE option CSVs |
| **Lookahead** | None — 9:15 and 9:25 prices both observed before/at entry |
| **Baseline** | v2/backtest |
| **BS backtest** | Not applicable — no pre-2021 intraday NIFTY data |

**Why**: By 9:25, the gap direction has been in play for 10 minutes. If NIFTY is already
fading the gap, the reversal is in motion and the PUT entry is better timed. If NIFTY
is extending the gap at 9:25, momentum is against the trade and SL risk is higher.

**Change**: Skip trade if `(nifty_925_open - nifty_915_open) / nifty_915_open > FIRST_10MIN_THRESH`
Default threshold: -0.001 (NIFTY must fall at least 0.1% from 9:15 to 9:25).
""")

    cell1 = code("""\
VERSION    = 'v4.7'
KEY_CHANGE = '9:15-9:25 direction filter: only enter if NIFTY fading (not extending gap)'
DATA_SRC   = 'real_2024_options'

SL_PCT    = 0.15
TP_PCT    = 0.40
BASE_LOTS = 2
MAX_LOTS  = 10
DTE0_LOTS = 5
LOT_SIZE  = 75
BEAR_N    = 10
BASE_RATE = 54.5
ENTRY_TIME      = '09:25'
EXIT_TIME       = '11:15'
INITIAL_CAPITAL = 3000.0   # fixed starting capital for all versions (Rs)

FIRST_10MIN_THRESH = -0.001   # NIFTY must fall >0.1% from 9:15 to 9:25
# Set to 0.0 to accept any non-positive move; raise to -0.002 for stricter filter
""")

    cell2 = code(CELL2_IMPORTS)

    # Anchor on the unique code line after winning_combo (avoids fragile dash-count matching)
    build_v47 = BUILD_SIGNAL_DAYS_BLOCK.replace(
        "        row_925 = spot[spot['time'] == dtime(9, 25)]\n",
        """\
        # ── v4.7: first-10-min direction filter ────────────────────────────────────
        open_915 = spot[spot['time'] == dtime(9, 15)]
        open_925_row = spot[spot['time'] == dtime(9, 25)]
        if not open_915.empty and not open_925_row.empty:
            p915 = float(open_915.iloc[0]['open'])
            p925_open = float(open_925_row.iloc[0]['open'])
            move_10min = (p925_open - p915) / p915
            if move_10min > FIRST_10MIN_THRESH:
                skipped.append((d, 'GapExtending'))
                signal_days[d] = None
                continue

        row_925 = spot[spot['time'] == dtime(9, 25)]
"""
    )

    cell3 = code(
        DATA_DIR_SETUP +
        HOLIDAYS_BLOCK +
        EXPIRY_BLOCK +
        GLOBAL_DATA_BLOCK +
        SIGNAL_COMBO_BLOCK +
        NIFTY_SPOT_CACHE_BLOCK +
        build_v47
    )

    cell4_diag = """\
# ── First-10-min diagnostic ────────────────────────────────────────────────────
fading_days    = sum(1 for v in signal_days.values() if v is not None)
extending_days = sum(1 for d, r in skipped if r == 'GapExtending')
print(f"Trades after 10-min filter : {fading_days}  (gap fading/flat at 9:25)")
print(f"Skipped — gap extending    : {extending_days}")
""" + CELL4_RUN

    cell4 = code(cell4_diag)
    cell5 = code(CELL5_RESULTS)

    write_nb(BASE / 'v4/v4.7/backtest.ipynb',
             [cell0, cell1, cell2, cell3, cell4, cell5])


# ════════════════════════════════════════════════════════════════════
# v2/backtest/backtest_BS.ipynb  — BS baseline
# ════════════════════════════════════════════════════════════════════

BS_CELL2_IMPORTS = """\
import sys, os
from pathlib import Path

HERE    = Path(globals().get('__vsc_ipynb_file__', Path.cwd())).parent
# HERE.parent.parent == gap_trading/ for both v2/backtest and v4/v4.x layouts
V4_DIR  = HERE.parent.parent / 'v4'
sys.path.insert(0, str(V4_DIR))

from _engine   import (compute_metrics, save_results, sig_map,
                        combo_fires, load_reliable_signals, print_summary)
from _bs_engine import (bs_put_price, simulate_bs_exit, vix_to_sigma,
                        dte_to_T, print_bs_limitations)

import pandas as pd
import numpy  as np
import yfinance as yf
import warnings
from datetime import date, timedelta
from pathlib  import Path
warnings.filterwarnings('ignore')
"""

def make_bs_notebook(version, key_change, folder_path,
                     signals_csv_rel="HERE.parent.parent / 'v2' / 'v2_reliable_signals.csv'",
                     extra_cell3_pre="",
                     ticker_override=""):
    """Generic BS notebook factory."""

    cell0 = md(f"""\
# {version} — Black-Scholes Backtest (Long History)

| | |
|---|---|
| **Version** | {version} |
| **Key change** | {key_change} |
| **Data source** | Black-Scholes simulation using yfinance daily data |
| **Period** | Configurable `BS_START_DATE` (default 2012-01-01) to 2026-04-15 |
| **Lookahead** | None |

⚠️ **BS limitations apply** — see printed warning at start of Cell 5.
OHLC-proxy SL/TP and no volatility smile. Use for directional confirmation only.
""")

    sgx_ticker = ticker_override if ticker_override else "'NKD=F'"

    cell1 = code(f"""\
VERSION     = '{version}_bs'
KEY_CHANGE  = '{key_change}'
DATA_SRC    = 'black_scholes'

BS_START_DATE = '2012-01-01'   # change to '2019-01-01' for shorter run
BS_END_DATE   = '2026-04-15'

SL_PCT    = 0.15
TP_PCT    = 0.40
BASE_LOTS = 2
MAX_LOTS  = 10
DTE0_LOTS = 5
LOT_SIZE  = 75
BEAR_N    = 10
BASE_RATE = 54.5
ENTRY_TIME      = '09:25'
EXIT_TIME       = '11:15'
RISK_FREE       = 0.065   # Indian T-bill proxy
INITIAL_CAPITAL = 3000.0  # fixed starting capital for all versions (Rs)

print(f"Backtest period: {{BS_START_DATE}} to {{BS_END_DATE}}")
print(f"Breakeven win rate: {{SL_PCT/(SL_PCT+TP_PCT)*100:.1f}}%")
""")

    cell2 = code(BS_CELL2_IMPORTS)

    cell3 = code(f"""\
# ── Paths ──────────────────────────────────────────────────────────────────────
SIGNALS_CSV = {signals_csv_rel}
if not SIGNALS_CSV.exists():
    raise FileNotFoundError(f"Signals CSV not found: {{SIGNALS_CSV}}")

# ── Global market data ─────────────────────────────────────────────────────────
print("Fetching global daily data ...", end=' ', flush=True)
TICKERS = {{'SP500': '^GSPC', 'SGX': {sgx_ticker}, 'DAX': '^GDAXI',
           'VIX': '^VIX', 'NIFTY': '^NSEI', 'INDIAVIX': '^INDIAVIX'}}

raw = {{}}
for name, ticker in TICKERS.items():
    try:
        df = yf.download(ticker, start=BS_START_DATE, end=BS_END_DATE,
                         progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC')
        df.index = df.index.date
        raw[name] = df[['Open','High','Low','Close']]
    except Exception as e:
        print(f"  [warn] {{name}}: {{e}}")
        raw[name] = pd.DataFrame()
print("done.")

nifty   = raw.get('NIFTY',    pd.DataFrame())
sp500   = raw.get('SP500',    pd.DataFrame())
sgx     = raw.get('SGX',      pd.DataFrame())
dax_df  = raw.get('DAX',      pd.DataFrame())
vix_df  = raw.get('VIX',      pd.DataFrame())
ivix_df = raw.get('INDIAVIX', pd.DataFrame())

# ── Signal combos ──────────────────────────────────────────────────────────────
bear_combos = load_reliable_signals(SIGNALS_CSV, bear_n=BEAR_N, base_rate=BASE_RATE)
print(f"Loaded {{len(bear_combos)}} bearish combos.")

# ── NSE weekly expiry: Thursday before Sep 2 2025, Tuesday from Sep 2 2025 ───
from datetime import date as _date
EXPIRY_CHANGE = _date(2025, 9, 2)
def next_expiry(d):
    wd_target = 1 if d >= EXPIRY_CHANGE else 3   # Tue=1, Thu=3
    days = (wd_target - d.weekday()) % 7
    return d + timedelta(days=days)

# ── NSE holidays (rough annual calendar) ──────────────────────────────────────
NSE_HOLIDAYS = set()   # kept minimal — BS backtest spans years, exact holidays skipped

{extra_cell3_pre}

# ── Build signal days + BS simulation ─────────────────────────────────────────
from _engine import compute_charges

trade_log = []
capital   = None
peak      = None
trade_num = 0
SKIP_MON  = True   # keep Monday skip consistent with v2 baseline

all_dates = sorted([d for d in nifty.index
                    if isinstance(d, _date)
                    and _date.fromisoformat(BS_START_DATE) <= d
                    and d <= _date.fromisoformat(BS_END_DATE)])

for d in all_dates:
    if SKIP_MON and d.weekday() == 0: continue
    if d in NSE_HOLIDAYS: continue

    prev_rows = [x for x in nifty.index if x < d]
    if len(prev_rows) < 2: continue
    prev, prev2 = prev_rows[-1], prev_rows[-2]

    def _r(df, d1, d2):
        try:
            return float((df.loc[d1,'Close'] - df.loc[d2,'Close']) / df.loc[d2,'Close'])
        except Exception: return None

    def _c(df, d1):
        try: return float(df.loc[d1,'Close'])
        except Exception: return None

    sp500_ret = _r(sp500, prev, prev2)
    sgx_ret   = _r(sgx,   prev, prev2)
    dax_ret   = _r(dax_df,prev, prev2)
    vix_ret   = _r(vix_df, prev, prev2)
    pind_ret  = _r(nifty,  prev, prev2)
    vix_india = _c(ivix_df, prev)

    # ── Gap: use NIFTY open on trade day ──────────────────────────────────
    try:
        nifty_open  = float(nifty.loc[d, 'Open'])
        nifty_prev_close = float(nifty.loc[prev, 'Close'])
        if nifty_prev_close <= 0: continue
    except Exception: continue

    gap = (nifty_open - nifty_prev_close) / nifty_prev_close

    sigs  = sig_map(gap, pind_ret, sp500_ret, sgx_ret, dax_ret, vix_ret)
    fired = [c for c in bear_combos if combo_fires(c, sigs)]
    if not fired: continue

    # ── Strike + expiry + BS pricing ──────────────────────────────────────
    STRIKE_STEP = 50
    atm    = round(nifty_open / STRIKE_STEP) * STRIKE_STEP
    strike = atm - STRIKE_STEP
    exp    = next_expiry(d)
    dte    = (exp - d).days

    sigma     = vix_to_sigma(vix_india)
    T_en, T_ex = dte_to_T(dte)
    entry_price = bs_put_price(nifty_open, strike, T_en, RISK_FREE, sigma)
    if entry_price <= 0.5: continue

    # ── NIFTY daily OHLC for exit simulation ──────────────────────────────
    try:
        S_high  = float(nifty.loc[d, 'High'])
        S_low   = float(nifty.loc[d, 'Low'])
        S_close = float(nifty.loc[d, 'Close'])
    except Exception: continue

    exit_price, exit_reason = simulate_bs_exit(
        entry_price, nifty_open, S_high, S_low, S_close,
        strike, T_en, T_ex, SL_PCT, TP_PCT, RISK_FREE, sigma, dte
    )

    # ── Capital + lot sizing ───────────────────────────────────────────────
    cost_per_lot = entry_price * LOT_SIZE
    if capital is None:
        capital = float(INITIAL_CAPITAL) if INITIAL_CAPITAL is not None else cost_per_lot * BASE_LOTS
        peak    = capital
    refill = 0.0
    if capital < cost_per_lot:
        refill  = cost_per_lot * BASE_LOTS - capital
        capital += refill
        peak = max(peak, capital)

    lots = min(max(int(capital // cost_per_lot), 1), MAX_LOTS)
    if dte == 0: lots = min(lots, DTE0_LOTS)

    charges = compute_charges(entry_price, exit_price, lots, LOT_SIZE)
    pnl_rs  = round((exit_price - entry_price) * lots * LOT_SIZE - charges, 4)

    cap_before = round(capital, 4)
    capital    = round(capital + pnl_rs, 4)
    peak       = max(peak, capital)
    dd         = round((peak - capital) / peak * 100, 4) if peak > 0 else 0.0

    trade_num += 1
    trade_log.append(dict(
        trade_num=trade_num, date=str(d), strike=strike, dte=dte,
        entry=round(entry_price,4), lots=lots,
        sl_price=round(entry_price*(1-SL_PCT),4),
        tp_price=round(entry_price*(1+TP_PCT),4),
        exit_price=round(exit_price,4), exit_reason=exit_reason,
        exit_time='BS-approx', pnl_pts=round(exit_price-entry_price,4),
        pnl_rs=pnl_rs, charges_rs=round(charges,4),
        capital_before=cap_before, capital_after=capital,
        drawdown_pct=dd, combo=fired[0],
        refill_rs=round(refill, 4),
        dte0_warning=(dte == 0),
    ))

df_log = pd.DataFrame(trade_log)
print(f"Simulation complete: {{len(df_log)}} trades, period {{BS_START_DATE}}–{{BS_END_DATE}}")
df_log.head()
""")

    cell4 = code("""\
params = dict(
    SL_PCT=SL_PCT, TP_PCT=TP_PCT, BASE_LOTS=BASE_LOTS,
    MAX_LOTS=MAX_LOTS, DTE0_LOTS=DTE0_LOTS, LOT_SIZE=LOT_SIZE,
    BEAR_N=BEAR_N, ENTRY_TIME=ENTRY_TIME, EXIT_TIME=EXIT_TIME,
    INITIAL_CAPITAL=INITIAL_CAPITAL,
)
metrics = compute_metrics(df_log, params)
""")

    cell5 = code("""\
print_bs_limitations()
print_summary(df_log, metrics, params)

dte0_trades = df_log.get('dte0_warning', pd.Series(dtype=bool))
if hasattr(dte0_trades, 'sum') and dte0_trades.sum() > 0:
    print(f"  ⚠ DTE=0 trades: {dte0_trades.sum()} — BS unreliable for these")

version_meta = dict(version=VERSION, key_change=KEY_CHANGE, data_source=DATA_SRC)
out = save_results(metrics, params, version_meta, HERE / 'results')
print(f"Run ID: {out.stem}")
""")

    write_nb(folder_path, [cell0, cell1, cell2, cell3, cell4, cell5])


# ════════════════════════════════════════════════════════════════════
# v4.5/signal_rebuild.ipynb
# ════════════════════════════════════════════════════════════════════

def make_v45_rebuild():
    cell0 = md("""\
# v4.5 — signal_rebuild.ipynb

Rebuilds the signal combination CSV using `dir_120` (11:15 outcome) as the
target variable instead of `dir_60` (60-min return used in v2).

**Run this once** before running `backtest.ipynb` in v4.5.
Output: `v45_reliable_signals.csv` (same schema as `v2/v2_reliable_signals.csv`).
""")

    cell1 = code("""\
import sys
from pathlib import Path
HERE   = Path(globals().get('__vsc_ipynb_file__', Path.cwd())).parent
V2_DIR = HERE.parent.parent / 'v2'
import pandas as pd
import numpy  as np
import warnings
from scipy.stats import binomtest
warnings.filterwarnings('ignore')

ALIGNED_CSV = V2_DIR / 'v2_aligned_dataset.csv'
SPOT_DIR    = V2_DIR / 'backtesting_2024_options' / '2024' / '2024Nifty'
KITE_CACHE  = HERE.parent.parent / 'kite_minute_cache'
OUT_CSV     = HERE / 'v45_reliable_signals.csv'

BASE_RATE   = 54.5   # % sessions where first-hour closes DOWN
MIN_N       = 40     # minimum occurrences to test a combo
MAX_PVAL    = 0.05   # significance threshold

print(f"Aligned dataset: {ALIGNED_CSV}")
print(f"Output: {OUT_CSV}")
""")

    cell2 = code("""\
# ── Cell 2: Load aligned dataset and build dir_120 ───────────────────────────
df = pd.read_csv(ALIGNED_CSV)
print(f"Loaded aligned dataset: {df.shape}")
print(f"Columns: {df.columns.tolist()[:10]} ...")

# ── Load NIFTY 1-min spot from 2024Nifty CSVs ────────────────────────────────
from datetime import time as dtime
spot_1115 = {}   # date -> NIFTY close at 11:15
spot_0915 = {}   # date -> NIFTY open  at 09:15

for f in sorted(SPOT_DIR.glob('Nifty-2024*.csv')):
    try:
        s = pd.read_csv(f)
        s.columns = [c.strip().lower() for c in s.columns]
        s['dt'] = pd.to_datetime(s['datetime'])
        s['date'] = s['dt'].dt.date
        s['time'] = s['dt'].dt.time
        for d, grp in s.groupby('date'):
            r915 = grp[grp['time'] == dtime(9,15)]
            r1115 = grp[grp['time'] == dtime(11,15)]
            if not r915.empty:
                spot_0915[str(d)] = float(r915.iloc[0]['open'])
            if not r1115.empty:
                spot_1115[str(d)] = float(r1115.iloc[-1]['close'])
    except Exception as e:
        print(f"  [warn] {f.name}: {e}")

print(f"9:15 open  available for {len(spot_0915)} days")
print(f"11:15 close available for {len(spot_1115)} days")

# ── Compute ret_110 and dir_120 ───────────────────────────────────────────────
def _ret110(row):
    d = str(row.get('india_date', ''))[:10]
    o = spot_0915.get(d)
    c = spot_1115.get(d)
    if o and c and o > 0:
        return (c - o) / o
    return np.nan

df['ret_110'] = df.apply(_ret110, axis=1)
df['dir_120'] = df['ret_110'].apply(lambda x: -1.0 if x < 0 else (1.0 if x > 0 else np.nan))

valid = df['dir_120'].notna().sum()
down  = (df['dir_120'] == -1.0).sum()
print(f"\\ndir_120 computed for {valid} / {len(df)} rows")
print(f"  DOWN (dir_120 = -1): {down} ({down/valid*100:.1f}%)")
print(f"  UP   (dir_120 = +1): {valid-down} ({(valid-down)/valid*100:.1f}%)")
""")

    cell3 = code("""\
# ── Cell 3: Re-run signal combination analysis on dir_120 ──────────────────────
# Use same signal columns as v2 (already binarised in aligned dataset)
SIG_COLS = {
    'Gap Up':         lambda r: r.get('gap_pct', 0)  >  0.0015,
    'Gap Up Strong':  lambda r: r.get('gap_pct', 0)  >  0.0050,
    'Gap Down':       lambda r: r.get('gap_pct', 0)  < -0.0015,
    'Prev India UP':  lambda r: r.get('prev_india_ret', 0) > 0,
    'Prev India DOWN':lambda r: r.get('prev_india_ret', 0) < 0,
    'US UP':          lambda r: r.get('SP500_ret', 0)  > 0,
    'US DOWN':        lambda r: r.get('SP500_ret', 0)  < 0,
    'SGX UP':         lambda r: r.get('SGX_ret', 0)    > 0,
    'SGX DOWN':       lambda r: r.get('SGX_ret', 0)    < 0,
    'DAX UP':         lambda r: r.get('DAX_ret', 0)    > 0,
    'VIX Rising':     lambda r: r.get('VIX_US_ret', 0) > 0.03,
    'VIX Falling':    lambda r: r.get('VIX_US_ret', 0) < 0,
    'VIX Spike':      lambda r: r.get('VIX_US_ret', 0) > 0.05,
}

# Build binary signal matrix
sub = df[df['dir_120'].notna()].copy()
for name, fn in SIG_COLS.items():
    sub[name] = sub.apply(fn, axis=1).astype(bool)
sub['target_down'] = (sub['dir_120'] == -1.0)

print(f"Working dataset: {len(sub)} rows with dir_120 target")

# ── Test all 2-4 signal combinations ─────────────────────────────────────────
from itertools import combinations
sig_names = list(SIG_COLS.keys())
results = []

for level in [2, 3, 4]:
    for combo in combinations(sig_names, level):
        mask = sub[list(combo)].all(axis=1)
        n = mask.sum()
        if n < MIN_N: continue
        n_down = sub.loc[mask, 'target_down'].sum()
        p_down = n_down / n * 100
        p_up   = 100 - p_down
        freq   = n / len(sub) * 100

        # Binomial test: is P(DOWN) significantly different from base rate?
        direction = 'DOWN' if p_down > BASE_RATE else 'UP'
        test_k    = n_down if direction == 'DOWN' else (n - n_down)
        test_p    = BASE_RATE / 100 if direction == 'DOWN' else (1 - BASE_RATE / 100)
        result    = binomtest(test_k, n, test_p, alternative='greater')
        pval      = result.pvalue

        if pval < MAX_PVAL:
            edge = abs(p_down - BASE_RATE)
            # 95% CI
            ci_lo = (test_k - 1.96 * (n * test_p * (1-test_p)) ** 0.5) / n * 100
            ci_hi = (test_k + 1.96 * (n * test_p * (1-test_p)) ** 0.5) / n * 100
            sig_str = '***' if pval < 0.001 else ('**' if pval < 0.01 else '*')

            results.append({
                'N': n, 'Freq_pct': round(freq,1),
                'P_Down': round(p_down,1), 'P_Up': round(p_up,1),
                'Edge_pp': round(edge,1),
                'CI_lo': round(ci_lo,1), 'CI_hi': round(ci_hi,1),
                'p_val': round(pval,4), 'Sig': sig_str,
                'Direction': direction, 'Verdict': 'RELIABLE',
                'Level': level,
                'Signal': ' + '.join(combo),
            })

results_df = pd.DataFrame(results).sort_values('Edge_pp', ascending=False).reset_index(drop=True)
print(f"\\nFound {len(results_df)} reliable combos (dir_120 target, p<{MAX_PVAL}, N>={MIN_N})")
results_df.head(15)
""")

    cell4 = code("""\
# ── Cell 4: Compare v2 vs v4.5 top-10 bearish combos ──────────────────────────
v2_csv = V2_DIR / 'v2_reliable_signals.csv'
v2_df  = pd.read_csv(v2_csv)
v2_bear = v2_df[v2_df['P_Down'] > BASE_RATE].sort_values('Edge_pp', ascending=False).head(10)
v45_bear = results_df[results_df['Direction'] == 'DOWN'].head(10)

print("=" * 72)
print("  v2 TOP-10 BEARISH (trained on dir_60)")
print("=" * 72)
for i, r in v2_bear.iterrows():
    print(f"  {r['P_Down']:>5.1f}%  N={r['N']:>4}  {r['Signal']}")

print()
print("=" * 72)
print("  v4.5 TOP-10 BEARISH (trained on dir_120)")
print("=" * 72)
for i, r in v45_bear.iterrows():
    print(f"  {r['P_Down']:>5.1f}%  N={r['N']:>4}  {r['Signal']}")

# ── Save ──────────────────────────────────────────────────────────────────────
results_df.to_csv(OUT_CSV, index=False)
print(f"\\nSaved {len(results_df)} combos to {OUT_CSV}")
""")

    write_nb(BASE / 'v4/v4.5/signal_rebuild.ipynb',
             [cell0, cell1, cell2, cell3, cell4])


# ════════════════════════════════════════════════════════════════════
# compare_versions.ipynb
# ════════════════════════════════════════════════════════════════════

def make_compare():
    cell0 = md("""\
# compare_versions.ipynb

Scans all `*/results/*.json` files, loads the most recent run per
`(version, data_source)` pair, and prints a side-by-side comparison table
with deltas vs the v2/backtest baseline.

Re-run at any time as new results accumulate.
""")

    cell1 = code("""\
import json, sys
from pathlib import Path
import pandas as pd

HERE   = Path(globals().get('__vsc_ipynb_file__', Path.cwd())).parent
V2_BT  = HERE.parent / 'v2' / 'backtest' / 'results'
V4_DIR = HERE

# ── Scan all results/ folders ─────────────────────────────────────────────────
def load_latest(root):
    rows = []
    for json_file in sorted(root.rglob('*.json')):
        if 'trade_cache' in json_file.name: continue
        try:
            with open(json_file, encoding='utf-8') as f:
                d = json.load(f)
            row = {'version': d.get('version',''), 'key_change': d.get('key_change',''),
                   'data_source': d.get('data_source',''), 'run_id': d.get('run_id',''),
                   '_file': json_file}
            row.update(d.get('results', {}))
            rows.append(row)
        except Exception as e:
            print(f"  [warn] {json_file.name}: {e}")
    return rows

all_rows = load_latest(V2_BT) + load_latest(V4_DIR)
df_all   = pd.DataFrame(all_rows)
print(f"Found {len(df_all)} result files across all versions.")
df_all[['version','data_source','run_id']].head(20)
""")

    cell2 = code("""\
# ── Keep most recent run per (version, data_source) ───────────────────────────
if df_all.empty:
    print("No results yet — run some backtest notebooks first.")
else:
    df_latest = (df_all
                 .sort_values('run_id', ascending=False)
                 .drop_duplicates(subset=['version','data_source'])
                 .sort_values(['data_source','xirr_pct'], ascending=[True,False])
                 .reset_index(drop=True))

    COLS = ['version','data_source','total_trades','profit_trade_pct',
            'tp_hit_pct','sl_hit_pct','time_exit_pct',
            'xirr_pct','max_drawdown_pct','net_return_pct','key_change']
    avail = [c for c in COLS if c in df_latest.columns]
    print("\\n=== SUMMARY TABLE (sorted by XIRR) ===")
    display(df_latest[avail])
""")

    cell3 = code("""\
# ── Delta table vs v2/backtest baseline ───────────────────────────────────────
if not df_all.empty:
    for ds in df_latest['data_source'].unique():
        sub = df_latest[df_latest['data_source'] == ds].copy()
        baseline_rows = sub[sub['version'].str.replace('_bs', '', regex=False) == 'v2_backtest']
        if baseline_rows.empty:
            print(f"  [{ds}] No v2/backtest baseline yet — skipping delta.")
            continue
        baseline = baseline_rows.iloc[0]

        DELTA_COLS = ['total_trades','profit_trade_pct','xirr_pct',
                      'max_drawdown_pct','net_return_pct']
        delta_rows = []
        for _, r in sub[sub['version'] != 'v2_backtest'].iterrows():
            row = {'version': r['version'], 'key_change': r.get('key_change','')}
            for c in DELTA_COLS:
                try:
                    row[f'Δ {c}'] = round(float(r[c]) - float(baseline[c]), 2)
                except Exception:
                    row[f'Δ {c}'] = None
            delta_rows.append(row)

        if delta_rows:
            print(f"\\n=== DELTA vs v2/backtest BASELINE  [{ds}] ===")
            display(pd.DataFrame(delta_rows))
""")

    write_nb(BASE / 'v4/compare_versions.ipynb',
             [cell0, cell1, cell2, cell3])


# ════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print(f"Generating notebooks under {BASE} ...")

    # v2/backtest
    make_v2_backtest()

    # v4.x real-data backtests
    make_v41()
    make_v42()
    make_v43()
    make_v44()
    make_v45()
    make_v46()
    make_v47()

    # v4.5 signal rebuild
    make_v45_rebuild()

    # BS notebooks
    make_bs_notebook(
        version='v2_backtest',
        key_change='Baseline — v2 signals, Black-Scholes simulation',
        folder_path=BASE / 'v2/backtest/backtest_BS.ipynb',
        signals_csv_rel="HERE.parent.parent / 'v2' / 'v2_reliable_signals.csv'",
    )
    for vname, kchange, ticker in [
        ('v4.1', 'SGX proxy: NKD=F → ^N225 (Nikkei 225 cash)', "'^N225'"),
        ('v4.2', 'Include Monday sessions (BS)', ''),
        ('v4.3', 'SGX live at 9:25 IST (BS uses daily close fallback)', ''),
        ('v4.4', 'India VIX regime filter (BS)', ''),
        ('v4.6', 'NASDAQ confirmation filter (BS)', ''),
    ]:
        extra = ""
        if vname == 'v4.2':
            extra = "SKIP_MON = False   # v4.2: include Mondays\n"
        if vname == 'v4.4':
            extra = """\
VIX_INDIA_HIGH_THRESH = 20.0
# In loop below, add: if vix_india and vix_india > VIX_INDIA_HIGH_THRESH: continue
"""
        make_bs_notebook(
            version=vname,
            key_change=kchange,
            folder_path=BASE / f'v4/{vname}/backtest_BS.ipynb',
            signals_csv_rel="HERE.parent.parent / 'v2' / 'v2_reliable_signals.csv'",
            extra_cell3_pre=extra,
            ticker_override=ticker,
        )

    # v4.5 BS uses rebuilt signals
    make_bs_notebook(
        version='v4.5',
        key_change='Signal combos rebuilt on dir_120 (BS simulation)',
        folder_path=BASE / 'v4/v4.5/backtest_BS.ipynb',
        signals_csv_rel="HERE / 'v45_reliable_signals.csv'",
    )

    # compare
    make_compare()

    print("\nAll notebooks written.")
