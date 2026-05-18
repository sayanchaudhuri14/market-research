#!/usr/bin/env python3
"""Strip strategy backtest — same config, data, and engine as grid_search.ipynb."""
import sys, pickle, warnings
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from pathlib import Path
from datetime import date, timedelta

_NB   = Path(__file__).parent
_ROOT = _NB.parent.parent

sys.path.insert(0, str(_NB.parent))
from strategies.strip import get_legs as strip_get_legs

# ── Config (identical to notebook) ────────────────────────────────────────────
MERGE_DIR        = _ROOT / 'merged'
MERGE_OLD        = MERGE_DIR / 'old_format'
MERGE_NEW        = MERGE_DIR / 'expiry_wise'
KITE_DIR         = _ROOT / 'gap_trading' / 'kite_minute_cache'
CACHE_DIR        = _NB / 'gs_cache'

STARTING_CAPITAL = 100_000
SLIP_PER_UNIT    = 1.0
MARGIN_BUF       = 2.0
LOT_SIZE         = 75
STRIKE_STEP      = 50
ENTRY_TIME       = '09:21'
EXIT_TIME        = '15:20'
SPAN             = 25_000
MAX_LOTS         = 5

DTE_GRID = [0, 1, 2, 3, 4]
SL_GRID  = [0.50, 0.75, 1.00, 1.25, 1.50]
TP_GRID  = [0.25, 0.50, 0.75, 1.00]

NSE_HOLIDAYS = {
    date(2024,  1, 22), date(2024,  3, 25), date(2024,  3, 29), date(2024,  4, 14),
    date(2024,  4, 17), date(2024,  5, 23), date(2024,  6, 17), date(2024,  7, 17),
    date(2024,  8, 15), date(2024, 10,  2), date(2024, 10, 24), date(2024, 11,  1),
    date(2024, 11, 15), date(2024, 12, 25),
    date(2025,  2, 26), date(2025,  3, 14), date(2025,  3, 31), date(2025,  4, 10),
    date(2025,  4, 14), date(2025,  4, 18), date(2025,  5,  1), date(2025,  8, 15),
    date(2025,  8, 27), date(2025, 10,  2), date(2025, 10, 21), date(2025, 10, 22),
    date(2025, 11,  5), date(2025, 12, 25),
    date(2026,  1, 26), date(2026,  3, 26),
}

_MON       = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC']
OLD_CUTOFF = date(2024, 11, 1)
_NEW_CUTOFF = date(2024, 10, 3)

# ── Calendar ──────────────────────────────────────────────────────────────────
_d = date(2024, 1, 2)
sorted_days = []
while _d <= date(2026, 3, 31):
    if _d.weekday() < 5 and _d not in NSE_HOLIDAYS:
        sorted_days.append(_d)
    _d += timedelta(days=1)
all_days = set(sorted_days)

def d2dmy(d):
    return f'{d.day:02d}{_MON[d.month-1]}{str(d.year)[2:]}'

def parse_dmy(s):
    s = s.strip()
    return date(int(s[5:]) + 2000, _MON.index(s[2:5].upper()) + 1, int(s[:2]))

def _expiries_from_csv():
    csv = MERGE_DIR / 'expiry.csv'
    if not csv.exists():
        return []
    raw = pd.read_csv(csv, header=0)
    out = []
    for s in raw.iloc[:, 0].dropna().astype(str):
        s = s.strip()
        if len(s) == 7 and s[:2].isdigit():
            try:
                d = parse_dmy(s)
                if d < _NEW_CUTOFF:
                    out.append(d)
            except ValueError:
                pass
    return out

def _expiries_from_folders():
    if not MERGE_NEW.exists():
        return []
    return [
        date.fromisoformat(f.name)
        for f in MERGE_NEW.iterdir()
        if f.is_dir() and len(f.name) == 10 and f.name[4] == '-'
    ]

all_expiries  = sorted(set(_expiries_from_csv() + _expiries_from_folders()))
expiry_dates  = [e for e in all_expiries if e.weekday() < 5 and e not in NSE_HOLIDAYS]

def get_n_before(expiry, n):
    try:
        idx = sorted_days.index(expiry)
        return sorted_days[idx - n] if idx >= n else None
    except ValueError:
        return None

def get_window(start, end):
    return [d for d in sorted_days if start <= d <= end]

# ── Kite ATM map ──────────────────────────────────────────────────────────────
kite_map = {}
if KITE_DIR.exists():
    for fp in sorted(KITE_DIR.glob('minute_256265_*.pkl')):
        with open(fp, 'rb') as fh:
            chunk = pickle.load(fh)
        if chunk.index.tz is not None:
            chunk.index = chunk.index.tz_localize(None)
        for dt, row in chunk.iterrows():
            if dt.strftime('%H:%M') == '09:25':
                kite_map[dt.date()] = float(row['open'])

def _atm_from_options(opt_df):
    sub    = opt_df[opt_df['time_str'] == ENTRY_TIME]
    ce     = sub[sub['right'] == 'CE'].set_index('strike_price')['open']
    pe     = sub[sub['right'] == 'PE'].set_index('strike_price')['open']
    common = ce.index.intersection(pe.index)
    if common.empty:
        return None
    return int((ce[common] - pe[common]).abs().idxmin())

def get_atm(d, opt_df=None):
    if d in kite_map:
        return round(kite_map[d] / STRIKE_STEP) * STRIKE_STEP
    if opt_df is not None:
        return _atm_from_options(opt_df)
    return None

# ── Data loaders ──────────────────────────────────────────────────────────────
def _load_old(trade_date, expiry_date):
    mon = _MON[trade_date.month - 1]
    fp  = MERGE_OLD / f'2024{mon}' / f'NIFTY-{d2dmy(expiry_date)}-{d2dmy(trade_date)}.csv'
    if not fp.exists():
        return None
    df = pd.read_csv(fp)
    df.columns    = [c.strip() for c in df.columns]
    df['time_str'] = df['datetime'].astype(str).str[:5]
    return df

def _load_new(trade_date, expiry_date):
    exp_dir = MERGE_NEW / expiry_date.strftime('%Y-%m-%d')
    if not exp_dir.exists():
        return None
    exp_str = f'{expiry_date.day:02d}_{_MON[expiry_date.month-1]}_{str(expiry_date.year)[2:]}'
    files   = list(exp_dir.glob(f'NIFTY_*_*_{exp_str}.csv'))
    if not files:
        return None
    dfs = []
    for fp in files:
        parts = fp.stem.split('_')
        try:
            strike = int(parts[1]); right = parts[2]
        except (ValueError, IndexError):
            continue
        try:
            df = pd.read_csv(fp, usecols=['timestamp','open','high','low','close','volume','oi'])
        except Exception:
            continue
        df['ts'] = pd.to_datetime(df['timestamp']).dt.tz_localize(None)
        day = df[df['ts'].dt.date == trade_date].copy()
        if day.empty:
            continue
        day['time_str']     = day['ts'].dt.strftime('%H:%M')
        day['strike_price'] = strike
        day['right']        = right
        day.rename(columns={'oi': 'open_interest'}, inplace=True)
        dfs.append(day[['time_str','strike_price','right','open','high','low','close','open_interest','volume']])
    if not dfs:
        return None
    return (pd.concat(dfs).sort_values(['time_str','strike_price','right']).reset_index(drop=True))

def load_opt(trade_date, expiry_date):
    if expiry_date < OLD_CUTOFF:
        return _load_old(trade_date, expiry_date)
    return _load_new(trade_date, expiry_date)

_opt_cache = {}
def load_opt_cached(td, exp):
    k = (td, exp)
    if k not in _opt_cache:
        _opt_cache[k] = load_opt(td, exp)
    return _opt_cache[k]

# ── Engine (identical to notebook) ────────────────────────────────────────────
def compute_max_loss(legs, entry_px):
    strikes = [l.strike for l in legs]
    spots   = np.arange(min(strikes) - 10*STRIKE_STEP, max(strikes) + 11*STRIKE_STEP, STRIKE_STEP)
    worst   = 0.0
    for s in spots:
        pnl = 0.0
        for l in legs:
            intr = max(0, s - l.strike) if l.right == 'CE' else max(0, l.strike - s)
            ep   = entry_px[(l.strike, l.right)]
            pnl += ((ep - intr) if l.action == 'SELL' else (intr - ep)) * l.lots * LOT_SIZE
        worst = min(worst, pnl)
    return abs(worst)

def compute_charges(nc, exit_pnl, n_legs):
    brok = 20 * 2 * n_legs
    tv   = abs(nc) + abs(exit_pnl)
    stt  = 0.000625 * abs(nc)
    exc  = 0.00053  * tv
    gst  = 0.18 * (brok + exc)
    sebi = (tv / 1e7) * 10
    return round(brok + stt + exc + gst + sebi, 2)

def precompute_series(dte):
    series = []
    for expiry in expiry_dates:
        td = get_n_before(expiry, dte)
        if td is None or td not in all_days:
            continue
        prev = next((e for e in expiry_dates if e < expiry), None)
        if prev and td <= prev:
            continue

        oe = load_opt_cached(td, expiry)
        if oe is None:
            continue
        atm = get_atm(td, oe)
        if atm is None:
            continue

        legs = strip_get_legs(atm, STRIKE_STEP, lots=1)
        lk   = [(l.strike, l.right) for l in legs]
        wt   = np.array([(1 if l.action == 'SELL' else -1) * l.lots * LOT_SIZE
                         for l in legs], dtype=float)

        es       = oe[oe['time_str'] == ENTRY_TIME]
        entry_px = {}
        skip     = False
        for l in legs:
            row = es[(es['strike_price'] == l.strike) & (es['right'] == l.right)]
            if row.empty:
                skip = True; break
            entry_px[(l.strike, l.right)] = float(row['open'].iloc[0])
        if skip:
            continue

        nc = sum(entry_px[(l.strike, l.right)] * l.lots * LOT_SIZE *
                 (1 if l.action == 'SELL' else -1) for l in legs)
        ml = compute_max_loss(legs, entry_px)

        pnl_vals = []
        for day in get_window(td, expiry):
            od = load_opt_cached(day, expiry)
            if od is None:
                continue
            sub = od[(od['time_str'] >= ENTRY_TIME) & (od['time_str'] <= EXIT_TIME)]
            if sub.empty:
                continue
            piv = sub.pivot_table(index='time_str', columns=['strike_price','right'],
                                  values='open', aggfunc='first')
            if any(k not in piv.columns for k in lk):
                continue
            arr = nc - piv[lk].values @ wt
            pnl_vals.extend(arr.tolist())

        if not pnl_vals:
            continue

        ox = load_opt_cached(expiry, expiry)
        expiry_pnl = 0.0
        if ox is not None:
            xs = ox[ox['time_str'] == EXIT_TIME]
            for l in legs:
                row = xs[(xs['strike_price'] == l.strike) & (xs['right'] == l.right)]
                if row.empty:
                    continue
                ep = float(row['open'].iloc[0])
                if l.action == 'SELL':
                    expiry_pnl += (entry_px[(l.strike, l.right)] - ep) * l.lots * LOT_SIZE
                else:
                    expiry_pnl += (ep - entry_px[(l.strike, l.right)]) * l.lots * LOT_SIZE

        series.append(dict(
            trade_date=td, expiry=expiry,
            pnl_arr=np.array(pnl_vals, dtype=float),
            nc=nc, ml=ml, n_legs=len(legs),
            expiry_pnl=expiry_pnl,
        ))
    return series

def apply_sltp(series, sl_pct, tp_pct):
    records = []
    for s in series:
        pa   = s['pnl_arr']
        sl_t = -sl_pct * s['ml']
        tp_t =  tp_pct * abs(s['nc'])

        shi = np.where(pa <= sl_t)[0]
        thi = np.where(pa >= tp_t)[0]
        si  = int(shi[0]) if len(shi) else len(pa)
        ti  = int(thi[0]) if len(thi) else len(pa)

        if si == len(pa) and ti == len(pa):
            xp = s['expiry_pnl']; xr = 'timeout'
        elif si <= ti:
            xp = float(pa[si]); xr = 'sl'
        else:
            xp = float(pa[ti]); xr = 'tp'

        ch = compute_charges(s['nc'], xp, s['n_legs'])
        records.append(dict(
            Trade_Date=s['trade_date'], N_Legs=s['n_legs'],
            NC=round(s['nc'], 2), Gross_PnL=round(xp, 2),
            Charges=round(ch, 2), Net_PnL=round(xp - ch, 2), Exit=xr,
        ))
    return pd.DataFrame(records)

def simulate(df):
    if df.empty:
        return float(STARTING_CAPITAL), pd.DataFrame(), 0.0

    legs_ref   = strip_get_legs(24000, STRIKE_STEP, lots=1)
    total_lots = sum(l.lots for l in legs_ref)        # = 3 (1 CE + 2 PE)
    slip_lot   = SLIP_PER_UNIT * total_lots * LOT_SIZE * 2
    eff        = SPAN * MARGIN_BUF

    df    = df.sort_values('Trade_Date').reset_index(drop=True)
    cap   = float(STARTING_CAPITAL)
    peak  = cap
    month = None
    lots  = 1
    log   = []

    for _, r in df.iterrows():
        if cap < SPAN:
            break
        d = r['Trade_Date']
        m = (d.year, d.month)
        if m != month:
            lots  = min(MAX_LOTS, max(1, int(cap // eff)))
            month = m

        gross = float(r['Gross_PnL']) * lots
        ch    = float(r['Charges'])   * lots
        net   = gross - ch - slip_lot * lots
        cap  += net
        peak  = max(peak, cap)
        dd    = (peak - cap) / peak if peak > 0 else 0.0
        log.append({'Trade_Date': d, 'lots': lots,
                    'net_pnl': round(net), 'capital': round(cap), 'dd': round(dd, 4)})

    log_df = pd.DataFrame(log)
    max_dd = float(log_df['dd'].max()) if not log_df.empty else 0.0
    return round(cap, 2), log_df, max_dd

# ── Run ───────────────────────────────────────────────────────────────────────
print(f'Strip backtest | Jan 2024 – Mar 2026 | SLIP={SLIP_PER_UNIT} Rs/unit | LOT={LOT_SIZE}')
print(f'Calendar: {len(sorted_days)} trading days | {len(expiry_dates)} expiries')
print(f'Kite ATM dates loaded: {len(kite_map)}')
print()

results = []
for dte in DTE_GRID:
    key = f'gs_Strip_DTE{dte}.pkl'
    fp  = CACHE_DIR / key
    if fp.exists():
        with open(fp, 'rb') as f:
            series = pickle.load(f)
        print(f'  Loaded  Strip DTE{dte}: {len(series)} trades (cached)')
    else:
        print(f'  Computing Strip DTE{dte} ...', end='', flush=True)
        series = precompute_series(dte)
        with open(fp, 'wb') as f:
            pickle.dump(series, f)
        print(f' {len(series)} trades done')

    for sl_pct in SL_GRID:
        for tp_pct in TP_GRID:
            df_t          = apply_sltp(series, sl_pct, tp_pct)
            fin, log, mdd = simulate(df_t)
            n_trades      = len(log)
            wins          = int((log['net_pnl'] > 0).sum()) if n_trades else 0
            wr            = wins / n_trades if n_trades else 0.0
            roi            = (fin - STARTING_CAPITAL) / STARTING_CAPITAL * 100
            results.append(dict(
                DTE=dte, SL=sl_pct, TP=tp_pct,
                Trades=n_trades, WinRate=round(wr, 3),
                TP_n=int((df_t['Exit']=='tp').sum()),
                SL_n=int((df_t['Exit']=='sl').sum()),
                TM_n=int((df_t['Exit']=='timeout').sum()),
                MaxDD=round(mdd, 3),
                FinalCap=round(fin), ROI=round(roi, 1),
            ))

df_res = pd.DataFrame(results)
out_csv = CACHE_DIR / 'strip_results.csv'
df_res.to_csv(out_csv, index=False)

print()
print('=' * 80)
print('STRIP — BEST COMBO PER DTE')
print('=' * 80)
print(f"  {'DTE':>4}  {'SL':>5}  {'TP':>5}  {'ROI':>8}  {'WR':>6}  {'Trades':>7}  {'MaxDD':>7}  {'FinalCap':>12}")
print('  ' + '-' * 68)
for dte in DTE_GRID:
    sub  = df_res[df_res['DTE'] == dte]
    best = sub.loc[sub['ROI'].idxmax()]
    print(f"  {int(best['DTE']):>4}  {best['SL']:.0%}  {best['TP']:.0%}  "
          f"{best['ROI']:>+7.1f}%  {best['WinRate']:.1%}  {int(best['Trades']):>7}  "
          f"{best['MaxDD']:.1%}  Rs{int(best['FinalCap']):>9,}")

print()
print('=' * 80)
print('STRIP — ALL COMBOS SORTED BY ROI (top 20)')
print('=' * 80)
print(f"  {'#':>3}  {'DTE':>4}  {'SL':>5}  {'TP':>5}  {'ROI':>8}  {'WR':>6}  {'Trades':>7}  {'MaxDD':>7}  {'TP_n':>5}  {'SL_n':>5}  {'TM_n':>5}")
print('  ' + '-' * 74)
top = df_res.sort_values('ROI', ascending=False).head(20).reset_index(drop=True)
for i, r in top.iterrows():
    print(f"  {i+1:>3}  {int(r['DTE']):>4}  {r['SL']:.0%}  {r['TP']:.0%}  "
          f"{r['ROI']:>+7.1f}%  {r['WinRate']:.1%}  {int(r['Trades']):>7}  "
          f"{r['MaxDD']:.1%}  {int(r['TP_n']):>5}  {int(r['SL_n']):>5}  {int(r['TM_n']):>5}")

print()
print(f'Full results saved -> {out_csv}')
