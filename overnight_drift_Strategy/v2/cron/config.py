"""
config.py — Shared constants for paper-trading cron scripts.
All charge values match backtest.ipynb cell b1 exactly.
"""
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
CRON_DIR       = Path(__file__).parent
STATE_FILE     = CRON_DIR / "state.json"       # running portfolio capital
POSITIONS_FILE = CRON_DIR / "positions.json"   # open positions (buy→sell)
LOG_FILE       = CRON_DIR / "logs" / "trade_log.jsonl"

# ── Capital ────────────────────────────────────────────────────────────────────
STARTING_CAPITAL = 2_00_000.0   # Rs 2L initial paper capital

# ── Strategy ───────────────────────────────────────────────────────────────────
LOOKBACK = 20    # rolling sessions for overnight momentum score
TOP_N    = 10    # stocks to buy per session

# ── NIFTY 50 tickers (current composition, .NS suffix) ────────────────────────
NIFTY50_YF = [
    'ADANIENT.NS',   'ADANIPORTS.NS', 'APOLLOHOSP.NS', 'ASIANPAINT.NS', 'AXISBANK.NS',
    'BAJAJ-AUTO.NS', 'BAJFINANCE.NS', 'BAJAJFINSV.NS', 'BEL.NS',        'BHARTIARTL.NS',
    'CIPLA.NS',      'COALINDIA.NS',  'DRREDDY.NS',    'EICHERMOT.NS',  'ETERNAL.NS',
    'GRASIM.NS',     'HCLTECH.NS',    'HDFCBANK.NS',   'HDFCLIFE.NS',   'HINDALCO.NS',
    'HINDUNILVR.NS', 'ICICIBANK.NS',  'INDIGO.NS',     'INFY.NS',       'ITC.NS',
    'JIOFIN.NS',     'JSWSTEEL.NS',   'KOTAKBANK.NS',  'LT.NS',         'M%26M.NS',
    'MARUTI.NS',     'MAXHEALTH.NS',  'NESTLEIND.NS',  'NTPC.NS',       'ONGC.NS',
    'POWERGRID.NS',  'RELIANCE.NS',   'SBILIFE.NS',    'SHRIRAMFIN.NS', 'SBIN.NS',
    'SUNPHARMA.NS',  'TCS.NS',        'TATACONSUM.NS', 'TMPV.NS',       'TATASTEEL.NS',
    'TECHM.NS',      'TITAN.NS',      'TRENT.NS',      'ULTRACEMCO.NS', 'WIPRO.NS',
]

# ── Charge parameters (Zerodha / AngelOne, equity delivery CNC) ───────────────
# Source: Finance Act (No. 2) 2004; matches backtest.ipynb cell b1
STT_BUY_RATE  = 0.001_0        # 0.10%  buy-side  (delivery — both sides charged)
STT_SELL_RATE = 0.001_0        # 0.10%  sell-side
STAMP_RATE    = 0.000_15       # 0.015% buy-side only
EXCHANGE_RATE = 0.000_029_7    # NSE exchange charge, per side
IPFT_RATE     = 0.000_001      # Investor Protection Fund Trust, per side
SEBI_RATE     = 0.000_001      # SEBI charge, per side
GST_RATE      = 0.18           # 18% GST on exchange + IPFT + SEBI

DP_PER_SCRIP  = 13.0           # Rs — Zerodha CDSL debit per scrip sold
GST_DP        = 0.18

# Pre-computed totals
PCT_COST  = (STT_BUY_RATE + STT_SELL_RATE + STAMP_RATE
             + 2 * (EXCHANGE_RATE + IPFT_RATE + SEBI_RATE) * (1 + GST_RATE))
# = 0.2225% per round-trip

FLAT_COST = TOP_N * DP_PER_SCRIP * (1 + GST_DP)   # Rs 153.40 (DP on 10 stocks, sell-side only)
