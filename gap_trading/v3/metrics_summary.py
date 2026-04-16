import sys, io, contextlib, os
from pathlib import Path
import pandas as pd
import numpy as np
from scipy.optimize import brentq

BT_DIR = Path('c:/Users/sayan/OneDrive/Desktop/Projects/03_Market_Research/market-research/backtesting')
sys.path.insert(0, str(BT_DIR))
os.chdir(BT_DIR)

print('Loading backtest (please wait)...')
with contextlib.redirect_stdout(io.StringIO()):
    import py_backtest as bt

bt.STOP_LOSS_PCT     = 0.40
bt.PROFIT_TARGET_PCT = 0.40

print('Re-simulating 162 trades with SL=40% TP=40%...')
tradeable = bt.trade_days_df[bt.trade_days_df['action'].isin(['BEARISH','BULLISH'])].copy()

records = []
for _, trow in tradeable.iterrows():
    res = bt.simulate_trade(
        trow['india_date'], trow['action'],
        trow['india_open'], trow['vix_india'], bt.minute_all
    )
    if res is None:
        continue
    records.append({
        'Date'        : pd.to_datetime(trow['india_date']),
        'Signal'      : trow['action'],
        'Entry (pts)' : res['entry_pts'],
        'pnl_1lot'    : res['pnl_rs'],   # 1-lot P&L
    })

df = pd.DataFrame(records).sort_values('Date').reset_index(drop=True)
print(f'Done. {len(df)} trades.\n')

LOT_SIZE   = 75
BROKERAGE  = 80
FIXED_LOTS = 5

def compute_xirr(cfs, dates):
    def npv(r):
        t0 = dates[0]
        return sum(cf / (1+r)**((d-t0).days/365.0) for cf, d in zip(cfs, dates))
    for lo, hi in [(-0.99,0),(0,1),(0,5),(0,20),(0,100),(0,500)]:
        try:
            return brentq(npv, lo, hi, maxiter=1000)
        except Exception:
            continue
    return None

def metrics_fixed(sub, label, lots=5):
    """Fixed lot size — no compounding. Most realistic for an individual trader."""
    sub = sub.reset_index(drop=True)

    # P&L per trade at fixed lot size
    pnl_series = sub['pnl_1lot'] * lots

    # Initial capital: worst realistic case = 5 lots * max entry premium seen
    # Practical: keep enough to absorb 3 consecutive SL hits
    max_single_loss = abs(pnl_series.min())
    avg_entry_cost  = sub['Entry (pts)'].mean() * LOT_SIZE * lots
    initial_capital = avg_entry_cost * 1.5  # 1.5x average premium as buffer

    total_pnl  = pnl_series.sum()
    win_rate   = (pnl_series > 0).mean() * 100
    avg_win    = pnl_series[pnl_series > 0].mean()
    avg_loss   = pnl_series[pnl_series < 0].mean()
    years      = (sub['Date'].iloc[-1] - sub['Date'].iloc[0]).days / 365.25

    # XIRR: put in initial capital day 0, get each trade P&L on its date,
    # get initial capital back at end (it's a reserve, not consumed)
    cfs   = [-initial_capital] + list(pnl_series)
    dates = [sub['Date'].iloc[0]] + list(sub['Date'])
    cfs[-1] += initial_capital   # return reserve at end

    xirr  = compute_xirr(cfs, dates)
    cagr  = ((initial_capital + total_pnl) / initial_capital) ** (1/years) - 1

    sep = '-' * 54
    print(f'  {label}')
    print(f'  {sep}')
    print(f'  Lots per trade    : {lots} (fixed, no compounding)')
    print(f'  Trades            : {len(sub)}  over {years:.2f} years')
    print(f'  Win rate          : {win_rate:.1f}%')
    print(f'  Avg win / trade   : Rs{avg_win:,.0f}')
    print(f'  Avg loss / trade  : Rs{avg_loss:,.0f}')
    print(f'  Max single loss   : Rs{max_single_loss:,.0f}')
    print()
    print(f'  Capital required  : Rs{initial_capital:,.0f}  (1.5x avg premium, kept as reserve)')
    print(f'  No refills needed : fixed lots, reserve always covers losses')
    print()
    print(f'  Total P&L         : Rs{total_pnl:,.0f}  over {years:.2f} years')
    print(f'  Per year (avg)    : Rs{total_pnl/years:,.0f}')
    print(f'  CAGR on capital   : {cagr*100:.1f}%')
    if xirr is not None:
        print(f'  XIRR              : {xirr*100:.1f}%')
    else:
        print(f'  XIRR              : could not compute')
    print()

SEP = '=' * 56
print(SEP)
metrics_fixed(df,                                   'ALL TRADES  (SL=40%  TP=40%  5 lots)', lots=5)
print(SEP)
metrics_fixed(df[df['Signal']=='BEARISH'].copy(),   'BEARISH ONLY  (5 lots)', lots=5)
print(SEP)
metrics_fixed(df[df['Signal']=='BULLISH'].copy(),   'BULLISH ONLY  (5 lots)', lots=5)
print(SEP)
print()
print('  --- 1-lot reference (minimum capital) ---')
print(SEP)
metrics_fixed(df, 'ALL TRADES  (1 lot, minimum)', lots=1)
