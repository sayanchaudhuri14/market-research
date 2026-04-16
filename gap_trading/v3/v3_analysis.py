# ── V3 Analysis ────────────────────────────────────────────────────────────────
# Adds 4 new markets: China SSE, Hang Seng, Crude Oil, Dollar Index
# Tests ONLY combinations that include at least 1 new signal.
# Existing v2 combinations (old signals only) are NOT retested.
# Compares best new combos against v2 top-3 bearish/bullish.
# ──────────────────────────────────────────────────────────────────────────────

import pandas as pd
import numpy as np
import yfinance as yf
from pathlib import Path
from datetime import timedelta
from itertools import combinations
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

# ── Config ────────────────────────────────────────────────────────────────────
BASE          = Path(__file__).parent.parent
# Data lives under market-research/ subdirectory
_mr           = BASE / 'market-research'
V2_CSV        = _mr / 'v2' / 'v2_aligned_dataset.csv'
V2_SIGNALS    = _mr / 'v2' / 'v2_reliable_signals.csv'
V3_DIR        = Path(__file__).parent
V3_DATASET    = V3_DIR / 'v3_aligned_dataset.csv'
V3_SIGNALS    = V3_DIR / 'v3_new_signals.csv'

BASE_RATE  = 54.5    # % of sessions where NIFTY first hour is DOWN
MIN_N      = 40      # minimum occurrences for a combo to be tested
P_THRESH   = 0.05    # significance threshold

# ── New tickers to download ───────────────────────────────────────────────────
NEW_TICKERS = {
    'China'   : '000001.SS',   # Shanghai Composite -- closes 15 min before India opens
    'HangSeng': '^HSI',        # Hang Seng -- Asia sentiment, independent of SGX
    'Oil'     : 'CL=F',        # WTI Crude -- India imports 85% of oil needs
    'DXY'     : 'DX-Y.NYB',    # US Dollar Index -- strong dollar = FII outflows from India
}

# ── Step 1: Load v2 dataset ───────────────────────────────────────────────────
print('Loading v2 aligned dataset...')
v2 = pd.read_csv(V2_CSV, parse_dates=['india_date'])
v2 = v2.sort_values('india_date').reset_index(drop=True)
print(f'  {len(v2)} sessions  ({v2["india_date"].iloc[0].date()} to {v2["india_date"].iloc[-1].date()})')

# ── Step 2: Download new market data ─────────────────────────────────────────
start = str(v2['india_date'].min().date() - timedelta(days=15))
end   = str(v2['india_date'].max().date() + timedelta(days=5))
print(f'\nDownloading new market data ({start} -> {end})...')

new_rets = {}
for name, ticker in NEW_TICKERS.items():
    try:
        df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        # Ensure tz-naive date index
        df.index = pd.to_datetime(df.index)
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        df.index = df.index.normalize()
        ret = df['Close'].pct_change()
        new_rets[name] = ret.dropna()
        print(f'  {name:10}: {len(ret.dropna()):>4} rows  ({ticker})')
    except Exception as e:
        print(f'  {name:10}: FAILED -- {e}')

# ── Step 3: Align new returns to India sessions ───────────────────────────────
# For each India session date T, use the most recent global date strictly < T.
# Same alignment rule as v2 -- ensures no look-ahead bias.
print('\nAligning to India sessions...')

def align_to_india(india_dates, ret_series, max_gap=5):
    aligned = []
    for idate in india_dates:
        d = idate.date() if hasattr(idate, 'date') else idate
        candidates = ret_series[ret_series.index.date < d]
        if len(candidates) == 0:
            aligned.append(np.nan)
            continue
        gap = (d - candidates.index[-1].date()).days
        aligned.append(float(candidates.iloc[-1]) if gap <= max_gap else np.nan)
    return aligned

v3 = v2.copy()
for name, ret_series in new_rets.items():
    col = f'{name}_ret'
    v3[col] = align_to_india(v3['india_date'], ret_series)
    n_ok = v3[col].notna().sum()
    print(f'  {name:10}: {n_ok}/{len(v3)} sessions  (missing: {len(v3)-n_ok})')

v3.to_csv(V3_DATASET, index=False)
print(f'\nV3 dataset saved -> {V3_DATASET}')

# ── Step 4: Build signal matrix ───────────────────────────────────────────────
print('\nBuilding signal matrix...')

# Old signals -- exact definitions from py_backtest.py (post-audit)
OLD_SIGNALS = {
    'Gap Up'          : lambda r: r['gap_pct']        >  0.0015,
    'Gap Up Strong'   : lambda r: r['gap_pct']        >  0.0050,
    'Gap Down'        : lambda r: r['gap_pct']        < -0.0015,
    'Prev India UP'   : lambda r: r['prev_india_ret'] >  0,
    'Prev India DOWN' : lambda r: r['prev_india_ret'] <  0,
    'US UP'           : lambda r: r['SP500_ret']      >  0,
    'US DOWN'         : lambda r: r['SP500_ret']      <  0,
    'SGX UP'          : lambda r: r['SGX_ret']        >  0,
    'SGX DOWN'        : lambda r: r['SGX_ret']        <  0,
    'DAX UP'          : lambda r: r['DAX_ret']        >  0,
    'VIX Rising'      : lambda r: r['VIX_US_ret']     >  0.03,
    'VIX Falling'     : lambda r: r['VIX_US_ret']     <  0,
    'VIX Spike'       : lambda r: r['VIX_US_ret']     >  0.05,
}

# New signals -- each tied to an independent market/factor
NEW_SIGNALS = {
    'China UP'        : lambda r: r['China_ret']    >  0,
    'China DOWN'      : lambda r: r['China_ret']    <  0,
    'HangSeng UP'     : lambda r: r['HangSeng_ret'] >  0,
    'HangSeng DOWN'   : lambda r: r['HangSeng_ret'] <  0,
    'Oil UP'          : lambda r: r['Oil_ret']      >  0,   # higher oil = cost pressure on India
    'Oil DOWN'        : lambda r: r['Oil_ret']      <  0,
    'DXY UP'          : lambda r: r['DXY_ret']      >  0,   # stronger dollar = FII outflows
    'DXY DOWN'        : lambda r: r['DXY_ret']      <  0,
}

ALL_SIGNALS = {**OLD_SIGNALS, **NEW_SIGNALS}
OLD_NAMES = set(OLD_SIGNALS.keys())
NEW_NAMES = set(NEW_SIGNALS.keys())

# Mutually exclusive pairs -- these can never both be True, skip any combo containing both
MUTEX = [
    ('Gap Up', 'Gap Down'),
    ('Gap Up Strong', 'Gap Down'),
    ('US UP', 'US DOWN'),
    ('SGX UP', 'SGX DOWN'),
    ('Prev India UP', 'Prev India DOWN'),
    ('VIX Rising', 'VIX Falling'),
    ('China UP', 'China DOWN'),
    ('HangSeng UP', 'HangSeng DOWN'),
    ('Oil UP', 'Oil DOWN'),
    ('DXY UP', 'DXY DOWN'),
    # Subsets: Gap Up Strong ⊆ Gap Up, so both in a combo is redundant
    ('Gap Up', 'Gap Up Strong'),
    # VIX Spike ⊆ VIX Rising
    ('VIX Rising', 'VIX Spike'),
]
MUTEX_SETS = [frozenset(p) for p in MUTEX]

def is_valid_combo(combo_set):
    for ms in MUTEX_SETS:
        if ms.issubset(combo_set):
            return False
    return True

# Build boolean signal columns
sig_mat = pd.DataFrame(index=v3.index)
for name, fn in ALL_SIGNALS.items():
    try:
        sig_mat[name] = v3.apply(fn, axis=1).fillna(False).astype(bool)
    except:
        sig_mat[name] = False

sig_mat['dir_60'] = v3['dir_60'].values  # -1 DOWN, +1 UP

# Print new signal base rates
print('\nNew signal frequencies and base P(DOWN):')
for name in NEW_NAMES:
    mask = sig_mat[name]
    n = int(mask.sum())
    if n > 0:
        p_down = (sig_mat.loc[mask, 'dir_60'] == -1).mean() * 100
        print(f'  {name:16}: N={n:3d} ({n/len(sig_mat)*100:.1f}%)  P(DOWN)={p_down:.1f}%  '
              f'{"BEARISH lean" if p_down > BASE_RATE else "BULLISH lean"}')

# ── Step 5: Test all NEW combinations (>=1 new signal) ────────────────────────
print(f'\nTesting combinations (size 2-4, >=1 new signal, N>={MIN_N}, p<{P_THRESH})...')

ALL_NAMES_LIST = list(ALL_SIGNALS.keys())

def test_combo(names_set):
    cols = list(names_set)
    mask = sig_mat[cols].all(axis=1)
    n = int(mask.sum())
    if n < MIN_N:
        return None

    n_down = int((sig_mat.loc[mask, 'dir_60'] == -1).sum())
    p_down_val = n_down / n

    result = stats.binomtest(n_down, n, BASE_RATE / 100, alternative='two-sided')
    p_val = result.pvalue
    if p_val >= P_THRESH:
        return None

    # Wilson 95% CI
    z = 1.96
    denom  = 1 + z**2 / n
    center = (p_down_val + z**2 / (2*n)) / denom
    margin = z * np.sqrt(p_down_val*(1-p_down_val)/n + z**2/(4*n**2)) / denom

    edge    = p_down_val * 100 - BASE_RATE
    sig_str = '***' if p_val < 0.001 else '**' if p_val < 0.01 else '*'

    # Sort: new signals first, then old -- makes readability easier
    ordered = sorted(names_set, key=lambda x: (x not in NEW_NAMES, x))

    return {
        'N'      : n,
        'Freq'   : round(n / len(sig_mat) * 100, 1),
        'P_Down' : round(p_down_val * 100, 1),
        'P_Up'   : round((1 - p_down_val) * 100, 1),
        'Edge'   : round(edge, 1),
        'CI_lo'  : round((center - margin) * 100, 1),
        'CI_hi'  : round((center + margin) * 100, 1),
        'p_val'  : round(p_val, 4),
        'Sig'    : sig_str,
        'Verdict': 'RELIABLE',
        'Level'  : len(names_set),
        'Signal' : ' + '.join(ordered),
    }

results = []
for size in [2, 3, 4]:
    count = tested = 0
    for combo in combinations(ALL_NAMES_LIST, size):
        combo_set = frozenset(combo)
        if not combo_set.intersection(NEW_NAMES):
            continue          # skip pure-old combos -- already covered by v2
        if not is_valid_combo(combo_set):
            continue          # skip mutually exclusive / redundant combos
        tested += 1
        res = test_combo(combo_set)
        if res:
            results.append(res)
            count += 1
    print(f'  Size {size}: {tested:>5} combos tested  ->  {count} significant')

print(f'\nTotal new reliable signals: {len(results)}')

# ── Step 6: Save and compare ──────────────────────────────────────────────────
if not results:
    print('\nNo significant new combinations found with p<0.05 and N>=40.')
else:
    res_df = pd.DataFrame(results)
    res_df = res_df.sort_values('Edge', key=abs, ascending=False).reset_index(drop=True)
    res_df.to_csv(V3_SIGNALS, index=False)
    print(f'Saved -> {V3_SIGNALS}')

    v2_sigs    = pd.read_csv(V2_SIGNALS)
    v2_bear    = v2_sigs[v2_sigs['P_Down'] > BASE_RATE].sort_values('Edge', ascending=False).head(3)
    v2_bull    = v2_sigs[v2_sigs['P_Down'] < (100 - BASE_RATE)].sort_values('P_Down').head(3)

    new_bear   = res_df[res_df['P_Down'] > BASE_RATE].head(10)
    new_bull   = res_df[res_df['P_Down'] < (100 - BASE_RATE)].head(10)

    SEP = '=' * 72

    # ── Bearish ──
    print(f'\n{SEP}')
    print('  NEW BEARISH SIGNALS  (predict NIFTY first-hour DOWN)')
    print(SEP)
    if len(new_bear) > 0:
        print(f"  {'Signal':<52} {'P(DOWN)':>6} {'Edge':>6} {'N':>5} {'p':>7} {'Sig'}")
        print(f"  {'-'*52} {'-'*6} {'-'*6} {'-'*5} {'-'*7} {'-'*3}")
        for _, r in new_bear.iterrows():
            print(f"  {r['Signal']:<52} {r['P_Down']:>5.1f}% {r['Edge']:>+5.1f}% "
                  f"{int(r['N']):>5}  {r['p_val']:>6.4f} {r['Sig']}")
    else:
        print('  None found.')

    print(f'\n{SEP}')
    print('  V2 TOP-3 BEARISH  (benchmark)')
    print(SEP)
    for _, r in v2_bear.iterrows():
        print(f"  {r['Signal']:<52} {r['P_Down']:>5.1f}% {r['Edge']:>+5.1f}% "
              f"{int(r['N']):>5}  {r['p_val']:>6.4f} {r['Sig']}")

    # ── Bullish ──
    print(f'\n{SEP}')
    print('  NEW BULLISH SIGNALS  (predict NIFTY first-hour UP)')
    print(SEP)
    if len(new_bull) > 0:
        print(f"  {'Signal':<52} {'P(UP)':>6} {'Edge':>6} {'N':>5} {'p':>7} {'Sig'}")
        print(f"  {'-'*52} {'-'*6} {'-'*6} {'-'*5} {'-'*7} {'-'*3}")
        for _, r in new_bull.iterrows():
            print(f"  {r['Signal']:<52} {100-r['P_Down']:>5.1f}% {abs(r['Edge']):>+5.1f}% "
                  f"{int(r['N']):>5}  {r['p_val']:>6.4f} {r['Sig']}")
    else:
        print('  None found.')

    print(f'\n{SEP}')
    print('  V2 TOP-3 BULLISH  (benchmark)')
    print(SEP)
    for _, r in v2_bull.iterrows():
        print(f"  {r['Signal']:<52} {100-r['P_Down']:>5.1f}% {abs(r['Edge']):>+5.1f}% "
              f"{int(r['N']):>5}  {r['p_val']:>6.4f} {r['Sig']}")

    # ── Summary ──
    print(f'\n{SEP}')
    print('  SUMMARY')
    print(SEP)
    print(f'  New signals tested          : {len(results)}')
    print(f'  New bearish (P_Down>54.5%)  : {len(new_bear)}')
    print(f'  New bullish (P_Down<45.5%)  : {len(new_bull)}')

    if len(new_bear) > 0:
        best_new_bear = new_bear.iloc[0]
        best_v2_bear  = v2_bear.iloc[0]
        if best_new_bear['Edge'] > best_v2_bear['Edge']:
            print(f'\n  *** NEW BEARISH beats V2: {best_new_bear["Signal"]}')
            print(f'      Edge {best_new_bear["Edge"]:+.1f}% vs V2 best {best_v2_bear["Edge"]:+.1f}%')
        else:
            print(f'\n  V2 bearish still strongest: {best_v2_bear["Signal"]} (Edge {best_v2_bear["Edge"]:+.1f}%)')
            print(f'  Best new bearish edge: {best_new_bear["Edge"]:+.1f}%')

    if len(new_bull) > 0:
        best_new_bull = new_bull.iloc[0]
        best_v2_bull  = v2_bull.iloc[0]
        if abs(best_new_bull['Edge']) > abs(best_v2_bull['Edge']):
            print(f'\n  *** NEW BULLISH beats V2: {best_new_bull["Signal"]}')
            print(f'      Edge {abs(best_new_bull["Edge"]):+.1f}% vs V2 best {abs(best_v2_bull["Edge"]):+.1f}%')
        else:
            print(f'\n  V2 bullish still strongest: {best_v2_bull["Signal"]} (Edge {abs(best_v2_bull["Edge"]):+.1f}%)')
            print(f'  Best new bullish edge: {abs(best_new_bull["Edge"]):+.1f}%')

print(f'\nDone.')
