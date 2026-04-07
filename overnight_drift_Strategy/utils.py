"""
utils.py — shared helpers for the Overnight Drift strategy.
"""

import json
import pickle
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
import os

from config import (
    OHLC_CACHE_DIR,
    TOKEN_CACHE_FILE,
    CONSTITUENTS_FILE,
    LOOKBACK_SESSIONS,
    KITE_RATE_LIMIT_SLEEP,
)

# ── 1. Kite authentication ─────────────────────────────────────────────────────

def get_kite_session():
    """
    Load credentials from .env, validate cached access token (must be from today),
    and return an authenticated KiteConnect object.

    Token refresh is manual — Zerodha requires a fresh login each day.
    To update the token:
        1. Run kite.login_url() and open in browser.
        2. After redirect, extract `request_token` from URL.
        3. Call kite.generate_session(request_token, api_secret) to get access_token.
        4. Save it: save_access_token(access_token)
    """
    from kiteconnect import KiteConnect

    # Load .env from the strategy root
    env_path = Path(__file__).parent / ".env"
    load_dotenv(dotenv_path=env_path)

    api_key    = os.getenv("api_key")
    api_secret = os.getenv("api_secret")

    if not api_key or not api_secret:
        raise EnvironmentError(
            ".env missing api_key or api_secret. "
            f"Expected at: {env_path}"
        )

    kite = KiteConnect(api_key=api_key)

    # Load cached token
    if not TOKEN_CACHE_FILE.exists():
        raise FileNotFoundError(
            f"No access token cache found at {TOKEN_CACHE_FILE}.\n"
            "Generate a token with:\n"
            "  from utils import generate_and_save_token\n"
            "  generate_and_save_token()\n"
        )

    with open(TOKEN_CACHE_FILE) as f:
        cache = json.load(f)

    token_date = cache.get("date")
    access_token = cache.get("access_token")

    today_str = date.today().isoformat()
    if token_date != today_str:
        raise ValueError(
            f"Access token is stale (cached: {token_date}, today: {today_str}).\n"
            "Re-authenticate with:\n"
            "  from utils import generate_and_save_token\n"
            "  generate_and_save_token()\n"
        )

    kite.set_access_token(access_token)
    return kite


def save_access_token(access_token: str):
    """Persist access token with today's date stamp."""
    TOKEN_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"access_token": access_token, "date": date.today().isoformat()}
    with open(TOKEN_CACHE_FILE, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"Token saved to {TOKEN_CACHE_FILE}")


def generate_and_save_token():
    """
    Interactive helper to generate and cache a fresh access token.
    Run this from a Python REPL or notebook cell once each trading day.
    """
    from kiteconnect import KiteConnect

    env_path = Path(__file__).parent / ".env"
    load_dotenv(dotenv_path=env_path)
    api_key    = os.getenv("api_key")
    api_secret = os.getenv("api_secret")

    kite = KiteConnect(api_key=api_key)
    print("Open this URL in your browser and log in:")
    print(kite.login_url())
    print()
    request_token = input("Paste the request_token from the redirect URL: ").strip()
    data = kite.generate_session(request_token, api_secret=api_secret)
    save_access_token(data["access_token"])
    print("Done. Token is valid for today.")
    return kite


# ── 2. Instrument list ─────────────────────────────────────────────────────────

def get_nifty50_instruments() -> dict:
    """
    Read nifty50_constituents.csv and return {symbol: instrument_token}.
    CSV must have columns: symbol, instrument_token, name.
    """
    if not CONSTITUENTS_FILE.exists():
        raise FileNotFoundError(
            f"Constituents file not found: {CONSTITUENTS_FILE}\n"
            "Run the bootstrap snippet in steps.md (Step 1) to generate it."
        )
    df = pd.read_csv(CONSTITUENTS_FILE, dtype={"instrument_token": int})
    return dict(zip(df["symbol"], df["instrument_token"]))


# ── 3. OHLC fetch + cache ──────────────────────────────────────────────────────

def _cache_path(symbol: str) -> Path:
    return OHLC_CACHE_DIR / f"{symbol}.pkl"


def fetch_daily_ohlc(
    kite,
    instrument_token: int,
    symbol: str,
    from_date: str,
    to_date: str,
) -> pd.DataFrame:
    """
    Fetch daily OHLC from Kite, merge with cached data, and save.
    Returns a DataFrame with columns: date, open, high, low, close, volume.
    date column is pd.Timestamp (timezone-naive).
    """
    cache = _cache_path(symbol)
    existing = pd.DataFrame()

    if cache.exists():
        with open(cache, "rb") as f:
            existing = pickle.load(f)

        # Determine what dates are already cached
        if not existing.empty:
            last_cached = existing["date"].max()
            # Only fetch dates after the last cached date
            fetch_from = (last_cached + timedelta(days=1)).strftime("%Y-%m-%d")
            if fetch_from > to_date:
                return existing  # fully up to date
            from_date = fetch_from

    raw = kite.historical_data(
        instrument_token=instrument_token,
        from_date=from_date,
        to_date=to_date,
        interval="day",
        continuous=False,
        oi=False,
    )

    if not raw:
        return existing

    df = pd.DataFrame(raw)
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    df = df[["date", "open", "high", "low", "close", "volume"]]

    if not existing.empty:
        df = pd.concat([existing, df], ignore_index=True)
        df = df.drop_duplicates(subset="date").sort_values("date").reset_index(drop=True)
    else:
        df = df.sort_values("date").reset_index(drop=True)

    OHLC_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache, "wb") as f:
        pickle.dump(df, f, protocol=4)

    return df


# ── 4. Load all OHLC ──────────────────────────────────────────────────────────

def load_all_ohlc(symbols: list) -> dict:
    """
    Load cached OHLC for all symbols.
    Returns {symbol: DataFrame} aligned to the common trading calendar
    (dates where ALL symbols have data).
    """
    raw = {}
    for sym in symbols:
        path = _cache_path(sym)
        if not path.exists():
            print(f"  WARNING: no cache for {sym}, skipping")
            continue
        with open(path, "rb") as f:
            df = pickle.load(f)
        df = df.set_index("date").sort_index()
        raw[sym] = df

    if not raw:
        raise RuntimeError("No OHLC cache files found. Run fetch_ohlc.py first.")

    # Align to the UNION of all trading dates (not intersection).
    # Symbols listed later (e.g. JIOFIN, ETERNAL) will have NaN on dates before
    # their listing — they are simply excluded from ranking on those days.
    all_dates = sorted(set().union(*[set(df.index) for df in raw.values()]))
    aligned = {sym: df.reindex(all_dates) for sym, df in raw.items()}
    return aligned


# ── 5. Overnight returns ──────────────────────────────────────────────────────

def compute_overnight_returns(ohlc_dict: dict) -> pd.DataFrame:
    """
    For each symbol: overnight_return[t] = open[t] / close[t-1] - 1
    Returns wide DataFrame: rows=dates, columns=symbols.
    """
    frames = {}
    for sym, df in ohlc_dict.items():
        close = df["close"]
        open_ = df["open"]
        ret = open_ / close.shift(1) - 1
        frames[sym] = ret

    result = pd.DataFrame(frames)
    result = result.iloc[1:]  # drop first row (NaN from shift)
    return result


# ── 6. Rolling score ──────────────────────────────────────────────────────────

def compute_scores(overnight_df: pd.DataFrame, lookback: int = LOOKBACK_SESSIONS) -> pd.DataFrame:
    """
    Rolling mean of overnight returns over `lookback` sessions.
    Value at row t = mean of the last `lookback` overnight returns up to and including t.
    min_periods=lookback to avoid partial windows.
    """
    return overnight_df.rolling(window=lookback, min_periods=lookback).mean()


# ── 7. Rank stocks ────────────────────────────────────────────────────────────

def rank_stocks(scores_df: pd.DataFrame, date, top_n: int = 10) -> list:
    """
    For a given date (pd.Timestamp or string), return the top `top_n` symbols
    sorted by score descending. Returns a list of symbol strings.
    """
    date = pd.Timestamp(date)
    if date not in scores_df.index:
        raise KeyError(f"Date {date.date()} not in scores index.")

    row = scores_df.loc[date].dropna()
    ranked = row.sort_values(ascending=False)
    return list(ranked.head(top_n).index)


# ── 8. Filter checks ─────────────────────────────────────────────────────────

def check_us_filter(date_str: str = None) -> tuple:
    """
    Returns (pass: bool, sp500_return: float).
    Fetches previous S&P 500 close return via yfinance.
    If date_str is None, uses yesterday.
    """
    import yfinance as yf

    end = pd.Timestamp(date_str) if date_str else pd.Timestamp.today().normalize()
    start = end - timedelta(days=10)

    sp = yf.download("^GSPC", start=start.strftime("%Y-%m-%d"),
                     end=end.strftime("%Y-%m-%d"), progress=False)

    if sp.empty or len(sp) < 2:
        return True, float("nan")  # default to pass if data unavailable

    last_return = float(sp["Close"].iloc[-1] / sp["Close"].iloc[-2] - 1)
    return last_return >= 0, last_return


def check_vix_filter(kite) -> tuple:
    """
    Returns (pass: bool, vix_value: float).
    Fetches India VIX last traded price from Kite.
    """
    from config import INSTRUMENT_TOKEN_NIFTY_VIX, VIX_MAX

    try:
        quote = kite.ltp([f"NSE:{256265}"])  # fallback to index if VIX token wrong
        # Try VIX instrument
        vix_data = kite.ltp([f"NSE:INDIA VIX"])
        vix = list(vix_data.values())[0]["last_price"]
    except Exception:
        try:
            # Some accounts use the instrument token directly
            vix_data = kite.ltp([f"{INSTRUMENT_TOKEN_NIFTY_VIX}"])
            vix = list(vix_data.values())[0]["last_price"]
        except Exception:
            return True, float("nan")  # default pass if unavailable

    return vix <= VIX_MAX, vix


# ── 9. Cost calculation ───────────────────────────────────────────────────────

def compute_transaction_cost(price: float, qty: int) -> float:
    """
    Approximate total round-trip cost for one CNC stock position.
    Buy leg + sell leg.
    """
    from config import (
        BROKERAGE_PER_ORDER, STT_SELL_RATE,
        EXCHANGE_CHARGE_RATE, SEBI_CHARGE_RATE, STAMP_DUTY_RATE,
    )
    turnover_buy  = price * qty
    turnover_sell = price * qty  # approximate (use exit price in practice)

    brokerage = BROKERAGE_PER_ORDER * 2
    stt       = turnover_sell * STT_SELL_RATE
    exchange  = (turnover_buy + turnover_sell) * EXCHANGE_CHARGE_RATE
    sebi      = (turnover_buy + turnover_sell) * SEBI_CHARGE_RATE
    stamp     = turnover_buy * STAMP_DUTY_RATE
    gst       = brokerage * 0.18

    return brokerage + stt + exchange + sebi + stamp + gst


# ── 10. Trade log ─────────────────────────────────────────────────────────────

TRADE_LOG_COLS = [
    "date", "symbol", "entry_price", "exit_price", "qty",
    "overnight_return_pct", "pnl_rs", "transaction_cost_rs", "net_pnl_rs",
    "signal_score", "rank", "vix_at_entry", "us_prev_close_return", "session_notes",
]


def append_trade_log(records: list):
    """
    Append a list of trade dicts to the trade log CSV.
    Each dict should match TRADE_LOG_COLS keys.
    """
    from config import TRADE_LOG_FILE

    df_new = pd.DataFrame(records, columns=TRADE_LOG_COLS)

    if TRADE_LOG_FILE.exists():
        df_existing = pd.read_csv(TRADE_LOG_FILE)
        df_out = pd.concat([df_existing, df_new], ignore_index=True)
    else:
        df_out = df_new

    TRADE_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(TRADE_LOG_FILE, index=False)
    print(f"Trade log updated: {len(df_new)} new rows → {TRADE_LOG_FILE}")


def rolling_performance_check():
    """
    Print rolling win rate and mean net return over the last ROLLING_REVIEW_WINDOW sessions.
    Warns if rolling mean net return < ROLLING_REVIEW_FLOOR.
    """
    from config import TRADE_LOG_FILE, ROLLING_REVIEW_WINDOW, ROLLING_REVIEW_FLOOR

    if not TRADE_LOG_FILE.exists():
        print("No trade log yet.")
        return

    df = pd.read_csv(TRADE_LOG_FILE)
    if df.empty:
        print("Trade log is empty.")
        return

    recent = df.tail(ROLLING_REVIEW_WINDOW)
    win_rate = (recent["net_pnl_rs"] > 0).mean()
    mean_ret = recent["overnight_return_pct"].mean() if "overnight_return_pct" in recent else float("nan")
    mean_net_ret = (recent["net_pnl_rs"] / (recent["entry_price"] * recent["qty"])).mean()

    print(f"=== Rolling Performance (last {len(recent)} sessions) ===")
    print(f"  Win rate:              {win_rate:.1%}")
    print(f"  Mean overnight return: {mean_ret:.4%}" if not pd.isna(mean_ret) else "  Mean overnight return: N/A")
    print(f"  Mean net return:       {mean_net_ret:.4%}")

    if mean_net_ret < ROLLING_REVIEW_FLOOR:
        print(f"  *** WARNING: Rolling mean net return {mean_net_ret:.4%} is below "
              f"floor {ROLLING_REVIEW_FLOOR:.4%}. Consider pausing. ***")
