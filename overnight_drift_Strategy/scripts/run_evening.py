"""
scripts/run_evening.py
──────────────────────
Run at 3:15 PM. Generates today's buy list, saves to data/current_positions.json,
and prints buy instructions.

Usage:
    python scripts/run_evening.py
"""

import sys
import json
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from config import POSITIONS_FILE, WEIGHT_PER_STOCK, CAPITAL
from utils import get_kite_session
from scripts.compute_signal import run_signal


def main():
    print("Authenticating with Kite...")
    try:
        kite = get_kite_session()
    except Exception as e:
        print(f"  WARNING: Kite auth failed ({e}). Proceeding without live VIX check.")
        kite = None

    result = run_signal(kite=kite)

    if result is None:
        print("\nNo positions to take today. Exiting.")
        return

    buy_list, scores_df, ohlc_dict, signal_date = result

    # Build positions record
    scores_row = scores_df.loc[signal_date]
    positions = []
    for rank, sym in enumerate(buy_list, 1):
        df = ohlc_dict.get(sym)
        prev_close = None
        if df is not None:
            avail = df.index[df.index <= signal_date]
            if not avail.empty:
                prev_close = float(df.loc[avail[-1], "close"])

        qty = int(WEIGHT_PER_STOCK / prev_close) if prev_close else 0

        positions.append({
            "symbol":       sym,
            "rank":         rank,
            "signal_score": float(scores_row.get(sym, float("nan"))),
            "prev_close":   prev_close,
            "allocated_rs": WEIGHT_PER_STOCK,
            "qty":          qty,
            "entry_price":  None,   # fill manually after execution
            "date":         signal_date.strftime("%Y-%m-%d"),
        })

    # Save to JSON
    POSITIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(POSITIONS_FILE, "w") as f:
        json.dump(positions, f, indent=2)

    print(f"\nPositions saved to: {POSITIONS_FILE}")
    print("\n=== ACTION REQUIRED ===")
    print(f"Place BUY orders between 3:20–3:25 PM (CNC order type):")
    print(f"{'Rank':<6} {'Symbol':<14} {'Qty':>6}  {'~Price':>10}  {'~Rs':>10}")
    print("-" * 52)
    for p in positions:
        price_str = f"{p['prev_close']:,.2f}" if p["prev_close"] else "N/A"
        print(f"{p['rank']:<6} {p['symbol']:<14} {p['qty']:>6}  {price_str:>10}  {p['allocated_rs']:>10,.0f}")

    print(f"\nTotal: Rs {CAPITAL:,.0f} across {len(positions)} stocks")
    print(f"\nAfter filling, update entry_price in: {POSITIONS_FILE}")
    print("Run tomorrow morning at 9:25 AM: python scripts/run_morning.py")


if __name__ == "__main__":
    main()
