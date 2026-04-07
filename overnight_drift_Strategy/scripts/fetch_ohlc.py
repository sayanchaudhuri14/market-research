"""
scripts/fetch_ohlc.py
─────────────────────
Fetch and cache daily OHLC for all 50 NIFTY stocks from Kite.

Run once to bootstrap 5 years of history, then daily for incremental updates.

Usage:
    python scripts/fetch_ohlc.py
    python scripts/fetch_ohlc.py --from 2021-04-01 --to 2026-04-06
"""

import sys
import time
import argparse
from datetime import date
from pathlib import Path

# Allow imports from strategy root
sys.path.insert(0, str(Path(__file__).parent.parent))

from tqdm import tqdm

from config import (
    HISTORY_FROM,
    KITE_RATE_LIMIT_SLEEP,
)
from utils import get_kite_session, get_nifty50_instruments, fetch_daily_ohlc, _cache_path


def main(from_date: str, to_date: str):
    print("Authenticating with Kite...")
    kite = get_kite_session()

    print("Loading NIFTY 50 instrument tokens...")
    instruments = get_nifty50_instruments()
    symbols = list(instruments.keys())
    print(f"  {len(symbols)} symbols loaded.\n")

    results = []

    for sym in tqdm(symbols, desc="Fetching OHLC", unit="stock"):
        token = instruments[sym]
        try:
            df = fetch_daily_ohlc(
                kite=kite,
                instrument_token=token,
                symbol=sym,
                from_date=from_date,
                to_date=to_date,
            )
            date_min = df["date"].min().strftime("%Y-%m-%d") if not df.empty else "N/A"
            date_max = df["date"].max().strftime("%Y-%m-%d") if not df.empty else "N/A"
            results.append((sym, date_min, date_max, len(df), "OK"))
        except Exception as e:
            results.append((sym, "ERROR", "ERROR", 0, str(e)))

        time.sleep(KITE_RATE_LIMIT_SLEEP)

    # Summary
    print("\n=== OHLC Fetch Summary ===")
    print(f"{'Symbol':<14} {'From':<12} {'To':<12} {'Rows':>6}  {'Status'}")
    print("-" * 60)
    errors = []
    for sym, d_min, d_max, rows, status in results:
        flag = "" if status == "OK" else f"  ← {status}"
        print(f"{sym:<14} {d_min:<12} {d_max:<12} {rows:>6}  {status}{flag}")
        if status != "OK":
            errors.append(sym)

    print(f"\nCompleted: {len(results) - len(errors)}/{len(results)} symbols.")
    if errors:
        print(f"Errors ({len(errors)}): {', '.join(errors)}")
        print("Re-run to retry failed symbols.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch NIFTY 50 daily OHLC from Kite.")
    parser.add_argument("--from", dest="from_date", default=HISTORY_FROM,
                        help=f"Start date YYYY-MM-DD (default: {HISTORY_FROM})")
    parser.add_argument("--to", dest="to_date", default=date.today().isoformat(),
                        help="End date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    main(from_date=args.from_date, to_date=args.to_date)
