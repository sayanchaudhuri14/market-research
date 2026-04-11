#!/usr/bin/env python3
"""
backtest.py — Gap trading strategy backtest using REAL 2024 NSE options 1-min data.

Uses IDENTICAL assumptions to cron_gap_trading/config.py:
  - Same signal combos (top-10 bearish from v2_reliable_signals.csv)
  - Same SL=15% / TP=40% / entry 9:25 / exit 11:15
  - Same charge model (brokerage + STT + stamp + exchange + SEBI + GST)
  - Same lot sizing (BASE_LOTS=5, DTE0_MAX_LOTS=10, MAX_LOTS=25)
  - Same skip days (Mondays, NSE holidays, event days)
  - Same compounding capital model with refill at Rs 50k

Data sources (must exist relative to this file's parent):
  backtesting_2024_options/2024/2024{MON}/NIFTY-{expiry}-{tradedate}.csv
  backtesting_2024_options/2024/2024Nifty/Nifty-2024{MON}.csv
  backtesting_2024_options/2024/expiry.csv
  v2/v2_aligned_dataset.csv
  v2/v2_reliable_signals.csv

Outputs → cron_gap_trading/backtest_results/:
  trades.csv     — one row per trade with full detail
  daily_log.csv  — one row per day (traded, skipped, no-signal)
  summary.txt    — win rate, CAGR, XIRR, max drawdown, charge breakdown
"""

import os
import sys
import warnings
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    CRON_DIR, SIGNALS_CSV,
    SIGNAL_MODE, BASE_RATE,
    GAP_THRESHOLD, GAP_LARGE_THRESHOLD, VIX_RISING_THRESHOLD, VIX_SPIKE_THRESHOLD,
    LOT_SIZE, STRIKE_STEP, BASE_LOTS, DTE0_MAX_LOTS, MAX_LOTS,
    SL_PCT, TP_PCT,
    BROKERAGE_PER_ORDER, STT_SELL_RATE, STAMP_BUY_RATE,
    EXCHANGE_RATE, SEBI_RATE, GST_RATE,
    STARTING_CAPITAL, REFILL_THRESHOLD,
    NSE_HOLIDAYS, EVENT_DAYS,
)

ROOT_DIR  = CRON_DIR.parent
DATA_DIR  = ROOT_DIR / 'backtesting_2024_options' / '2024'
NIFTY_DIR = DATA_DIR / '2024Nifty'
OUT_DIR   = CRON_DIR / 'backtest_results'
OUT_DIR.mkdir(parents=True, exist_ok=True)

MONTH_ABBR = ['JAN','FEB','MAR','APR','MAY','JUN',
              'JUL','AUG','SEP','OCT','NOV','DEC']

ENTRY_TIME = '09:25'
EXIT_TIME  = '11:15'


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def dmy(d: date) -> str:
    """Convert date to DDMMMYY format used in option file names (e.g. 01APR24)."""
    return f"{d.day:02d}{MONTH_ABBR[d.month-1]}{str(d.year)[2:]}"


def load_expiry_schedule() -> list[date]:
    """Load list of expiry dates from expiry.csv."""
    path = DATA_DIR / 'expiry.csv'
    df   = pd.read_csv(path)
    col  = df.columns[0]
    expiries = []
    for s in df[col].dropna():
        s = str(s).strip()
        try:
            day = int(s[:2])
            mon = MONTH_ABBR.index(s[2:5].upper()) + 1
            yr  = int(s[5:]) + 2000
            expiries.append(date(yr, mon, day))
        except Exception:
            pass
    return sorted(expiries)


def nearest_expiry(trade_date: date, expiries: list[date]) -> date | None:
    """Return the nearest expiry >= trade_date."""
    for exp in expiries:
        if exp >= trade_date:
            return exp
    return None


def load_nifty_spot() -> pd.DataFrame:
    """Load and concatenate all monthly NIFTY 1-min spot files."""
    frames = []
    for mon in MONTH_ABBR:
        fpath = NIFTY_DIR / f'Nifty-2024{mon}.csv'
        if not fpath.exists():
            continue
        df = pd.read_csv(fpath, header=0,
                         names=['datetime','open','high','low','close','volume'],
                         skiprows=1)
        df['datetime'] = pd.to_datetime(df['datetime'],
                                        format='%Y-%m-%d %H:%M', errors='coerce')
        df = df.dropna(subset=['datetime'])
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No NIFTY spot files found in {NIFTY_DIR}")
    spot = pd.concat(frames, ignore_index=True).sort_values('datetime')
    spot['date'] = spot['datetime'].dt.date
    spot['time'] = spot['datetime'].dt.strftime('%H:%M')
    return spot


def load_option_file(trade_date: date, expiry: date) -> pd.DataFrame | None:
    """Load 1-min option CSV for a given trade date and expiry."""
    mon_str  = MONTH_ABBR[trade_date.month - 1]
    folder   = DATA_DIR / f'2024{mon_str}'
    filename = f'NIFTY-{dmy(expiry)}-{dmy(trade_date)}.csv'
    fpath    = folder / filename
    if not fpath.exists():
        return None
    df = pd.read_csv(fpath)
    df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]
    # Normalise column names
    if 'datetime' not in df.columns and 'time' in df.columns:
        df = df.rename(columns={'time': 'datetime'})
    df['datetime'] = df['datetime'].astype(str).str.strip().str[:5]  # HH:MM
    return df


def load_signal_dataset() -> pd.DataFrame:
    """Load v2_aligned_dataset.csv and parse dates."""
    df = pd.read_csv(ROOT_DIR / 'v2' / 'v2_aligned_dataset.csv')
    df['india_date'] = pd.to_datetime(df['india_date']).dt.date
    return df.set_index('india_date')


def load_signal_combos() -> tuple[list[str], pd.DataFrame]:
    """Load top-10 bearish combos from v2_reliable_signals.csv."""
    reliable = pd.read_csv(SIGNALS_CSV)
    top_bear = (reliable[reliable['P_Down'] > BASE_RATE]
                .sort_values('Edge_pp', ascending=False)
                .head(10)
                .reset_index(drop=True))
    return list(top_bear['Signal']), top_bear


# ══════════════════════════════════════════════════════════════════════════════
# SIGNAL COMPUTATION
# ══════════════════════════════════════════════════════════════════════════════

def row_to_signals(row: pd.Series) -> dict:
    """Convert a v2_aligned_dataset row to the binary signals dict."""
    def _f(col):
        v = row.get(col)
        return None if pd.isna(v) else float(v)

    gap        = _f('gap_pct')
    india_ret  = _f('prev_india_ret')
    sp500_ret  = _f('SP500_ret')
    sgx_ret    = _f('SGX_ret')
    dax_ret    = _f('DAX_ret')
    vix_ret    = _f('VIX_US_ret')

    return {
        'Gap Up'          : gap        is not None and gap        >  GAP_THRESHOLD,
        'Gap Up Strong'   : gap        is not None and gap        >  GAP_LARGE_THRESHOLD,
        'Gap Down'        : gap        is not None and gap        < -GAP_THRESHOLD,
        'Prev India UP'   : india_ret  is not None and india_ret  >  0,
        'Prev India DOWN' : india_ret  is not None and india_ret  <  0,
        'US UP'           : sp500_ret  is not None and sp500_ret  >  0,
        'US DOWN'         : sp500_ret  is not None and sp500_ret  <  0,
        'SGX UP'          : sgx_ret    is not None and sgx_ret    >  0,
        'SGX DOWN'        : sgx_ret    is not None and sgx_ret    <  0,
        'DAX UP'          : dax_ret    is not None and dax_ret    >  0,
        'VIX Rising'      : vix_ret    is not None and vix_ret    >  VIX_RISING_THRESHOLD,
        'VIX Falling'     : vix_ret    is not None and vix_ret    <  0,
        'VIX Spike'       : vix_ret    is not None and vix_ret    >  0.05,
    }


def first_fired_combo(signals: dict, combos: list[str]) -> str | None:
    """Return first combo that fires (all constituent signals True), else None."""
    for combo in combos:
        if all(signals.get(s.strip(), False) for s in combo.split('+')):
            return combo
    return None


# ══════════════════════════════════════════════════════════════════════════════
# TRADE SIMULATION
# ══════════════════════════════════════════════════════════════════════════════

def get_nifty_price_at(spot: pd.DataFrame, trade_date: date, time_str: str) -> float | None:
    """Get NIFTY spot price at a specific time on a given date."""
    rows = spot[(spot['date'] == trade_date) & (spot['time'] == time_str)]
    if rows.empty:
        # Fallback: nearest bar after time_str
        day_rows = spot[spot['date'] == trade_date].sort_values('time')
        after    = day_rows[day_rows['time'] >= time_str]
        if after.empty:
            return None
        return float(after.iloc[0]['open'])
    return float(rows.iloc[0]['open'])


def simulate_trade(opt_df: pd.DataFrame, strike: int, opt_type: str,
                   entry_time: str, exit_time: str,
                   sl_pct: float, tp_pct: float) -> dict | None:
    """
    Simulate a single option trade on real 1-min data.
    Uses HIGH to check TP hit, LOW to check SL hit (per-candle).
    Returns dict with entry_price, exit_price, exit_reason, exit_time_str, pnl_pts.
    """
    candles = (opt_df[(opt_df['strike_price'] == strike) &
                      (opt_df['right'].str.upper() == opt_type.upper())]
               .copy()
               .sort_values('datetime'))

    if candles.empty:
        return None

    # Entry: open of first candle at or after entry_time
    entry_candles = candles[candles['datetime'] >= entry_time]
    if entry_candles.empty:
        return None
    entry_price = float(entry_candles.iloc[0]['open'])
    if entry_price <= 0:
        return None

    sl_price = entry_price * (1 - sl_pct)
    tp_price = entry_price * (1 + tp_pct)

    exit_price  = None
    exit_reason = None
    exit_t      = None

    # Scan minute candles between entry and hard exit
    window = candles[(candles['datetime'] >= entry_time) &
                     (candles['datetime'] <= exit_time)]

    for _, row in window.iterrows():
        t    = row['datetime']
        high = float(row['high'])
        low  = float(row['low'])
        close = float(row['close'])

        # TP check (use high)
        if high >= tp_price:
            exit_price  = tp_price
            exit_reason = 'TAKE_PROFIT'
            exit_t      = t
            break

        # SL check (use low)
        if low <= sl_price:
            exit_price  = sl_price
            exit_reason = 'STOP_LOSS'
            exit_t      = t
            break

        # At or past hard exit time
        if t >= exit_time:
            exit_price  = close
            exit_reason = 'HARD_EXIT_1115'
            exit_t      = t
            break

    if exit_price is None:
        # Use close of last available candle before/at exit_time
        before = candles[candles['datetime'] <= exit_time]
        if before.empty:
            return None
        last_row    = before.iloc[-1]
        exit_price  = float(last_row['close'])
        exit_reason = 'HARD_EXIT_1115'
        exit_t      = last_row['datetime']

    return {
        'entry_price': round(entry_price, 2),
        'exit_price':  round(exit_price,  2),
        'exit_reason': exit_reason,
        'exit_time':   exit_t,
        'pnl_pts':     round(exit_price - entry_price, 2),
    }


# ══════════════════════════════════════════════════════════════════════════════
# CHARGE COMPUTATION  (identical to config.py rates)
# ══════════════════════════════════════════════════════════════════════════════

def compute_charges(entry_premium: float, exit_premium: float, lots: int) -> dict:
    """
    Full round-trip charge breakdown for NIFTY index options (Zerodha):
      Brokerage  : Rs 20 buy + Rs 20 sell = Rs 40
      STT        : 0.0625% on sell premium value (buy side = 0 for options)
      Stamp      : 0.003% on buy premium value
      Exchange   : 0.053% on total turnover (buy + sell premium)
      SEBI       : 0.0001% on total turnover
      GST        : 18% on (brokerage + exchange + SEBI)
    """
    buy_val   = entry_premium * lots * LOT_SIZE
    sell_val  = exit_premium  * lots * LOT_SIZE
    turnover  = buy_val + sell_val

    brokerage = BROKERAGE_PER_ORDER * 2          # Rs 40
    stt_sell  = STT_SELL_RATE  * sell_val
    stamp_buy = STAMP_BUY_RATE * buy_val
    exchange  = EXCHANGE_RATE  * turnover
    sebi      = SEBI_RATE      * turnover
    gst       = GST_RATE * (brokerage + exchange + sebi)
    total     = brokerage + stt_sell + stamp_buy + exchange + sebi + gst

    return {
        'brokerage': round(brokerage, 4),
        'stt_sell':  round(stt_sell,  4),
        'stamp_buy': round(stamp_buy, 4),
        'exchange':  round(exchange,  4),
        'sebi':      round(sebi,      4),
        'gst':       round(gst,       4),
        'total':     round(total,     4),
    }


def compute_lots(capital: float, entry_premium: float, dte: int) -> int:
    """Mirror cron_gap_trading lot sizing exactly."""
    cost = entry_premium * LOT_SIZE
    if cost <= 0:
        return BASE_LOTS
    lots = int(capital // cost)
    lots = max(lots, BASE_LOTS)
    lots = min(lots, MAX_LOTS)
    if dte == 0:
        lots = min(lots, DTE0_MAX_LOTS)
    return max(lots, 1)


# ══════════════════════════════════════════════════════════════════════════════
# XIRR
# ══════════════════════════════════════════════════════════════════════════════

def xirr(cash_flows: list[tuple[float, date]]) -> float | None:
    """Compute XIRR via binary search on NPV. cash_flows = [(amount, date), ...]."""
    if len(cash_flows) < 2:
        return None
    t0 = cash_flows[0][1]

    def npv(rate):
        return sum(amt / (1 + rate) ** ((d - t0).days / 365.25)
                   for amt, d in cash_flows)

    try:
        lo, hi = -0.999, 100.0
        for _ in range(400):
            mid = (lo + hi) / 2
            if npv(mid) > 0:
                lo = mid
            else:
                hi = mid
            if hi - lo < 1e-8:
                break
        result = (lo + hi) / 2
        return result if abs(result) < 99 else None
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# MAIN BACKTEST LOOP
# ══════════════════════════════════════════════════════════════════════════════

def run_backtest():
    print("=" * 70)
    print("  NIFTY Gap Strategy — Backtest on Real 2024 Options Data")
    print("  Config: entry=09:25  exit=11:15  SL=15%  TP=40%  BEARISH_ONLY")
    print("=" * 70)

    # ── Load all data ──────────────────────────────────────────────────────────
    print("\nLoading data ...", end=' ', flush=True)
    signal_data  = load_signal_dataset()
    bear_combos, bear_df = load_signal_combos()
    expiries     = load_expiry_schedule()
    spot         = load_nifty_spot()
    print("done.")

    print(f"  Signal dataset : {len(signal_data)} rows  "
          f"({signal_data.index.min()} → {signal_data.index.max()})")
    print(f"  Expiry dates   : {len(expiries)} entries")
    print(f"  NIFTY spot     : {len(spot):,} candles")
    print(f"  Bearish combos : {len(bear_combos)} (top-10 by edge)")
    print()

    # ── Only process days in 2024 that have options data ──────────────────────
    trading_days = sorted([
        d for d in signal_data.index
        if isinstance(d, date) and d.year == 2024
    ])
    print(f"  2024 dates in signal dataset: {len(trading_days)}")

    # ── Backtest loop ──────────────────────────────────────────────────────────
    capital      = float(STARTING_CAPITAL)
    peak_capital = capital
    max_dd       = 0.0
    total_refill = 0.0
    refill_count = 0
    cash_flows   = [(-capital, trading_days[0])]

    daily_log  = []
    trades     = []

    for trade_date in trading_days:
        row = signal_data.loc[trade_date]

        # Skip conditions (same as entry.py)
        skip_reason = None
        if trade_date.weekday() == 0:
            skip_reason = "Monday"
        elif trade_date in NSE_HOLIDAYS:
            skip_reason = "NSE_holiday"
        elif trade_date in EVENT_DAYS:
            skip_reason = "Event_day"

        if skip_reason:
            daily_log.append({'date': trade_date, 'status': 'SKIP',
                               'reason': skip_reason, 'capital': round(capital, 2)})
            continue

        # Compute signals
        signals     = row_to_signals(row)
        combo_fired = first_fired_combo(signals, bear_combos)

        if combo_fired is None:
            daily_log.append({'date': trade_date, 'status': 'NO_SIGNAL',
                               'reason': 'no combo fired', 'capital': round(capital, 2)})
            continue

        # Expiry + options data
        expiry = nearest_expiry(trade_date, expiries)
        if expiry is None:
            daily_log.append({'date': trade_date, 'status': 'NO_EXPIRY',
                               'reason': 'no expiry found', 'capital': round(capital, 2)})
            continue

        opt_df = load_option_file(trade_date, expiry)
        if opt_df is None:
            daily_log.append({'date': trade_date, 'status': 'NO_DATA',
                               'reason': f'options file missing for {dmy(trade_date)}',
                               'capital': round(capital, 2)})
            continue

        # NIFTY spot at 9:25 for ATM
        nifty_925 = get_nifty_price_at(spot, trade_date, ENTRY_TIME)
        if nifty_925 is None:
            # Fallback: use india_open from signal dataset
            nifty_925 = float(row.get('india_open', 0))
        if nifty_925 <= 0:
            daily_log.append({'date': trade_date, 'status': 'NO_DATA',
                               'reason': 'NIFTY spot unavailable', 'capital': round(capital, 2)})
            continue

        dte       = (expiry - trade_date).days
        atm       = round(nifty_925 / STRIKE_STEP) * STRIKE_STEP
        strike_pe = atm - STRIKE_STEP   # 1-OTM PUT (bearish)

        # Simulate trade on real 1-min data
        result = simulate_trade(opt_df, strike_pe, 'PE',
                                ENTRY_TIME, EXIT_TIME, SL_PCT, TP_PCT)

        if result is None:
            # Try ATM PE as fallback
            result = simulate_trade(opt_df, atm, 'PE',
                                    ENTRY_TIME, EXIT_TIME, SL_PCT, TP_PCT)
            if result is None:
                daily_log.append({'date': trade_date, 'status': 'NO_DATA',
                                   'reason': f'strike {strike_pe} PE not in options file',
                                   'capital': round(capital, 2)})
                continue
            strike_pe = atm  # used ATM fallback

        entry_premium = result['entry_price']
        exit_premium  = result['exit_price']
        lots          = compute_lots(capital, entry_premium, dte)
        charges       = compute_charges(entry_premium, exit_premium, lots)

        gross_pnl     = result['pnl_pts'] * lots * LOT_SIZE
        net_pnl       = gross_pnl - charges['total']
        capital      += net_pnl

        # Drawdown tracking
        if capital > peak_capital:
            peak_capital = capital
        dd = (peak_capital - capital) / peak_capital * 100 if peak_capital > 0 else 0
        if dd > max_dd:
            max_dd = dd

        # Refill check
        refilled = 0.0
        if capital < REFILL_THRESHOLD:
            refilled      = STARTING_CAPITAL - capital
            capital      += refilled
            peak_capital  = max(peak_capital, capital)
            total_refill += refilled
            refill_count += 1
            cash_flows.append((-refilled, trade_date))

        # Signal details
        active_sigs = [k for k, v in signals.items() if v]
        gap_val     = float(row.get('gap_pct', 0) or 0)
        combo_row   = bear_df[bear_df['Signal'] == combo_fired]
        p_down      = float(combo_row['P_Down'].iloc[0]) if len(combo_row) else 0

        # Record trade
        trade_rec = {
            'date':           trade_date,
            'combo':          combo_fired,
            'p_down':         p_down,
            'gap_pct':        round(gap_val, 4),
            'nifty_spot_925': round(nifty_925, 1),
            'expiry':         expiry,
            'dte':            dte,
            'atm':            atm,
            'strike':         strike_pe,
            'opt_type':       'PE',
            'entry_premium':  entry_premium,
            'exit_premium':   exit_premium,
            'exit_reason':    result['exit_reason'],
            'exit_time':      result['exit_time'],
            'lots':           lots,
            'buy_value':      round(entry_premium * lots * LOT_SIZE, 2),
            'sell_value':     round(exit_premium  * lots * LOT_SIZE, 2),
            'gross_pnl':      round(gross_pnl, 2),
            'charges_total':  charges['total'],
            'charges_brok':   charges['brokerage'],
            'charges_stt':    charges['stt_sell'],
            'charges_stamp':  charges['stamp_buy'],
            'charges_exch':   charges['exchange'],
            'charges_sebi':   charges['sebi'],
            'charges_gst':    charges['gst'],
            'net_pnl':        round(net_pnl, 2),
            'pct_return':     round(net_pnl / (capital - net_pnl) * 100, 4),
            'capital_after':  round(capital, 2),
            'refilled':       round(refilled, 2),
        }
        trades.append(trade_rec)
        daily_log.append({
            'date': trade_date, 'status': 'TRADE',
            'exit_reason': result['exit_reason'],
            'net_pnl': round(net_pnl, 2),
            'capital': round(capital, 2),
        })

    # Final cash flow
    if trades:
        cash_flows.append((capital, trades[-1]['date']))

    # ── Compile DataFrames ─────────────────────────────────────────────────────
    trades_df = pd.DataFrame(trades)
    daily_df  = pd.DataFrame(daily_log)

    # ── Summary stats ──────────────────────────────────────────────────────────
    n_trades    = len(trades_df)
    n_win       = int((trades_df['net_pnl'] > 0).sum()) if n_trades else 0
    n_sl        = int((trades_df['exit_reason'] == 'STOP_LOSS').sum()) if n_trades else 0
    n_tp        = int((trades_df['exit_reason'] == 'TAKE_PROFIT').sum()) if n_trades else 0
    n_hard      = int((trades_df['exit_reason'] == 'HARD_EXIT_1115').sum()) if n_trades else 0
    win_rate    = n_win / n_trades * 100 if n_trades else 0

    net_return  = (capital + total_refill - STARTING_CAPITAL) / STARTING_CAPITAL * 100
    days_elapsed = (trading_days[-1] - trading_days[0]).days if len(trading_days) > 1 else 365
    cagr        = ((capital + total_refill) / STARTING_CAPITAL) ** (365.25 / days_elapsed) - 1 \
                  if days_elapsed > 0 else 0

    xi = xirr(cash_flows)
    xi_str = f"{xi*100:.1f}%" if xi is not None else "N/A"

    avg_net     = float(trades_df['net_pnl'].mean()) if n_trades else 0
    avg_gross   = float(trades_df['gross_pnl'].mean()) if n_trades else 0
    avg_charges = float(trades_df['charges_total'].mean()) if n_trades else 0
    total_charges_all = float(trades_df['charges_total'].sum()) if n_trades else 0

    signal_days   = len([d for d in daily_log if d['status'] in ('TRADE', 'NO_DATA')])
    skipped_days  = len([d for d in daily_log if d['status'] == 'SKIP'])
    no_signal_days = len([d for d in daily_log if d['status'] == 'NO_SIGNAL'])

    # ── Print summary ──────────────────────────────────────────────────────────
    print("=" * 70)
    print("  BACKTEST RESULTS — 2024")
    print("=" * 70)
    print(f"  Period          : {trading_days[0]} → {trading_days[-1]}")
    print(f"  Total days      : {len(trading_days)}")
    print(f"    Skipped       : {skipped_days} (Mon/holiday/event)")
    print(f"    No signal     : {no_signal_days}")
    print(f"    Traded        : {n_trades}")
    print()
    print(f"  Signal rate     : {n_trades / (len(trading_days)-skipped_days)*100:.1f}% of eligible days")
    print(f"  Win rate        : {win_rate:.1f}%  ({n_win}/{n_trades})")
    print(f"    Take Profit   : {n_tp} trades ({n_tp/n_trades*100:.1f}%)" if n_trades else "")
    print(f"    Stop Loss     : {n_sl} trades ({n_sl/n_trades*100:.1f}%)" if n_trades else "")
    print(f"    Hard Exit     : {n_hard} trades ({n_hard/n_trades*100:.1f}%)" if n_trades else "")
    print()
    print(f"  Starting capital: Rs {STARTING_CAPITAL:>12,.2f}")
    print(f"  Final capital   : Rs {capital:>12,.2f}")
    print(f"  Total refilled  : Rs {total_refill:>12,.2f} ({refill_count} refills)")
    print(f"  Net return      : {net_return:>+.2f}%")
    print(f"  CAGR            : {cagr*100:>+.2f}%")
    print(f"  XIRR            : {xi_str}")
    print(f"  Max drawdown    : {max_dd:.1f}%")
    print()
    print(f"  Avg gross P&L/trade : Rs {avg_gross:>+,.2f}")
    print(f"  Avg charges/trade   : Rs {avg_charges:>,.2f}")
    print(f"  Avg net P&L/trade   : Rs {avg_net:>+,.2f}")
    print(f"  Total charges (all) : Rs {total_charges_all:>,.2f}")
    print()
    if n_trades:
        print("  Charge breakdown (avg per trade):")
        print(f"    Brokerage : Rs {trades_df['charges_brok'].mean():>8.2f}")
        print(f"    STT sell  : Rs {trades_df['charges_stt'].mean():>8.2f}")
        print(f"    Stamp buy : Rs {trades_df['charges_stamp'].mean():>8.2f}")
        print(f"    Exchange  : Rs {trades_df['charges_exch'].mean():>8.2f}")
        print(f"    SEBI      : Rs {trades_df['charges_sebi'].mean():>8.4f}")
        print(f"    GST       : Rs {trades_df['charges_gst'].mean():>8.2f}")
    print("=" * 70)

    # ── Save outputs ───────────────────────────────────────────────────────────
    trades_path = OUT_DIR / 'trades.csv'
    daily_path  = OUT_DIR / 'daily_log.csv'
    summary_path = OUT_DIR / 'summary.txt'

    trades_df.to_csv(trades_path, index=False)
    daily_df.to_csv(daily_path,  index=False)

    summary_lines = [
        "NIFTY Gap Strategy — Backtest Summary (Real 2024 Options Data)",
        "=" * 60,
        f"Period          : {trading_days[0]} to {trading_days[-1]}",
        f"Config          : entry=09:25  exit=11:15  SL={SL_PCT:.0%}  TP={TP_PCT:.0%}",
        f"Mode            : {SIGNAL_MODE}  (top-10 bearish combos)",
        "",
        "DAYS",
        f"  Total 2024 days  : {len(trading_days)}",
        f"  Skipped          : {skipped_days}",
        f"  No signal        : {no_signal_days}",
        f"  Traded           : {n_trades}",
        f"  Signal rate      : {n_trades/(len(trading_days)-skipped_days)*100:.1f}% of eligible days",
        "",
        "PERFORMANCE",
        f"  Win rate         : {win_rate:.1f}%  ({n_win}/{n_trades})",
        f"  Take Profit hits : {n_tp}  ({n_tp/n_trades*100:.1f}%)" if n_trades else "",
        f"  Stop Loss hits   : {n_sl}  ({n_sl/n_trades*100:.1f}%)" if n_trades else "",
        f"  Hard exits       : {n_hard}  ({n_hard/n_trades*100:.1f}%)" if n_trades else "",
        f"  Starting capital : Rs {STARTING_CAPITAL:,.2f}",
        f"  Final capital    : Rs {capital:,.2f}",
        f"  Total refilled   : Rs {total_refill:,.2f}  ({refill_count} refills)",
        f"  Net return       : {net_return:+.2f}%",
        f"  CAGR             : {cagr*100:+.2f}%",
        f"  XIRR             : {xi_str}",
        f"  Max drawdown     : {max_dd:.1f}%",
        "",
        "P&L (per trade averages)",
        f"  Avg gross P&L    : Rs {avg_gross:+,.2f}",
        f"  Avg charges      : Rs {avg_charges:,.2f}",
        f"  Avg net P&L      : Rs {avg_net:+,.2f}",
        f"  Total charges    : Rs {total_charges_all:,.2f}",
        "",
        "CHARGE BREAKDOWN (avg per trade)",
        f"  Brokerage : Rs {trades_df['charges_brok'].mean():.2f}"  if n_trades else "",
        f"  STT sell  : Rs {trades_df['charges_stt'].mean():.2f}"   if n_trades else "",
        f"  Stamp buy : Rs {trades_df['charges_stamp'].mean():.4f}" if n_trades else "",
        f"  Exchange  : Rs {trades_df['charges_exch'].mean():.2f}"  if n_trades else "",
        f"  SEBI      : Rs {trades_df['charges_sebi'].mean():.4f}"  if n_trades else "",
        f"  GST       : Rs {trades_df['charges_gst'].mean():.2f}"   if n_trades else "",
        "",
        "OUTPUTS",
        f"  trades.csv   : {len(trades_df)} rows",
        f"  daily_log.csv: {len(daily_df)} rows",
    ]

    with open(summary_path, 'w') as f:
        f.write('\n'.join(summary_lines))

    print(f"\n  Outputs saved to: {OUT_DIR}")
    print(f"    trades.csv    ({len(trades_df)} trades)")
    print(f"    daily_log.csv ({len(daily_df)} days)")
    print(f"    summary.txt")

    return trades_df, daily_df


if __name__ == '__main__':
    run_backtest()
