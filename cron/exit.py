#!/usr/bin/env python3
"""
exit.py — Paper trading exit/monitor script for NIFTY gap strategy.
Runs at 9:27 AM IST Tue–Fri (2 min after entry.py) via cron.

What it does:
  1. Reads positions.json written by entry.py
  2. Polls NSE option chain every 2 minutes for current premium
  3. Exits early if SL or TP is hit (thresholds from config.py)
  4. Hard exits at 11:15 AM if SL/TP not triggered
  5. Computes full P&L with all charges (sell side + entry charges)
  6. Updates state.json (compounding capital), clears positions.json
  7. Appends SELL/NO_POSITION event to trade_log.jsonl

Runtime: ~110 minutes (9:27 AM → 11:15 AM)

Cron entry (EC2, Asia/Kolkata timezone):
  27 9 * * 2-5  python3 /path/to/cron_gap_trading/exit.py >> /path/logs/exit.log 2>&1
"""

import datetime
import json
import os
import sys
import tempfile
import time
import traceback
from typing import Optional

import pytz
import requests

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    STARTING_CAPITAL,
    STATE_FILE, POSITIONS_FILE, LOG_FILE, LOCK_FILE,
    SL_PCT, TP_PCT,
    EXIT_HR, EXIT_MIN,
    POLL_INTERVAL_SEC,
    LOT_SIZE,
    BROKERAGE_PER_ORDER, STT_SELL_RATE, EXCHANGE_RATE, SEBI_RATE, GST_RATE,
)

IST = pytz.timezone('Asia/Kolkata')

NSE_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.nseindia.com/',
    'Connection': 'keep-alive',
}


# ── Utility ────────────────────────────────────────────────────────────────────

def now_ist() -> datetime.datetime:
    return datetime.datetime.now(IST)

def today_str() -> str:
    return now_ist().strftime('%Y-%m-%d')

def atomic_write_json(path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=str(path.parent), delete=False, suffix='.tmp') as f:
        json.dump(data, f, indent=2)
        tmp = f.name
    os.replace(tmp, str(path))

def append_log(event: str, payload: dict):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": now_ist().isoformat(), "date": today_str(),
              "script": "exit", "event": event}
    record.update(payload)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, default=str) + '\n')
        f.flush()
        os.fsync(f.fileno())

def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"capital": STARTING_CAPITAL, "cumulative_pnl": 0.0, "trade_count": 0}


# ── NSE option chain ───────────────────────────────────────────────────────────

def get_nse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(NSE_HEADERS)
    session.get('https://www.nseindia.com', timeout=15)
    time.sleep(1)
    return session

def fetch_current_premium(session: requests.Session,
                          strike: int, expiry_str: str, opt_type: str) -> Optional[float]:
    """Fetch current LTP for the position's option from NSE."""
    url = 'https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY'
    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        for row in data['records']['data']:
            if (row.get('strikePrice') == strike
                    and row.get('expiryDate', '').strip() == expiry_str):
                opt_data = row.get(opt_type, {})
                ltp = opt_data.get('lastPrice')
                if ltp is not None and ltp > 0:
                    return float(ltp)
        return None
    except Exception as e:
        print(f"  [warn] Premium fetch failed: {e}")
        return None


# ── Charge computation (sell side) ────────────────────────────────────────────

def compute_exit_charges(exit_premium: float, lots: int) -> float:
    """
    Sell-side charges for options:
      - Brokerage (sell order): Rs 20
      - STT sell: 0.0625% of sell premium value
      - Exchange (sell side): 0.053% of sell value
      - SEBI: 0.0001% of sell value
      - GST: 18% on (brokerage + exchange + SEBI)
    No stamp duty on sell side.
    """
    sell_value = exit_premium * lots * LOT_SIZE
    brokerage  = BROKERAGE_PER_ORDER
    stt_sell   = STT_SELL_RATE * sell_value
    exchange   = EXCHANGE_RATE * sell_value
    sebi       = SEBI_RATE     * sell_value
    gst        = GST_RATE * (brokerage + exchange + sebi)
    return round(brokerage + stt_sell + exchange + sebi + gst, 4)


# ── Capital update ─────────────────────────────────────────────────────────────

def close_trade(pos: dict, exit_premium: float, exit_reason: str):
    """
    Compute full P&L, update state.json, clear positions.json, log SELL event.
    """
    lots          = pos['lots']
    entry_premium = pos['entry_premium']
    charges_entry = pos['charges_entry']
    capital_at_entry = pos['capital_at_entry']

    buy_value  = entry_premium * lots * LOT_SIZE
    sell_value = exit_premium  * lots * LOT_SIZE

    gross_pnl     = (exit_premium - entry_premium) * lots * LOT_SIZE
    charges_exit  = compute_exit_charges(exit_premium, lots)
    total_charges = charges_entry + charges_exit
    net_pnl       = gross_pnl - total_charges

    state         = load_state()
    old_cum       = float(state.get('cumulative_pnl', 0.0))
    old_count     = int(state.get('trade_count', 0))
    new_capital   = capital_at_entry + net_pnl
    new_cum       = old_cum + net_pnl
    new_count     = old_count + 1

    # Handle refill logging (capital tracking: record if refill would be triggered)
    from config import REFILL_THRESHOLD, STARTING_CAPITAL
    refilled = 0.0
    if new_capital < REFILL_THRESHOLD:
        refilled  = STARTING_CAPITAL - new_capital
        new_capital += refilled
        print(f"\n  *** REFILL TRIGGERED — capital Rs {new_capital - refilled:,.2f} "
              f"< threshold Rs {REFILL_THRESHOLD:,.0f} ***")
        print(f"  *** Adding Rs {refilled:,.2f} → new capital Rs {new_capital:,.2f} ***")

    atomic_write_json(STATE_FILE, {
        "capital":        round(new_capital, 4),
        "last_updated":   today_str(),
        "cumulative_pnl": round(new_cum, 4),
        "trade_count":    new_count,
        "total_refilled": round(float(state.get('total_refilled', 0.0)) + refilled, 4),
    })

    atomic_write_json(POSITIONS_FILE, {
        "status":       "cleared",
        "trade_date":   pos['trade_date'],
        "cleared_date": today_str(),
        "exit_reason":  exit_reason,
    })

    pct = net_pnl / capital_at_entry * 100 if capital_at_entry else 0
    append_log("SELL", {
        "trade_date":     pos['trade_date'],
        "combo":          pos['combo'],
        "strike":         pos['strike'],
        "expiry":         pos['expiry_str'],
        "dte":            pos['dte'],
        "lots":           lots,
        "entry_premium":  round(entry_premium, 2),
        "exit_premium":   round(exit_premium, 2),
        "exit_reason":    exit_reason,
        "buy_value":      round(buy_value, 2),
        "sell_value":     round(sell_value, 2),
        "gross_pnl":      round(gross_pnl, 4),
        "charges_entry":  round(charges_entry, 4),
        "charges_exit":   round(charges_exit, 4),
        "total_charges":  round(total_charges, 4),
        "net_pnl":        round(net_pnl, 4),
        "pct_return":     round(pct, 4),
        "capital_before": round(capital_at_entry, 2),
        "capital_after":  round(new_capital, 2),
        "cumulative_pnl": round(new_cum, 4),
        "trade_count":    new_count,
        "refilled":       round(refilled, 2),
    })

    # Print summary
    sign = "+" if net_pnl >= 0 else ""
    print(f"\n  EXIT — {exit_reason}")
    print(f"  Premium  : Rs {entry_premium:.2f}  →  Rs {exit_premium:.2f}")
    print(f"  Gross P&L: Rs {gross_pnl:>+,.2f}")
    print(f"  Charges  : Rs {total_charges:>,.2f}  "
          f"(entry {charges_entry:.2f} + exit {charges_exit:.2f})")
    print(f"  Net P&L  : Rs {net_pnl:>+,.2f}  ({pct:+.4f}%)")
    print(f"  Capital  : Rs {capital_at_entry:>,.2f}  →  Rs {new_capital:>,.2f}")
    print(f"  Cumulative P&L: Rs {new_cum:>+,.2f}  (trade #{new_count})")


# ── Main monitoring loop ───────────────────────────────────────────────────────

def main():
    # Lockfile guard — prevent duplicate runs
    if LOCK_FILE.exists():
        print("LOCK exists — exit.py already running. Exiting.")
        sys.exit(0)

    try:
        LOCK_FILE.write_text(now_ist().isoformat())
    except Exception:
        pass

    try:
        _run()
    finally:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()


def _run():
    # 1. Load positions
    if not POSITIONS_FILE.exists():
        append_log("NO_POSITION", {"reason": "positions.json not found — entry.py may have skipped"})
        print("NO_POSITION — nothing to monitor.")
        return

    with open(POSITIONS_FILE) as f:
        pos = json.load(f)

    if pos.get("status") == "cleared":
        print(f"NO_POSITION — already cleared ({pos.get('cleared_date')}).")
        return

    strike     = pos['strike']
    expiry_str = pos['expiry_str']
    opt_type   = pos['opt_type']
    entry_prem = pos['entry_premium']
    sl_price   = pos['sl_price']
    tp_price   = pos['tp_price']
    lots       = pos['lots']

    print(f"\nMonitoring {pos['opt_type']} {pos['strike']} exp={expiry_str}"
          f" | Entry={entry_prem:.2f}  SL={sl_price:.2f}  TP={tp_price:.2f}"
          f" | Lots={lots}")

    # 2. Init NSE session
    print("Connecting to NSE ...", end=' ', flush=True)
    session = get_nse_session()
    print("done.")

    hard_exit_time = now_ist().replace(
        hour=EXIT_HR, minute=EXIT_MIN, second=0, microsecond=0
    )

    poll_count = 0
    while True:
        current_time = now_ist()

        # Hard exit check
        if current_time >= hard_exit_time:
            prem = fetch_current_premium(session, strike, expiry_str, opt_type)
            if prem is None:
                prem = entry_prem  # fallback: flat
                print("  [warn] Could not fetch exit price — using entry price as fallback")
            close_trade(pos, prem, "HARD_EXIT_1115")
            return

        # Fetch current premium
        prem = fetch_current_premium(session, strike, expiry_str, opt_type)
        poll_count += 1

        if prem is not None:
            pct_chg = (prem - entry_prem) / entry_prem * 100
            print(f"  [{current_time.strftime('%H:%M:%S')}]  premium={prem:.2f}"
                  f"  chg={pct_chg:>+.1f}%  "
                  f"(SL={sl_price:.2f}  TP={tp_price:.2f})")

            if prem <= sl_price:
                close_trade(pos, prem, f"STOP_LOSS_{pct_chg:+.1f}%")
                return

            if prem >= tp_price:
                close_trade(pos, prem, f"TAKE_PROFIT_{pct_chg:+.1f}%")
                return
        else:
            print(f"  [{current_time.strftime('%H:%M:%S')}]  premium fetch failed — retrying next poll")

            # Re-init session if repeated failures
            if poll_count % 5 == 0:
                try:
                    session = get_nse_session()
                except Exception:
                    pass

        # Wait for next poll (but wake up 10s before hard exit)
        sleep_until = min(
            current_time.timestamp() + POLL_INTERVAL_SEC,
            hard_exit_time.timestamp() - 10,
        )
        sleep_secs = max(0, sleep_until - now_ist().timestamp())
        if sleep_secs > 0:
            time.sleep(sleep_secs)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        # Ensure lockfile is removed on crash
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
        append_log("ERROR", {"error": str(e), "traceback": traceback.format_exc()})
        print(f"ERROR: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
