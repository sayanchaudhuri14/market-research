"""
Grid Search over STOP_LOSS_PCT and PROFIT_TARGET_PCT.

Imports pre-loaded data from py_backtest.py (runs it once silently),
then re-runs only the simulation loop for each (SL, TP) combination.

Run from the backtesting/ folder:
    python grid_search.py
"""

import os
import sys
import io
import contextlib
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')                   # suppress all plot windows before importing py_backtest
import matplotlib.pyplot as plt

# ── Grid parameters ────────────────────────────────────────────────────────────
SL_RANGE = [round(0.30 + i * 0.05, 2) for i in range(7)]   # 0.30, 0.35 ... 0.60
TP_RANGE = [round(0.10 + i * 0.05, 2) for i in range(7)]   # 0.10, 0.15 ... 0.40

OUT_DIR = Path(__file__).parent / 'grid_search_results'
OUT_DIR.mkdir(exist_ok=True)

# ── Import py_backtest once — loads aligned data + minute cache ────────────────
# All print output and plt.show() calls are suppressed during import.
print('Loading py_backtest (runs the full initial backtest once — please wait)...')

_here = Path(__file__).parent
os.chdir(_here)                         # ensure py_backtest resolves relative paths correctly
sys.path.insert(0, str(_here))

with contextlib.redirect_stdout(io.StringIO()):
    import py_backtest as bt

# Pull pre-classified tradeable days from the already-loaded module
tradeable = (
    bt.trade_days_df[bt.trade_days_df['action'].isin(['BEARISH', 'BULLISH'])]
    .copy()
    .reset_index(drop=True)
)

print(f'Done. Tradeable days  : {len(tradeable)}')
print(f'Backtest period       : {bt.start_date}  to  {bt.end_date}')
print(f'Grid size             : {len(SL_RANGE)} SL  x  {len(TP_RANGE)} TP'
      f'  =  {len(SL_RANGE) * len(TP_RANGE)} combinations')
print()


# ── Single-run backtest (reuses pre-loaded data, only SL/TP change) ───────────
def run_one(sl_pct: float, tp_pct: float):
    """
    Override bt's module-level globals and re-run simulate_trade on every
    tradeable day. simulate_trade reads STOP_LOSS_PCT / PROFIT_TARGET_PCT
    from bt's namespace at call-time, so overriding them here takes effect.
    """
    bt.STOP_LOSS_PCT     = sl_pct
    bt.PROFIT_TARGET_PCT = tp_pct

    rows = []
    for _, trow in tradeable.iterrows():
        res = bt.simulate_trade(
            trade_date = trow['india_date'],
            action     = trow['action'],
            nifty_open = trow['india_open'],
            vix_india  = trow['vix_india'],
            minute_df  = bt.minute_all,
        )
        if res is None:
            continue

        actual_dir = int(trow['dir_60'])
        pred_dir   = -1 if trow['action'] == 'BEARISH' else +1

        rows.append({
            'signal'      : trow['action'],
            'entry_pts'   : res['entry_pts'],
            'pnl_rs'      : res['pnl_rs'],
            'pnl_pts'     : res['pnl_pts'],
            'exit_reason' : res['exit_reason'],
            'correct'     : int(pred_dir == actual_dir),
        })

    if not rows:
        return None

    df = pd.DataFrame(rows)

    def _m(sub, prefix):
        if len(sub) == 0:
            return {f'{prefix}_{k}': 0 for k in
                    ['n', 'win_pct', 'total_pnl', 'avg_pnl',
                     'pred_acc', 'sl_hits', 'tp_hits', 'time_exits']}
        return {
            f'{prefix}_n'          : len(sub),
            f'{prefix}_win_pct'    : round((sub['pnl_rs'] > 0).mean() * 100, 2),
            f'{prefix}_total_pnl'  : round(sub['pnl_rs'].sum(), 0),
            f'{prefix}_avg_pnl'    : round(sub['pnl_rs'].mean(), 1),
            f'{prefix}_pred_acc'   : round(sub['correct'].mean() * 100, 2),
            f'{prefix}_sl_hits'    : int((sub['exit_reason'] == 'Stop Loss').sum()),
            f'{prefix}_tp_hits'    : int((sub['exit_reason'] == 'Target Hit').sum()),
            f'{prefix}_time_exits' : int((sub['exit_reason'] == '10:15 exit').sum()),
        }

    result = {
        'SL_pct'  : sl_pct,
        'TP_pct'  : tp_pct,
        'SL_label': f'{sl_pct:.0%}',
        'TP_label': f'{tp_pct:.0%}',
    }
    result.update(_m(df,                              'all'))
    result.update(_m(df[df['signal'] == 'BEARISH'],   'bear'))
    result.update(_m(df[df['signal'] == 'BULLISH'],   'bull'))
    return result


# ── Run the grid ───────────────────────────────────────────────────────────────
grid_rows = []
total     = len(SL_RANGE) * len(TP_RANGE)

print(f'{"#":>4}  {"SL":>5}  {"TP":>5}  {"Trades":>7}  {"Win%":>6}  '
      f'{"Total P&L":>12}  {"Avg/trade":>10}  {"SL hits":>7}  {"TP hits":>7}')
print('-' * 78)

for i, (sl, tp) in enumerate(product(SL_RANGE, TP_RANGE), 1):
    r = run_one(sl, tp)
    if r:
        grid_rows.append(r)
        print(f'{i:>4}  {sl:>5.0%}  {tp:>5.0%}  '
              f'{r["all_n"]:>7}  '
              f'{r["all_win_pct"]:>5.1f}%  '
              f'Rs{r["all_total_pnl"]:>+10,.0f}  '
              f'Rs{r["all_avg_pnl"]:>+8,.0f}  '
              f'{r["all_sl_hits"]:>7}  '
              f'{r["all_tp_hits"]:>7}')
    else:
        print(f'{i:>4}  {sl:>5.0%}  {tp:>5.0%}  (no trades)')

print()

# ── Save full results CSV ──────────────────────────────────────────────────────
grid_df = pd.DataFrame(grid_rows)
csv_path = OUT_DIR / 'grid_search_full.csv'
grid_df.to_csv(csv_path, index=False)
print(f'Full results saved : {csv_path}')

# ── Top 10 by total P&L ────────────────────────────────────────────────────────
print()
print('Top 10 combinations by Total P&L (all trades):')
print('-' * 75)
top10 = (
    grid_df.nlargest(10, 'all_total_pnl')
    [['SL_label', 'TP_label', 'all_n', 'all_win_pct', 'all_total_pnl',
      'all_avg_pnl', 'all_pred_acc', 'all_sl_hits', 'all_tp_hits', 'all_time_exits']]
    .reset_index(drop=True)
)
top10.index += 1
print(top10.to_string())
top10.to_csv(OUT_DIR / 'grid_top10.csv', index=False)

# ── Best combination summary ───────────────────────────────────────────────────
best = grid_df.loc[grid_df['all_total_pnl'].idxmax()]
print()
print('=' * 58)
print('  BEST COMBINATION  (highest total P&L, all trades)')
print('=' * 58)
print(f'  Stop Loss      : {best["SL_label"]}  of entry premium')
print(f'  Profit Target  : {best["TP_label"]}  of entry premium')
print(f'  Trades         : {int(best["all_n"])}')
print(f'  Win rate       : {best["all_win_pct"]:.1f}%')
print(f'  Total P&L      : Rs{best["all_total_pnl"]:,.0f}')
print(f'  Avg / trade    : Rs{best["all_avg_pnl"]:,.0f}')
print(f'  Pred accuracy  : {best["all_pred_acc"]:.1f}%')
print(f'  SL hits        : {int(best["all_sl_hits"])}  |  '
      f'TP hits : {int(best["all_tp_hits"])}  |  '
      f'Time exits : {int(best["all_time_exits"])}')
print()
print(f'  BEARISH only   : {int(best["bear_n"])} trades  '
      f'win {best["bear_win_pct"]:.1f}%  '
      f'P&L Rs{best["bear_total_pnl"]:,.0f}')
print(f'  BULLISH only   : {int(best["bull_n"])} trades  '
      f'win {best["bull_win_pct"]:.1f}%  '
      f'P&L Rs{best["bull_total_pnl"]:,.0f}')
print('=' * 58)


# ── Heatmaps ───────────────────────────────────────────────────────────────────
def draw_heatmap(ax, pivot, title, fmt, cmap='RdYlGn'):
    im = ax.imshow(pivot.values.astype(float), cmap=cmap, aspect='auto')
    plt.colorbar(im, ax=ax, shrink=0.85)
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_yticks(range(len(pivot.index)))
    ax.set_xticklabels([f'{v:.0%}' for v in pivot.columns], rotation=45, ha='right', fontsize=8)
    ax.set_yticklabels([f'{v:.0%}' for v in pivot.index], fontsize=8)
    ax.set_xlabel('Profit Target', fontsize=9)
    ax.set_ylabel('Stop Loss', fontsize=9)
    ax.set_title(title, fontsize=10, fontweight='bold')
    norm_vals = (pivot.values - pivot.values.min()) / max(pivot.values.max() - pivot.values.min(), 1e-9)
    for r in range(pivot.shape[0]):
        for c in range(pivot.shape[1]):
            val = pivot.values[r, c]
            txt = f'{val:{fmt}}'
            text_color = 'white' if norm_vals[r, c] < 0.25 or norm_vals[r, c] > 0.85 else 'black'
            ax.text(c, r, txt, ha='center', va='center', fontsize=7, color=text_color)


panels = [
    ('all_total_pnl',  'ALL — Total P&L (Rs)',          ',.0f', 'RdYlGn'),
    ('all_win_pct',    'ALL — Win Rate (%)',              '.1f',  'RdYlGn'),
    ('all_avg_pnl',    'ALL — Avg P&L per trade (Rs)',   ',.0f', 'RdYlGn'),
    ('bear_total_pnl', 'BEARISH — Total P&L (Rs)',       ',.0f', 'RdYlGn'),
    ('bear_win_pct',   'BEARISH — Win Rate (%)',          '.1f',  'RdYlGn'),
    ('bull_total_pnl', 'BULLISH — Total P&L (Rs)',       ',.0f', 'RdYlGn'),
]

fig, axes = plt.subplots(2, 3, figsize=(21, 12))
fig.suptitle(
    f'Grid Search Heatmaps  |  SL {SL_RANGE[0]:.0%}–{SL_RANGE[-1]:.0%}  x  '
    f'TP {TP_RANGE[0]:.0%}–{TP_RANGE[-1]:.0%}  |  {len(tradeable)} tradeable days',
    fontsize=13, fontweight='bold'
)

for ax, (col, title, fmt, cmap) in zip(axes.flat, panels):
    pivot = grid_df.pivot(index='SL_pct', columns='TP_pct', values=col)
    draw_heatmap(ax, pivot, title, fmt=fmt, cmap=cmap)

# Highlight best cell on the first heatmap
_piv = grid_df.pivot(index='SL_pct', columns='TP_pct', values='all_total_pnl')
_ri  = list(_piv.index).index(best['SL_pct'])
_ci  = list(_piv.columns).index(best['TP_pct'])
axes[0, 0].add_patch(plt.Rectangle(
    (_ci - 0.5, _ri - 0.5), 1, 1,
    fill=False, edgecolor='blue', linewidth=3
))
axes[0, 0].text(_ci, _ri - 0.38, 'BEST', ha='center', va='top',
                fontsize=7, color='blue', fontweight='bold')

plt.tight_layout()
heatmap_path = OUT_DIR / 'grid_search_heatmaps.png'
plt.savefig(heatmap_path, dpi=150, bbox_inches='tight')
plt.close()
print(f'\nHeatmaps saved : {heatmap_path}')
print('Grid search complete.')
