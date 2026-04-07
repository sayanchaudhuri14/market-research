"""
scripts/compute_signal.py
─────────────────────────
Compute today's ranked buy list from cached OHLC data.

Usage:
    python scripts/compute_signal.py
    python scripts/compute_signal.py --date 2026-04-07
"""

import sys
import argparse
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from config import (
    NIFTY50_SYMBOLS,
    LOOKBACK_SESSIONS,
    TOP_N,
    CAPITAL,
    WEIGHT_PER_STOCK,
    SKIP_DATES,
    US_FILTER,
)
from utils import (
    get_kite_session,
    load_all_ohlc,
    compute_overnight_returns,
    compute_scores,
    rank_stocks,
    check_us_filter,
    check_vix_filter,
)


def run_signal(target_date: str = None, kite=None):
    """
    Compute and print the buy list for target_date (default: today).
    Returns (buy_list, scores_df, ohlc_dict, signal_date) or None if filtered out.
    """
    # Determine signal date
    if target_date:
        signal_date = pd.Timestamp(target_date)
    else:
        signal_date = pd.Timestamp(date.today())

    date_str = signal_date.strftime("%Y-%m-%d")

    print(f"\n{'='*60}")
    print(f"  OVERNIGHT DRIFT SIGNAL — {date_str}")
    print(f"{'='*60}")

    # ── Skip rule: hard-coded dates ─────────────────────────────────────────
    if date_str in SKIP_DATES:
        print(f"\nSKIP: {date_str} is in SKIP_DATES (event day).")
        return None

    # ── US market filter ────────────────────────────────────────────────────
    us_pass, us_ret = check_us_filter(date_str)
    us_label = f"S&P 500 prev: {us_ret:+.2%}" if not pd.isna(us_ret) else "S&P 500: N/A"
    us_icon  = "✓" if us_pass else "✗"

    if US_FILTER and not us_pass:
        print(f"\nFilter: {us_label} {us_icon}")
        print(f"\nSKIP: S&P 500 previous close was negative ({us_ret:+.2%}).")
        return None

    # ── India VIX filter ────────────────────────────────────────────────────
    vix_pass = True
    vix_val  = float("nan")
    vix_label = "VIX: N/A"
    vix_icon  = "?"

    if kite is not None:
        try:
            vix_pass, vix_val = check_vix_filter(kite)
            vix_label = f"India VIX: {vix_val:.1f}"
            vix_icon  = "✓" if vix_pass else "✗"
        except Exception as e:
            print(f"  (VIX check failed: {e} — proceeding)")

    if not vix_pass:
        print(f"\nFilter: {us_label} {us_icon} | {vix_label} {vix_icon}")
        print(f"\nSKIP: India VIX ({vix_val:.1f}) exceeds maximum ({20}).")
        return None

    print(f"\nFilter: {us_label} {us_icon} | {vix_label} {vix_icon}")

    # ── Load data and compute signal ────────────────────────────────────────
    ohlc_dict = load_all_ohlc(NIFTY50_SYMBOLS)
    overnight_df = compute_overnight_returns(ohlc_dict)
    scores_df    = compute_scores(overnight_df, lookback=LOOKBACK_SESSIONS)

    # Use the latest available date on or before signal_date
    available = scores_df.index[scores_df.index <= signal_date]
    if available.empty:
        print(f"\nERROR: No score data available on or before {date_str}.")
        return None

    latest = available[-1]
    if latest != signal_date:
        print(f"  (Note: using latest available date {latest.date()} for signal)")

    try:
        buy_list = rank_stocks(scores_df, latest, top_n=TOP_N)
    except KeyError as e:
        print(f"\nERROR: {e}")
        return None

    # ── Build output table ──────────────────────────────────────────────────
    scores_row = scores_df.loc[latest]

    # Get prev close prices
    prev_close_date = overnight_df.index[overnight_df.index <= latest]
    prev_close_date = prev_close_date[-1] if not prev_close_date.empty else latest

    close_prices = {}
    for sym in buy_list:
        df = ohlc_dict.get(sym)
        if df is not None:
            avail = df.index[df.index <= prev_close_date]
            if not avail.empty:
                close_prices[sym] = df.loc[avail[-1], "close"]

    # Print buy list
    print(f"\nBUY LIST (enter at 3:20–3:25 PM):")
    print(f"{'Rank':<6} {'Symbol':<14} {'Score':>8}  {'Prev Close':>12}  {'Rs Allocation':>14}")
    print("-" * 60)

    for i, sym in enumerate(buy_list, 1):
        score = scores_row.get(sym, float("nan"))
        prev_close = close_prices.get(sym, float("nan"))
        alloc = WEIGHT_PER_STOCK
        score_str = f"{score:+.4%}" if not pd.isna(score) else "N/A"
        close_str = f"{prev_close:,.2f}" if not pd.isna(prev_close) else "N/A"
        print(f"{i:<6} {sym:<14} {score_str:>8}  {close_str:>12}  {alloc:>14,.0f}")

    print(f"\nTotal capital to deploy: Rs {CAPITAL:,.0f}")
    print(f"Order type: CNC (delivery) — free brokerage on Zerodha")
    print(f"Exit: sell at 9:25 AM next trading morning")

    return buy_list, scores_df, ohlc_dict, latest


def main(target_date: str = None, authenticate: bool = True):
    kite = None
    if authenticate:
        try:
            kite = get_kite_session()
        except Exception as e:
            print(f"  (Kite auth skipped for VIX check: {e})")

    result = run_signal(target_date=target_date, kite=kite)

    if result is None:
        print("\n→ No trade today.")
    else:
        print("\n→ Ready to trade. Place orders manually on Zerodha Kite.")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute overnight drift buy signal.")
    parser.add_argument("--date", dest="target_date", default=None,
                        help="Signal date YYYY-MM-DD (default: today)")
    parser.add_argument("--no-auth", dest="no_auth", action="store_true",
                        help="Skip Kite authentication (no VIX filter)")
    args = parser.parse_args()

    main(target_date=args.target_date, authenticate=not args.no_auth)
