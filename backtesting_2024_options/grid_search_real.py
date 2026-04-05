#!/usr/bin/env python3
"""
grid_search_real.py
────────────────────────────────────────────────────────────────────────────
Full grid search backtest — 2024 only — using REAL NIFTY options minute data.
NO Black-Scholes anywhere.

Runs THREE configs in one pass and writes a comparison Excel:
  Config A  entry=09:15  exit=10:15  SL lockout before 09:20  (original)
  Config B  entry=09:25  exit=11:00  no SL lockout             (delayed)
  Config C  entry=09:30  exit=11:00  no SL lockout             (delayed)

Entry  = real option OPEN at the entry-time candle
Exit   = real option candles (high/low) — TP on high, SL on low
Expiry = always Thursday in 2024 (from expiry.csv)

Run:
  cd market-research
  python backtesting_2024_options/grid_search_real.py
────────────────────────────────────────────────────────────────────────────
"""

import sys, warnings, itertools
from pathlib import Path
from datetime import date, datetime, timedelta
from datetime import time as dtime

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings('ignore')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# ══════════════════════════════════════════════════════════════════════════════
# 1. PATHS & CONFIG
# ══════════════════════════════════════════════════════════════════════════════

HERE        = Path(__file__).parent                   # backtesting_2024_options/
DATA_DIR    = HERE / '2024'
NIFTY_DIR   = DATA_DIR / '2024Nifty'
EXPIRY_CSV  = DATA_DIR / 'expiry.csv'
SIGNALS_CSV = HERE.parent / 'v2' / 'v2_reliable_signals.csv'
OUTPUT_DIR  = HERE / 'backtest_outputs'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

STRIKE_STEP = 50
STRIKES_OTM = 1          # 1 strike OTM
LOT_SIZE    = 75
BROKERAGE   = 80          # Rs per trade
BASE_RATE   = 54.5        # historical P(NIFTY closes down)
SIGNAL_MODE = 'BEARISH_ONLY'

GAP_THRESHOLD        = 0.0015
GAP_LARGE_THRESHOLD  = 0.0050
VIX_RISING_THRESHOLD = 0.03
VIX_SPIKE_THRESHOLD  = 0.05

NSE_HOLIDAYS = {
    date(2024,  1, 22), date(2024,  3, 25), date(2024,  3, 29),
    date(2024,  4, 11), date(2024,  4, 14), date(2024,  4, 17),
    date(2024,  5,  1), date(2024,  6, 17), date(2024,  8, 15),
    date(2024, 10,  2), date(2024, 10, 24), date(2024, 11, 15),
    date(2024, 12, 25),
}

EVENT_DAYS = {
    date(2024,  2,  1),   # Interim Budget
    date(2024,  4,  5),   # RBI MPC
    date(2024,  6,  4),   # Election results
    date(2024,  6,  5),   # Day after election results
    date(2024,  6,  7),   # RBI MPC
    date(2024,  7, 23),   # Union Budget
    date(2024,  8,  8),   # RBI MPC
    date(2024, 10,  9),   # RBI MPC
    date(2024, 12,  6),   # RBI MPC
}

# ── Entry/exit configurations to test ────────────────────────────────────────
# Signal filtration levels to compare — all use entry=09:25, exit=11:15 (best from prior test)
# BEAR_N = top N bearish combos, BULL_N = top N bullish combos
CONFIGS = [
    {'label': 'A_Bear3_Bull0',  'entry_time': '09:25', 'exit_time': '11:15', 'sl_lockout': None, 'bear_n':  3, 'bull_n': 0},
    {'label': 'B_Bear5_Bull3',  'entry_time': '09:25', 'exit_time': '11:15', 'sl_lockout': None, 'bear_n':  5, 'bull_n': 3},
    {'label': 'C_Bear10_Bull5', 'entry_time': '09:25', 'exit_time': '11:15', 'sl_lockout': None, 'bear_n': 10, 'bull_n': 5},
    {'label': 'D_Bear10_Bull0', 'entry_time': '09:25', 'exit_time': '11:15', 'sl_lockout': None, 'bear_n': 10, 'bull_n': 0},
]

SL_GRID  = [0.15, 0.20, 0.25, 0.30, 0.35, 0.40]
TP_GRID  = [0.30, 0.40, 0.50, 0.60]
LOT_CONFIGS = [
    {'FIXED':  5, 'MAX_LOTS': 20, 'DTE0_MAX_LOTS': 10},
    {'FIXED': 10, 'MAX_LOTS': 20, 'DTE0_MAX_LOTS': 10},
    {'FIXED':  5, 'MAX_LOTS': 15, 'DTE0_MAX_LOTS':  5},
    {'FIXED': 10, 'MAX_LOTS': 25, 'DTE0_MAX_LOTS': 10},
    {'FIXED':  7, 'MAX_LOTS': 20, 'DTE0_MAX_LOTS': 10},
    {'FIXED': 15, 'MAX_LOTS': 30, 'DTE0_MAX_LOTS': 10},
]

INITIAL_CAPITAL  = 200_000
REFILL_THRESHOLD =  50_000

MONTH_ABBR = ['JAN','FEB','MAR','APR','MAY','JUN',
              'JUL','AUG','SEP','OCT','NOV','DEC']

# ══════════════════════════════════════════════════════════════════════════════
# 2. HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def date_to_dmy(d: date) -> str:
    return f"{d.day:02d}{MONTH_ABBR[d.month - 1]}{str(d.year)[2:]}"

def parse_dmy(s: str) -> date:
    day = int(s[:2])
    mon = MONTH_ABBR.index(s[2:5].upper()) + 1
    yr  = int(s[5:]) + 2000
    return date(yr, mon, day)

def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in NSE_HOLIDAYS

# ══════════════════════════════════════════════════════════════════════════════
# 3. LOAD NIFTY SPOT (2024Nifty files, yfinance fallback per missing date)
# ══════════════════════════════════════════════════════════════════════════════

print('Loading NIFTY spot data from 2024Nifty files...')
nifty_chunks = []
for fpath in sorted(NIFTY_DIR.glob('Nifty-2024*.csv')):
    df = pd.read_csv(fpath, header=0,
                     names=['datetime','open','high','low','close','volume'],
                     skiprows=1)
    df['datetime'] = pd.to_datetime(df['datetime'], format='%Y-%m-%d %H:%M', errors='coerce')
    df.dropna(subset=['datetime'], inplace=True)
    nifty_chunks.append(df)

nifty_spot = pd.concat(nifty_chunks).sort_values('datetime').reset_index(drop=True)
nifty_spot['date'] = nifty_spot['datetime'].dt.date
nifty_spot['time'] = nifty_spot['datetime'].dt.time
print(f'  Rows: {len(nifty_spot):,}  ({nifty_spot["date"].min()} → {nifty_spot["date"].max()})')

# Build daily open/close from real data
daily_from_file = (
    nifty_spot[nifty_spot['time'] == dtime(9, 15)][['date','open']]
    .rename(columns={'open': 'nifty_open'})
    .merge(
        nifty_spot.groupby('date')['close'].last().reset_index()
                  .rename(columns={'close': 'nifty_close'}),
        on='date'
    )
    .sort_values('date').reset_index(drop=True)
)
dates_in_file = set(daily_from_file['date'])

# Detect which 2024 trading days are missing from the files
all_2024_trading = [
    date(2024, 1, 1) + timedelta(days=i)
    for i in range(366)
    if is_trading_day(date(2024, 1, 1) + timedelta(days=i))
]
missing_dates = [d for d in all_2024_trading if d not in dates_in_file]

if missing_dates:
    print(f'  {len(missing_dates)} dates missing from files → fetching from yfinance...')
    yf_df = yf.download('^NSEI', start='2023-12-31', end='2025-01-02',
                        interval='1m', progress=False, auto_adjust=True)
    if isinstance(yf_df.columns, pd.MultiIndex):
        yf_df.columns = yf_df.columns.get_level_values(0)
    if yf_df.index.tz is not None:
        yf_df.index = yf_df.index.tz_convert('Asia/Kolkata')
    yf_df['date'] = yf_df.index.date
    yf_df['time'] = yf_df.index.time

    yf_open = (yf_df[yf_df['time'] == dtime(9, 15)][['date','Open']]
               .rename(columns={'Open': 'nifty_open'}))
    yf_close = (yf_df.groupby('date')['Close'].last().reset_index()
                .rename(columns={'Close': 'nifty_close'}))
    yf_daily = yf_open.merge(yf_close, on='date')
    yf_daily = yf_daily[yf_daily['date'].isin(missing_dates)]
    print(f'  yfinance filled {len(yf_daily)} dates')
    daily_nifty = (pd.concat([daily_from_file, yf_daily])
                   .sort_values('date').reset_index(drop=True))
else:
    daily_nifty = daily_from_file

print(f'  Daily NIFTY rows: {len(daily_nifty)}')

# ══════════════════════════════════════════════════════════════════════════════
# 4. EXPIRY SCHEDULE (Thursday-only in 2024)
# ══════════════════════════════════════════════════════════════════════════════

print('Loading expiry schedule...')
exp_raw = pd.read_csv(EXPIRY_CSV, header=0)
exp_col = exp_raw.iloc[:, 0].dropna().astype(str)
expiry_dates = sorted([
    parse_dmy(s.strip())
    for s in exp_col
    if len(s.strip()) == 7 and s.strip()[:2].isdigit()
    and parse_dmy(s.strip()).year == 2024
])
print(f'  2024 expiries: {len(expiry_dates)}  ({expiry_dates[0]} → {expiry_dates[-1]})')

def get_nearest_expiry(trade_date: date) -> date | None:
    for exp in expiry_dates:
        if exp >= trade_date:
            return exp
    return None

# ══════════════════════════════════════════════════════════════════════════════
# 5. GLOBAL MARKET DATA (yfinance — overnight signals)
# ══════════════════════════════════════════════════════════════════════════════

print('Fetching global market data from yfinance...')
TICKERS = {
    'SP500'    : '^GSPC',
    'SGX'      : 'NKD=F',
    'DAX'      : '^GDAXI',
    'VIX_US'   : '^VIX',
    'VIX_INDIA': '^INDIAVIX',
}
raw_global = {}
for name, ticker in TICKERS.items():
    try:
        df = yf.download(ticker, start='2023-12-01', end='2025-01-05',
                         progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        raw_global[name] = df[['Close']].rename(columns={'Close': name})
        print(f'  {name}: {len(df)} rows')
    except Exception as e:
        print(f'  WARNING: {name} failed: {e}')
        raw_global[name] = pd.DataFrame()

global_df = None
for name, df in raw_global.items():
    if df.empty:
        continue
    df.index = pd.to_datetime(df.index).normalize()
    global_df = df if global_df is None else global_df.join(df, how='outer')
global_df = global_df.sort_index().ffill()

# ══════════════════════════════════════════════════════════════════════════════
# 6. BUILD DAILY SIGNALS DATAFRAME
# ══════════════════════════════════════════════════════════════════════════════

print('Building daily signals dataframe...')
rows = []
daily_nifty_sorted = daily_nifty.sort_values('date').reset_index(drop=True)

for i, row in daily_nifty_sorted.iterrows():
    d = row['date']
    if not isinstance(d, date):
        d = d.date() if hasattr(d, 'date') else d
    if d.year != 2024 or not is_trading_day(d):
        continue

    nifty_open  = float(row['nifty_open'])
    nifty_close = float(row['nifty_close'])

    prev_rows = daily_nifty_sorted[daily_nifty_sorted['date'] < d]
    if len(prev_rows) < 2:
        continue
    prev_close     = float(prev_rows.iloc[-1]['nifty_close'])
    prev_prev_close = float(prev_rows.iloc[-2]['nifty_close'])

    gap_pct        = (nifty_open - prev_close) / prev_close
    prev_india_ret = (prev_close - prev_prev_close) / prev_prev_close

    ts = pd.Timestamp(d)
    global_before = global_df[global_df.index < ts]
    if len(global_before) < 2:
        continue

    def _ret(col):
        if col not in global_before.columns:
            return 0.0
        vals = global_before[col].dropna()
        if len(vals) < 2:
            return 0.0
        return float((vals.iloc[-1] - vals.iloc[-2]) / vals.iloc[-2])

    sp500_ret  = _ret('SP500')
    sgx_ret    = _ret('SGX')
    dax_ret    = _ret('DAX')
    vix_us_ret = _ret('VIX_US')

    global_today = global_df[global_df.index <= ts]
    vix_india = (float(global_today['VIX_INDIA'].dropna().iloc[-1])
                 if 'VIX_INDIA' in global_today.columns and not global_today['VIX_INDIA'].dropna().empty
                 else 15.0)

    actual_ret = (nifty_close - nifty_open) / nifty_open
    dir_actual = -1 if actual_ret < 0 else 1

    rows.append({
        'date'          : d,
        'nifty_open'    : nifty_open,
        'nifty_close'   : nifty_close,
        'gap_pct'       : gap_pct,
        'prev_india_ret': prev_india_ret,
        'SP500_ret'     : sp500_ret,
        'SGX_ret'       : sgx_ret,
        'DAX_ret'       : dax_ret,
        'VIX_US_ret'    : vix_us_ret,
        'vix_india'     : vix_india,
        'actual_ret'    : actual_ret,
        'dir_actual'    : dir_actual,
    })

daily_df = pd.DataFrame(rows)
print(f'  Days built: {len(daily_df)}')

# ══════════════════════════════════════════════════════════════════════════════
# 7. SIGNAL CLASSIFICATION
# ══════════════════════════════════════════════════════════════════════════════

print('Loading signal library...')
reliable    = pd.read_csv(SIGNALS_CSV)
all_bearish = (reliable[reliable['P_Down'] > BASE_RATE]
               .sort_values('Edge_pp', ascending=False).reset_index(drop=True))
all_bullish = (reliable[reliable['P_Down'] < (100 - BASE_RATE)]
               .sort_values('P_Down').reset_index(drop=True))
print(f'  Bearish pool: {len(all_bearish)} combos  |  Bullish pool: {len(all_bullish)} combos')

def compute_signals(r: dict) -> dict:
    return {
        'Gap Up'         : r['gap_pct']       >  GAP_THRESHOLD,
        'Gap Up Strong'  : r['gap_pct']       >  GAP_LARGE_THRESHOLD,
        'Gap Down'       : r['gap_pct']       < -GAP_THRESHOLD,
        'Prev India UP'  : r['prev_india_ret'] > 0,
        'Prev India DOWN': r['prev_india_ret'] < 0,
        'US UP'          : r['SP500_ret']      > 0,
        'US DOWN'        : r['SP500_ret']      < 0,
        'SGX UP'         : r['SGX_ret']        > 0,
        'SGX DOWN'       : r['SGX_ret']        < 0,
        'DAX UP'         : r['DAX_ret']        > 0,
        'VIX Rising'     : r['VIX_US_ret']     > VIX_RISING_THRESHOLD,
        'VIX Falling'    : r['VIX_US_ret']     < 0,
        'VIX Spike'      : r['VIX_US_ret']     > VIX_SPIKE_THRESHOLD,
    }

def combo_fires(signals: dict, combo_str: str) -> bool:
    return all(signals.get(s.strip(), False) for s in combo_str.split('+'))

def build_tradeable(bear_n: int, bull_n: int) -> pd.DataFrame:
    bear_combos = list(all_bearish['Signal'][:bear_n])
    bull_combos = list(all_bullish['Signal'][:bull_n])
    rows, skip_mon, skip_ev = [], 0, 0
    for _, row in daily_df.iterrows():
        d = row['date']
        if d.weekday() == 0:
            skip_mon += 1; continue
        if d in EVENT_DAYS:
            skip_ev  += 1; continue
        s = compute_signals(row.to_dict())
        bf  = [c for c in bear_combos if combo_fires(s, c)]
        bulf= [c for c in bull_combos if combo_fires(s, c)]
        if not bf and not bulf:
            continue
        action = 'BEARISH' if bf else 'BULLISH'
        rows.append({
            'date'      : d,
            'action'    : action,
            'combo'     : (bf or bulf)[0],
            'nifty_open': row['nifty_open'],
            'vix_india' : row['vix_india'],
            'dir_actual': row['dir_actual'],
            'actual_ret': row['actual_ret'],
        })
    df = pd.DataFrame(rows)
    bear_ct = (df['action']=='BEARISH').sum() if not df.empty else 0
    bull_ct = (df['action']=='BULLISH').sum() if not df.empty else 0
    print(f'    bear_n={bear_n} bull_n={bull_n} → {len(df)} trades  (BEAR={bear_ct} BULL={bull_ct}  Mon_skip={skip_mon} Ev_skip={skip_ev})')
    return df

# Pre-build tradeable sets for each unique (bear_n, bull_n) combo
print('Building tradeable day sets...')
_tradeable_cache: dict = {}
for cfg in CONFIGS:
    key = (cfg['bear_n'], cfg['bull_n'])
    if key not in _tradeable_cache:
        _tradeable_cache[key] = build_tradeable(*key)

# For backward compatibility the main loop uses per-config tradeable_df
tradeable_df = _tradeable_cache[(CONFIGS[0]['bear_n'], CONFIGS[0]['bull_n'])]  # placeholder

# ══════════════════════════════════════════════════════════════════════════════
# 8. OPTION DATA LOADER
# ══════════════════════════════════════════════════════════════════════════════

_opt_cache: dict = {}

def load_option_file(trade_date: date, expiry: date) -> pd.DataFrame | None:
    key = (trade_date, expiry)
    if key in _opt_cache:
        return _opt_cache[key]
    mon_str = MONTH_ABBR[trade_date.month - 1]
    fpath   = DATA_DIR / f'2024{mon_str}' / f'NIFTY-{date_to_dmy(expiry)}-{date_to_dmy(trade_date)}.csv'
    if not fpath.exists():
        _opt_cache[key] = None
        return None
    df = pd.read_csv(fpath)
    df.columns = [c.strip() for c in df.columns]
    _opt_cache[key] = df
    return df

def get_entry_price(trade_date, expiry, strike: int, opt_type: str,
                    entry_time: str = '09:15') -> float | None:
    df = load_option_file(trade_date, expiry)
    if df is None:
        return None
    mask = (df['strike_price'] == strike) & (df['right'] == opt_type) & (df['datetime'] == entry_time)
    rows = df[mask]
    if rows.empty:
        # Use first available candle at or after entry_time
        fb = df[(df['strike_price'] == strike) & (df['right'] == opt_type)
                & (df['datetime'] >= entry_time)].sort_values('datetime')
        if fb.empty:
            return None
        rows = fb.head(1)
    price = float(rows.iloc[0]['open'])
    return price if price > 0 else None

def get_option_candles(trade_date, expiry, strike: int, opt_type: str,
                       entry_time: str = '09:15', exit_time: str = '10:15') -> pd.DataFrame:
    df = load_option_file(trade_date, expiry)
    if df is None:
        return pd.DataFrame()
    mask = (df['strike_price'] == strike) & (df['right'] == opt_type)
    candles = df[mask].copy()
    candles = candles[(candles['datetime'] >= entry_time) & (candles['datetime'] <= exit_time)]
    return candles.sort_values('datetime').reset_index(drop=True)

# ══════════════════════════════════════════════════════════════════════════════
# 9. PRE-CACHE ENTRY DATA — per config (entry time varies)
# ══════════════════════════════════════════════════════════════════════════════

def build_entry_cache(cfg: dict) -> dict:
    entry_time = cfg['entry_time']
    exit_time  = cfg['exit_time']
    cache      = {}
    tradeable_df = _tradeable_cache[(cfg['bear_n'], cfg['bull_n'])]
    print(f"\n  [{cfg['label']}] entry={entry_time}  exit={exit_time}  trades={len(tradeable_df)}")
    for _, trow in tradeable_df.iterrows():
        d          = trow['date']
        action     = trow['action']
        nifty_open = trow['nifty_open']

        expiry = get_nearest_expiry(d)
        if expiry is None:
            cache[d] = None
            continue

        dte    = (expiry - d).days
        atm    = round(nifty_open / STRIKE_STEP) * STRIKE_STEP
        opt    = 'PE' if action == 'BEARISH' else 'CE'
        strike = (atm - STRIKE_STEP * STRIKES_OTM if action == 'BEARISH'
                  else atm + STRIKE_STEP * STRIKES_OTM)

        entry_price = get_entry_price(d, expiry, int(strike), opt, entry_time)
        if entry_price is None:
            cache[d] = None
            print(f'    {d}: SKIPPED — no {entry_time} price for {strike}{opt}')
            continue

        candles = get_option_candles(d, expiry, int(strike), opt, entry_time, exit_time)
        if candles.empty:
            cache[d] = None
            print(f'    {d}: SKIPPED — no candles in [{entry_time}–{exit_time}]')
            continue

        cache[d] = {
            'expiry'     : expiry,
            'dte'        : dte,
            'opt'        : opt,
            'strike'     : int(strike),
            'atm'        : int(atm),
            'entry_price': entry_price,
            'candles'    : candles,
        }
        print(f'    {d}  {strike}{opt}  DTE={dte}  entry={entry_price:.1f}  '
              f'candles={len(candles)}')

    loaded  = sum(1 for v in cache.values() if v is not None)
    skipped = sum(1 for v in cache.values() if v is None)
    print(f'    → Loaded={loaded}  Skipped={skipped}')
    return cache

# ══════════════════════════════════════════════════════════════════════════════
# 10. TRADE SIMULATION (real candles, no BS)
# ══════════════════════════════════════════════════════════════════════════════

def simulate_trade(d: date, sl_pct: float, tp_pct: float,
                   entry_cache: dict, exit_time: str, sl_lockout: str | None) -> dict | None:
    info = entry_cache.get(d)
    if info is None:
        return None

    entry_price = info['entry_price']
    candles     = info['candles']
    sl_price    = entry_price * (1 - sl_pct)
    tp_price    = entry_price * (1 + tp_pct)

    exit_price  = None
    exit_reason = f'{exit_time} exit'
    exit_t      = exit_time

    for _, row in candles.iterrows():
        t_str  = str(row['datetime'])
        low_p  = float(row['low'])
        high_p = float(row['high'])

        if high_p >= tp_price:
            exit_price, exit_reason, exit_t = tp_price, 'Target Hit', t_str
            break

        sl_active = (sl_lockout is None) or (t_str >= sl_lockout)
        if sl_active and low_p <= sl_price:
            exit_price, exit_reason, exit_t = sl_price, 'Stop Loss', t_str
            break

    if exit_price is None:
        row_exit = candles[candles['datetime'] == exit_time]
        if not row_exit.empty:
            exit_price = float(row_exit.iloc[0]['close'])
        else:
            last = candles[candles['datetime'] <= exit_time]
            exit_price = float(last.iloc[-1]['close']) if not last.empty else entry_price

    return {
        'expiry'     : info['expiry'],
        'dte'        : info['dte'],
        'opt'        : info['opt'],
        'strike'     : info['strike'],
        'atm'        : info['atm'],
        'entry_price': entry_price,
        'exit_price' : round(exit_price, 2),
        'exit_reason': exit_reason,
        'exit_time'  : exit_t,
        'pnl_pts'    : round(exit_price - entry_price, 2),
    }

# ══════════════════════════════════════════════════════════════════════════════
# 11. CAPITAL / XIRR METRICS
# ══════════════════════════════════════════════════════════════════════════════

def compute_capital_metrics(trades: list[dict], lot_cfg: dict) -> dict:
    FIXED        = lot_cfg['FIXED']
    MAX_LOTS     = lot_cfg['MAX_LOTS']
    DTE0_CAP     = lot_cfg['DTE0_MAX_LOTS']

    capital      = float(INITIAL_CAPITAL)
    peak         = capital
    max_dd       = 0.0
    refill_count = 0
    total_refill = 0.0
    t0           = date(2024, 1, 1)
    cash_flows   = [(-capital, t0)]

    for tr in trades:
        lots = FIXED
        if capital > 0:
            lots = min(int(capital // (tr['entry_price'] * LOT_SIZE)), MAX_LOTS)
            lots = max(lots, FIXED)
        if tr['dte'] == 0:
            lots = min(lots, DTE0_CAP)
        lots = max(lots, 1)

        pnl_rs   = tr['pnl_pts'] * lots * LOT_SIZE - BROKERAGE
        capital += pnl_rs

        if capital > peak:
            peak = capital
        dd = (peak - capital) / peak * 100
        if dd > max_dd:
            max_dd = dd

        if capital < REFILL_THRESHOLD:
            refill    = INITIAL_CAPITAL - capital
            capital  += refill
            peak      = max(peak, capital)
            refill_count += 1
            total_refill += refill
            cash_flows.append((-refill, tr['expiry']))

    cash_flows.append((capital, date(2024, 12, 31)))

    def npv(rate):
        return sum(amt / (1 + rate) ** ((d - t0).days / 365.25) for amt, d in cash_flows)

    xirr = None
    try:
        lo, hi = -0.999, 100.0
        for _ in range(300):
            mid = (lo + hi) / 2
            if npv(mid) > 0:
                lo = mid
            else:
                hi = mid
            if hi - lo < 1e-7:
                break
        xirr = round((lo + hi) / 2 * 100, 1)
    except Exception:
        pass

    return {
        'final_capital' : round(capital, 0),
        'net_return_pct': round((capital - INITIAL_CAPITAL - total_refill) / INITIAL_CAPITAL * 100, 1),
        'xirr_pct'      : xirr,
        'max_dd_pct'    : round(max_dd, 1),
        'refill_count'  : refill_count,
        'total_refilled': round(total_refill, 0),
    }

# ══════════════════════════════════════════════════════════════════════════════
# 12. MULTI-CONFIG GRID SEARCH
# ══════════════════════════════════════════════════════════════════════════════

print('\nPre-loading option data for all configs...')
all_entry_caches = {cfg['label']: build_entry_cache(cfg) for cfg in CONFIGS}

all_results   = {}   # cfg_label → summary_df
all_trades    = {}   # cfg_label → {sheet_key: [trade dicts]}
comparison    = []   # one row per cfg × reference SL/TP

total_combos = len(SL_GRID) * len(TP_GRID) * len(LOT_CONFIGS)

for cfg in CONFIGS:
    label      = cfg['label']
    exit_time  = cfg['exit_time']
    sl_lockout = cfg['sl_lockout']
    entry_cache = all_entry_caches[label]

    tradeable_df  = _tradeable_cache[(cfg['bear_n'], cfg['bull_n'])]

    print(f'\n{"═"*70}')
    print(f'CONFIG {label}  —  entry={cfg["entry_time"]}  exit={exit_time}  '
          f'bear_n={cfg["bear_n"]}  bull_n={cfg["bull_n"]}  trades={len(tradeable_df)}')
    print('═' * 70)

    summary_rows = []
    trade_sheets = {}
    combo_idx    = 0

    for sl_pct, tp_pct in itertools.product(SL_GRID, TP_GRID):
        trade_results = []
        for _, trow in tradeable_df.iterrows():
            d   = trow['date']
            res = simulate_trade(d, sl_pct, tp_pct, entry_cache, exit_time, sl_lockout)
            if res is None:
                continue
            pred_dir = -1 if trow['action'] == 'BEARISH' else 1
            trade_results.append({
                **res,
                'date'      : d,
                'action'    : trow['action'],
                'combo'     : trow['combo'],
                'nifty_open': trow['nifty_open'],
                'dir_actual': trow['dir_actual'],
                'actual_ret': trow['actual_ret'],
                'correct'   : pred_dir == trow['dir_actual'],
            })

        if not trade_results:
            continue

        n        = len(trade_results)
        wins     = sum(1 for t in trade_results if t['pnl_pts'] > 0)
        win_rate = round(wins / n * 100, 1)
        avg_pnl  = round(np.mean([t['pnl_pts'] for t in trade_results]), 2)
        tot_pnl  = round(sum(t['pnl_pts'] for t in trade_results), 2)

        sheet_key = f'SL{int(sl_pct*100)}_TP{int(tp_pct*100)}'
        trade_sheets[sheet_key] = trade_results

        for lot_cfg in LOT_CONFIGS:
            combo_idx += 1
            metrics = compute_capital_metrics(trade_results, lot_cfg)
            summary_rows.append({
                'Config'            : label,
                'SL %'              : f'{sl_pct:.0%}',
                'TP %'              : f'{tp_pct:.0%}',
                'FIXED'             : lot_cfg['FIXED'],
                'MAX_LOTS'          : lot_cfg['MAX_LOTS'],
                'DTE0_MAX_LOTS'     : lot_cfg['DTE0_MAX_LOTS'],
                'Trades'            : n,
                'Wins'              : wins,
                'Win Rate %'        : win_rate,
                'Avg PnL/Trade (pts)': avg_pnl,
                'Total PnL (pts)'   : tot_pnl,
                'Initial Capital'   : INITIAL_CAPITAL,
                'Final Capital'     : metrics['final_capital'],
                'Net Return %'      : metrics['net_return_pct'],
                'XIRR %'            : metrics['xirr_pct'],
                'Max Drawdown %'    : metrics['max_dd_pct'],
                'Refill Count'      : metrics['refill_count'],
                'Total Refilled'    : metrics['total_refilled'],
            })

            if combo_idx % 12 == 0 or combo_idx == total_combos:
                print(f'  [{combo_idx:>3}/{total_combos}]  SL={sl_pct:.0%}  TP={tp_pct:.0%}  '
                      f'FIXED={lot_cfg["FIXED"]:>2}  win={win_rate}%  '
                      f'XIRR={metrics["xirr_pct"]}%  DD={metrics["max_dd_pct"]}%')

    all_results[label] = pd.DataFrame(summary_rows)
    all_trades[label]  = trade_sheets

    # reference row for comparison table (SL=20%, TP=40%, FIXED=5)
    ref = [r for r in summary_rows
           if r['SL %'] == '20%' and r['TP %'] == '40%' and r['FIXED'] == 5]
    if ref:
        r = ref[0]
        comparison.append({
            'Config'         : label,
            'Bear Combos'    : cfg['bear_n'],
            'Bull Combos'    : cfg['bull_n'],
            'Entry Time'     : cfg['entry_time'],
            'Exit Time'      : exit_time,
            'Trades'         : r['Trades'],
            'Win Rate %'     : r['Win Rate %'],
            'Total PnL (pts)': r['Total PnL (pts)'],
            'XIRR %'         : r['XIRR %'],
            'Max DD %'       : r['Max Drawdown %'],
        })

# ══════════════════════════════════════════════════════════════════════════════
# 13. EXPORT — one Excel, separate sheet groups per config + comparison
# ══════════════════════════════════════════════════════════════════════════════

print('\nExporting to Excel...')
out_path = OUTPUT_DIR / 'grid_search_signal_width.xlsx'

with pd.ExcelWriter(out_path, engine='openpyxl') as writer:

    # Comparison summary first
    pd.DataFrame(comparison).to_excel(writer, sheet_name='⭐ Config Comparison', index=False)

    # Combined master across all configs
    combined = pd.concat(all_results.values(), ignore_index=True)
    combined.to_excel(writer, sheet_name='All Configs Master', index=False)

    for cfg in CONFIGS:
        label      = cfg['label']
        short      = label[:3]   # A, B, C prefix
        df         = all_results[label]
        trade_dict = all_trades[label]

        if df.empty:
            continue

        # Per-config summary
        df.to_excel(writer, sheet_name=f'{short} Summary', index=False)

        # Top 10 by XIRR for this config
        (df.dropna(subset=['XIRR %'])
           .sort_values('XIRR %', ascending=False)
           .head(10)
           .to_excel(writer, sheet_name=f'{short} Top10 XIRR', index=False))

        # XIRR pivot (FIXED=5)
        piv = df[df['FIXED'] == 5].pivot_table(values='XIRR %', index='SL %', columns='TP %')
        piv.to_excel(writer, sheet_name=f'{short} XIRR Pivot')

        # Win rate pivot (FIXED=5)
        piv_wr = df[df['FIXED'] == 5].pivot_table(values='Win Rate %', index='SL %', columns='TP %')
        piv_wr.to_excel(writer, sheet_name=f'{short} WinRate Pivot')

        # Trade detail for SL=20% TP=40%
        ref_key = 'SL20_TP40'
        if ref_key in trade_dict:
            trades = trade_dict[ref_key]
            detail = [{
                'Date'           : t['date'],
                'Action'         : t['action'],
                'NIFTY Open'     : int(round(t['nifty_open'])),
                'Strike'         : f"{t['strike']} {t['opt']}",
                'DTE'            : t['dte'],
                'Entry (pts)'    : t['entry_price'],
                'Exit (pts)'     : t['exit_price'],
                'Exit Reason'    : t['exit_reason'],
                'Exit Time'      : t['exit_time'],
                'P&L (pts)'      : t['pnl_pts'],
                'P&L (Rs) 1-lot' : round(t['pnl_pts'] * LOT_SIZE - BROKERAGE, 2),
                'Correct?'       : 'YES' if t['correct'] else 'NO',
                'Actual Dir'     : 'DOWN' if t['dir_actual'] == -1 else 'UP',
                'Actual Ret%'    : f"{t['actual_ret']:+.2%}",
            } for t in trades]
            pd.DataFrame(detail).to_excel(
                writer, sheet_name=f'{short} Trades SL20 TP40', index=False)

print(f'\n{"="*70}')
print(f'Output: {out_path}')
print(f'{"="*70}')

# ── Console comparison ─────────────────────────────────────────────────────────
print('\n⭐  CONFIG COMPARISON  (SL=20%, TP=40%, FIXED=5 lots)\n')
print(f'{"Config":<35} {"Entry":>6} {"Exit":>6} {"Trades":>7} {"Win%":>6} '
      f'{"TotPnL":>10} {"XIRR%":>8} {"MaxDD%":>8}')
print('-' * 95)
for row in comparison:
    print(f'{row["Config"]:<35} {row["Entry Time"]:>6} {row["Exit Time"]:>6} '
          f'{row["Trades"]:>7} {row["Win Rate %"]:>6} '
          f'{row["Total PnL (pts)"]:>10.1f} {str(row["XIRR %"]):>8} {row["Max DD %"]:>8}')
