"""
scripts/run_morning.py
──────────────────────
Run at 9:25 AM. Fetches today's open prices for held positions,
computes realized overnight returns, prints sell instructions, and updates trade log.

Usage:
    python scripts/run_morning.py
"""

import sys
import json
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from config import POSITIONS_FILE, KITE_RATE_LIMIT_SLEEP
from utils import (
    get_kite_session,
    get_nifty50_instruments,
    compute_transaction_cost,
    append_trade_log,
    rolling_performance_check,
)


def fetch_open_prices(kite, positions: list) -> dict:
    """
    Fetch today's open price for each held symbol using kite.quote().
    Returns {symbol: open_price}.
    """
    instruments = get_nifty50_instruments()
    prices = {}

    for pos in positions:
        sym = pos["symbol"]
        token = instruments.get(sym)
        if token is None:
            print(f"  WARNING: no token for {sym}")
            continue
        try:
            quote = kite.quote([f"NSE:{sym}"])
            data = quote.get(f"NSE:{sym}", {})
            ohlc = data.get("ohlc", {})
            open_price = ohlc.get("open")
            if open_price:
                prices[sym] = float(open_price)
            else:
                # Fallback to last_price if open not yet settled
                prices[sym] = float(data.get("last_price", 0))
        except Exception as e:
            print(f"  ERROR fetching {sym}: {e}")

        time.sleep(KITE_RATE_LIMIT_SLEEP)

    return prices


def main():
    today = date.today().isoformat()

    print(f"\n{'='*60}")
    print(f"  SELL SIGNAL — {today} 09:25 AM")
    print(f"{'='*60}")

    # ── Load yesterday's positions ──────────────────────────────────────────
    if not POSITIONS_FILE.exists():
        print(f"\nERROR: No positions file found at {POSITIONS_FILE}.")
        print("Did you run run_evening.py yesterday?")
        return

    with open(POSITIONS_FILE) as f:
        positions = json.load(f)

    if not positions:
        print("\nNo positions to exit.")
        return

    held_date = positions[0].get("date", "unknown")
    print(f"\nPositions from: {held_date}")
    print(f"Symbols held:   {', '.join(p['symbol'] for p in positions)}\n")

    # ── Authenticate and fetch open prices ──────────────────────────────────
    print("Authenticating with Kite...")
    kite = get_kite_session()

    print("Fetching open prices at 9:25 AM...")
    open_prices = fetch_open_prices(kite, positions)

    # ── Compute P&L ─────────────────────────────────────────────────────────
    total_pnl      = 0.0
    total_cost     = 0.0
    total_invested = 0.0
    trade_records  = []

    print(f"\n{'Symbol':<14} {'Entry':>10} {'Exit':>10} {'Overnight':>10}  {'P&L (Rs)':>10}")
    print("-" * 62)

    for pos in positions:
        sym         = pos["symbol"]
        entry_price = pos.get("entry_price")
        qty         = pos.get("qty", 0)
        score       = pos.get("signal_score", float("nan"))
        rank        = pos.get("rank")
        exit_price  = open_prices.get(sym)

        if entry_price is None:
            print(f"{sym:<14} {'N/A':>10} {'N/A':>10}  entry_price not set in {POSITIONS_FILE}")
            continue

        if exit_price is None:
            print(f"{sym:<14} {entry_price:>10,.2f} {'N/A':>10}  could not fetch open price")
            continue

        overnight_ret = exit_price / entry_price - 1
        gross_pnl     = (exit_price - entry_price) * qty
        cost          = compute_transaction_cost(entry_price, qty)
        net_pnl       = gross_pnl - cost

        total_pnl      += net_pnl
        total_cost     += cost
        total_invested += entry_price * qty

        print(f"{sym:<14} {entry_price:>10,.2f} {exit_price:>10,.2f} {overnight_ret:>+10.2%}  {net_pnl:>+10.0f}")

        trade_records.append({
            "date":                  today,
            "symbol":                sym,
            "entry_price":           entry_price,
            "exit_price":            exit_price,
            "qty":                   qty,
            "overnight_return_pct":  overnight_ret,
            "pnl_rs":                gross_pnl,
            "transaction_cost_rs":   cost,
            "net_pnl_rs":            net_pnl,
            "signal_score":          score,
            "rank":                  rank,
            "vix_at_entry":          None,
            "us_prev_close_return":  None,
            "session_notes":         "",
        })

    print("-" * 62)
    total_return = total_pnl / total_invested if total_invested else float("nan")
    print(f"\nTOTAL NET P&L:    Rs {total_pnl:>+,.0f}")
    print(f"TOTAL RETURN:     {total_return:>+.2%}" if not pd.isna(total_return) else "TOTAL RETURN: N/A")
    print(f"Transaction costs: Rs {total_cost:,.0f}")

    # ── Update trade log ────────────────────────────────────────────────────
    if trade_records:
        append_trade_log(trade_records)

    # ── Rolling performance check ───────────────────────────────────────────
    print()
    rolling_performance_check()

    print("\n=== ACTION REQUIRED ===")
    print("Place SELL orders now (CNC, market order or limit at current price):")
    for pos in positions:
        sym = pos["symbol"]
        qty = pos.get("qty", 0)
        exit_p = open_prices.get(sym, "N/A")
        print(f"  SELL {qty:>4}  {sym:<14}  ~{exit_p}")


if __name__ == "__main__":
    main()
