#!/usr/bin/env python3
"""
sell.py — Paper trading sell script.
Runs at 9:30 AM IST Mon–Fri via cron (fetches 9:25 AM open price).

What it does:
  1. Loads positions.json written by buy.py
  2. Fetches current open prices via yfinance (1-min intraday, first bar ≥ 9:25 AM IST)
  3. Simulates selling all positions, applies sell-side charges
  4. Updates state.json with compounded capital
  5. Clears positions.json + appends to logs/trade_log.jsonl

Note: Runs Mon–Fri. Friday buy → positions persist over weekend → Monday sell
      correctly captures the Friday-close → Monday-open overnight gap.

Cron entry (EC2, Asia/Kolkata timezone):
  30 9 * * 1-5  /usr/bin/python3 /path/to/cron/sell.py
"""

import datetime
import json
import os
import sys
import tempfile
import traceback

import pandas as pd
import pytz
import yfinance as yf

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    STARTING_CAPITAL, TOP_N,
    STT_SELL_RATE, EXCHANGE_RATE, IPFT_RATE, SEBI_RATE, GST_RATE, FLAT_COST,
    STATE_FILE, POSITIONS_FILE, LOG_FILE,
)

IST = pytz.timezone('Asia/Kolkata')


# ── Utility ────────────────────────────────────────────────────────────────────

def now_ist() -> str:
    return datetime.datetime.now(IST).isoformat()

def today_str() -> str:
    return datetime.datetime.now(IST).strftime('%Y-%m-%d')

def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).replace('.NS', '').replace('%26', '&') for c in df.columns]
    return df

def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"capital": STARTING_CAPITAL, "cumulative_pnl": 0.0, "trade_count": 0}

def atomic_write_json(path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=str(path.parent), delete=False, suffix='.tmp') as f:
        json.dump(data, f, indent=2)
        tmp = f.name
    os.replace(tmp, str(path))

def append_log(event: str, payload: dict):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": now_ist(), "date": today_str(), "script": "sell", "event": event}
    record.update(payload)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, default=str) + '\n')
        f.flush()
        os.fsync(f.fileno())


# ── Sell price fetch ───────────────────────────────────────────────────────────

def fetch_sell_prices(symbols: list) -> dict:
    """
    Fetch open price of first 1-min bar at or after 9:25 AM IST.
    This simulates selling at the 9:25 AM market price (same as backtest's daily open).
    sell.py runs at 9:30 AM so the 9:25 bar is already available.
    """
    ns_tickers = [s.replace('&', '%26') + '.NS' for s in symbols]
    raw = yf.download(ns_tickers, period='1d', interval='1m',
                      progress=False, auto_adjust=True)

    if raw.empty:
        return {}

    opens = raw['Open']
    if isinstance(opens.columns, pd.MultiIndex):
        opens.columns = opens.columns.droplevel(0)
    opens = clean(opens)

    # Convert to IST
    if opens.index.tz is None:
        opens.index = opens.index.tz_localize('UTC')
    opens.index = opens.index.tz_convert(IST)

    # First bar at or after 9:25 AM
    mask = opens.index.time >= datetime.time(9, 25)
    if mask.sum() == 0:
        # Fallback: first available bar (market just opened)
        mask = pd.Series([True] * len(opens), index=opens.index)
        print("  [warn] No bar found at 9:25 AM — using earliest available bar")

    row = opens[mask].iloc[0]
    bar_time = opens[mask].index[0].strftime('%H:%M:%S')
    print(f"  Sell price bar: {bar_time} IST")

    return {sym: float(row[sym]) for sym in symbols
            if sym in row.index and not pd.isna(row.get(sym))}


# ── Sell-side charge computation ───────────────────────────────────────────────

def compute_sell_charges(total_sell_value: float) -> float:
    """
    Sell-side charges:
      - STT sell:          0.10% of total sell value
      - Exchange+IPFT+SEBI+GST (sell side): ~0.0035% of sell value
      - DP flat:           Rs 153.40 (Zerodha CDSL, 10 scrips × Rs 13 + GST)
    """
    stt_sell   = STT_SELL_RATE * total_sell_value
    exch_side  = (EXCHANGE_RATE + IPFT_RATE + SEBI_RATE) * (1 + GST_RATE) * total_sell_value
    dp         = FLAT_COST   # Rs 153.40 flat
    return stt_sell + exch_side + dp


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    # 1. Load positions
    if not POSITIONS_FILE.exists():
        append_log("NO_POSITIONS", {"reason": "positions.json missing — buy.py may have skipped"})
        print("NO_POSITIONS — nothing to sell today.")
        return

    with open(POSITIONS_FILE) as f:
        pos_data = json.load(f)

    # Already cleared guard
    if pos_data.get("status") == "cleared":
        cleared_on = pos_data.get("cleared_date", "unknown")
        append_log("NO_POSITIONS", {
            "reason": f"Positions already cleared on {cleared_on} — idempotent exit"
        })
        print(f"NO_POSITIONS — already sold (cleared on {cleared_on}).")
        return

    buy_date       = pos_data["buy_date"]
    capital_at_buy = float(pos_data["capital_at_buy"])
    charges_buy    = float(pos_data["charges_buy"])
    positions      = pos_data["positions"]

    # Same-day guard: CNC cannot be sold intraday
    if buy_date == today_str():
        append_log("SKIP", {
            "reason":   "buy_date == today — CNC positions cannot be sold intraday",
            "buy_date": buy_date,
        })
        print(f"SKIP — buy_date is today ({buy_date}). Cannot sell CNC same day.")
        return

    symbols = [p["symbol"] for p in positions if p.get("qty", 0) > 0]
    if not symbols:
        append_log("NO_POSITIONS", {"reason": "All positions have qty=0 (buy prices were unavailable)"})
        print("NO_POSITIONS — all positions have qty=0.")
        return

    print(f"\nSELL — {today_str()}  (bought {buy_date})")

    # 2. Fetch sell prices (9:25 AM 1-min bar open)
    sell_prices = fetch_sell_prices(symbols)

    # 3. Compute per-stock P&L
    stock_results    = []
    total_sell_value = 0.0
    gross_pnl        = 0.0

    for p in positions:
        sym       = p["symbol"]
        qty       = p.get("qty", 0)
        buy_price = p.get("buy_price")

        if qty == 0 or buy_price is None:
            stock_results.append({**p, "sell_price": None, "sell_value": 0.0, "pnl": 0.0})
            continue

        sell_price = sell_prices.get(sym)
        if sell_price is None or sell_price <= 0:
            # Price unavailable: assume flat (no gain/loss for this stock)
            sell_price = buy_price
            note = "price unavailable — assumed flat"
        else:
            note = None

        sell_val = qty * sell_price
        pnl      = (sell_price - buy_price) * qty
        total_sell_value += sell_val
        gross_pnl        += pnl

        result = {
            "symbol":     sym,
            "qty":        qty,
            "buy_price":  round(buy_price, 4),
            "sell_price": round(sell_price, 4),
            "sell_value": round(sell_val, 2),
            "pnl":        round(pnl, 2),
            "pct_return": round((sell_price - buy_price) / buy_price, 6),
        }
        if note:
            result["note"] = note
        stock_results.append(result)

    # 4. Sell-side charges
    charges_sell   = compute_sell_charges(total_sell_value)
    total_charges  = charges_buy + charges_sell

    # 5. Net P&L
    net_pnl = gross_pnl - total_charges

    # 6. Update compounding capital
    state          = load_state()
    old_cumulative = float(state.get("cumulative_pnl", 0.0))
    old_count      = int(state.get("trade_count", 0))
    new_capital    = capital_at_buy + net_pnl
    new_cumulative = old_cumulative + net_pnl
    new_count      = old_count + 1

    atomic_write_json(STATE_FILE, {
        "capital":        round(new_capital, 4),
        "last_updated":   today_str(),
        "cumulative_pnl": round(new_cumulative, 4),
        "trade_count":    new_count,
    })

    # 7. Clear positions (mark as sold — prevents double-sell)
    atomic_write_json(POSITIONS_FILE, {
        "status":       "cleared",
        "buy_date":     buy_date,
        "cleared_date": today_str(),
    })

    # 8. Log SELL event
    pct_return = net_pnl / capital_at_buy if capital_at_buy else 0.0
    append_log("SELL", {
        "buy_date":         buy_date,
        "capital_before":   round(capital_at_buy, 2),
        "capital_after":    round(new_capital, 4),
        "gross_pnl":        round(gross_pnl, 4),
        "charges_buy":      round(charges_buy, 4),
        "charges_sell":     round(charges_sell, 4),
        "total_charges":    round(total_charges, 4),
        "net_pnl":          round(net_pnl, 4),
        "pct_return":       round(pct_return, 6),
        "cumulative_pnl":   round(new_cumulative, 4),
        "trade_count":      new_count,
        "total_sell_value": round(total_sell_value, 2),
        "stocks":           stock_results,
    })

    # 9. Print summary
    sign = "+" if net_pnl >= 0 else ""
    print(f"  Gross P&L  : Rs {gross_pnl:>+12,.2f}")
    print(f"  Charges    : Rs {total_charges:>12,.2f}  "
          f"(buy {charges_buy:.2f} + sell {charges_sell:.2f})")
    print(f"  Net P&L    : Rs {net_pnl:>+12,.2f}  ({pct_return:+.4%})")
    print(f"  Capital    : Rs {capital_at_buy:>12,.2f}  →  Rs {new_capital:>12,.2f}")
    print(f"  Cumulative : Rs {new_cumulative:>+12,.2f}  (trade #{new_count})")
    print(f"\n  {'Symbol':<14}  {'Buy':>9}  {'Sell':>9}  {'Qty':>5}  {'P&L':>10}  {'Ret%':>8}")
    print(f"  {'─'*14}  {'─'*9}  {'─'*9}  {'─'*5}  {'─'*10}  {'─'*8}")
    for r in stock_results:
        if r.get("sell_price"):
            pnl_sign = "+" if r['pnl'] >= 0 else ""
            print(f"  {r['symbol']:<14}  {r['buy_price']:>9.2f}  {r['sell_price']:>9.2f}  "
                  f"{r['qty']:>5d}  {r['pnl']:>+10.2f}  {r['pct_return']:>+8.4%}")
    print()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        append_log("ERROR", {
            "error":     str(e),
            "traceback": traceback.format_exc(),
        })
        print(f"ERROR: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
