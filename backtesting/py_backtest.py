# ── Cell 1: Configuration — all variables are here ────────────────────────────
import numpy as np
import pandas as pd
import pickle
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path
from datetime import date, timedelta, datetime
from datetime import time as dtime
from scipy.stats import norm as _norm
import warnings
warnings.filterwarnings('ignore')

STOP_LOSS_PCT      = 0.8
PROFIT_TARGET_PCT  = 0.25
LOT_SIZE           = 75
STRIKE_STEP        = 50
STRIKES_OTM        = 1
RISK_FREE_RATE     = 0.065
BROKERAGE          = 80
BACKTEST_DAYS      = 252 * 3   # ~3 trading years (756 trading days)
BASE_RATE          = 54.5

_cwd = Path.cwd()
BASE = _cwd if (_cwd / 'v2' / 'v2_aligned_dataset.csv').exists() else _cwd.parent
ALIGNED_CSV  = BASE / 'v2' / 'v2_aligned_dataset.csv'
MINUTE_CACHE = BASE / 'v2' / 'kite_minute_cache'
SIGNALS_CSV  = BASE / 'v2' / 'v2_reliable_signals.csv'


#  
# ── Cell 2: Load aligned dataset + define top-3 bear/bull signals ──────────────
aligned = pd.read_csv(ALIGNED_CSV, parse_dates=['india_date'])
aligned = aligned.sort_values('india_date').reset_index(drop=True)
aligned['VIX_INDIA_level'] = aligned['VIX_INDIA_level'].ffill().bfill()

# Last N trading days
backtest_df = aligned.tail(BACKTEST_DAYS).copy().reset_index(drop=True)
start_date  = backtest_df['india_date'].iloc[0].date()
end_date    = backtest_df['india_date'].iloc[-1].date()
print(f'Backtest period : {start_date}  to  {end_date}')
print(f'Trading days    : {len(backtest_df)}')

# Load reliable signal combinations
reliable = pd.read_csv(SIGNALS_CSV)

# Top 3 BEARISH: highest P_Down > base rate, sorted by edge descending
top_bearish = (reliable[reliable['P_Down'] > BASE_RATE]
               .sort_values('Edge', ascending=False)
               .head(3)
               .reset_index(drop=True))

# Top 3 BULLISH: lowest P_Down < (100 - base rate), sorted ascending
top_bullish = (reliable[reliable['P_Down'] < (100 - BASE_RATE)]
               .sort_values('P_Down', ascending=True)
               .head(3)
               .reset_index(drop=True))

print('\nTop 3 BEARISH signal combos:')
for _, r in top_bearish.iterrows():
    print(f'  [{int(r["Level"])}] {r["Signal"]:<55} P(DOWN)={r["P_Down"]:.1f}%  Edge=+{r["Edge"]:.1f}%  N={int(r["N"])}')

print('\nTop 3 BULLISH signal combos:')
for _, r in top_bullish.iterrows():
    print(f'  [{int(r["Level"])}] {r["Signal"]:<55} P(UP)={100-r["P_Down"]:.1f}%  Edge=+{abs(r["Edge"]):.1f}%  N={int(r["N"])}')

#  
# ── Cell 3: Load NIFTY minute data from cache ──────────────────────────────────
all_chunks = []
for pkl_path in sorted(MINUTE_CACHE.glob('minute_256265_*.pkl')):
    with open(pkl_path, 'rb') as f:
        chunk = pickle.load(f)
    chunk.index = pd.to_datetime(chunk.index)
    # Ensure timezone aware (IST)
    if chunk.index.tzinfo is None:
        chunk.index = chunk.index.tz_localize('Asia/Kolkata')
    # Filter to backtest date range (with 1-day buffer each side)
    lo = pd.Timestamp(start_date) - pd.Timedelta(days=1)
    hi = pd.Timestamp(end_date)   + pd.Timedelta(days=1)
    mask = (chunk.index >= lo.tz_localize('Asia/Kolkata')) & \
           (chunk.index <= hi.tz_localize('Asia/Kolkata'))
    if mask.sum() > 0:
        all_chunks.append(chunk[mask])

if all_chunks:
    minute_all = pd.concat(all_chunks).sort_index()
    print(f'Minute data loaded : {len(minute_all):,} rows')
    print(f'Date range         : {minute_all.index[0].date()}  to  {minute_all.index[-1].date()}')
    print(f'Columns            : {list(minute_all.columns)}')
else:
    print('WARNING: No minute data found in cache for backtest range.')
    minute_all = pd.DataFrame()

#  
# ── Cell 4: Compute binary signals + classify each backtest day ─────────────────
GAP_THR   = 0.0015
GAP_LARGE = 0.0050   # matches training threshold (0.50%) in v2_india_global.ipynb

def compute_signals(row):
    return {
        'Gap Up'          : float(row['gap_pct']) >  GAP_THR,
        'Gap Up Strong'   : float(row['gap_pct']) >  GAP_LARGE,
        'Gap Down'        : float(row['gap_pct']) < -GAP_THR,
        'Prev India UP'   : float(row['prev_india_ret']) > 0,
        'Prev India DOWN' : float(row['prev_india_ret']) < 0,
        'US UP'           : float(row['SP500_ret']) > 0,
        'US DOWN'         : float(row['SP500_ret']) < 0,
        'SGX UP'          : float(row['SGX_ret']) > 0,
        'SGX DOWN'        : float(row['SGX_ret']) < 0,
        'DAX UP'          : float(row['DAX_ret']) > 0,
        'VIX Rising'      : float(row['VIX_US_ret']) > 0.03,   # matches training: >3% daily move
        'VIX Falling'     : float(row['VIX_US_ret']) < 0,
        'VIX Spike'       : float(row['VIX_US_ret']) > 0.05,
    }

def check_combo(signals, signal_str):
    return all(signals.get(s.strip(), False) for s in signal_str.split('+'))

bear_combos = list(top_bearish['Signal'])
bull_combos = list(top_bullish['Signal'])

trade_days = []
for _, row in backtest_df.iterrows():
    sigs = compute_signals(row)
    bear_fired = [c for c in bear_combos if check_combo(sigs, c)]
    bull_fired = [c for c in bull_combos if check_combo(sigs, c)]

    if bear_fired and bull_fired:
        action, combo_fired = 'CONFLICT', None
    elif bear_fired:
        action, combo_fired = 'BEARISH', bear_fired[0]
    elif bull_fired:
        action, combo_fired = 'BULLISH', bull_fired[0]
    else:
        action, combo_fired = 'NO_SIGNAL', None

    trade_days.append({
        'india_date'  : row['india_date'],
        'india_open'  : float(row['india_open']),
        'gap_pct'     : float(row['gap_pct']),
        'vix_india'   : float(row['VIX_INDIA_level']),
        'dir_60'      : int(row['dir_60']),
        'ret_60'      : float(row['ret_60']),
        'action'      : action,
        'combo_fired' : combo_fired,
    })

trade_days_df = pd.DataFrame(trade_days)

print('Signal distribution across backtest period:')
for k, v in trade_days_df['action'].value_counts().items():
    print(f'  {k:<12}: {v:>3} days  ({v/len(trade_days_df)*100:.1f}%)')
print(f'\nTrade-able days : {(trade_days_df["action"].isin(["BEARISH","BULLISH"])).sum()}')

#  
# ── Cell 5: Black-Scholes pricing + trade simulation function ──────────────────

def bs_price(S, K, T, r, sigma, opt_type='CE'):
    '''Black-Scholes price in index points. opt_type = CE or PE.'''
    if T <= 1e-7:
        return max(0.0, S - K) if opt_type == 'CE' else max(0.0, K - S)
    sq = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / sq
    d2 = d1 - sq
    if opt_type == 'CE':
        return float(S * _norm.cdf(d1) - K * np.exp(-r * T) * _norm.cdf(d2))
    return float(K * np.exp(-r * T) * _norm.cdf(-d2) - S * _norm.cdf(-d1))


def nearest_thursday(d):
    '''Current-or-next Thursday. If d is Thursday, returns same day (DTE=0).'''
    days = (3 - d.weekday()) % 7
    return d + timedelta(days=days)


def simulate_trade(trade_date, action, nifty_open, vix_india, minute_df):
    '''
    Simulate one options trade minute-by-minute using BS pricing.
    Returns dict with trade details + P&L, or None if degenerate.
    '''
    if isinstance(trade_date, pd.Timestamp):
        trade_date = trade_date.date()

    expiry = nearest_thursday(trade_date)
    dte    = (expiry - trade_date).days

    atm = round(nifty_open / STRIKE_STEP) * STRIKE_STEP
    if action == 'BEARISH':
        strike   = atm - STRIKE_STEP * STRIKES_OTM
        opt_type = 'PE'
    else:
        strike   = atm + STRIKE_STEP * STRIKES_OTM
        opt_type = 'CE'

    # IV: India VIX/100 with weekly-skew adjustment
    iv_raw = vix_india / 100.0
    iv     = iv_raw * (1.30 if dte <= 2 else 1.15 if dte <= 4 else 1.05)

    def tte(t_obj):
        '''Time to expiry in years from t_obj (time) on trade_date.'''
        expiry_dt  = datetime.combine(expiry, dtime(15, 30))
        current_dt = datetime.combine(trade_date, t_obj)
        secs = (expiry_dt - current_dt).total_seconds()
        return max(secs, 0.0) / (365.25 * 24 * 3600)

    # Entry at 9:15 using NIFTY open
    entry_price = bs_price(nifty_open, strike, tte(dtime(9, 15)), RISK_FREE_RATE, iv, opt_type)
    if entry_price < 0.5:
        return None   # degenerate option

    sl_price = entry_price * (1 - STOP_LOSS_PCT)
    tp_price = entry_price * (1 + PROFIT_TARGET_PCT)

    # Filter minute data to this trading date, 9:16-10:15
    day_min = minute_df[minute_df.index.date == trade_date]
    day_min = day_min.between_time('09:16', '10:15')

    exit_price  = None
    exit_reason = '10:15 exit'
    exit_time   = '10:15'

    for ts, m in day_min.iterrows():
        spot  = float(m['close'])
        t_now = ts.to_pydatetime().replace(tzinfo=None).time()
        price = bs_price(spot, strike, tte(t_now), RISK_FREE_RATE, iv, opt_type)

        if price <= sl_price:
            exit_price, exit_reason, exit_time = sl_price, 'Stop Loss', str(t_now)[:5]
            break
        if price >= tp_price:
            exit_price, exit_reason, exit_time = tp_price, 'Target Hit', str(t_now)[:5]
            break

    if exit_price is None:
        spot_last = float(day_min.iloc[-1]['close']) if len(day_min) > 0 else nifty_open
        exit_price = bs_price(spot_last, strike, tte(dtime(10, 15)), RISK_FREE_RATE, iv, opt_type)

    pnl_pts = exit_price - entry_price
    pnl_rs  = pnl_pts * LOT_SIZE - BROKERAGE

    return {
        'expiry'     : expiry,
        'dte'        : dte,
        'opt_type'   : opt_type,
        'strike'     : int(strike),
        'atm'        : int(atm),
        'iv_pct'     : round(iv * 100, 1),
        'entry_pts'  : round(entry_price, 2),
        'exit_pts'   : round(exit_price, 2),
        'exit_reason': exit_reason,
        'exit_time'  : exit_time,
        'pnl_pts'    : round(pnl_pts, 2),
        'pnl_rs'     : round(pnl_rs, 2),
    }

# Quick sanity check
_chk = bs_price(22000, 21950, 5/365, RISK_FREE_RATE, 0.15, 'PE')
print(f'BS sanity check: NIFTY=22000, 1-OTM PUT (21950), DTE=5, VIX=15% -> {_chk:.1f} pts')
print(f'  (Expected: ~100-150 pts for weekly OTM put)')

#  
# ── Cell 6: Run the 90-day backtest ────────────────────────────────────────────
tradeable = trade_days_df[trade_days_df['action'].isin(['BEARISH', 'BULLISH'])].copy()
print(f'Running backtest on {len(tradeable)} tradeable days...')

results = []
skipped = 0

for _, trow in tradeable.iterrows():
    res = simulate_trade(
        trade_date = trow['india_date'],
        action     = trow['action'],
        nifty_open = trow['india_open'],
        vix_india  = trow['vix_india'],
        minute_df  = minute_all,
    )
    if res is None:
        skipped += 1
        continue

    actual_dir = int(trow['dir_60'])
    pred_dir   = -1 if trow['action'] == 'BEARISH' else +1
    correct    = (pred_dir == actual_dir)

    results.append({
        'Date'        : trow['india_date'].date(),
        'Signal'      : trow['action'],
        'Combo'       : trow['combo_fired'],
        'NIFTY Open'  : int(round(trow['india_open'])),
        'Gap%'        : f"{trow['gap_pct']:+.2%}",
        'Strike'      : f"{res['strike']} {res['opt_type']}",
        'ATM'         : res['atm'],
        'DTE'         : res['dte'],
        'IV%'         : res['iv_pct'],
        'Entry (pts)' : res['entry_pts'],
        'Exit (pts)'  : res['exit_pts'],
        'Exit Reason' : res['exit_reason'],
        'Exit Time'   : res['exit_time'],
        'P&L (pts)'   : res['pnl_pts'],
        'P&L (Rs)'    : res['pnl_rs'],
        'Actual'      : 'DOWN' if actual_dir == -1 else 'UP',
        'Actual Ret%' : f"{trow['ret_60']:+.2%}",
        'Correct?'    : 'YES' if correct else 'NO',
    })

results_df = pd.DataFrame(results)

print(f'Done. Trades simulated : {len(results_df)}')
if skipped:
    print(f'Skipped (degenerate)   : {skipped}')
if len(results_df) > 0:
    wins = (results_df['P&L (Rs)'] > 0).sum()
    pnl  = results_df['P&L (Rs)'].sum()
    print(f'Wins / Losses          : {wins} / {len(results_df)-wins}')
    print(f'Total P&L              : Rs{pnl:,.0f}')

#  
# ── Cell 7: Trade log table ─────────────────────────────────────────────────────
pd.set_option('display.max_rows', 200)
pd.set_option('display.max_columns', 25)
pd.set_option('display.width', 220)

if len(results_df) == 0:
    print('No trades to display.')
else:
    display_cols = [
        'Date', 'Signal', 'NIFTY Open', 'Gap%', 'Strike', 'DTE', 'IV%',
        'Entry (pts)', 'Exit (pts)', 'Exit Reason', 'Exit Time',
        'P&L (pts)', 'P&L (Rs)', 'Actual', 'Actual Ret%', 'Correct?'
    ]
    log = results_df[display_cols].copy()

    sep = '=' * 200
    h1  = 'NIFTY OPTIONS BACKTEST — FULL TRADE LOG'
    h2  = f'SL={STOP_LOSS_PCT:.0%} premium  |  Target={PROFIT_TARGET_PCT:.0%} premium  |  {STRIKES_OTM}-strike OTM  |  Exit at SL / Target / 10:15 AM'
    print(sep)
    print(f'{h1:^200}')
    print(f'{h2:^200}')
    print(sep)
    print(log.to_string(index=False))
    print(sep)

    # Summary footer
    bear_log = results_df[results_df['Signal'] == 'BEARISH']
    bull_log = results_df[results_df['Signal'] == 'BULLISH']
    for lbl, sub in [('ALL', results_df), ('BEARISH', bear_log), ('BULLISH', bull_log)]:
        if len(sub) == 0: continue
        wr  = (sub['P&L (Rs)'] > 0).mean() * 100
        acc = (sub['Correct?'] == 'YES').mean() * 100
        tot = sub['P&L (Rs)'].sum()
        print(f'  {lbl:<8}: {len(sub):>3} trades  |  Win rate {wr:.1f}%  |  Pred accuracy {acc:.1f}%  |  Total P&L Rs{tot:,.0f}')


# ── Cell 8: Performance metrics — MODIFIED ────────────────────────────────────
# ── Cell 8: Performance metrics — FINAL ────────────────────────────────────

def compute_xirr(cash_flows, dates):
    from scipy.optimize import newton

    def xnpv(rate):
        return sum(cf / ((1 + rate) ** ((d - dates[0]).days / 365.0))
                   for cf, d in zip(cash_flows, dates))

    try:
        return newton(xnpv, 0.1)
    except:
        return None


def metrics_block(df, label):

    if len(df) == 0:
        print(f'  {label}: no trades.')
        return [0.0]

    capital = None
    cap_curve = []

    FIXED_LOTS = 5
    refill_count = 0
    total_refilled = 0.0
    refill_events = []

    # 🔥 XIRR tracking
    cash_flows = []
    cash_dates = []

    for i in range(len(df)):
        row = df.iloc[i]
        trade_date = pd.to_datetime(row['Date'])

        cost_per_lot = row['Entry (pts)'] * LOT_SIZE

        # Initial capital
        if capital is None:
            capital = cost_per_lot * FIXED_LOTS
            initial_capital = capital

            cash_flows.append(-initial_capital)
            cash_dates.append(trade_date)

        # Required capital (min 5 lots)
        required_capital = cost_per_lot * FIXED_LOTS

        if capital < required_capital:
            refill_amt = required_capital - capital
            capital += refill_amt

            refill_count += 1
            total_refilled += refill_amt
            refill_events.append((i, refill_amt))

            # XIRR
            cash_flows.append(-refill_amt)
            cash_dates.append(trade_date)

        # Dynamic lots
        lots = max(FIXED_LOTS, int(capital / cost_per_lot))

        trade_pnl = row['P&L (pts)'] * LOT_SIZE * lots - BROKERAGE * lots
        capital += trade_pnl

        cap_curve.append(round(capital, 2))

    # Final capital → XIRR inflow
    cash_flows.append(capital)
    cash_dates.append(pd.to_datetime(df.iloc[-1]['Date']))

    # Metrics
    total_pnl = capital - initial_capital - total_refilled
    net_return = (total_pnl / (initial_capital + total_refilled)) * 100 if (initial_capital + total_refilled) > 0 else 0

    xirr = compute_xirr(cash_flows, cash_dates)

        # 🔥 PRINT EVERYTHING
    # 🔥 CAPITAL SUMMARY
    total_invested = initial_capital + total_refilled
    total_profit = capital - total_invested

    net_return = (total_profit / total_invested) * 100 if total_invested > 0 else 0

    print(f'\n{"="*58}')
    print(f'  {label} — CAPITAL SUMMARY')
    print(f'{"="*58}')
    print(f'  Initial capital   : Rs{initial_capital:,.0f}')
    print(f'  Total invested    : Rs{total_invested:,.0f}')
    print(f'  Total profit      : Rs{total_profit:,.0f}')
    print(f'  Final capital     : Rs{capital:,.0f}')
    print(f'  Total refilled    : Rs{total_refilled:,.0f}')
    print(f'  Net return        : {net_return:+.2f}%')
    print(f'  Refill count      : {refill_count}')

    if xirr is not None:
        print(f'  XIRR              : {xirr*100:.2f}%')
    else:
        print(f'  XIRR              : Could not compute')

    print(f'{"="*58}')

    # Optional: show each refill
    if refill_events:
        print("\n  Refill events:")
        for idx, amt in refill_events:
            print(f"    Trade {idx}: +Rs{amt:,.0f}")

    return cap_curve

curves = {}
curves['ALL']     = metrics_block(results_df, 'ALL TRADES')
curves['BEARISH'] = metrics_block(results_df[results_df['Signal'] == 'BEARISH'], 'BEARISH ONLY')
curves['BULLISH'] = metrics_block(results_df[results_df['Signal'] == 'BULLISH'], 'BULLISH ONLY')

# ── Cell 9: Charts (UNCHANGED except NO SAVE) ────────────────────────────────

if len(results_df) > 0:
    fig = plt.figure(figsize=(20, 13))
    gs  = gridspec.GridSpec(2, 3, figure=fig)

    subsets = {
        'ALL': results_df,
        'BEARISH': results_df[results_df['Signal'] == 'BEARISH'],
        'BULLISH': results_df[results_df['Signal'] == 'BULLISH'],
    }

    for i, key in enumerate(['ALL','BEARISH','BULLISH']):
        ax = fig.add_subplot(gs[0, i])
        cap = curves[key]
        ax.plot(cap)
        ax.set_title(key)

    for i, key in enumerate(['ALL','BEARISH','BULLISH']):
        ax = fig.add_subplot(gs[1, i])
        sub = subsets[key]
        if len(sub) > 0:
            ax.bar(range(len(sub)), sub['P&L (Rs)'])

    plt.show()