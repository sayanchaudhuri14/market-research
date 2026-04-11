"""
config.py — Shared constants for NIFTY gap trading paper-trading cron scripts.
Strategy: Buy 1-OTM NIFTY PUT at 9:25 AM on bearish signal days. Exit at SL/TP or 11:15 AM hard exit.
"""
from pathlib import Path
from datetime import date

CRON_DIR       = Path(__file__).parent
SIGNALS_CSV    = CRON_DIR.parent / 'v2' / 'v2_reliable_signals.csv'
STATE_FILE     = CRON_DIR / 'state.json'
POSITIONS_FILE = CRON_DIR / 'positions.json'
LOG_FILE       = CRON_DIR / 'logs' / 'trade_log.jsonl'
LOCK_FILE      = CRON_DIR / 'exit.lock'

# ── Capital ────────────────────────────────────────────────────────────────────
STARTING_CAPITAL  = 2_00_000.0   # Rs 2L initial paper capital
REFILL_THRESHOLD  =  50_000.0    # auto-refill if capital drops below this

# ── Signal parameters (must match backtest exactly) ────────────────────────────
SIGNAL_MODE          = 'BEARISH_ONLY'
BASE_RATE            = 54.5     # historical P(NIFTY first-hour closes DOWN)
GAP_THRESHOLD        = 0.0015   # 0.15% gap to trigger Gap Up / Gap Down signal
GAP_LARGE_THRESHOLD  = 0.0050   # 0.50% — Gap Up Strong
VIX_RISING_THRESHOLD = 0.03     # 3% VIX daily change → VIX Rising
VIX_SPIKE_THRESHOLD  = 0.05     # 5% VIX daily change → VIX Spike
MAX_STALE_DAYS       = 5        # days before treating global data as missing/stale

# ── Trade parameters (best from backtest grid search) ─────────────────────────
SL_PCT = 0.15    # exit if option premium falls 15% from entry
TP_PCT = 0.40    # exit if option premium rises 40% from entry

ENTRY_HR, ENTRY_MIN = 9,  25   # entry time IST
EXIT_HR,  EXIT_MIN  = 11, 15   # hard exit time IST
POLL_INTERVAL_SEC   = 120      # check SL/TP every 2 minutes

# ── Options parameters ─────────────────────────────────────────────────────────
LOT_SIZE       = 75    # units per lot (NIFTY)
STRIKE_STEP    = 50    # NIFTY strike granularity
BASE_LOTS      = 5     # minimum lots on normal days
DTE0_MAX_LOTS  = 10    # max lots on expiry day (DTE=0, extreme gamma)
MAX_LOTS       = 25    # hard global cap

# NSE weekly expiry: Thursday before Sep 2 2025, Tuesday from Sep 2 2025 onward
EXPIRY_CHANGE_DATE = date(2025, 9, 2)

# ── Charges (NIFTY index options, Zerodha, NSE) ────────────────────────────────
# Source: NSE circular + Zerodha charges page
BROKERAGE_PER_ORDER = 20.0      # Rs 20 flat per executed F&O order (buy or sell)
STT_SELL_RATE       = 0.000625  # 0.0625% on sell-side premium (2024 budget; buy side = 0)
STAMP_BUY_RATE      = 0.00003   # 0.003% on buy-side premium
EXCHANGE_RATE       = 0.00053   # NSE options: 0.053% of total premium turnover
SEBI_RATE           = 0.000001  # 0.0001% of total premium turnover
GST_RATE            = 0.18      # 18% on (brokerage + exchange + SEBI)

# ── NSE holiday calendar ───────────────────────────────────────────────────────
# Update annually (add next year's holidays in December)
NSE_HOLIDAYS = {
    # 2025
    date(2025,  2, 26), date(2025,  3, 14), date(2025,  3, 31),
    date(2025,  4, 10), date(2025,  4, 14), date(2025,  4, 18),
    date(2025,  5,  1), date(2025,  8, 15), date(2025, 10,  2),
    date(2025, 10, 21), date(2025, 10, 22), date(2025, 11,  5),
    date(2025, 12, 25),
    # 2026 (estimated — verify against NSE circular before Jan 2026)
    date(2026,  1, 26), date(2026,  3, 26), date(2026,  4,  3),
    date(2026,  4, 14), date(2026,  5,  1), date(2026,  8, 15),
    date(2026, 10,  2), date(2026, 11, 11), date(2026, 12, 25),
}

# ── Event days: skip trading (stale data / high uncertainty) ──────────────────
# Update annually. RBI MPC = ~6x/year (Feb/Apr/Jun/Aug/Oct/Dec first Fri)
EVENT_DAYS = {
    # 2025
    date(2025,  2,  1),   # Union Budget
    date(2025,  2,  7),   # RBI MPC
    date(2025,  4,  9),   # RBI MPC
    date(2025,  6,  6),   # RBI MPC
    date(2025,  8,  6),   # RBI MPC
    date(2025, 10,  8),   # RBI MPC
    date(2025, 12,  5),   # RBI MPC
    # 2026 (estimated — update when RBI announces dates)
    date(2026,  2,  1),   # Union Budget
    date(2026,  2,  6),   # RBI MPC
    date(2026,  4,  8),   # RBI MPC
    date(2026,  6,  5),   # RBI MPC
    date(2026,  8,  7),   # RBI MPC
    date(2026, 10,  7),   # RBI MPC
    date(2026, 12,  4),   # RBI MPC
}
