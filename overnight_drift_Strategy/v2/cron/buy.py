#!/usr/bin/env python3
"""
buy.py — Paper trading buy script.
Runs at 3:20 PM IST Mon–Fri via cron.

What it does:
  1. Checks S&P 500 filter (prev close must be non-negative)
  2. Computes overnight momentum signal (top-10 NIFTY 50 stocks)
  3. Fetches live prices via yfinance (last 5-min bar ~ 3:20 PM)
  4. Simulates equal-weight buy, applies buy-side charges
  5. Writes positions.json + appends to logs/trade_log.jsonl

Cron entry (EC2, Asia/Kolkata timezone):
  20 15 * * 1-5  /usr/bin/python3 /path/to/cron/buy.py
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

# Import from same directory
sys.path.insert(0, os.path.dirname(__file__))
from config import (
    STARTING_CAPITAL, LOOKBACK, TOP_N, NIFTY50_YF,
    STT_BUY_RATE, STAMP_RATE, EXCHANGE_RATE, IPFT_RATE, SEBI_RATE, GST_RATE,
    STATE_FILE, POSITIONS_FILE, LOG_FILE,
)

IST = pytz.timezone('Asia/Kolkata')


# ── Utility ────────────────────────────────────────────────────────────────────

def now_ist() -> str:
    return datetime.datetime.now(IST).isoformat()

def today_str() -> str:
    return datetime.datetime.now(IST).strftime('%Y-%m-%d')

def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Strip .NS suffix and decode %26 → & in column names."""
    df = df.copy()
    df.columns = [str(c).replace('.NS', '').replace('%26', '&') for c in df.columns]
    return df

def load_capital() -> float:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return float(json.load(f)['capital'])
    return STARTING_CAPITAL

def atomic_write_json(path, data: dict):
    """Write JSON atomically via temp-file rename (safe on Linux ext4)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=str(path.parent), delete=False, suffix='.tmp') as f:
        json.dump(data, f, indent=2)
        tmp = f.name
    os.replace(tmp, str(path))

def append_log(event: str, payload: dict):
    """Append one JSON line to trade_log.jsonl. fsync ensures durability."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": now_ist(), "date": today_str(), "script": "buy", "event": event}
    record.update(payload)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, default=str) + '\n')
        f.flush()
        os.fsync(f.fileno())


# ── S&P 500 filter ─────────────────────────────────────────────────────────────

def check_sp500() -> tuple[float, str, bool]:
    """
    Returns (sp_ret, sp_date_str, pass).
    pass = True if prev S&P 500 close return >= 0.
    """
    sp = yf.download('^GSPC', period='5d', progress=False, auto_adjust=True)['Close']
    sp = sp.squeeze().dropna()

    # Keep only sessions that have already closed (before today UTC midnight)
    today_utc = pd.Timestamp.now(tz='UTC').normalize()
    if sp.index.tz is None:
        sp.index = sp.index.tz_localize('UTC')
    sp = sp[sp.index < today_utc]

    sp_ret  = float(sp.iloc[-1] / sp.iloc[-2] - 1)
    sp_date = str(sp.index[-1].date())
    return sp_ret, sp_date, sp_ret >= 0


# ── Signal computation ─────────────────────────────────────────────────────────

def compute_signal() -> tuple[list, pd.Series]:
    """
    Returns (top10_symbols, last_scores_series).
    Uses 60-day yfinance data; overnight score = rolling(20) mean of open/prev_close-1.
    """
    raw    = yf.download(NIFTY50_YF, period='60d', progress=False, auto_adjust=True)
    close  = clean(raw['Close'])
    open_  = clean(raw['Open'])

    scores = (open_ / close.shift(1) - 1).rolling(LOOKBACK, min_periods=LOOKBACK).mean()

    # Use last valid score per stock independently (handles live-day NaN in last row)
    last_scores = scores.apply(
        lambda col: col.dropna().iloc[-1] if col.notna().any() else float('nan')
    )
    last_scores = last_scores.dropna()
    top10 = last_scores.nlargest(TOP_N).index.tolist()
    return top10, last_scores


# ── Buy price fetch ────────────────────────────────────────────────────────────

def fetch_buy_prices(symbols: list) -> dict:
    """
    Fetch last 5-min bar close at or before 3:20 PM IST.
    This is the simulated buy price (market price near close).
    """
    ns_tickers = [s.replace('&', '%26') + '.NS' for s in symbols]
    raw = yf.download(ns_tickers, period='1d', interval='5m',
                      progress=False, auto_adjust=True)

    if raw.empty:
        return {}

    close = raw['Close']
    # yfinance MultiIndex: (Price, Ticker) — drop Price level
    if isinstance(close.columns, pd.MultiIndex):
        close.columns = close.columns.droplevel(0)
    close = clean(close)

    # Convert index to IST, filter up to 3:20 PM
    if close.index.tz is None:
        close.index = close.index.tz_localize('UTC')
    close.index = close.index.tz_convert(IST)

    cutoff = datetime.time(15, 20)
    filtered = close[close.index.time <= cutoff]
    if filtered.empty:
        filtered = close  # fallback: use all available bars

    last = filtered.iloc[-1]
    return {sym: float(last[sym]) for sym in symbols
            if sym in last.index and not pd.isna(last.get(sym))}


# ── Buy-side charge computation ────────────────────────────────────────────────

def compute_buy_charges(deployed: float) -> float:
    """
    Buy-side only charges (sell-side DP + STT deducted in sell.py):
      - STT buy:        0.10% of deployed value
      - Stamp duty:     0.015% of deployed value (buy-side only)
      - Exchange+IPFT+SEBI+GST (buy side): ~0.0035% of deployed
    """
    stt_buy        = STT_BUY_RATE  * deployed
    stamp          = STAMP_RATE    * deployed
    exch_side      = (EXCHANGE_RATE + IPFT_RATE + SEBI_RATE) * (1 + GST_RATE) * deployed
    return stt_buy + stamp + exch_side


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    capital = load_capital()

    # 1. S&P 500 filter
    sp_ret, sp_date, sp_pass = check_sp500()
    if not sp_pass:
        msg = f"S&P 500 ({sp_date}) returned {sp_ret:.4%} — negative close, skipping"
        append_log("SKIP", {
            "reason":   msg,
            "sp_ret":   round(sp_ret, 6),
            "sp_date":  sp_date,
            "capital":  round(capital, 2),
        })
        print(f"SKIP — {msg}")
        return

    # 2. Compute momentum signal
    top10, last_scores = compute_signal()
    if len(top10) < TOP_N:
        err = f"Signal returned only {len(top10)} stocks (need {TOP_N}) — aborting"
        append_log("ERROR", {"error": err})
        sys.exit(1)

    # 3. Fetch live buy prices (5-min intraday, last bar ≤ 3:20 PM)
    buy_prices = fetch_buy_prices(top10)

    # 4. Calculate quantities (equal weight allocation)
    alloc = capital / TOP_N
    positions      = []
    total_deployed = 0.0

    for sym in top10:
        price = buy_prices.get(sym, 0.0)
        score = round(float(last_scores.get(sym, float('nan'))), 6)
        if price <= 0:
            positions.append({
                "symbol": sym, "qty": 0,
                "buy_price": None, "buy_value": 0.0, "score": score,
                "note": "price unavailable — skipped",
            })
            continue
        qty     = int(alloc / price)
        buy_val = round(qty * price, 2)
        total_deployed += buy_val
        positions.append({
            "symbol":    sym,
            "qty":       qty,
            "buy_price": round(price, 4),
            "buy_value": buy_val,
            "score":     score,
        })

    # 5. Compute buy-side charges
    charges_buy = round(compute_buy_charges(total_deployed), 4)

    # 6. Write positions.json atomically
    pos_data = {
        "buy_date":        today_str(),
        "capital_at_buy":  round(capital, 4),
        "sp_ret":          round(sp_ret, 6),
        "sp_date":         sp_date,
        "positions":       positions,
        "total_deployed":  round(total_deployed, 2),
        "charges_buy":     charges_buy,
    }
    atomic_write_json(POSITIONS_FILE, pos_data)

    # 7. Log BUY event
    append_log("BUY", {
        "sp_ret":          round(sp_ret, 6),
        "sp_date":         sp_date,
        "capital_before":  round(capital, 2),
        "total_deployed":  round(total_deployed, 2),
        "charges_buy":     charges_buy,
        "alloc_per_stock": round(alloc, 2),
        "stocks":          positions,
    })

    # 8. Print summary
    print(f"\nBUY — {today_str()}")
    print(f"  S&P 500  : {sp_ret:+.4%} on {sp_date}  ✓ filter passed")
    print(f"  Capital  : Rs {capital:>12,.2f}")
    print(f"  Deployed : Rs {total_deployed:>12,.2f}")
    print(f"  Charges  : Rs {charges_buy:>12,.4f}  (buy-side only)")
    print(f"\n  {'#':>2}  {'Symbol':<14}  {'Score':>8}  {'Price':>9}  {'Qty':>5}  {'Value':>10}")
    print(f"  {'─'*2}  {'─'*14}  {'─'*8}  {'─'*9}  {'─'*5}  {'─'*10}")
    for i, p in enumerate(positions, 1):
        if p['qty'] > 0:
            print(f"  {i:>2}  {p['symbol']:<14}  {p['score']:>+8.4%}  "
                  f"{p['buy_price']:>9.2f}  {p['qty']:>5d}  {p['buy_value']:>10,.2f}")
        else:
            print(f"  {i:>2}  {p['symbol']:<14}  {p['score']:>+8.4%}  {'N/A':>9}  {'—':>5}  {'—':>10}")
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
