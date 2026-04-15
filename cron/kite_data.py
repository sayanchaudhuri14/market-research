"""
kite_data.py — Kite Connect data helpers for entry.py.

Replaces NSE scraping (session cookies / option-chain HTML parsing) with
direct Kite API calls: quotes, historical candles, and NFO instrument lookup.
"""

import datetime
import json
from pathlib import Path
from typing import Optional

import pytz
from kiteconnect import KiteConnect

IST = pytz.timezone("Asia/Kolkata")

# NFO instruments are cached here once per day (~40k records, no need to re-fetch)
_INSTRUMENTS_CACHE = Path(__file__).parent / "kite_nfo_instruments.json"

# Hardcoded NIFTY 50 index instrument token on Kite (constant across accounts)
_NIFTY50_TOKEN = 256265


# ── Spot price ────────────────────────────────────────────────────────────────

def get_nifty_spot(kite: KiteConnect) -> Optional[float]:
    """Current NIFTY 50 last traded price."""
    try:
        q = kite.ltp("NSE:NIFTY 50")
        return float(q["NSE:NIFTY 50"]["last_price"])
    except Exception as e:
        print(f"  [warn] Kite NIFTY spot failed: {e}")
        return None


# ── 9:15 AM opening candle ────────────────────────────────────────────────────

def get_nifty_915_open(kite: KiteConnect) -> Optional[float]:
    """
    NIFTY 50 open price of the 9:15 AM minute candle using Kite historical data.
    Falls back to the first available candle of the day.
    """
    try:
        today = datetime.datetime.now(IST).date()
        from_dt = datetime.datetime(today.year, today.month, today.day, 9, 0)
        to_dt   = datetime.datetime(today.year, today.month, today.day, 9, 30)
        candles = kite.historical_data(
            _NIFTY50_TOKEN,
            from_date=from_dt,
            to_date=to_dt,
            interval="minute",
        )
        if not candles:
            return None
        for c in candles:
            dt = c["date"]
            # dt is timezone-aware; compare in IST
            if hasattr(dt, "tzinfo") and dt.tzinfo:
                dt_ist = dt.astimezone(IST)
            else:
                dt_ist = IST.localize(dt)
            if dt_ist.hour == 9 and dt_ist.minute == 15:
                return float(c["open"])
        # fallback: very first candle of the day
        return float(candles[0]["open"])
    except Exception as e:
        print(f"  [warn] Kite NIFTY 9:15 open failed: {e}")
        return None


# ── NFO instruments (cached per day) ─────────────────────────────────────────

def _load_nfo_instruments(kite: KiteConnect) -> list[dict]:
    """
    Download and cache NIFTY NFO options instruments for today.
    Only keeps NIFTY index options (name == 'NIFTY') to keep the cache small.
    """
    today = datetime.date.today().isoformat()
    if _INSTRUMENTS_CACHE.exists():
        try:
            cached = json.loads(_INSTRUMENTS_CACHE.read_text())
            if cached.get("date") == today:
                return cached["instruments"]
        except (json.JSONDecodeError, KeyError):
            pass

    print("  [kite_data] Downloading NFO instruments ...", end=" ", flush=True)
    all_insts = kite.instruments("NFO")
    # Filter to NIFTY weekly/monthly options only
    nifty_opts = [
        {
            "instrument_token": int(i["instrument_token"]),
            "tradingsymbol":    i["tradingsymbol"],
            "expiry":           str(i["expiry"]),   # "2025-04-17"
            "strike":           float(i["strike"]),
            "instrument_type":  i["instrument_type"],  # "CE" or "PE"
        }
        for i in all_insts
        if i.get("name") == "NIFTY" and i.get("instrument_type") in ("CE", "PE")
    ]
    _INSTRUMENTS_CACHE.write_text(
        json.dumps({"date": today, "instruments": nifty_opts}, default=str)
    )
    print(f"done. ({len(nifty_opts)} NIFTY options cached)")
    return nifty_opts


# ── Option premium ────────────────────────────────────────────────────────────

def get_option_premium(
    kite: KiteConnect,
    strike: int,
    expiry: datetime.date,
    opt_type: str,
) -> Optional[float]:
    """
    Last traded price for a NIFTY option via Kite quote API.
    opt_type: 'CE' or 'PE'
    """
    try:
        instruments = _load_nfo_instruments(kite)
        expiry_str  = expiry.isoformat()           # "2025-04-17"

        token = None
        symbol = None
        for inst in instruments:
            if (
                float(inst["strike"]) == float(strike)
                and inst["expiry"] == expiry_str
                and inst["instrument_type"] == opt_type
            ):
                token  = inst["instrument_token"]
                symbol = f"NFO:{inst['tradingsymbol']}"
                break

        if symbol is None:
            print(f"  [warn] No Kite instrument: NIFTY {strike}{opt_type} {expiry_str}")
            return None

        q = kite.ltp(symbol)
        ltp = q[symbol]["last_price"]
        return float(ltp) if ltp else None
    except Exception as e:
        print(f"  [warn] Kite option premium failed ({strike} {opt_type} {expiry}): {e}")
        return None
