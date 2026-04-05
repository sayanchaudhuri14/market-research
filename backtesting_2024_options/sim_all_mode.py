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
SL_PCT = 0.15; TP_PCT = 0.40; FIXED = 10; MAX_LOTS = 25; DTE0_LOTS = 10
ENTRY_TIME = '09:25'; EXIT_TIME = '11:15'
GAP_THR = 0.0015; GAP_LRG = 0.0050; VIX_RIS = 0.03
BEAR_N = 10; BULL_N = 10

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

def date_to_dmy(d): return f'{d.day:02d}{MONTH_ABBR[d.month-1]}{str(d.year)[2:]}'

# ── Aligned dataset ──
aligned = pd.read_csv(ALIGNED_CSV, parse_dates=['india_date'])
aligned['VIX_INDIA_level'] = aligned['VIX_INDIA_level'].ffill().bfill()
aligned['date'] = aligned['india_date'].dt.date
aligned_map = aligned.set_index('date').to_dict('index')

# ── Signal combos ──
reliable    = pd.read_csv(SIGNALS_CSV)
bear_combos = list(reliable[reliable['P_Down'] > BASE_RATE]
                   .sort_values('Edge_pp', ascending=False)['Signal'][:BEAR_N])
bull_combos = list(reliable[reliable['P_Down'] < (100 - BASE_RATE)]
                   .sort_values('Edge_pp', ascending=False)['Signal'][:BULL_N])
print(f'Bear combos top 3: {bear_combos[:3]}')
print(f'Bull combos top 3: {bull_combos[:3]}')

def compute_signals(r):
    return {
        'Gap Up'         : r['gap_pct']       >  GAP_THR,
        'Gap Up Strong'  : r['gap_pct']       >  GAP_LRG,
        'Gap Down'       : r['gap_pct']       < -GAP_THR,
        'Prev India UP'  : r['prev_india_ret'] > 0,
        'Prev India DOWN': r['prev_india_ret'] < 0,
        'US UP'          : r['SP500_ret']      > 0,
        'US DOWN'        : r['SP500_ret']      < 0,
        'SGX UP'         : r['SGX_ret']        > 0,
        'SGX DOWN'       : r['SGX_ret']        < 0,
        'DAX UP'         : r['DAX_ret']        > 0,
        'VIX Rising'     : r['VIX_US_ret']     > VIX_RIS,
        'VIX Falling'    : r['VIX_US_ret']     < 0,
        'VIX Spike'      : r['VIX_US_ret']     > 0.05,
    }

def fires(sigs, combo):
    return all(sigs.get(s.strip(), False) for s in combo.split('+'))

# ── Build ALL-mode signal days for 2024 ──
tradeable = []
for d, row in aligned_map.items():
    if not (date(2024,1,1) <= d <= date(2024,12,31)): continue
    if d.weekday() == 0 or d in EVENT_DAYS or d in NSE_HOLIDAYS: continue
    sigs = compute_signals(row)
    bf   = [c for c in bear_combos if fires(sigs, c)]
    bulf = [c for c in bull_combos if fires(sigs, c)]
    if bf:
        tradeable.append({'date': d, 'signal': 'BEARISH', 'combo': bf[0], 'nifty_open': row['india_open']})
    elif bulf:
        tradeable.append({'date': d, 'signal': 'BULLISH', 'combo': bulf[0], 'nifty_open': row['india_open']})

tradeable_df = pd.DataFrame(tradeable).sort_values('date').reset_index(drop=True)
bear_days = (tradeable_df['signal'] == 'BEARISH').sum()
bull_days = (tradeable_df['signal'] == 'BULLISH').sum()
print(f'Signal days (ALL mode): {len(tradeable_df)}  ({bear_days} bearish, {bull_days} bullish)')

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

# ── Simulate ──
def simulate(side_override):
    capital = None; init_cap = None
    refills = 0; total_ref = 0.0
    trades  = []; cf = []; cd = []

    for _, trow in tradeable_df.iterrows():
        d          = trow['date']
        nifty_open = trow['nifty_open']
        atm        = round(nifty_open / STRIKE_STEP) * STRIKE_STEP
        expiry     = get_expiry(d)
        dte        = (expiry - d).days

        if side_override == 'PE': strike = atm - 50; side = 'PE'
        else:                     strike = atm + 50; side = 'CE'

        df_opt = load_opt(d, expiry)
        if df_opt is None: continue
        match = df_opt[(df_opt['strike_price'] == strike) & (df_opt['right'] == side)]
        if match.empty: continue

        entry_row = match[match['datetime'] == ENTRY_TIME]
        if entry_row.empty: continue
        ep = float(entry_row.iloc[0]['open'])
        if ep <= 0: continue

        cost_lot  = ep * LOT_SIZE
        min_lots  = DTE0_LOTS if dte == 0 else FIXED

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
        window = match[(match['datetime'] >= '09:26') & (match['datetime'] <= EXIT_TIME)]

        exit_p = None; reason = '11:15 exit'
        for _, c in window.iterrows():
            if float(c['low'])  <= sl_p: exit_p = sl_p; reason = 'Stop Loss';  break
            if float(c['high']) >= tp_p: exit_p = tp_p; reason = 'Target Hit'; break
        if exit_p is None:
            last   = window[window['datetime'] <= EXIT_TIME]
            exit_p = float(last.iloc[-1]['close']) if not last.empty else ep

        pnl     = (exit_p - ep) * LOT_SIZE * lots - BROKERAGE * lots
        capital = max(0.0, capital + pnl)

        trades.append({
            'date': d, 'signal': trow['signal'], 'dte': dte,
            'entry': ep, 'exit': exit_p, 'reason': reason,
            'lots': lots, 'pnl': pnl, 'capital': capital,
        })

    return trades, capital, init_cap, refills, total_ref, cf, cd

def print_metrics(trades, capital, init_cap, refills, total_ref, cf, cd, label):
    df  = pd.DataFrame(trades)
    n   = len(df)
    if n == 0: print(f'{label}: no trades'); return
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
    try:    xirr = newton(lambda r: sum(c/((1+r)**((d-cd2[0]).days/365)) for c,d in zip(cf2,cd2)), 0.5) * 100
    except: xirr = None

    print(f'=== {label} ===')
    print(f'  Trades          : {n}  ({(df["signal"]=="BEARISH").sum()} bear signal days / {(df["signal"]=="BULLISH").sum()} bull signal days)')
    print(f'  Win rate        : {wins/n*100:.1f}%  ({wins}W / {n-wins}L)')
    print(f'  Stop Loss hits  : {sl} ({sl/n*100:.1f}%)')
    print(f'  Target hits     : {tp} ({tp/n*100:.1f}%)')
    print(f'  Time exits      : {te} ({te/n*100:.1f}%)')
    print(f'  Initial capital : Rs {init_cap:,.0f}')
    print(f'  Total invested  : Rs {total_invested:,.0f}  ({refills} refills, Rs {total_ref:,.0f})')
    print(f'  Final capital   : Rs {capital:,.0f}')
    print(f'  Net return      : {(capital - total_invested)/total_invested*100:.1f}%')
    print(f'  XIRR            : {xirr:.0f}%' if xirr else '  XIRR            : N/A')
    print(f'  Max drawdown    : {max_dd:.1f}%')
    w_trades = df[df['pnl'] > 0]['pnl']; l_trades = df[df['pnl'] < 0]['pnl']
    print(f'  Avg win         : Rs {w_trades.mean():,.0f}' if len(w_trades) else '  Avg win: -')
    print(f'  Avg loss        : Rs {l_trades.mean():,.0f}' if len(l_trades) else '  Avg loss: -')
    print()
    print('  Monthly:')
    for mth, grp in df.groupby(pd.to_datetime(df['date']).dt.month):
        w  = (grp['pnl'] > 0).sum()
        p  = grp['pnl'].sum()
        mn = pd.to_datetime(grp['date'].iloc[0]).strftime('%b')
        bar = ('+' if p > 0 else '-') * min(int(abs(p) // 5000), 40)
        print(f'    {mn}  {len(grp):2d}d  {w}W/{len(grp)-w}L  Rs{p:>9,.0f}  {bar}')
    print()

t1, c1, i1, r1, tr1, cf1, cd1 = simulate('PE')
t2, c2, i2, r2, tr2, cf2, cd2 = simulate('CE')

print()
print_metrics(t1, c1, i1, r1, tr1, cf1, cd1, 'ALWAYS PE  (signal mode=ALL, ignore direction)')
print_metrics(t2, c2, i2, r2, tr2, cf2, cd2, 'ALWAYS CE  (signal mode=ALL, ignore direction)')

# Quick compare
print('=== QUICK COMPARE ===')
print(f'{"":30s}  {"Always PE":>15}  {"Always CE":>15}  {"Correct PE (bearish only)":>25}')
print(f'{"Signal days traded":30s}  {len(t1):>15}  {len(t2):>15}  {"~60":>25}')
print(f'{"Final capital":30s}  Rs{c1:>13,.0f}  Rs{c2:>13,.0f}  {"Rs 2,10,372":>25}')
print(f'{"Net return":30s}  {(c1-i1-tr1)/(i1+tr1)*100:>14.1f}%  {(c2-i2-tr2)/(i2+tr2)*100:>14.1f}%  {"1306%":>25}')
