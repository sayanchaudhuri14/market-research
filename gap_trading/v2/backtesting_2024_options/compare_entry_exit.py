import sys, warnings
from pathlib import Path
from datetime import date, timedelta
import numpy as np, pandas as pd
from scipy.optimize import newton
warnings.filterwarnings('ignore')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

HERE        = Path(__file__).parent
DATA_DIR    = HERE / '2024'
NIFTY_DIR   = DATA_DIR / '2024Nifty'
SIGNALS_CSV = HERE.parent / 'v2' / 'v2_reliable_signals.csv'
ALIGNED_CSV = HERE.parent / 'v2' / 'v2_aligned_dataset.csv'

STRIKE_STEP = 50; LOT_SIZE = 75; BROKERAGE = 80; BASE_RATE = 54.5
SL_PCT = 0.15; TP_PCT = 0.40
FIXED = 5; MAX_LOTS = 20; DTE0_LOTS = 10
BEAR_N = 10

MONTH_ABBR = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC']
NSE_HOLIDAYS = {
    date(2024,1,22), date(2024,3,25), date(2024,3,29), date(2024,4,11),
    date(2024,4,14), date(2024,4,17), date(2024,5,1),  date(2024,6,17),
    date(2024,8,15), date(2024,10,2), date(2024,10,24),date(2024,11,15),date(2024,12,25),
}
EVENT_DAYS = {
    date(2024,2,1), date(2024,4,5), date(2024,6,4), date(2024,6,5),
    date(2024,6,7), date(2024,7,23),date(2024,8,8), date(2024,10,9),date(2024,12,6),
}

CONFIGS = [
    {'label': 'OLD  (entry 09:15, exit 10:15)', 'entry': '09:15', 'scan_from': '09:16', 'exit': '10:15'},
    {'label': 'NEW  (entry 09:25, exit 11:15)', 'entry': '09:25', 'scan_from': '09:26', 'exit': '11:15'},
]

def date_to_dmy(d): return f'{d.day:02d}{MONTH_ABBR[d.month-1]}{str(d.year)[2:]}'

# ── Aligned dataset & signals ──
aligned = pd.read_csv(ALIGNED_CSV, parse_dates=['india_date'])
aligned['VIX_INDIA_level'] = aligned['VIX_INDIA_level'].ffill().bfill()
aligned['date'] = aligned['india_date'].dt.date
aligned_map = aligned.set_index('date').to_dict('index')

reliable    = pd.read_csv(SIGNALS_CSV)
bear_combos = list(reliable[reliable['P_Down'] > BASE_RATE]
                   .sort_values('Edge_pp', ascending=False)['Signal'][:BEAR_N])

GAP_THR = 0.0015; GAP_LRG = 0.0050; VIX_RIS = 0.03
def compute_signals(r):
    return {
        'Gap Up'         : r['gap_pct']        >  GAP_THR,
        'Gap Up Strong'  : r['gap_pct']        >  GAP_LRG,
        'Gap Down'       : r['gap_pct']        < -GAP_THR,
        'Prev India UP'  : r['prev_india_ret']  > 0,
        'Prev India DOWN': r['prev_india_ret']  < 0,
        'US UP'          : r['SP500_ret']       > 0,
        'US DOWN'        : r['SP500_ret']       < 0,
        'SGX UP'         : r['SGX_ret']         > 0,
        'SGX DOWN'       : r['SGX_ret']         < 0,
        'DAX UP'         : r['DAX_ret']         > 0,
        'VIX Rising'     : r['VIX_US_ret']      > VIX_RIS,
        'VIX Falling'    : r['VIX_US_ret']      < 0,
        'VIX Spike'      : r['VIX_US_ret']      > 0.05,
    }
def fires(sigs, combo):
    return all(sigs.get(s.strip(), False) for s in combo.split('+'))

# ── Build bearish signal days (same for both configs) ──
tradeable = []
for d, row in aligned_map.items():
    if not (date(2024,1,1) <= d <= date(2024,12,31)): continue
    if d.weekday() == 0 or d in EVENT_DAYS or d in NSE_HOLIDAYS: continue
    sigs = compute_signals(row)
    bf   = [c for c in bear_combos if fires(sigs, c)]
    if bf:
        tradeable.append({'date': d, 'combo': bf[0], 'nifty_open': row['india_open']})

tradeable_df = pd.DataFrame(tradeable).sort_values('date').reset_index(drop=True)
print(f'Bearish signal days in 2024: {len(tradeable_df)}')
print()

# ── Expiry map ──
expiry_df  = pd.read_csv(DATA_DIR / 'expiry.csv')
expiry_df['date']   = pd.to_datetime(expiry_df.iloc[:, 0]).dt.date
expiry_df['expiry'] = pd.to_datetime(expiry_df.iloc[:, 1]).dt.date
expiry_map = dict(zip(expiry_df['date'], expiry_df['expiry']))

def get_expiry(d):
    if d in expiry_map: return expiry_map[d]
    days = (3 - d.weekday()) % 7
    exp  = d + timedelta(days=days)
    while exp in NSE_HOLIDAYS: exp -= timedelta(days=1)
    return exp

# ── Option loader ──
_cache = {}
def load_opt(trade_date, expiry):
    key = (trade_date, expiry)
    if key in _cache: return _cache[key]
    mon  = MONTH_ABBR[trade_date.month - 1]
    fp   = DATA_DIR / f'2024{mon}' / f'NIFTY-{date_to_dmy(expiry)}-{date_to_dmy(trade_date)}.csv'
    if not fp.exists(): _cache[key] = None; return None
    df   = pd.read_csv(fp)
    df['datetime'] = df['datetime'].astype(str).str.strip()
    _cache[key] = df
    return df

# ── Simulate one config ──
def simulate(entry_t, scan_from, exit_t):
    capital = None; init_cap = None
    refills = 0; total_ref = 0.0
    trades  = []; cf = []; cd = []

    for _, trow in tradeable_df.iterrows():
        d          = trow['date']
        nifty_open = trow['nifty_open']
        atm        = round(nifty_open / STRIKE_STEP) * STRIKE_STEP
        strike     = atm - STRIKE_STEP
        expiry     = get_expiry(d)
        dte        = (expiry - d).days

        df_opt = load_opt(d, expiry)
        if df_opt is None: continue
        match  = df_opt[(df_opt['strike_price'] == strike) & (df_opt['right'] == 'PE')]
        if match.empty: continue

        entry_row = match[match['datetime'] == entry_t]
        if entry_row.empty: continue
        ep = float(entry_row.iloc[0]['open'])
        if ep <= 0: continue

        cost_lot = ep * LOT_SIZE
        min_lots = DTE0_LOTS if dte == 0 else FIXED

        if capital is None:
            capital  = cost_lot * min_lots
            init_cap = capital
            cf.append(-capital); cd.append(pd.Timestamp(d))

        if capital < cost_lot * min_lots:
            ref      = cost_lot * min_lots - capital
            capital += ref; refills += 1; total_ref += ref
            cf.append(-ref); cd.append(pd.Timestamp(d))

        lots   = min(max(int(capital / cost_lot), min_lots), MAX_LOTS)
        sl_p   = ep * (1 - SL_PCT)
        tp_p   = ep * (1 + TP_PCT)
        window = match[(match['datetime'] >= scan_from) & (match['datetime'] <= exit_t)]

        exit_p = None; reason = f'{exit_t} exit'
        for _, c in window.iterrows():
            if float(c['low'])  <= sl_p: exit_p = sl_p; reason = 'Stop Loss';  break
            if float(c['high']) >= tp_p: exit_p = tp_p; reason = 'Target Hit'; break
        if exit_p is None:
            last   = window[window['datetime'] <= exit_t]
            exit_p = float(last.iloc[-1]['close']) if not last.empty else ep

        pnl     = (exit_p - ep) * LOT_SIZE * lots - BROKERAGE * lots
        capital = max(0.0, capital + pnl)

        trades.append({
            'date': d, 'dte': dte, 'entry': round(ep,2), 'exit': round(exit_p,2),
            'reason': reason, 'lots': lots,
            'pnl': round(pnl,2), 'capital': round(capital,2),
        })

    return trades, capital, init_cap, refills, total_ref, cf, cd

# ── Print metrics ──
def print_metrics(cfg, trades, capital, init_cap, refills, total_ref, cf, cd):
    df  = pd.DataFrame(trades)
    n   = len(df)
    wins = (df['pnl'] > 0).sum()
    sl   = (df['reason'] == 'Stop Loss').sum()
    tp   = (df['reason'] == 'Target Hit').sum()
    te   = n - sl - tp
    total_invested = init_cap + total_ref

    peak = init_cap; max_dd = 0.0; running = init_cap
    for p in df['pnl']:
        running += p
        if running > peak: peak = running
        dd = (peak - running) / peak * 100
        if dd > max_dd: max_dd = dd

    cf2 = cf + [capital]; cd2 = cd + [pd.Timestamp(df['date'].iloc[-1])]
    try:    xirr = newton(lambda r: sum(c/((1+r)**((d-cd2[0]).days/365)) for c,d in zip(cf2,cd2)), 0.5)*100
    except: xirr = None

    print(f'=== {cfg["label"]} ===')
    print(f'  Trades          : {n}')
    print(f'  Win rate        : {wins/n*100:.1f}%  ({wins}W / {n-wins}L)')
    print(f'  Stop Loss hits  : {sl}  ({sl/n*100:.1f}%)')
    print(f'  Target hits     : {tp}  ({tp/n*100:.1f}%)')
    print(f'  Time exits      : {te}  ({te/n*100:.1f}%)')
    print(f'  Initial capital : Rs {init_cap:,.0f}')
    print(f'  Total invested  : Rs {total_invested:,.0f}  ({refills} refills, Rs {total_ref:,.0f})')
    print(f'  Final capital   : Rs {capital:,.0f}')
    print(f'  Net return      : {(capital - total_invested)/total_invested*100:.1f}%')
    print(f'  XIRR            : {xirr:.0f}%' if xirr else '  XIRR            : N/A')
    print(f'  Max drawdown    : {max_dd:.1f}%')
    print(f'  Avg win         : Rs {df[df["pnl"]>0]["pnl"].mean():,.0f}')
    print(f'  Avg loss        : Rs {df[df["pnl"]<0]["pnl"].mean():,.0f}')
    print()
    print('  Monthly:')
    for mth, grp in df.groupby(pd.to_datetime(df['date']).dt.month):
        w  = (grp['pnl'] > 0).sum()
        p  = grp['pnl'].sum()
        mn = pd.to_datetime(grp['date'].iloc[0]).strftime('%b')
        bar = ('+' if p > 0 else '-') * min(int(abs(p)//3000), 40)
        print(f'    {mn}  {len(grp):2d}d  {w}W/{len(grp)-w}L  Rs{p:>9,.0f}  {bar}')
    print()
    return {'trades': n, 'win_rate': wins/n*100, 'sl': sl, 'tp': tp, 'te': te,
            'init_cap': init_cap, 'final_cap': capital, 'net_ret': (capital-total_invested)/total_invested*100,
            'xirr': xirr, 'max_dd': max_dd, 'refills': refills}

results = []
for cfg in CONFIGS:
    t, c, i, r, tr, cf, cd = simulate(cfg['entry'], cfg['scan_from'], cfg['exit'])
    m = print_metrics(cfg, t, c, i, r, tr, cf, cd)
    results.append(m)

print('=' * 60)
print('SIDE BY SIDE COMPARISON')
print('=' * 60)
labels = [cfg['label'] for cfg in CONFIGS]
keys   = [('trades','Trades'), ('win_rate','Win Rate %'), ('sl','SL hits'),
          ('tp','TP hits'), ('te','Time exits'), ('init_cap','Initial Capital'),
          ('final_cap','Final Capital'), ('net_ret','Net Return %'),
          ('xirr','XIRR %'), ('max_dd','Max Drawdown %'), ('refills','Refills')]
print(f'  {"Metric":<22}  {labels[0]:<30}  {labels[1]:<30}')
print(f'  {"-"*22}  {"-"*30}  {"-"*30}')
for key, label in keys:
    v0 = results[0][key]; v1 = results[1][key]
    if key in ('init_cap','final_cap'):
        print(f'  {label:<22}  Rs {v0:>26,.0f}  Rs {v1:>26,.0f}')
    elif key in ('net_ret','win_rate','max_dd'):
        s0 = f'{v0:.1f}%' if v0 else 'N/A'
        s1 = f'{v1:.1f}%' if v1 else 'N/A'
        print(f'  {label:<22}  {s0:>28}  {s1:>28}')
    elif key == 'xirr':
        s0 = f'{v0:.0f}%' if v0 else 'N/A'
        s1 = f'{v1:.0f}%' if v1 else 'N/A'
        print(f'  {label:<22}  {s0:>28}  {s1:>28}')
    else:
        print(f'  {label:<22}  {str(v0):>28}  {str(v1):>28}')
