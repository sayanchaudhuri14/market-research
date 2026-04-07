from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
DATA_DIR         = ROOT / "data"
OHLC_CACHE_DIR   = DATA_DIR / "ohlc_cache"
CONSTITUENTS_FILE = DATA_DIR / "nifty50_constituents.csv"
TOKEN_CACHE_FILE = DATA_DIR / "access_token_cache.json"
POSITIONS_FILE   = DATA_DIR / "current_positions.json"
TRADE_LOG_FILE   = DATA_DIR / "trade_log.csv"

# ── Universe ───────────────────────────────────────────────────────────────────
NIFTY50_SYMBOLS = [
    # Current composition (verified Dec 2025 via NSE + Kite instruments dump)
    # Removed: BPCL, BRITANNIA, DIVISLAB, HEROMOTOCO, INDUSINDBK, IOC
    # Added:   ETERNAL (Zomato), INDIGO, ITC, JIOFIN, MAXHEALTH, TMPV (Tata Motors PV)
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL", "BHARTIARTL",
    "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
    "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO",
    "HINDUNILVR", "ICICIBANK", "INDIGO", "INFY", "ITC",
    "JIOFIN", "JSWSTEEL", "KOTAKBANK", "LT", "M&M",
    "MARUTI", "MAXHEALTH", "NESTLEIND", "NTPC", "ONGC",
    "POWERGRID", "RELIANCE", "SBILIFE", "SHRIRAMFIN", "SBIN",
    "SUNPHARMA", "TCS", "TATACONSUM", "TMPV", "TATASTEEL",
    "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO",
]

# ── Signal ─────────────────────────────────────────────────────────────────────
LOOKBACK_SESSIONS = 20      # trailing sessions for mean overnight return score
TOP_N             = 10      # number of stocks to long

# ── Execution timing ───────────────────────────────────────────────────────────
ENTRY_TIME = "15:20"        # buy near close
EXIT_TIME  = "09:25"        # sell after open settles

# ── Risk / filters ─────────────────────────────────────────────────────────────
VIX_MAX   = 20.0            # skip days when India VIX > this
US_FILTER = True            # only trade when S&P 500 prev close return >= 0

# ── Sizing ─────────────────────────────────────────────────────────────────────
CAPITAL          = 200_000  # Rs — adjust to actual capital
EQUAL_WEIGHT     = True
WEIGHT_PER_STOCK = CAPITAL / TOP_N   # Rs per position

# ── Costs ──────────────────────────────────────────────────────────────────────
# Zerodha: equity delivery (CNC) is free brokerage; intraday MIS is Rs 20/order.
# This strategy holds overnight so CNC is the correct order type.
# STT on CNC sell side: 0.1% of turnover.
BROKERAGE_PER_ORDER  = 0       # Rs (CNC delivery — free on Zerodha)
STT_SELL_RATE        = 0.001   # 0.1% on sell-side turnover
EXCHANGE_CHARGE_RATE = 0.0000325  # NSE transaction charge ~0.00325%
SEBI_CHARGE_RATE     = 0.000001   # 0.0001%
STAMP_DUTY_RATE      = 0.00015    # 0.015% on buy side
# Approximate total round-trip cost per stock: ~0.15%
ROUND_TRIP_COST_RATE = 0.0015

# ── Kite ───────────────────────────────────────────────────────────────────────
INSTRUMENT_TOKEN_NIFTY_VIX = 264969   # India VIX (verify token on your account)
INSTRUMENT_TOKEN_NIFTY50   = 256265   # NIFTY 50 index

# ── Skip rules ─────────────────────────────────────────────────────────────────
# Hard-code known event dates here; update monthly.
SKIP_DATES = [
    # "2026-02-01",  # Budget
    # Add RBI MPC dates, election result days here
]

# ── Historical data bootstrap ──────────────────────────────────────────────────
HISTORY_FROM = "2021-04-01"   # start of 5-year history fetch
KITE_RATE_LIMIT_SLEEP = 0.4   # seconds between historical_data() calls

# ── Trade monitoring ───────────────────────────────────────────────────────────
ROLLING_REVIEW_WINDOW = 20    # sessions
ROLLING_REVIEW_FLOOR  = -0.0005  # pause if rolling mean net return < -0.05%/session
