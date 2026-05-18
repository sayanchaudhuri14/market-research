#!/usr/bin/env python3
"""
Nifty Weekly Options Paper Trader
- 10 strategies with optimised SL/TP from 2024 backtesting
- Real Kite LTP for entry/exit/monitoring (no real orders placed)
- Compounding lot sizing, 15% DD circuit-breaker
- Runs 09:25–15:25 daily, monitoring every 60s
- State persisted in logs/{STRATEGY_ID}.json between runs
- Reads Kite token from gap trading's kite_token.json (never generates its own)

Cron: 25 9 * * 2-5 /home/ec2-user/venv/bin/python3 /home/ec2-user/Gap_Trading_Strategy/options/paper_trader/paper_trader.py >> /home/ec2-user/Gap_Trading_Strategy/options/paper_trader/logs/cron.log 2>&1
"""

import os, sys, json, time, logging
from typing import Optional
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from kiteconnect import KiteConnect

# ── Environment ────────────────────────────────────────────────────────────────
load_dotenv(Path(__file__).parent / '.env')

KITE_TOKEN_PATH  = Path(os.getenv('KITE_TOKEN_PATH', ''))   # path to gap trading's kite_token.json
KITE_API_KEY     = os.getenv('KITE_API_KEY')
LOG_DIR          = Path(os.getenv('OPTIONS_LOG_DIR', str(Path(__file__).parent / 'logs')))
STARTING_CAPITAL = float(os.getenv('OPTIONS_STARTING_CAPITAL', '100000'))
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'paper_trader.log'),
    ]
)
log = logging.getLogger(__name__)

# ── Strategy imports ───────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))
import strategies.bear_call_spread as bcs_mod
import strategies.bull_put_spread  as bps_mod
import strategies.batman           as batman_mod
import strategies.strip            as strip_mod
import strategies.long_straddle    as straddle_mod

# ── Constants ──────────────────────────────────────────────────────────────────
LOT_SIZE         = 75
STRIKE_STEP      = 50
MARGIN_BUF       = 2.0
DD_LIMIT         = 0.15
PAUSE_WEEKS      = 4
MONITOR_INTERVAL = 30          # seconds between SL/TP checks
NIFTY_SYMBOL     = 'NSE:NIFTY 50'

# ── NSE Holidays 2025 (update each year) ──────────────────────────────────────
NSE_HOLIDAYS = {
    date(2025, 2, 26), date(2025, 3, 14), date(2025, 3, 31),
    date(2025, 4, 10), date(2025, 4, 14), date(2025, 4, 18),
    date(2025, 5,  1), date(2025, 8, 15), date(2025, 8, 27),
    date(2025, 10, 2), date(2025, 10, 21), date(2025, 10, 22),
    date(2025, 11, 5), date(2025, 12, 25),
}

def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in NSE_HOLIDAYS

# ── Strategy definitions (optimised SL/TP from 2024 backtesting) ──────────────
STRATEGIES = [
    {'id': 'BCS_DTE1',  'type': 'BCS',     'dte': 1, 'sl': 0.90, 'tp': 0.80, 'span': 25_000, 'max_lots': 5, 'name': 'Bear Call Spread DTE1'},
    {'id': 'BCS_DTE2',  'type': 'BCS',     'dte': 2, 'sl': 1.00, 'tp': 0.80, 'span': 25_000, 'max_lots': 5, 'name': 'Bear Call Spread DTE2'},
    {'id': 'BCS_DTE3',  'type': 'BCS',     'dte': 3, 'sl': 1.00, 'tp': 0.80, 'span': 25_000, 'max_lots': 5, 'name': 'Bear Call Spread DTE3'},
    {'id': 'BCS_DTE4',  'type': 'BCS',     'dte': 4, 'sl': 1.00, 'tp': 0.80, 'span': 25_000, 'max_lots': 5, 'name': 'Bear Call Spread DTE4'},
    {'id': 'BPS_DTE2',  'type': 'BPS',     'dte': 2, 'sl': 0.65, 'tp': 0.80, 'span': 25_000, 'max_lots': 5, 'name': 'Bull Put Spread DTE2'},
    {'id': 'BPS_DTE3',  'type': 'BPS',     'dte': 3, 'sl': 0.75, 'tp': 0.80, 'span': 25_000, 'max_lots': 5, 'name': 'Bull Put Spread DTE3'},
    {'id': 'BPS_DTE4',  'type': 'BPS',     'dte': 4, 'sl': 0.75, 'tp': 0.80, 'span': 25_000, 'max_lots': 5, 'name': 'Bull Put Spread DTE4'},
    {'id': 'STRIP_DTE4','type': 'STRIP',   'dte': 4, 'sl': 1.00, 'tp': 0.25, 'span': 25_000, 'max_lots': 5, 'name': 'Strip DTE4'},
    {'id': 'BAT_DTE2',  'type': 'BATMAN',  'dte': 2, 'sl': 0.90, 'tp': 0.80, 'span': 90_000, 'max_lots': 1, 'name': 'Batman DTE2'},
    {'id': 'STAD_DTE1', 'type': 'STRADDLE','dte': 1, 'sl': 0.90, 'tp': 0.35, 'span': 20_000, 'max_lots': 5, 'name': 'Long Straddle DTE1'},
]

# ── Kite client ────────────────────────────────────────────────────────────────
def get_kite() -> Optional[KiteConnect]:
    """
    Monday: gap trading doesn't run, so self-login via kite_auth.
    Tue-Fri: wait for gap trading's token (written by entry.py at 9:25).
             Paper trader sleeps 15s first, so gap trading auth always wins —
             one login per day, no token conflicts.
    """
    import importlib.util, sys as _sys
    _spec = importlib.util.spec_from_file_location("kite_auth", Path(__file__).parent / "kite_auth.py")
    kite_auth = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(kite_auth)

    today     = date.today().isoformat()
    is_monday = date.today().weekday() == 0

    if is_monday:
        log.info("Monday — self-login (gap trading not running)")
        try:
            return kite_auth.get_kite(force_refresh=True)
        except Exception as e:
            log.error(f"Self-login failed: {e}")
            return None

    # Tue-Fri: read gap trading token (entry.py runs at 9:25, same time as us;
    # our 15s sleep ensures their auth completes first)
    if not KITE_TOKEN_PATH or not KITE_TOKEN_PATH.exists():
        log.error(f"Token file not found: {KITE_TOKEN_PATH}")
        return None

    try:
        cached = json.loads(KITE_TOKEN_PATH.read_text())
    except Exception as e:
        log.error(f"Could not read token file {KITE_TOKEN_PATH}: {e}")
        return None

    if cached.get('date') != today:
        log.error(f"Gap trading token is stale (dated {cached.get('date')}). Has entry.py run yet?")
        return None

    kite = KiteConnect(api_key=KITE_API_KEY)
    kite.set_access_token(cached['access_token'])
    log.info(f"Kite authenticated via gap trading token (dated {today})")
    return kite

_instruments: Optional[list] = None

def load_instruments(kite: KiteConnect) -> list:
    global _instruments
    if _instruments is None:
        raw          = kite.instruments('NFO')
        _instruments = [i for i in raw
                        if i['name'] == 'NIFTY'
                        and i['instrument_type'] in ('CE', 'PE')]
        log.info(f"Loaded {len(_instruments)} NIFTY NFO instruments")
    return _instruments

def find_instrument(kite: KiteConnect, expiry: date, strike: float, right: str) -> Optional[dict]:
    for inst in load_instruments(kite):
        if (inst['expiry'] == expiry
                and float(inst['strike']) == float(strike)
                and inst['instrument_type'] == right):
            return inst
    return None

def get_ltp(kite: KiteConnect, tradingsymbols: list[str]) -> dict:
    """Returns {tradingsymbol: ltp}. Retries once on failure."""
    if not tradingsymbols:
        return {}
    full = [f"NFO:{s}" for s in tradingsymbols]
    for attempt in range(2):
        try:
            data = kite.ltp(full)
            return {s: data[f"NFO:{s}"]['last_price']
                    for s in tradingsymbols if f"NFO:{s}" in data}
        except Exception as e:
            log.warning(f"LTP fetch attempt {attempt+1} failed: {e}")
            time.sleep(2)
    return {}

def get_nifty_spot(kite: KiteConnect) -> Optional[float]:
    try:
        return kite.ltp([NIFTY_SYMBOL])[NIFTY_SYMBOL]['last_price']
    except Exception as e:
        log.error(f"Spot fetch failed: {e}")
        return None

# ── Expiry & entry date helpers ────────────────────────────────────────────────
def get_upcoming_expiries(n: int = 15) -> list[date]:
    """Next n Nifty weekly expiry dates (Tuesdays from Sep 2 2025; holiday-adjusted to previous trading day)."""
    result = []
    d = date.today()
    while len(result) < n:
        if d.weekday() == 1:  # Tuesday
            exp = d
            while not is_trading_day(exp):
                exp -= timedelta(days=1)
            result.append(exp)
        d += timedelta(days=1)
    return result

def get_entry_date(expiry: date, dte: int) -> date:
    """Date that is `dte` trading days before expiry."""
    count = 0
    d     = expiry - timedelta(days=1)
    while True:
        if is_trading_day(d):
            count += 1
            if count == dte:
                return d
        d -= timedelta(days=1)

# ── Leg construction ───────────────────────────────────────────────────────────
def build_legs(strategy: dict, atm: int) -> list:
    t = strategy['type']
    if t == 'BCS':     return bcs_mod.get_legs(atm, STRIKE_STEP, lots=1, width=4)
    if t == 'BPS':     return bps_mod.get_legs(atm, STRIKE_STEP, lots=1, width=4)
    if t == 'BATMAN':  return batman_mod.get_legs(atm, STRIKE_STEP, lots=1, mid_width=1, outer_width=3, far_width=6)
    if t == 'STRIP':   return strip_mod.get_legs(atm, STRIKE_STEP, lots=1)
    if t == 'STRADDLE':return straddle_mod.get_legs(atm, STRIKE_STEP, lots=1)
    raise ValueError(f"Unknown strategy type: {t}")

def compute_max_loss(legs, entry_px: dict) -> float:
    strikes = [l.strike for l in legs]
    spots   = np.arange(min(strikes) - 10*STRIKE_STEP, max(strikes) + 11*STRIKE_STEP, STRIKE_STEP)
    worst   = 0.0
    for s in spots:
        pnl = 0.0
        for l in legs:
            intr = max(0, s - l.strike) if l.right == 'CE' else max(0, l.strike - s)
            ep   = entry_px[(l.strike, l.right)]
            pnl += ((ep - intr) if l.action == 'SELL' else (intr - ep)) * l.lots * LOT_SIZE
        worst = min(worst, pnl)
    return abs(worst)

def compute_charges(nc: float, xp: float, n_legs: int) -> float:
    brok = 20 * 2 * n_legs
    tv   = abs(nc) + abs(xp)
    stt  = 0.000625 * abs(nc)
    exc  = 0.00053  * tv
    gst  = 0.18 * (brok + exc)
    sebi = (tv / 1e7) * 10
    return round(brok + stt + exc + gst + sebi, 2)

def position_pnl(position: dict, ltp: dict) -> float:
    """Current unrealised PnL per lot from live LTP."""
    pnl = 0.0
    for l in position['legs']:
        price = ltp.get(l['tradingsymbol'], l['entry_price'])
        ep    = l['entry_price']
        pnl  += ((ep - price) if l['action'] == 'SELL' else (price - ep)) * l['leg_lots'] * LOT_SIZE
    return pnl

# ── State persistence ──────────────────────────────────────────────────────────
def state_file(strat_id: str) -> Path:
    return LOG_DIR / f"{strat_id}.json"

def load_state(strat_id: str) -> dict:
    f = state_file(strat_id)
    if f.exists():
        return json.loads(f.read_text())
    return {
        'strategy_id':         strat_id,
        'current_capital':     STARTING_CAPITAL,
        'peak_capital':        STARTING_CAPITAL,
        'pause_until':         None,
        'current_month':       None,
        'current_lots':        1,
        'position':            None,
        'trade_history':       [],
    }

def save_state(strat_id: str, state: dict):
    state_file(strat_id).write_text(json.dumps(state, indent=2, default=str))

# ── Trade entry ────────────────────────────────────────────────────────────────
def enter_position(kite: KiteConnect, strategy: dict, state: dict, expiry: date) -> bool:
    today = date.today()
    cap   = state['current_capital']
    span  = strategy['span']

    if cap < span:
        log.warning(f"[{strategy['id']}] Capital Rs{cap:,.0f} < SPAN Rs{span:,} — cannot enter")
        return False

    # Monthly lot recalc
    m = f"{today.year}-{today.month:02d}"
    if state['current_month'] != m:
        eff  = span * MARGIN_BUF
        lots = min(strategy['max_lots'], max(1, int(cap // eff)))
        state['current_lots']  = lots
        state['current_month'] = m
        log.info(f"[{strategy['id']}] New month {m}: lots={lots} (cap=Rs{cap:,.0f}, eff=Rs{eff:,.0f})")

    lots = state['current_lots']

    # Spot & ATM
    spot = get_nifty_spot(kite)
    if spot is None:
        return False
    atm  = round(spot / STRIKE_STEP) * STRIKE_STEP
    legs = build_legs(strategy, atm)

    # Fetch instrument tokens
    leg_data = []
    for l in legs:
        inst = find_instrument(kite, expiry, l.strike, l.right)
        if inst is None:
            log.error(f"[{strategy['id']}] Instrument not found: {l.strike}{l.right} exp={expiry}")
            return False
        leg_data.append({'leg': l, 'symbol': inst['tradingsymbol'], 'token': inst['instrument_token']})

    # Fetch entry LTP
    symbols = [ld['symbol'] for ld in leg_data]
    ltp     = get_ltp(kite, symbols)
    if len(ltp) < len(symbols):
        log.error(f"[{strategy['id']}] LTP fetch incomplete")
        return False

    entry_px = {(ld['leg'].strike, ld['leg'].right): ltp[ld['symbol']] for ld in leg_data}
    nc       = sum(entry_px[(l.strike, l.right)] * l.lots * LOT_SIZE *
                   (1 if l.action == 'SELL' else -1) for l in legs)
    ml       = compute_max_loss(legs, entry_px)
    sl_t     = -strategy['sl'] * ml   # per lot
    tp_t     =  strategy['tp'] * abs(nc)  # per lot

    position = {
        'entry_date':          today.isoformat(),
        'expiry':              expiry.isoformat(),
        'atm':                 atm,
        'lots':                lots,
        'legs': [
            {
                'strike':       ld['leg'].strike,
                'right':        ld['leg'].right,
                'action':       ld['leg'].action,
                'leg_lots':     ld['leg'].lots,
                'entry_price':  entry_px[(ld['leg'].strike, ld['leg'].right)],
                'tradingsymbol':ld['symbol'],
            }
            for ld in leg_data
        ],
        'net_credit_per_lot':  round(nc, 2),
        'max_loss_per_lot':    round(ml, 2),
        'sl_thresh_per_lot':   round(sl_t, 2),
        'tp_thresh_per_lot':   round(tp_t, 2),
    }

    state['position'] = position
    save_state(strategy['id'], state)

    log.info(f"[{strategy['id']}] ENTERED | ATM={atm} lots={lots} expiry={expiry} "
             f"credit=Rs{nc:+,.0f}/lot SL=Rs{sl_t:,.0f} TP=Rs{tp_t:,.0f}")
    for l in legs:
        ep = entry_px[(l.strike, l.right)]
        log.info(f"  {l.action:4s} {l.lots}x {l.strike}{l.right} @ Rs{ep:.2f}")
    return True

# ── Trade exit ─────────────────────────────────────────────────────────────────
def exit_position(kite: KiteConnect, strategy: dict, state: dict, reason: str, pnl_per_lot: Optional[float] = None):
    pos = state['position']
    if pos is None:
        return

    if pnl_per_lot is None:
        # Fetch live LTP for exit price
        symbols = [l['tradingsymbol'] for l in pos['legs']]
        ltp     = get_ltp(kite, symbols)
        pnl_per_lot = position_pnl(pos, ltp)

    lots          = pos['lots']
    n_legs        = len(pos['legs'])
    nc            = pos['net_credit_per_lot']
    gross         = pnl_per_lot * lots
    charges       = compute_charges(nc * lots, pnl_per_lot * lots, n_legs * lots)
    slip          = 8.0 * n_legs * LOT_SIZE * 2 * lots  # Rs8/unit/leg round-trip
    net           = gross - charges - slip

    old_cap       = state['current_capital']
    state['current_capital'] += net
    state['peak_capital']     = max(state['peak_capital'], state['current_capital'])

    trade_record = {
        'entry_date':         pos['entry_date'],
        'expiry':             pos['expiry'],
        'atm':                pos['atm'],
        'lots':               lots,
        'net_credit_per_lot': nc,
        'exit_reason':        reason,
        'exit_time':          datetime.now().strftime('%H:%M'),
        'pnl_per_lot':        round(pnl_per_lot, 2),
        'gross_pnl':          round(gross, 2),
        'charges':            round(charges, 2),
        'slippage':           round(slip, 2),
        'net_pnl':            round(net, 2),
        'capital_before':     round(old_cap, 2),
        'capital_after':      round(state['current_capital'], 2),
    }
    state['trade_history'].append(trade_record)
    state['position'] = None

    # DD check
    peak = state['peak_capital']
    cap  = state['current_capital']
    if peak > 0 and (peak - cap) / peak >= DD_LIMIT:
        pause_until = (date.today() + timedelta(weeks=PAUSE_WEEKS)).isoformat()
        state['pause_until'] = pause_until
        log.warning(f"[{strategy['id']}] DD {(peak-cap)/peak:.1%} triggered — paused until {pause_until}")

    save_state(strategy['id'], state)
    log.info(f"[{strategy['id']}] EXIT [{reason}] | gross=Rs{gross:+,.0f} "
             f"charges=Rs{charges:,.0f} slip=Rs{slip:,.0f} net=Rs{net:+,.0f} "
             f"capital=Rs{state['current_capital']:,.0f}")

# ── Main loop ──────────────────────────────────────────────────────────────────
def main():
    today = date.today()
    if not is_trading_day(today):
        log.info(f"{today} is not a trading day. Exiting.")
        return

    log.info(f"=== Paper Trader started {today} ===")

    # Brief pause so gap trading entry.py (also at 09:25) has time to write today's token
    time.sleep(15)

    kite = get_kite()
    if kite is None:
        log.error("Aborting — no valid token available.")
        return
    expiries = get_upcoming_expiries(15)
    states   = {s['id']: load_state(s['id']) for s in STRATEGIES}

    # Pre-compute entry dates for today
    entry_map: dict[str, date] = {}   # strat_id -> expiry to enter today
    for strat in STRATEGIES:
        for exp in expiries:
            if exp <= today:
                continue
            ed = get_entry_date(exp, strat['dte'])
            if ed == today:
                entry_map[strat['id']] = exp
                break

    log.info(f"Entry today: {[f'{k}→{v}' for k,v in entry_map.items()] or 'none'}")

    # ── Wait until 09:25 for entries ────────────────────────────────────────
    def now_hm():
        n = datetime.now()
        return n.hour, n.minute

    while now_hm() < (9, 25):
        time.sleep(15)

    # ── Enter positions ──────────────────────────────────────────────────────
    for strat in STRATEGIES:
        sid   = strat['id']
        state = states[sid]

        # Skip if paused
        if state.get('pause_until'):
            pu = date.fromisoformat(state['pause_until'])
            if today <= pu:
                log.info(f"[{sid}] PAUSED until {pu}")
                continue
            else:
                state['pause_until'] = None
                state['peak_capital'] = state['current_capital']
                save_state(sid, state)
                log.info(f"[{sid}] Pause ended, resuming")

        # Skip if already in a position (carry-over from previous day)
        if state.get('position'):
            pos_expiry = date.fromisoformat(state['position']['expiry'])
            if pos_expiry >= today:
                log.info(f"[{sid}] Carrying open position from {state['position']['entry_date']}")
                continue
            else:
                # Stale position (missed exit) — close it at market
                log.warning(f"[{sid}] Stale position found (expired {pos_expiry}), closing")
                exit_position(kite, strat, state, 'STALE_EXIT')

        # Enter if today is entry day
        if sid in entry_map:
            enter_position(kite, strat, state, entry_map[sid])

    # ── Monitoring loop 09:25 → 15:20 ────────────────────────────────────────
    log.info("Monitoring loop started...")
    while now_hm() < (15, 20):
        time.sleep(MONITOR_INTERVAL)

        # Collect all open position symbols
        open_symbols = set()
        for strat in STRATEGIES:
            pos = states[strat['id']].get('position')
            if pos:
                open_symbols.update(l['tradingsymbol'] for l in pos['legs'])

        if not open_symbols:
            continue

        ltp = get_ltp(kite, list(open_symbols))

        for strat in STRATEGIES:
            sid   = strat['id']
            state = states[sid]
            pos   = state.get('position')
            if not pos:
                continue

            pnl = position_pnl(pos, ltp)

            if pnl <= pos['sl_thresh_per_lot'] and strat['sl'] < 1.0:
                log.info(f"[{sid}] SL HIT  pnl=Rs{pnl:+,.0f}/lot thresh=Rs{pos['sl_thresh_per_lot']:,.0f}")
                exit_position(kite, strat, state, 'STOP LOSS', pnl)

            elif pnl >= pos['tp_thresh_per_lot']:
                log.info(f"[{sid}] TP HIT  pnl=Rs{pnl:+,.0f}/lot thresh=Rs{pos['tp_thresh_per_lot']:,.0f}")
                exit_position(kite, strat, state, 'TARGET HIT', pnl)

    # ── 15:20 force exit all remaining positions ───────────────────────────────
    log.info("15:20 — force-exiting all open positions")
    for strat in STRATEGIES:
        sid   = strat['id']
        state = states[sid]
        if state.get('position'):
            pos = state['position']
            # Check if position is expiring today
            pos_expiry = date.fromisoformat(pos['expiry'])
            if pos_expiry == today:
                exit_position(kite, strat, state, '15:20 EXPIRY EXIT')
            else:
                # Multi-day position (DTE > 1) — log PnL but keep position open
                symbols = [l['tradingsymbol'] for l in pos['legs']]
                ltp     = get_ltp(kite, symbols)
                pnl     = position_pnl(pos, ltp)
                log.info(f"[{sid}] EOD (expiry {pos_expiry}): unrealised PnL=Rs{pnl*pos['lots']:+,.0f}")
                save_state(sid, state)

    # ── Daily summary ──────────────────────────────────────────────────────────
    log.info("=" * 60)
    log.info("DAILY SUMMARY")
    log.info(f"  {'Strategy':<25} {'Capital':>12} {'ROI':>8} {'Trades':>7}")
    log.info("  " + "-" * 56)
    for strat in STRATEGIES:
        sid   = strat['id']
        state = states[sid]
        cap   = state['current_capital']
        roi   = (cap - STARTING_CAPITAL) / STARTING_CAPITAL * 100
        n     = len(state['trade_history'])
        log.info(f"  {strat['name']:<25} Rs{cap:>9,.0f} {roi:>7.1f}% {n:>7}")
    log.info("=" * 60)


if __name__ == '__main__':
    main()
