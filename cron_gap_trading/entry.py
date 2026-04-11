#!/usr/bin/env python3
"""
entry.py — Paper trading entry script for NIFTY gap strategy.
Runs at 9:25 AM IST Tue–Fri via cron.

What it does:
  1. Checks skip conditions (Monday, NSE holiday, event day)
  2. Fetches overnight global market data (yfinance)
  3. Computes binary signals + matches against top-10 bearish combos
  4. Fetches NIFTY spot from NSE option chain (9:25 AM price)
  5. Gets 9:15 AM open price via yfinance 1-min data (for gap %)
  6. Determines expiry, strike (1-OTM PUT), entry premium
  7. Computes lot size based on current capital
  8. Writes positions.json + appends BUY/SKIP event to trade_log.jsonl

Cron entry (EC2, Asia/Kolkata timezone — skip Mon = days 2-5):
  25 9 * * 2-5  python3 /path/to/cron_gap_trading/entry.py >> /path/logs/cron.log 2>&1
"""

import datetime
import json
import os
import sys
import tempfile
import traceback
import time

import pandas as pd
import pytz
import requests
import yfinance as yf

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    STARTING_CAPITAL, REFILL_THRESHOLD,
    SIGNALS_CSV, STATE_FILE, POSITIONS_FILE, LOG_FILE,
    SIGNAL_MODE, BASE_RATE,
    GAP_THRESHOLD, GAP_LARGE_THRESHOLD, VIX_RISING_THRESHOLD, VIX_SPIKE_THRESHOLD,
    MAX_STALE_DAYS,
    LOT_SIZE, STRIKE_STEP, BASE_LOTS, DTE0_MAX_LOTS, MAX_LOTS,
    EXPIRY_CHANGE_DATE,
    BROKERAGE_PER_ORDER, STAMP_BUY_RATE, EXCHANGE_RATE, SEBI_RATE, GST_RATE,
    NSE_HOLIDAYS, EVENT_DAYS,
)

IST = pytz.timezone('Asia/Kolkata')


# ── Utility ────────────────────────────────────────────────────────────────────

def now_ist() -> str:
    return datetime.datetime.now(IST).isoformat()

def today_ist() -> datetime.date:
    return datetime.datetime.now(IST).date()

def today_str() -> str:
    return today_ist().strftime('%Y-%m-%d')

def atomic_write_json(path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=str(path.parent), delete=False, suffix='.tmp') as f:
        json.dump(data, f, indent=2)
        tmp = f.name
    os.replace(tmp, str(path))

def append_log(event: str, payload: dict):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": now_ist(), "date": today_str(), "script": "entry", "event": event}
    record.update(payload)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, default=str) + '\n')
        f.flush()
        os.fsync(f.fileno())

def load_capital() -> float:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return float(json.load(f)['capital'])
    return STARTING_CAPITAL


# ── Skip day checks ────────────────────────────────────────────────────────────

def check_skip(today: datetime.date) -> tuple[bool, str]:
    """Returns (should_skip, reason)."""
    if today.weekday() == 0:  # Monday
        return True, "Monday — US data is 3 calendar days stale, skipping"
    if today in NSE_HOLIDAYS:
        return True, f"NSE holiday — market closed"
    if today in EVENT_DAYS:
        return True, f"Event day (RBI MPC / Budget / Election) — skipping"
    return False, ""


# ── Global market data ─────────────────────────────────────────────────────────

def fetch_global_data(today: datetime.date) -> dict:
    """Fetch previous session's data for all global markets via yfinance."""
    from datetime import timedelta
    start = str(today - timedelta(days=12))
    end   = str(today + timedelta(days=1))

    TICKERS = {
        'SP500': '^GSPC',
        'SGX':   'NKD=F',
        'DAX':   '^GDAXI',
        'VIX':   '^VIX',
        'NIFTY': '^NSEI',
    }

    raw = {}
    for name, ticker in TICKERS.items():
        try:
            df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            # Keep only sessions that have closed (before today)
            if df.index.tz is None:
                df.index = df.index.tz_localize('UTC')
            df = df[df.index.date < today]
            raw[name] = df
        except Exception as e:
            print(f"  [warn] {name} fetch failed: {e}")
            raw[name] = pd.DataFrame()

    def _ret(name):
        df = raw[name]
        if len(df) < 2: return None
        last_date = df.index[-1].date()
        if (today - last_date).days > MAX_STALE_DAYS: return None
        return float((df['Close'].iloc[-1] - df['Close'].iloc[-2]) / df['Close'].iloc[-2])

    def _close(name):
        df = raw[name]
        if len(df) == 0: return None
        last_date = df.index[-1].date()
        if (today - last_date).days > MAX_STALE_DAYS: return None
        return float(df['Close'].iloc[-1])

    return {
        'sp500_ret':   _ret('SP500'),
        'sgx_ret':     _ret('SGX'),
        'dax_ret':     _ret('DAX'),
        'vix_ret':     _ret('VIX'),
        'vix_level':   _close('VIX'),
        'nifty_ret':   _ret('NIFTY'),
        'nifty_close': _close('NIFTY'),
    }


# ── NIFTY intraday prices ──────────────────────────────────────────────────────

def fetch_nifty_915_open() -> float | None:
    """Get NIFTY 9:15 AM opening price via yfinance 1-min data."""
    try:
        raw = yf.download('^NSEI', period='1d', interval='1m', progress=False, auto_adjust=True)
        if raw.empty:
            return None
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        if raw.index.tz is None:
            raw.index = raw.index.tz_localize('UTC')
        raw.index = raw.index.tz_convert(IST)
        # Get 9:15 AM bar
        bar = raw[raw.index.time == datetime.time(9, 15)]
        if bar.empty:
            bar = raw.iloc[[0]]  # fallback: first available bar
        return float(bar['Open'].iloc[0])
    except Exception as e:
        print(f"  [warn] NIFTY 9:15 fetch failed: {e}")
        return None


# ── NSE option chain API ───────────────────────────────────────────────────────

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

def get_nse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(NSE_HEADERS)
    # Warm up cookies
    session.get('https://www.nseindia.com', timeout=15)
    time.sleep(1)
    return session

def fetch_option_chain(session: requests.Session) -> dict | None:
    """Fetch NIFTY option chain from NSE. Returns raw JSON data or None."""
    url = 'https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY'
    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  [warn] NSE option chain fetch failed: {e}")
        return None

def get_nifty_spot(chain_data: dict) -> float | None:
    """Extract current NIFTY underlying value from option chain."""
    try:
        return float(chain_data['records']['underlyingValue'])
    except Exception:
        return None

def get_option_premium(chain_data: dict, strike: int, expiry_str: str,
                       opt_type: str) -> float | None:
    """
    Extract LTP for a specific strike/expiry/type from option chain.
    opt_type: 'CE' or 'PE'
    expiry_str: NSE format e.g. '17-Apr-2025'
    """
    try:
        for row in chain_data['records']['data']:
            if (row.get('strikePrice') == strike
                    and row.get('expiryDate', '').strip() == expiry_str):
                opt_data = row.get(opt_type, {})
                ltp = opt_data.get('lastPrice')
                if ltp and ltp > 0:
                    return float(ltp)
        return None
    except Exception:
        return None


# ── Expiry calculation ─────────────────────────────────────────────────────────

def next_expiry(today: datetime.date) -> datetime.date:
    """
    Thursday expiry before EXPIRY_CHANGE_DATE, Tuesday expiry from it onward.
    Returns today itself if today is expiry day.
    """
    from datetime import timedelta
    target_wd = 1 if today >= EXPIRY_CHANGE_DATE else 3   # Tue=1, Thu=3
    days = (target_wd - today.weekday()) % 7
    return today + timedelta(days=days)

def expiry_to_nse_str(expiry: datetime.date) -> str:
    months = ['Jan','Feb','Mar','Apr','May','Jun',
              'Jul','Aug','Sep','Oct','Nov','Dec']
    return f"{expiry.day:02d}-{months[expiry.month-1]}-{expiry.year}"


# ── Signal computation ─────────────────────────────────────────────────────────

def compute_signals(gd: dict, nifty_open_915: float | None) -> dict:
    """
    Build the full signals dict. Gap signals require nifty_open_915.
    If nifty_open_915 is None, gap signals default to False.
    """
    nifty_close = gd['nifty_close']
    if nifty_open_915 and nifty_close and nifty_close > 0:
        gap = (nifty_open_915 - nifty_close) / nifty_close
    else:
        gap = None

    return {
        'Gap Up'          : gap is not None and gap >  GAP_THRESHOLD,
        'Gap Up Strong'   : gap is not None and gap >  GAP_LARGE_THRESHOLD,
        'Gap Down'        : gap is not None and gap < -GAP_THRESHOLD,
        'Prev India UP'   : gd['nifty_ret'] is not None and gd['nifty_ret'] > 0,
        'Prev India DOWN' : gd['nifty_ret'] is not None and gd['nifty_ret'] < 0,
        'US UP'           : gd['sp500_ret'] is not None and gd['sp500_ret'] > 0,
        'US DOWN'         : gd['sp500_ret'] is not None and gd['sp500_ret'] < 0,
        'SGX UP'          : gd['sgx_ret']   is not None and gd['sgx_ret']   > 0,
        'SGX DOWN'        : gd['sgx_ret']   is not None and gd['sgx_ret']   < 0,
        'DAX UP'          : gd['dax_ret']   is not None and gd['dax_ret']   > 0,
        'VIX Rising'      : gd['vix_ret']   is not None and gd['vix_ret']   > VIX_RISING_THRESHOLD,
        'VIX Falling'     : gd['vix_ret']   is not None and gd['vix_ret']   < 0,
        'VIX Spike'       : gd['vix_ret']   is not None and gd['vix_ret']   > VIX_SPIKE_THRESHOLD,
    }, gap


def load_signal_combos() -> tuple[list, list]:
    """Load top-10 bearish combos from v2_reliable_signals.csv."""
    import pandas as pd
    if not SIGNALS_CSV.exists():
        raise FileNotFoundError(f"Signals CSV not found: {SIGNALS_CSV}")
    reliable = pd.read_csv(SIGNALS_CSV)
    top_bearish = (reliable[reliable['P_Down'] > BASE_RATE]
                   .sort_values('Edge_pp', ascending=False)
                   .head(10)
                   .reset_index(drop=True))
    return list(top_bearish['Signal']), top_bearish


def combo_fires(combo_str: str, signals: dict) -> bool:
    return all(signals.get(s.strip(), False) for s in combo_str.split('+'))


# ── Charge computation (entry/buy side only) ───────────────────────────────────

def compute_entry_charges(entry_premium: float, lots: int) -> float:
    """
    Buy-side charges only. Sell-side charges computed in exit.py.
      - Brokerage (buy order): Rs 20
      - Stamp duty: 0.003% of buy premium value
      - Exchange (buy side half): 0.053%/2 of buy value (approximation)
      - SEBI (buy side half): 0.0001%/2
      - GST on brokerage+exchange+SEBI
    """
    buy_value   = entry_premium * lots * LOT_SIZE
    brokerage   = BROKERAGE_PER_ORDER                  # Rs 20 (buy order only here)
    stamp       = STAMP_BUY_RATE * buy_value
    exchange    = EXCHANGE_RATE * buy_value            # buy-side exchange charge
    sebi        = SEBI_RATE * buy_value
    gst         = GST_RATE * (brokerage + exchange + sebi)
    return round(brokerage + stamp + exchange + sebi + gst, 4)


# ── Lot sizing ─────────────────────────────────────────────────────────────────

def compute_lots(capital: float, entry_premium: float, dte: int) -> int:
    cost_per_lot = entry_premium * LOT_SIZE
    if cost_per_lot <= 0:
        return BASE_LOTS
    lots = int(capital // cost_per_lot)
    lots = max(lots, BASE_LOTS)
    lots = min(lots, MAX_LOTS)
    if dte == 0:
        lots = min(lots, DTE0_MAX_LOTS)
    return max(lots, 1)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    today = today_ist()

    # 1. Skip day check
    skip, reason = check_skip(today)
    if skip:
        append_log("SKIP", {"reason": reason})
        print(f"SKIP — {reason}")
        return

    # 2. Fetch global market data
    print(f"\nNIFTY Gap Strategy — {today.strftime('%d %b %Y, %A')}")
    print("Fetching global market data ...", end=' ', flush=True)
    gd = fetch_global_data(today)
    print("done.")

    if gd['nifty_close'] is None:
        msg = "NIFTY prev close unavailable — possible holiday or data delay"
        append_log("SKIP", {"reason": msg})
        print(f"SKIP — {msg}")
        return

    missing = [k for k, v in {
        'SP500': gd['sp500_ret'], 'SGX': gd['sgx_ret'],
        'DAX': gd['dax_ret'], 'VIX': gd['vix_ret']
    }.items() if v is None]
    if missing:
        print(f"  [warn] Missing/stale: {', '.join(missing)} — those signals default False")

    print(f"  NIFTY prev close  : {gd['nifty_close']:>10,.1f}")
    for k, v in [('S&P 500', gd['sp500_ret']), ('SGX/NK Fut', gd['sgx_ret']),
                 ('DAX', gd['dax_ret']), ('VIX', gd['vix_ret'])]:
        print(f"  {k:<16}: {v:>+10.2%}" if v is not None else f"  {k:<16}:    MISSING")

    # 3. Fetch NIFTY 9:15 AM open (for gap %)
    print("Fetching NIFTY 9:15 open ...", end=' ', flush=True)
    nifty_open_915 = fetch_nifty_915_open()
    print(f"{nifty_open_915:,.1f}" if nifty_open_915 else "unavailable")

    # 4. Compute signals
    signals, gap = compute_signals(gd, nifty_open_915)
    if gap is not None:
        gap_label = (f"GAP UP STRONG ({gap:+.2%})" if gap > GAP_LARGE_THRESHOLD
                     else f"GAP UP ({gap:+.2%})" if gap > GAP_THRESHOLD
                     else f"GAP DOWN ({gap:+.2%})" if gap < -GAP_THRESHOLD
                     else f"FLAT ({gap:+.2%})")
        print(f"  Gap               : {gap_label}")
    else:
        print("  Gap               : unknown (9:15 price unavailable)")

    active = [k for k, v in signals.items() if v]
    print(f"  Active signals    : {', '.join(active) if active else 'none'}")

    # 5. Match signal combos
    bear_combos, bear_df = load_signal_combos()
    fired = [c for c in bear_combos if combo_fires(c, signals)]

    if not fired:
        append_log("SKIP", {
            "reason":       "No bearish combo fired",
            "active_signals": active,
            "gap_pct":       round(gap, 6) if gap is not None else None,
            "nifty_close":   gd['nifty_close'],
        })
        print("\n  RESULT: NO SIGNAL — sit out today.")
        return

    winning_combo = fired[0]
    row = bear_df[bear_df['Signal'] == winning_combo].iloc[0]
    print(f"\n  BEARISH SIGNAL FIRED: {winning_combo}")
    print(f"  P(DOWN)={row['P_Down']:.1f}%  Edge=+{row['Edge_pp']:.1f}%  N={int(row['N'])}")

    # 6. Fetch live NIFTY spot + option chain from NSE
    print("\nFetching NSE option chain ...", end=' ', flush=True)
    session   = get_nse_session()
    chain     = fetch_option_chain(session)
    if chain is None:
        append_log("ERROR", {"error": "NSE option chain unavailable at entry time"})
        print("FAILED — NSE option chain unavailable.")
        sys.exit(1)
    print("done.")

    nifty_spot_925 = get_nifty_spot(chain)
    if not nifty_spot_925:
        append_log("ERROR", {"error": "Could not extract NIFTY spot from option chain"})
        sys.exit(1)
    print(f"  NIFTY spot (9:25) : {nifty_spot_925:,.1f}")

    # 7. Compute expiry, strike
    expiry     = next_expiry(today)
    dte        = (expiry - today).days
    expiry_str = expiry_to_nse_str(expiry)
    atm        = round(nifty_spot_925 / STRIKE_STEP) * STRIKE_STEP
    strike_pe  = atm - STRIKE_STEP   # 1-OTM PUT

    print(f"  Expiry            : {expiry_str}  (DTE={dte})")
    print(f"  ATM               : {atm:,}  →  1-OTM PE strike: {strike_pe:,}")

    # 8. Fetch entry premium
    entry_premium = get_option_premium(chain, strike_pe, expiry_str, 'PE')
    if entry_premium is None:
        # Fallback: try ATM PE
        entry_premium = get_option_premium(chain, atm, expiry_str, 'PE')
        if entry_premium:
            print(f"  [warn] 1-OTM PE not found — using ATM PE instead")
    if entry_premium is None:
        append_log("ERROR", {"error": f"Could not fetch PE premium for strike {strike_pe} expiry {expiry_str}"})
        print("ERROR — PE premium unavailable in option chain.")
        sys.exit(1)
    print(f"  Entry premium     : Rs {entry_premium:.2f}")

    # 9. Capital + lot sizing
    capital = load_capital()
    lots    = compute_lots(capital, entry_premium, dte)
    buy_val = entry_premium * lots * LOT_SIZE
    charges = compute_entry_charges(entry_premium, lots)

    print(f"  Capital           : Rs {capital:,.2f}")
    print(f"  Lots              : {lots}  (× {LOT_SIZE} = {lots*LOT_SIZE} units)")
    print(f"  Buy value         : Rs {buy_val:,.2f}")
    print(f"  Entry charges     : Rs {charges:.2f}")

    # 10. Write positions.json atomically
    pos = {
        "trade_date":    today_str(),
        "entry_time":    now_ist(),
        "capital_at_entry": round(capital, 4),
        "combo":         winning_combo,
        "p_down":        float(row['P_Down']),
        "gap_pct":       round(gap, 6) if gap is not None else None,
        "nifty_close_prev": round(gd['nifty_close'], 2),
        "nifty_spot_925":   round(nifty_spot_925, 2),
        "expiry_str":    expiry_str,
        "dte":           dte,
        "strike":        strike_pe,
        "opt_type":      "PE",
        "entry_premium": round(entry_premium, 2),
        "lots":          lots,
        "buy_value":     round(buy_val, 2),
        "charges_entry": round(charges, 4),
        "sl_price":      round(entry_premium * (1 - 0.15), 4),
        "tp_price":      round(entry_premium * (1 + 0.40), 4),
        "signals":       {k: v for k, v in signals.items() if v},
        "status":        "open",
    }
    atomic_write_json(POSITIONS_FILE, pos)

    # 11. Log BUY event
    append_log("BUY", {
        "combo":          winning_combo,
        "p_down":         float(row['P_Down']),
        "gap_pct":        round(gap, 6) if gap is not None else None,
        "nifty_spot_925": round(nifty_spot_925, 2),
        "expiry":         expiry_str,
        "dte":            dte,
        "strike":         strike_pe,
        "entry_premium":  round(entry_premium, 2),
        "sl_price":       pos['sl_price'],
        "tp_price":       pos['tp_price'],
        "lots":           lots,
        "buy_value":      round(buy_val, 2),
        "charges_entry":  round(charges, 4),
        "capital_before": round(capital, 2),
    })

    print(f"\n  ✓ Position written. exit.py will monitor SL={entry_premium*(1-0.15):.2f}"
          f" / TP={entry_premium*(1+0.40):.2f} until 11:15 AM.")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        append_log("ERROR", {"error": str(e), "traceback": traceback.format_exc()})
        print(f"ERROR: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
