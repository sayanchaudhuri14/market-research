#!/usr/bin/env python3
"""
grid_search_sl_tp.py
──────────────────────────────────────────────────────────────────────────────
SL × TP grid search for D_Bear10_Bull0 (entry=09:25, exit=11:15, bearish only)

Key differences from grid_search_real.py:
  1. Dynamic initial capital = first-trade cost (entry_price × 75 × lots)
     — not a hardcoded flat ₹2,00,000
  2. Lot sizing: floor(capital / cost_per_lot), capped at MAX_LOTS
     — never borrows / goes negative
  3. Single config, single lot setup — focused SL/TP comparison
  4. Wider SL grid (5 % → 50%) and TP grid (10% → 120%)

Run:
  cd market-research
  python backtesting_2024_options/grid_search_sl_tp.py
──────────────────────────────────────────────────────────────────────────────
"""

import sys, warnings
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
# 1. PATHS & CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

HERE        = Path(__file__).parent
DATA_DIR    = HERE / '2024'
NIFTY_DIR   = DATA_DIR / '2024Nifty'
EXPIRY_CSV  = DATA_DIR / 'expiry.csv'
SIGNALS_CSV = HERE.parent / 'v2' / 'v2_reliable_signals.csv'
OUTPUT_DIR  = HERE / 'backtest_outputs'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

STRIKE_STEP = 50
STRIKES_OTM = 1
LOT_SIZE    = 75
BROKERAGE   = 80       # Rs per trade (both legs)
BASE_RATE   = 54.5

GAP_THRESHOLD        = 0.0015
GAP_LARGE_THRESHOLD  = 0.0050
VIX_RISING_THRESHOLD = 0.03
VIX_SPIKE_THRESHOLD  = 0.05

# ── Config (D_Bear10_Bull0 — best from signal-width test) ────────────────────
ENTRY_TIME = '09:25'
EXIT_TIME  = '11:15'
BEAR_N     = 10
BULL_N     = 0

# ── Lot sizing ───────────────────────────────────────────────────────────────
FIXED_LOTS    = 10    # base lots
MAX_LOTS      = 25    # hard cap (as capital grows)
DTE0_MAX_LOTS = 10    # cap on expiry day

# ── SL / TP grid ─────────────────────────────────────────────────────────────
SL_GRID = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50]
TP_GRID = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.80, 1.00, 1.20]

NSE_HOLIDAYS = {
    date(2024,  1, 22), date(2024,  3, 25), date(2024,  3, 29),
    date(2024,  4, 11), date(2024,  4, 14), date(2024,  4, 17),
    date(2024,  5,  1), date(2024,  6, 17), date(2024,  8, 15),
    date(2024, 10,  2), date(2024, 10, 24), date(2024, 11, 15),
    date(2024, 12, 25),
}

EVENT_DAYS = {
    date(2024,  2,  1), date(2024,  4,  5), date(2024,  6,  4),
    date(2024,  6,  5), date(2024,  6,  7), date(2024,  7, 23),
    date(2024,  8,  8), date(2024, 10,  9), date(2024, 12,  6),
}

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
# 3. NIFTY SPOT DATA
# ══════════════════════════════════════════════════════════════════════════════

print('Loading NIFTY spot data...')
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

all_2024_trading = [
    date(2024, 1, 1) + timedelta(days=i)
    for i in range(366)
    if is_trading_day(date(2024, 1, 1) + timedelta(days=i))
]
missing_dates = [d for d in all_2024_trading if d not in set(daily_from_file['date'])]

if missing_dates:
    print(f'  {len(missing_dates)} dates missing — fetching from yfinance...')
    yf_df = yf.download('^NSEI', start='2023-12-31', end='2025-01-02',
                        interval='1m', progress=False, auto_adjust=True)
    if isinstance(yf_df.columns, pd.MultiIndex):
        yf_df.columns = yf_df.columns.get_level_values(0)
    if yf_df.index.tz is not None:
        yf_df.index = yf_df.index.tz_convert('Asia/Kolkata')
    yf_df['date'] = yf_df.index.date
    yf_df['time'] = yf_df.index.time
    yf_open  = yf_df[yf_df['time'] == dtime(9, 15)][['date','Open']].rename(columns={'Open': 'nifty_open'})
    yf_close = yf_df.groupby('date')['Close'].last().reset_index().rename(columns={'Close': 'nifty_close'})
    yf_daily = yf_open.merge(yf_close, on='date')
    yf_daily = yf_daily[yf_daily['date'].isin(missing_dates)]
    daily_nifty = pd.concat([daily_from_file, yf_daily]).sort_values('date').reset_index(drop=True)
else:
    daily_nifty = daily_from_file

print(f'  Daily rows: {len(daily_nifty)}')

# ══════════════════════════════════════════════════════════════════════════════
# 4. EXPIRY SCHEDULE
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

def get_nearest_expiry(trade_date: date) -> date | None:
    for exp in expiry_dates:
        if exp >= trade_date:
            return exp
    return None

# ══════════════════════════════════════════════════════════════════════════════
# 5. GLOBAL MARKET DATA (overnight signals)
# ══════════════════════════════════════════════════════════════════════════════

print('Fetching global market data...')
TICKERS = {
    'SP500': '^GSPC', 'SGX': 'NKD=F', 'DAX': '^GDAXI',
    'VIX_US': '^VIX', 'VIX_INDIA': '^INDIAVIX',
}
raw_global = {}
for name, ticker in TICKERS.items():
    try:
        df = yf.download(ticker, start='2023-12-01', end='2025-01-05',
                         progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        raw_global[name] = df[['Close']].rename(columns={'Close': name})
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
# 6. DAILY SIGNALS
# ══════════════════════════════════════════════════════════════════════════════

print('Building daily signals...')
rows = []
for i, row in daily_nifty.sort_values('date').iterrows():
    d = row['date']
    if not isinstance(d, date):
        d = d.date() if hasattr(d, 'date') else d
    if d.year != 2024 or not is_trading_day(d):
        continue

    nifty_open  = float(row['nifty_open'])
    nifty_close = float(row['nifty_close'])

    prev_rows = daily_nifty[daily_nifty['date'] < d]
    if len(prev_rows) < 2:
        continue
    prev_close      = float(prev_rows.iloc[-1]['nifty_close'])
    prev_prev_close = float(prev_rows.iloc[-2]['nifty_close'])

    gap_pct         = (nifty_open - prev_close) / prev_close
    prev_india_ret  = (prev_close - prev_prev_close) / prev_prev_close

    ts             = pd.Timestamp(d)
    global_before  = global_df[global_df.index < ts]
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
    rows.append({
        'date'          : d,
        'nifty_open'    : nifty_open,
        'gap_pct'       : gap_pct,
        'prev_india_ret': prev_india_ret,
        'SP500_ret'     : sp500_ret,
        'SGX_ret'       : sgx_ret,
        'DAX_ret'       : dax_ret,
        'VIX_US_ret'    : vix_us_ret,
        'vix_india'     : vix_india,
        'actual_ret'    : actual_ret,
    })

daily_df = pd.DataFrame(rows)
print(f'  Days built: {len(daily_df)}')

# ══════════════════════════════════════════════════════════════════════════════
# 7. SIGNAL CLASSIFICATION
# ══════════════════════════════════════════════════════════════════════════════

print('Loading signals...')
reliable    = pd.read_csv(SIGNALS_CSV)
all_bearish = reliable[reliable['P_Down'] > BASE_RATE].sort_values('Edge_pp', ascending=False).reset_index(drop=True)
bear_combos = list(all_bearish['Signal'][:BEAR_N])
print(f'  Using top {BEAR_N} bearish combos')

def compute_signals(r: dict) -> dict:
    return {
        'Gap Up'         : r['gap_pct']        >  GAP_THRESHOLD,
        'Gap Up Strong'  : r['gap_pct']        >  GAP_LARGE_THRESHOLD,
        'Gap Down'       : r['gap_pct']        < -GAP_THRESHOLD,
        'Prev India UP'  : r['prev_india_ret']  > 0,
        'Prev India DOWN': r['prev_india_ret']  < 0,
        'US UP'          : r['SP500_ret']       > 0,
        'US DOWN'        : r['SP500_ret']       < 0,
        'SGX UP'         : r['SGX_ret']         > 0,
        'SGX DOWN'       : r['SGX_ret']         < 0,
        'DAX UP'         : r['DAX_ret']         > 0,
        'VIX Rising'     : r['VIX_US_ret']      > VIX_RISING_THRESHOLD,
        'VIX Falling'    : r['VIX_US_ret']      < 0,
        'VIX Spike'      : r['VIX_US_ret']      > VIX_SPIKE_THRESHOLD,
    }

def combo_fires(signals: dict, combo_str: str) -> bool:
    return all(signals.get(s.strip(), False) for s in combo_str.split('+'))

# Build tradeable days
tradeable_rows = []
for _, row in daily_df.iterrows():
    d = row['date']
    if d.weekday() == 0 or d in EVENT_DAYS:
        continue
    s  = compute_signals(row.to_dict())
    bf = [c for c in bear_combos if combo_fires(s, c)]
    if not bf:
        continue
    tradeable_rows.append({
        'date'      : d,
        'action'    : 'BEARISH',
        'combo'     : bf[0],
        'nifty_open': row['nifty_open'],
    })

tradeable_df = pd.DataFrame(tradeable_rows)
print(f'  Tradeable days: {len(tradeable_df)}')

# ══════════════════════════════════════════════════════════════════════════════
# 8. OPTION DATA LOADER
# ══════════════════════════════════════════════════════════════════════════════

_opt_cache: dict = {}

def load_option_file(trade_date: date, expiry: date):
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

def get_entry_price(trade_date, expiry, strike: int, opt_type: str) -> float | None:
    df = load_option_file(trade_date, expiry)
    if df is None:
        return None
    mask = (df['strike_price'] == strike) & (df['right'] == opt_type) & (df['datetime'] == ENTRY_TIME)
    rows = df[mask]
    if rows.empty:
        fb = df[(df['strike_price'] == strike) & (df['right'] == opt_type)
                & (df['datetime'] >= ENTRY_TIME)].sort_values('datetime')
        if fb.empty:
            return None
        rows = fb.head(1)
    price = float(rows.iloc[0]['open'])
    return price if price > 0 else None

def get_option_candles(trade_date, expiry, strike: int, opt_type: str) -> pd.DataFrame:
    df = load_option_file(trade_date, expiry)
    if df is None:
        return pd.DataFrame()
    mask    = (df['strike_price'] == strike) & (df['right'] == opt_type)
    candles = df[mask].copy()
    candles = candles[(candles['datetime'] >= ENTRY_TIME) & (candles['datetime'] <= EXIT_TIME)]
    return candles.sort_values('datetime').reset_index(drop=True)

# ══════════════════════════════════════════════════════════════════════════════
# 9. PRE-CACHE ENTRY DATA
# ══════════════════════════════════════════════════════════════════════════════

print(f'\nPre-loading option data (entry={ENTRY_TIME}, exit={EXIT_TIME})...')
entry_cache = {}
for _, trow in tradeable_df.iterrows():
    d          = trow['date']
    nifty_open = trow['nifty_open']
    expiry     = get_nearest_expiry(d)
    if expiry is None:
        entry_cache[d] = None
        continue

    dte    = (expiry - d).days
    atm    = round(nifty_open / STRIKE_STEP) * STRIKE_STEP
    strike = atm - STRIKE_STEP * STRIKES_OTM   # bearish → buy OTM PE

    ep      = get_entry_price(d, expiry, int(strike), 'PE')
    candles = get_option_candles(d, expiry, int(strike), 'PE')

    if ep is None or candles.empty:
        entry_cache[d] = None
        continue

    entry_cache[d] = {
        'expiry'     : expiry,
        'dte'        : dte,
        'strike'     : int(strike),
        'entry_price': ep,
        'candles'    : candles,
        'nifty_open' : nifty_open,
        'action'     : 'BEARISH',
    }

valid_days = [d for d, v in entry_cache.items() if v is not None]
print(f'  Loaded {len(valid_days)} days  ({len(entry_cache) - len(valid_days)} skipped)')

# ══════════════════════════════════════════════════════════════════════════════
# 10. SIMULATE ALL TRADES FOR A GIVEN SL / TP
# ══════════════════════════════════════════════════════════════════════════════

def run_trades(sl_pct: float, tp_pct: float) -> list[dict]:
    results = []
    for d in sorted(valid_days):
        info        = entry_cache[d]
        entry_price = info['entry_price']
        sl_price    = entry_price * (1 - sl_pct)
        tp_price    = entry_price * (1 + tp_pct)
        candles     = info['candles']

        exit_price  = None
        exit_reason = f'{EXIT_TIME} exit'
        exit_t      = EXIT_TIME

        for _, row in candles.iterrows():
            t_str  = str(row['datetime'])
            low_p  = float(row['low'])
            high_p = float(row['high'])

            if high_p >= tp_price:
                exit_price, exit_reason, exit_t = tp_price, 'Target Hit', t_str
                break
            if low_p <= sl_price:
                exit_price, exit_reason, exit_t = sl_price, 'Stop Loss', t_str
                break

        if exit_price is None:
            row_exit = candles[candles['datetime'] == EXIT_TIME]
            exit_price = (float(row_exit.iloc[0]['close']) if not row_exit.empty
                          else float(candles[candles['datetime'] <= EXIT_TIME].iloc[-1]['close']))

        results.append({
            'date'       : d,
            'dte'        : info['dte'],
            'strike'     : info['strike'],
            'entry_price': entry_price,
            'exit_price' : round(exit_price, 2),
            'exit_reason': exit_reason,
            'exit_time'  : exit_t,
            'pnl_pts'    : round(exit_price - entry_price, 2),
        })
    return results

# ══════════════════════════════════════════════════════════════════════════════
# 11. CAPITAL / XIRR — DYNAMIC STARTING CAPITAL
# ══════════════════════════════════════════════════════════════════════════════

def compute_metrics(trades: list[dict]) -> dict:
    if not trades:
        return {}

    first = trades[0]
    first_lots = min(FIXED_LOTS, DTE0_MAX_LOTS) if first['dte'] == 0 else FIXED_LOTS
    initial_capital = first['entry_price'] * LOT_SIZE * first_lots
    # ensure we start with at least enough to buy 1 lot
    initial_capital = max(initial_capital, first['entry_price'] * LOT_SIZE)

    capital      = float(initial_capital)
    peak         = capital
    max_dd       = 0.0
    refill_count = 0
    total_refill = 0.0
    t0           = trades[0]['date']
    cash_flows   = [(-capital, t0)]

    wins = 0
    for tr in trades:
        # Lot sizing: how many lots can we afford?
        cost_per_lot = tr['entry_price'] * LOT_SIZE
        affordable   = max(int(capital // cost_per_lot), 1) if cost_per_lot > 0 else 1
        lots         = min(affordable, MAX_LOTS)
        if tr['dte'] == 0:
            lots = min(lots, DTE0_MAX_LOTS)
        lots = max(lots, 1)

        pnl_rs   = tr['pnl_pts'] * lots * LOT_SIZE - BROKERAGE
        capital += pnl_rs

        if tr['pnl_pts'] > 0:
            wins += 1

        if capital > peak:
            peak = capital
        dd = (peak - capital) / peak * 100
        if dd > max_dd:
            max_dd = dd

        # Refill if capital drops below cost of FIXED_LOTS (minimum trade size)
        min_lots   = DTE0_MAX_LOTS if tr['dte'] == 0 else FIXED_LOTS
        min_needed = tr['entry_price'] * LOT_SIZE * min_lots
        if capital < min_needed:
            refill        = initial_capital - capital   # top back to initial
            capital      += refill
            peak          = max(peak, capital)
            refill_count += 1
            total_refill += refill
            cash_flows.append((-refill, tr['date']))

    cash_flows.append((capital, date(2024, 12, 31)))

    def npv(rate):
        return sum(amt / (1 + rate) ** ((d - t0).days / 365.25)
                   for amt, d in cash_flows)

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

    n = len(trades)
    return {
        'trades'          : n,
        'wins'            : wins,
        'win_pct'         : round(wins / n * 100, 1) if n else 0,
        'avg_pnl_pts'     : round(sum(t['pnl_pts'] for t in trades) / n, 2) if n else 0,
        'total_pnl_pts'   : round(sum(t['pnl_pts'] for t in trades), 2),
        'initial_capital' : round(initial_capital, 0),
        'final_capital'   : round(capital, 0),
        'net_return_pct'  : round((capital - initial_capital - total_refill) / initial_capital * 100, 1),
        'xirr_pct'        : xirr,
        'max_dd_pct'      : round(max_dd, 1),
        'refill_count'    : refill_count,
        'total_refilled'  : round(total_refill, 0),
        'breakeven_winpct': round(100 * (1 / (1 + (1 / (1/1)))), 1),  # placeholder — filled below
    }

# ══════════════════════════════════════════════════════════════════════════════
# 12. GRID SEARCH
# ══════════════════════════════════════════════════════════════════════════════

print(f'\nRunning {len(SL_GRID)} x {len(TP_GRID)} = {len(SL_GRID)*len(TP_GRID)} SL/TP combos...')
grid_results = []

for sl in SL_GRID:
    for tp in TP_GRID:
        if tp <= sl:           # TP must be larger than SL for positive EV
            continue
        trades  = run_trades(sl, tp)
        metrics = compute_metrics(trades)
        if not metrics:
            continue

        breakeven = round(sl / (sl + tp) * 100, 1)   # min win% to break even

        grid_results.append({
            'SL %'            : f'{sl:.0%}',
            'TP %'            : f'{tp:.0%}',
            'RR'              : round(tp / sl, 1),       # reward:risk ratio
            'Breakeven Win%'  : breakeven,
            'Trades'          : metrics['trades'],
            'Wins'            : metrics['wins'],
            'Win Rate %'      : metrics['win_pct'],
            'Win vs BEven'    : round(metrics['win_pct'] - breakeven, 1),  # edge above breakeven
            'Avg PnL (pts)'   : metrics['avg_pnl_pts'],
            'Total PnL (pts)' : metrics['total_pnl_pts'],
            'Initial Cap (Rs)': metrics['initial_capital'],
            'Final Cap (Rs)'  : metrics['final_capital'],
            'Net Return %'    : metrics['net_return_pct'],
            'XIRR %'          : metrics['xirr_pct'],
            'Max DD %'        : metrics['max_dd_pct'],
            'Refill Count'    : metrics['refill_count'],
            'Total Refilled'  : metrics['total_refilled'],
            '_sl'             : sl,
            '_tp'             : tp,
        })
        print(f'  SL={sl:.0%}  TP={tp:.0%}  RR={tp/sl:.1f}  '
              f'Wins={metrics["wins"]}/{metrics["trades"]}  '
              f'WinPct={metrics["win_pct"]}%  '
              f'XIRR={metrics["xirr_pct"]}%  '
              f'DD={metrics["max_dd_pct"]}%  '
              f'Start=Rs{metrics["initial_capital"]:,.0f}')

# ══════════════════════════════════════════════════════════════════════════════
# 13. WRITE OUTPUT
# ══════════════════════════════════════════════════════════════════════════════

results_df = pd.DataFrame(grid_results).drop(columns=['_sl', '_tp'])

# Sorted views
by_xirr   = results_df.sort_values('XIRR %', ascending=False).reset_index(drop=True)
by_dd     = results_df.sort_values('Max DD %').reset_index(drop=True)
# Efficient frontier: best XIRR for each DD bucket
by_rr     = results_df.sort_values(['RR', 'XIRR %'], ascending=[False, False]).reset_index(drop=True)

# Pivot: XIRR % — rows=SL, cols=TP
pivot_df = pd.DataFrame(grid_results)
xirr_pivot = pivot_df.pivot(index='SL %', columns='TP %', values='XIRR %')
win_pivot  = pivot_df.pivot(index='SL %', columns='TP %', values='Win Rate %')
dd_pivot   = pivot_df.pivot(index='SL %', columns='TP %', values='Max DD %')

# Top 20 by XIRR also get individual trade detail (best single combo)
best_sl = float(grid_results[0]['_sl']) if grid_results else 0.15
best_tp = float(grid_results[0]['_tp']) if grid_results else 0.40
best_row = by_xirr.iloc[0]
best_sl = float(best_row['SL %'].strip('%')) / 100
best_tp = float(best_row['TP %'].strip('%')) / 100
best_trades = run_trades(best_sl, best_tp)

month_names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
trade_rows = []
for tr in best_trades:
    trade_rows.append({
        'Date'       : tr['date'],
        'Strike'     : tr['strike'],
        'DTE'        : tr['dte'],
        'Entry (pts)': tr['entry_price'],
        'Exit (pts)' : tr['exit_price'],
        'Exit Reason': tr['exit_reason'],
        'Exit Time'  : tr['exit_time'],
        'P&L (pts)'  : tr['pnl_pts'],
        'P&L (Rs) 1-lot': round(tr['pnl_pts'] * LOT_SIZE, 0),
    })
best_trades_df = pd.DataFrame(trade_rows)

outfile = OUTPUT_DIR / 'grid_search_sl_tp.xlsx'
with pd.ExcelWriter(outfile, engine='openpyxl') as xl:
    by_xirr.to_excel(xl, sheet_name='By XIRR', index=False)
    by_dd.to_excel(xl, sheet_name='By DD', index=False)
    by_rr.to_excel(xl, sheet_name='By RR', index=False)
    xirr_pivot.to_excel(xl, sheet_name='XIRR Pivot')
    win_pivot.to_excel(xl,  sheet_name='WinRate Pivot')
    dd_pivot.to_excel(xl,   sheet_name='DD Pivot')
    best_trades_df.to_excel(xl, sheet_name=f'Best Trades (SL{int(best_sl*100)} TP{int(best_tp*100)})', index=False)

print(f'\nSaved: {outfile}')
print(f'\nTop 15 by XIRR:')
print(by_xirr[['SL %','TP %','RR','Breakeven Win%','Win Rate %','Win vs BEven',
                'XIRR %','Max DD %','Initial Cap (Rs)','Refill Count']].head(15).to_string(index=False))
print(f'\nTop 10 lowest drawdown:')
print(by_dd[['SL %','TP %','RR','Win Rate %','XIRR %','Max DD %','Initial Cap (Rs)']].head(10).to_string(index=False))
