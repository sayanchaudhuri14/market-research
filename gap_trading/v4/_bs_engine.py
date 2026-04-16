"""
_bs_engine.py — Black-Scholes option pricer and OHLC-proxy exit simulator.

Used by all backtest_BS.ipynb notebooks to simulate option prices when
real 1-min option candles are unavailable (pre-2024 history).

Limitations (printed at results time):
  1. SL/TP timing within the day is unknown — OHLC proxy over/under-counts.
  2. Volatility smile ignored — BS underprices OTM options.
  3. DTE=0 positions are flagged (extreme gamma makes BS unreliable).
  4. Pre-2021 is out-of-sample for v2 signal combos.
"""

from __future__ import annotations

import math
import warnings
from typing import Optional, Tuple

import numpy as np

try:
    from scipy.stats import norm as _norm
    _USE_SCIPY = True
except ImportError:
    _USE_SCIPY = False


# ── Black-Scholes ──────────────────────────────────────────────────────────────

def _ncdf(x: float) -> float:
    """Cumulative standard normal CDF."""
    if _USE_SCIPY:
        return float(_norm.cdf(x))
    # Abramowitz & Stegun approximation (error < 7.5e-8)
    sign = 1 if x >= 0 else -1
    x = abs(x)
    t = 1.0 / (1.0 + 0.2316419 * x)
    poly = t * (0.319381530
                + t * (-0.356563782
                       + t * (1.781477937
                              + t * (-1.821255978
                                     + t * 1.330274429))))
    cdf = 1.0 - (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * x * x) * poly
    return cdf if sign >= 0 else 1.0 - cdf


def bs_put_price(S: float, K: float, T: float,
                 r: float = 0.065, sigma: float = 0.15) -> float:
    """
    Black-Scholes European put price.

    Parameters
    ----------
    S     : spot price (NIFTY level at entry)
    K     : strike price
    T     : time to expiry in years  (e.g., 1/365 for DTE=1)
    r     : risk-free rate (default 6.5% = Indian T-bill proxy)
    sigma : annualised volatility (use India VIX / 100 when available)

    Returns
    -------
    Put premium in index points.  Returns 0 if inputs are invalid.
    """
    if T <= 0 or S <= 0 or K <= 0 or sigma <= 0:
        return max(K - S, 0.0)   # intrinsic value at expiry

    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        put = K * math.exp(-r * T) * _ncdf(-d2) - S * _ncdf(-d1)
        return max(put, 0.0)
    except (ValueError, ZeroDivisionError):
        return max(K - S, 0.0)


# ── OHLC-proxy SL/TP simulation ────────────────────────────────────────────────

def simulate_bs_exit(
    entry_price: float,
    S_open:  float,
    S_high:  float,
    S_low:   float,
    S_close: float,
    K: float,
    T_entry: float,        # time to expiry at 9:25 entry
    T_exit:  float,        # time to expiry at 11:15 exit  (T_entry - 110min/year)
    SL_PCT:  float = 0.15,
    TP_PCT:  float = 0.40,
    r:       float = 0.065,
    sigma:   float = 0.15,
    dte:     int   = 1,
) -> Tuple[float, str]:
    """
    Approximate whether SL or TP was hit during the trading window.

    Method (OHLC proxy):
      - Compute BS put at nifty_high  → worst case for put holder (lowest put price)
      - Compute BS put at nifty_low   → best  case for put holder (highest put price)
      - Compute BS put at nifty_close → proxy for 11:15 price

    If put_at_high  <= entry * (1 - SL_PCT) → Stop Loss hit (approx)
    If put_at_low   >= entry * (1 + TP_PCT) → Target Hit  (approx)
    If both triggered (ambiguous day): conservatively record Stop Loss.
    Otherwise: time exit at put_at_close.

    Parameters
    ----------
    entry_price  : BS put price at 9:25 entry
    S_open/high/low/close : NIFTY daily OHLC
    K            : strike price
    T_entry      : time to expiry at entry (years)
    T_exit       : time to expiry at 11:15 exit (years) — for time decay
    SL_PCT, TP_PCT : stop loss and target percentages
    sigma        : annualised vol (India VIX / 100)
    dte          : days to expiry (used only for warning flag)

    Returns
    -------
    (exit_price, exit_reason)
    """
    sl_price = entry_price * (1 - SL_PCT)
    tp_price = entry_price * (1 + TP_PCT)

    # Volatility adjustments: put buyers gain when volatility spikes (VIX usually
    # rises when market falls), so use a slight upward sigma bump for the low scenario
    sigma_up   = sigma * 1.08   # mild vol expansion on down days
    sigma_down = sigma * 0.95   # mild vol contraction on up days

    put_at_high  = bs_put_price(S_high,  K, T_entry, r, sigma_down)
    put_at_low   = bs_put_price(S_low,   K, T_entry, r, sigma_up)
    put_at_close = bs_put_price(S_close, K, T_exit,  r, sigma)

    sl_hit = put_at_high  <= sl_price
    tp_hit = put_at_low   >= tp_price

    if sl_hit and tp_hit:
        # Ambiguous: both extremes triggered — conservative = SL
        return round(sl_price, 4), 'Stop Loss'
    elif sl_hit:
        return round(sl_price, 4), 'Stop Loss'
    elif tp_hit:
        return round(tp_price, 4), 'Target Hit'
    else:
        exit_price = max(put_at_close, 0.0)
        return round(exit_price, 4), '11:15 exit'


# ── Volatility helpers ─────────────────────────────────────────────────────────

FALLBACK_SIGMA = 0.15   # 15% flat — used when India VIX is unavailable

def vix_to_sigma(vix_level: Optional[float]) -> float:
    """Convert India VIX level (e.g., 13.5) to annualised volatility (0.135)."""
    if vix_level is None or math.isnan(vix_level) or vix_level <= 0:
        return FALLBACK_SIGMA
    return vix_level / 100.0


# ── DTE calculation ────────────────────────────────────────────────────────────

MINS_IN_YEAR = 365 * 24 * 60

def dte_to_T(dte: int, entry_mins_from_open: int = 10,
             exit_mins_from_open: int = 120) -> Tuple[float, float]:
    """
    Convert days-to-expiry into time fractions for BS.

    Parameters
    ----------
    dte                   : calendar days to expiry
    entry_mins_from_open  : minutes after market open at entry  (9:25 → 10 min)
    exit_mins_from_open   : minutes after market open at exit   (11:15 → 120 min)

    Returns
    -------
    (T_entry, T_exit) in years
    """
    # Trading session ≈ 375 min/day (9:15–15:30).  Convert residual to fractional days.
    residual_days = (375 - entry_mins_from_open) / (375)
    T_entry = max((dte - 1 + residual_days) / 365.0, 1 / MINS_IN_YEAR)

    residual_days_exit = (375 - exit_mins_from_open) / 375
    T_exit  = max((dte - 1 + residual_days_exit) / 365.0, 1 / MINS_IN_YEAR)

    return T_entry, T_exit


# ── Print BS limitations warning ───────────────────────────────────────────────

def print_bs_limitations():
    msg = """
╔══════════════════════════════════════════════════════════════════════╗
║  BLACK-SCHOLES BACKTEST — KNOWN LIMITATIONS                         ║
║                                                                      ║
║  1. SL/TP TIMING unknown: OHLC proxy cannot detect intraday order.  ║
║     Results may overstate wins (TP) or losses (SL) on volatile days.║
║  2. Volatility smile ignored: BS underprices deep-OTM options.      ║
║  3. DTE=0 trades are flagged — extreme gamma makes BS unreliable.   ║
║  4. Pre-2021 data is OUT-OF-SAMPLE for v2 signal combos.            ║
║     Combos were statistically selected on 2021–2026 data.           ║
║  Use these results for directional confirmation only.                ║
╚══════════════════════════════════════════════════════════════════════╝
"""
    print(msg)
