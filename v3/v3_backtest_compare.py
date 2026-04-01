import os, sys, io, contextlib
from pathlib import Path
import pandas as pd

BASE     = Path(__file__).parent.parent / 'market-research'
BT_DIR   = BASE / 'backtesting'
V3_CSV   = Path(__file__).parent / 'v3_aligned_dataset.csv'

sys.path.insert(0, str(BT_DIR))
os.chdir(BT_DIR)

with contextlib.redirect_stdout(io.StringIO()):
    import py_backtest as bt

# Load v3 dataset
v3 = pd.read_csv(V3_CSV, parse_dates=['india_date'])
v3 = v3.sort_values('india_date').reset_index(drop=True)
v3['VIX_INDIA_level'] = v3['VIX_INDIA_level'].ffill().bfill()
backtest_df = v3.tail(252*3).copy().reset_index(drop=True)
print(f'Backtest period: {backtest_df["india_date"].iloc[0].date()} to {backtest_df["india_date"].iloc[-1].date()}')
print(f'Sessions: {len(backtest_df)}')

def compute_signals(row):
    def safe(col):
        v = row.get(col)
        return float(v) if v is not None and str(v) != 'nan' else None
    hs  = safe('HangSeng_ret')
    oil = safe('Oil_ret')
    return {
        'Gap Up'          : float(row['gap_pct']) >  0.0015,
        'Gap Up Strong'   : float(row['gap_pct']) >  0.0050,
        'Gap Down'        : float(row['gap_pct']) < -0.0015,
        'Prev India UP'   : float(row['prev_india_ret']) > 0,
        'Prev India DOWN' : float(row['prev_india_ret']) < 0,
        'US UP'           : float(row['SP500_ret']) > 0,
        'US DOWN'         : float(row['SP500_ret']) < 0,
        'SGX UP'          : float(row['SGX_ret']) > 0,
        'SGX DOWN'        : float(row['SGX_ret']) < 0,
        'DAX UP'          : float(row['DAX_ret']) > 0,
        'VIX Rising'      : float(row['VIX_US_ret']) > 0.03,
        'VIX Falling'     : float(row['VIX_US_ret']) < 0,
        'HangSeng UP'     : hs  is not None and hs  > 0,
        'HangSeng DOWN'   : hs  is not None and hs  < 0,
        'Oil UP'          : oil is not None and oil > 0,
        'Oil DOWN'        : oil is not None and oil < 0,
    }

def check_combo(sigs, s):
    return all(sigs.get(x.strip(), False) for x in s.split('+'))

BEAR = [
    'Gap Up + Prev India DOWN + US UP + SGX UP',
    'Gap Up + Prev India DOWN + SGX UP + DAX UP',
    'Gap Up + Prev India DOWN + SGX UP',
]
BULL_V2 = [
    'Gap Down + US UP',
    'Prev India DOWN + US UP + SGX DOWN',
    'Gap Down + SGX UP',
]
BULL_V3 = [
    'Gap Down + US UP',
    'HangSeng UP + Oil UP + Gap Down',
    'HangSeng UP + Gap Down + Prev India DOWN',
]

def build_trade_days(df, bear_combos, bull_combos):
    rows = []
    for _, row in df.iterrows():
        sigs = compute_signals(row)
        bf  = [c for c in bear_combos if check_combo(sigs, c)]
        blf = [c for c in bull_combos if check_combo(sigs, c)]
        if bf and blf:
            action, combo = 'CONFLICT', None
        elif bf:
            action, combo = 'BEARISH', bf[0]
        elif blf:
            action, combo = 'BULLISH', blf[0]
        else:
            action, combo = 'NO_SIGNAL', None
        rows.append({
            'india_date' : row['india_date'],
            'india_open' : float(row['india_open']),
            'vix_india'  : float(row['VIX_INDIA_level']),
            'dir_60'     : int(row['dir_60']),
            'action'     : action,
            'combo_fired': combo,
        })
    return pd.DataFrame(rows)

def run_backtest(td, label):
    bt.STOP_LOSS_PCT = 0.40
    bt.PROFIT_TARGET_PCT = 0.40
    tradeable = td[td['action'].isin(['BEARISH', 'BULLISH'])]
    results = []
    for _, trow in tradeable.iterrows():
        res = bt.simulate_trade(
            trow['india_date'], trow['action'],
            trow['india_open'], trow['vix_india'], bt.minute_all
        )
        if res is None:
            continue
        pred = -1 if trow['action'] == 'BEARISH' else 1
        results.append({
            'Signal'  : trow['action'],
            'pnl_rs'  : res['pnl_rs'],
            'correct' : int(pred == int(trow['dir_60'])),
        })
    df = pd.DataFrame(results)
    win  = (df['pnl_rs'] > 0).mean() * 100
    pnl  = df['pnl_rs'].sum()
    acc  = df['correct'].mean() * 100
    bear = df[df['Signal'] == 'BEARISH']
    bull = df[df['Signal'] == 'BULLISH']
    print(f'\n{label}')
    print(f'  Trades={len(df)}  Win={win:.1f}%  Acc={acc:.1f}%  Total P&L=Rs{pnl:+,.0f}  Avg=Rs{pnl/len(df):+,.0f}')
    if len(bear):
        print(f'  BEARISH: {len(bear)} trades  win={(bear["pnl_rs"]>0).mean()*100:.1f}%  Rs{bear["pnl_rs"].sum():+,.0f}')
    if len(bull):
        print(f'  BULLISH: {len(bull)} trades  win={(bull["pnl_rs"]>0).mean()*100:.1f}%  Rs{bull["pnl_rs"].sum():+,.0f}')
    return pnl

td_v2 = build_trade_days(backtest_df, BEAR, BULL_V2)
td_v3 = build_trade_days(backtest_df, BEAR, BULL_V3)
n_v2 = td_v2['action'].isin(['BEARISH','BULLISH']).sum()
n_v3 = td_v3['action'].isin(['BEARISH','BULLISH']).sum()
print(f'\nTradeable days  V2={n_v2}  V3={n_v3}')

SEP = '=' * 52
print('\n' + SEP)
p2 = run_backtest(td_v2, 'V2  (original bullish)')
print('\n' + SEP)
p3 = run_backtest(td_v3, 'V3  (HangSeng + Oil bullish)')
print('\n' + SEP)
diff = p3 - p2
print(f'\n  V2 total P&L : Rs{p2:+,.0f}')
print(f'  V3 total P&L : Rs{p3:+,.0f}')
print(f'  Difference   : Rs{diff:+,.0f}  ({diff/abs(p2)*100:+.1f}%)')
