"""
_engine.py — Shared simulation engine for gap trading v4 backtests.

Extracted from backtest_2024.ipynb Cell 3 and grid_search_sl_tp.py.
All v2/backtest and v4.x notebooks import from here — simulation logic
is defined exactly once.

Usage:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / 'v4'))
    from _engine import simulate_trades, compute_metrics, save_results

signal_days format:
    {
        datetime.date(2024, 1, 4): {
            'entry_price': 125.30,
            'candles': pd.DataFrame,   # 1-min option candles 09:25..11:15
            'dte': 1,
            'strike': 21650,
            'combo': 'Gap Up + SGX UP + DAX UP',
            'nifty_open': 21711.6,
        },
        datetime.date(2024, 1, 5): None,   # no signal / skip
        ...
    }
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd


# ── Charge model (Zerodha / AngelOne, NIFTY F&O) ──────────────────────────────
# Source: cron/config.py — keep in sync
BROKERAGE_PER_ORDER = 20.0       # Rs 20 flat per F&O order (buy + sell = Rs 40)
STT_SELL_RATE       = 0.000625   # 0.0625% on sell-side premium value
STAMP_BUY_RATE      = 0.00003    # 0.003%  on buy-side premium value
EXCHANGE_RATE       = 0.00053    # 0.053%  of total (buy+sell) premium turnover
SEBI_RATE           = 0.000001   # 0.0001% of total premium turnover
GST_RATE            = 0.18       # 18% on (brokerage + exchange + SEBI)


def compute_charges(entry_price: float, exit_price: float,
                    lots: int, lot_size: int = 75) -> float:
    """Full round-trip transaction cost in Rs for one trade."""
    buy_val  = entry_price * lots * lot_size
    sell_val = exit_price  * lots * lot_size
    brok     = BROKERAGE_PER_ORDER * 2              # buy order + sell order
    stt      = STT_SELL_RATE  * sell_val
    stamp    = STAMP_BUY_RATE * buy_val
    exch     = EXCHANGE_RATE  * (buy_val + sell_val)
    sebi     = SEBI_RATE      * (buy_val + sell_val)
    gst      = GST_RATE * (brok + exch + sebi)
    return round(brok + stt + stamp + exch + sebi + gst, 4)


# ── Core simulation ────────────────────────────────────────────────────────────

def simulate_trades(signal_days: dict, params: dict) -> pd.DataFrame:
    """
    Run candle-by-candle simulation over all signal days.

    Parameters
    ----------
    signal_days : dict
        Keys: datetime.date objects (all candidate trade dates).
        Values: dict with keys {entry_price, candles, dte, strike, combo, nifty_open}
                OR None to skip the date.
    params : dict
        Must contain: SL_PCT, TP_PCT, BASE_LOTS, MAX_LOTS, DTE0_LOTS,
                      LOT_SIZE, ENTRY_TIME, EXIT_TIME.

    Returns
    -------
    pd.DataFrame with columns:
        trade_num, date, strike, dte, entry, lots,
        sl_price, tp_price, exit_price, exit_reason, exit_time,
        pnl_pts, pnl_rs, charges_rs, capital_before, capital_after,
        drawdown_pct, combo
    """
    SL_PCT    = params['SL_PCT']
    TP_PCT    = params['TP_PCT']
    BASE_LOTS = params['BASE_LOTS']
    MAX_LOTS  = params['MAX_LOTS']
    DTE0_LOTS = params['DTE0_LOTS']
    LOT_SIZE  = params.get('LOT_SIZE', 75)

    capital   = None
    peak      = None
    trade_log = []
    trade_num = 0

    for d in sorted(signal_days.keys()):
        info = signal_days[d]
        if info is None:
            continue

        entry_price = info['entry_price']
        candles     = info['candles']       # DataFrame with columns: time, open, high, low, close
        dte         = info['dte']
        strike      = info['strike']
        combo       = info.get('combo', '')

        if entry_price is None or entry_price <= 0:
            continue

        cost_per_lot = entry_price * LOT_SIZE

        # ── Initialise capital on first trade ──────────────────────────────
        if capital is None:
            fixed = params.get('INITIAL_CAPITAL')
            capital = float(fixed) if fixed is not None else cost_per_lot * BASE_LOTS
            peak    = capital

        # ── Lot sizing ─────────────────────────────────────────────────────
        lots = int(capital // cost_per_lot)
        lots = max(lots, 1)
        lots = min(lots, MAX_LOTS)
        if dte == 0:
            lots = min(lots, DTE0_LOTS)

        # ── Refill if capital too low for even 1 lot ───────────────────────
        refill = 0.0
        if capital < cost_per_lot:
            refill  = cost_per_lot * BASE_LOTS - capital
            capital += refill
            peak    = max(peak, capital)
            lots    = min(BASE_LOTS, MAX_LOTS)
            if dte == 0:
                lots = min(lots, DTE0_LOTS)

        sl_price = round(entry_price * (1 - SL_PCT), 4)
        tp_price = round(entry_price * (1 + TP_PCT), 4)

        # ── Candle-by-candle exit scan ─────────────────────────────────────
        exit_price  = None
        exit_reason = None
        exit_time   = None

        if candles is not None and len(candles) > 0:
            for _, row in candles.iterrows():
                t = row.get('time', row.name)
                # Check TP first (option buyer's upside)
                if row['high'] >= tp_price:
                    exit_price  = tp_price
                    exit_reason = 'Target Hit'
                    exit_time   = str(t)
                    break
                if row['low'] <= sl_price:
                    exit_price  = sl_price
                    exit_reason = 'Stop Loss'
                    exit_time   = str(t)
                    break
            else:
                # Hard exit: use close of last available candle
                last = candles.iloc[-1]
                exit_price  = float(last['close'])
                exit_reason = f"{params.get('EXIT_TIME', '11:15')} exit"
                exit_time   = str(last.get('time', last.name))
        else:
            # No candle data — skip trade (data gap)
            continue

        # ── P&L ───────────────────────────────────────────────────────────
        pnl_pts  = exit_price - entry_price
        charges  = compute_charges(entry_price, exit_price, lots, LOT_SIZE)
        pnl_rs   = round(pnl_pts * lots * LOT_SIZE - charges, 4)

        capital_before = round(capital, 4)
        capital        = round(capital + pnl_rs, 4)
        peak           = max(peak, capital)
        drawdown_pct   = round((peak - capital) / peak * 100, 4) if peak > 0 else 0.0

        trade_num += 1
        trade_log.append({
            'trade_num':     trade_num,
            'date':          str(d),
            'strike':        strike,
            'dte':           dte,
            'entry':         round(entry_price, 4),
            'lots':          lots,
            'sl_price':      sl_price,
            'tp_price':      tp_price,
            'exit_price':    round(exit_price, 4),
            'exit_reason':   exit_reason,
            'exit_time':     exit_time,
            'pnl_pts':       round(pnl_pts, 4),
            'pnl_rs':        pnl_rs,
            'charges_rs':    round(charges, 4),
            'capital_before': capital_before,
            'capital_after': capital,
            'drawdown_pct':  drawdown_pct,
            'combo':         combo,
            'refill_rs':     round(refill, 4),
        })

    return pd.DataFrame(trade_log)


# ── Metrics ────────────────────────────────────────────────────────────────────

def _xirr_bisection(cash_flows: list[tuple[date, float]],
                    lo: float = -0.99, hi: float = 100.0,
                    tol: float = 1e-6, max_iter: int = 1000) -> Optional[float]:
    """
    Compute XIRR via bisection.  cash_flows: list of (date, amount).
    Amounts: negative = outflow (capital deployed), positive = inflow (final value).
    Returns annualised rate as decimal (e.g. 0.48 for 48%) or None if no solution.
    """
    if not cash_flows:
        return None
    d0 = cash_flows[0][0]

    def npv(r):
        return sum(cf / (1 + r) ** ((d - d0).days / 365.0) for d, cf in cash_flows)

    try:
        if npv(lo) * npv(hi) > 0:
            return None
        for _ in range(max_iter):
            mid = (lo + hi) / 2
            if abs(hi - lo) < tol:
                return mid
            if npv(mid) * npv(lo) < 0:
                hi = mid
            else:
                lo = mid
        return (lo + hi) / 2
    except Exception:
        return None


def compute_metrics(df_log: pd.DataFrame, params: dict) -> dict:
    """
    Compute the full standardised metrics dict from a trade log.

    Returns the dict that matches the JSON schema (ready for save_results).
    """
    if df_log.empty:
        return {'error': 'no trades executed'}

    n          = len(df_log)
    tp_hits    = (df_log['exit_reason'] == 'Target Hit').sum()
    sl_hits    = (df_log['exit_reason'] == 'Stop Loss').sum()
    time_exits = n - tp_hits - sl_hits
    profits    = (df_log['pnl_rs'] > 0).sum()
    losses     = (df_log['pnl_rs'] <= 0).sum()

    starting_capital = round(float(df_log['capital_before'].iloc[0]), 2)
    ending_capital   = round(float(df_log['capital_after'].iloc[-1]), 2)
    total_pnl_rs     = round(float(df_log['pnl_rs'].sum()), 2)
    total_refills    = round(float(df_log['refill_rs'].sum()), 2) if 'refill_rs' in df_log.columns else 0.0
    refill_count     = int((df_log['refill_rs'] > 0).sum()) if 'refill_rs' in df_log.columns else 0
    total_invested   = round(starting_capital + total_refills, 2)
    max_dd           = round(float(df_log['drawdown_pct'].max()), 4)

    win_pnl   = df_log.loc[df_log['pnl_rs'] > 0,  'pnl_rs']
    loss_pnl  = df_log.loc[df_log['pnl_rs'] <= 0, 'pnl_rs']
    avg_win   = round(float(win_pnl.mean()),  2) if len(win_pnl)  > 0 else 0.0
    avg_loss  = round(float(loss_pnl.mean()), 2) if len(loss_pnl) > 0 else 0.0

    # ── XIRR ──────────────────────────────────────────────────────────────
    xirr_pct = None
    try:
        dates = [date.fromisoformat(d) for d in df_log['date']]
        # Build cash flows: initial outflow, then final inflow
        # Approximation: treat each refill as an additional inflow at trade date
        cf = [(dates[0], -starting_capital)]
        for i, row in df_log.iterrows():
            d_i = date.fromisoformat(row['date'])
            refill = float(row['refill_rs']) if 'refill_rs' in df_log.columns else 0.0
            if refill > 0:
                cf.append((d_i, -refill))
        cf.append((dates[-1], ending_capital))
        r = _xirr_bisection(cf)
        if r is not None:
            xirr_pct = round(r * 100, 2)
    except Exception:
        pass

    # ── Net return (total invested = starting capital + all refills) ─────────
    net_return_pct = round((ending_capital - total_invested) / total_invested * 100, 2)

    # ── Monthly breakdown ──────────────────────────────────────────────────
    df_log['month'] = df_log['date'].str[:7]   # YYYY-MM
    monthly = (
        df_log.groupby('month')
        .agg(trades=('pnl_rs', 'count'),
             wins=('pnl_rs', lambda x: (x > 0).sum()),
             pnl_rs=('pnl_rs', 'sum'))
        .reset_index()
    )
    monthly['win_pct'] = (monthly['wins'] / monthly['trades'] * 100).round(1)
    monthly['pnl_rs']  = monthly['pnl_rs'].round(2)
    monthly_list = monthly.to_dict(orient='records')

    # ── Breakeven win rate ─────────────────────────────────────────────────
    sl = params.get('SL_PCT', 0)
    tp = params.get('TP_PCT', 1)
    breakeven_win_pct = round(sl / (sl + tp) * 100, 1) if (sl + tp) > 0 else None

    period_start = df_log['date'].min()
    period_end   = df_log['date'].max()

    return {
        'period':             f"{period_start} to {period_end}",
        'total_trades':       n,
        'tp_hit_pct':         round(tp_hits    / n * 100, 2),
        'sl_hit_pct':         round(sl_hits    / n * 100, 2),
        'time_exit_pct':      round(time_exits / n * 100, 2),
        'profit_trade_pct':   round(profits    / n * 100, 2),
        'loss_trade_pct':     round(losses     / n * 100, 2),
        'avg_win_rs':         avg_win,
        'avg_loss_rs':        avg_loss,
        'total_pnl_rs':       total_pnl_rs,
        'net_return_pct':     net_return_pct,
        'xirr_pct':           xirr_pct,
        'max_drawdown_pct':   max_dd,
        'starting_capital_rs': starting_capital,
        'ending_capital_rs':   ending_capital,
        'refill_count':        refill_count,
        'total_refilled_rs':   total_refills,
        'total_invested_rs':   total_invested,
        'breakeven_win_pct':   breakeven_win_pct,
        'monthly':             monthly_list,
    }


# ── Results export ─────────────────────────────────────────────────────────────

def save_results(metrics: dict, params: dict, version_meta: dict,
                 output_path: Path) -> Path:
    """
    Write a timestamped JSON results file.

    version_meta must contain: version, key_change, data_source
    Returns the written file path.
    """
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    ts       = datetime.now().strftime('%Y%m%d_%H%M')
    ds_short = version_meta.get('data_source', 'unknown').replace('_', '').replace('-', '')
    run_id   = f"{version_meta['version']}_{ts}_{ds_short}"

    record = {
        'run_id':     run_id,
        'version':    version_meta['version'],
        'key_change': version_meta.get('key_change', ''),
        'data_source': version_meta.get('data_source', ''),
        'period':     metrics.get('period', ''),
        'params':     params,
        'results': {k: v for k, v in metrics.items()
                    if k not in ('period', 'monthly')},
        'monthly':    metrics.get('monthly', []),
    }

    out_file = output_path / f"{run_id}.json"
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(record, f, indent=2, default=str)

    print(f"  Results saved → {out_file}")
    return out_file


# ── Signal helpers (shared across notebooks) ──────────────────────────────────

def sig_map(gap, pind, sp500, sgx, dax, vix,
            GAP_TH=0.0015, GAP_LG_TH=0.0050,
            VIX_RIS_TH=0.03, VIX_SPK_TH=0.05) -> dict:
    """
    Convert raw returns/values to the binary signal dict expected by combo matching.
    All inputs should be floats or None (None → signal defaults to False).
    """
    def _f(v):
        return v if v is not None and not (isinstance(v, float) and math.isnan(v)) else None

    gap    = _f(gap);   pind  = _f(pind)
    sp500  = _f(sp500); sgx   = _f(sgx)
    dax    = _f(dax);   vix   = _f(vix)

    return {
        'Gap Up'          : gap  is not None and gap  >  GAP_TH,
        'Gap Up Strong'   : gap  is not None and gap  >  GAP_LG_TH,
        'Gap Down'        : gap  is not None and gap  < -GAP_TH,
        'Prev India UP'   : pind is not None and pind >  0,
        'Prev India DOWN' : pind is not None and pind <  0,
        'US UP'           : sp500 is not None and sp500 >  0,
        'US DOWN'         : sp500 is not None and sp500 <  0,
        'SGX UP'          : sgx  is not None and sgx  >  0,
        'SGX DOWN'        : sgx  is not None and sgx  <  0,
        'DAX UP'          : dax  is not None and dax  >  0,
        'VIX Rising'      : vix  is not None and vix  >  VIX_RIS_TH,
        'VIX Falling'     : vix  is not None and vix  <  0,
        'VIX Spike'       : vix  is not None and vix  >  VIX_SPK_TH,
    }


def combo_fires(combo_str: str, signals: dict) -> bool:
    """Return True if every component of a '+'-separated combo string is True."""
    return all(signals.get(s.strip(), False) for s in combo_str.split('+'))


def load_reliable_signals(signals_csv: Path, bear_n: int = 10,
                           base_rate: float = 54.5) -> list[str]:
    """
    Load top-N bearish combos from a v2_reliable_signals.csv-format file.
    Returns list of combo strings sorted by Edge_pp descending.
    """
    df = pd.read_csv(signals_csv)
    top = (df[df['P_Down'] > base_rate]
           .sort_values('Edge_pp', ascending=False)
           .head(bear_n)
           .reset_index(drop=True))
    return list(top['Signal'])


def print_summary(df_log: pd.DataFrame, metrics: dict, params: dict):
    """Pretty-print trade summary to stdout."""
    W = 72
    print('=' * W)
    print(f"  BACKTEST RESULTS  ·  {metrics.get('period', '')}")
    print('=' * W)
    n = metrics['total_trades']
    print(f"  Trades          : {n}")
    print(f"  TP hit          : {metrics['tp_hit_pct']:.1f}%  ({int(round(metrics['tp_hit_pct']*n/100))} trades)")
    print(f"  SL hit          : {metrics['sl_hit_pct']:.1f}%  ({int(round(metrics['sl_hit_pct']*n/100))} trades)")
    print(f"  Time exit       : {metrics['time_exit_pct']:.1f}%  ({int(round(metrics['time_exit_pct']*n/100))} trades)")
    print(f"  Profitable      : {metrics['profit_trade_pct']:.1f}%")
    print(f"  Avg win (Rs)    : {metrics['avg_win_rs']:>10,.0f}")
    print(f"  Avg loss (Rs)   : {metrics['avg_loss_rs']:>10,.0f}")
    print(f"  Total P&L (Rs)  : {metrics['total_pnl_rs']:>10,.0f}")
    print(f"  Net return      : {metrics['net_return_pct']:>+.1f}%")
    if metrics.get('xirr_pct') is not None:
        print(f"  XIRR            : {metrics['xirr_pct']:>+.1f}%")
    print(f"  Max drawdown    : {metrics['max_drawdown_pct']:.1f}%")
    print(f"  Starting cap    : Rs {metrics['starting_capital_rs']:>10,.0f}")
    if metrics.get('refill_count', 0) > 0:
        print(f"  Refills         : {metrics['refill_count']}x  (Rs {metrics['total_refilled_rs']:>10,.0f} total)")
        print(f"  Total invested  : Rs {metrics['total_invested_rs']:>10,.0f}")
    print(f"  Ending cap      : Rs {metrics['ending_capital_rs']:>10,.0f}")
    if metrics.get('breakeven_win_pct'):
        print(f"  Breakeven WR    : {metrics['breakeven_win_pct']:.1f}%  "
              f"(SL={params['SL_PCT']*100:.0f}% / TP={params['TP_PCT']*100:.0f}%)")
    print()
    print(f"  {'Month':<8}  {'Trades':>6}  {'Wins':>5}  {'Win%':>6}  {'P&L (Rs)':>12}")
    print(f"  {'-'*8}  {'-'*6}  {'-'*5}  {'-'*6}  {'-'*12}")
    for m in metrics.get('monthly', []):
        print(f"  {m['month']:<8}  {m['trades']:>6}  {m['wins']:>5}  "
              f"{m['win_pct']:>5.1f}%  {m['pnl_rs']:>12,.0f}")
    print('=' * W)
