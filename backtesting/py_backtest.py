# ── Full backtest script with session-wise saving ─────────────────────────────
import numpy as np
import pandas as pd
import pickle
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path
from datetime import date, timedelta, datetime
from datetime import time as dtime
from scipy.stats import norm as _norm
from scipy.optimize import newton
import warnings

warnings.filterwarnings("ignore")

# ── Configuration ──────────────────────────────────────────────────────────────
STOP_LOSS_PCT      = 0.4
PROFIT_TARGET_PCT  = 0.4
LOT_SIZE           = 75
STRIKE_STEP        = 50
STRIKES_OTM        = 1
RISK_FREE_RATE     = 0.065
BROKERAGE          = 80
BACKTEST_DAYS      = 252 * 1
BASE_RATE          = 54.5

DTE0_MAX_LOTS      = 10    # cap lots on expiry day (DTE=0); BS unreliable + huge spreads
MAX_LOTS           = 20    # hard global cap on any single trade regardless of DTE

# ── SIGNAL MODE ────────────────────────────────────────────────────────────────
# Options: "ALL"  →  trade both bearish and bullish signals (original behaviour)
#          "BULLISH_ONLY"  →  skip all bearish signals, only trade bullish
#          "BEARISH_ONLY"  →  skip all bullish signals, only trade bearish
SIGNAL_MODE = "BEARISH_ONLY"

# ──────────────────────────────────────────────────────────────────────────────

_cwd = Path.cwd()
BASE = _cwd if (_cwd / "v2" / "v2_aligned_dataset.csv").exists() else _cwd.parent

ALIGNED_CSV   = BASE / "v2" / "v2_aligned_dataset.csv"
MINUTE_CACHE  = BASE / "v2" / "kite_minute_cache"
SIGNALS_CSV   = BASE / "v2" / "v2_reliable_signals.csv"
OUTPUT_DIR    = BASE / "v2" / "backtest_outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Cell 2: Load aligned dataset + define top-3 bear/bull signals ──────────────
aligned = pd.read_csv(ALIGNED_CSV, parse_dates=["india_date"])
aligned = aligned.sort_values("india_date").reset_index(drop=True)
aligned["VIX_INDIA_level"] = aligned["VIX_INDIA_level"].ffill().bfill()

backtest_df = aligned.tail(BACKTEST_DAYS).copy().reset_index(drop=True)
start_date = backtest_df["india_date"].iloc[0].date()
end_date   = backtest_df["india_date"].iloc[-1].date()

print(f"Backtest period : {start_date}  to  {end_date}")
print(f"Trading days    : {len(backtest_df)}")
print(f"Signal mode     : {SIGNAL_MODE}")
print(f"Max lots (global cap) : {MAX_LOTS}  |  DTE=0 cap : {DTE0_MAX_LOTS}")

reliable = pd.read_csv(SIGNALS_CSV)

top_bearish = (
    reliable[reliable["P_Down"] > BASE_RATE]
    .sort_values("Edge", ascending=False)
    .head(3)
    .reset_index(drop=True)
)

top_bullish = (
    reliable[reliable["P_Down"] < (100 - BASE_RATE)]
    .sort_values("P_Down", ascending=True)
    .head(3)
    .reset_index(drop=True)
)

print("\nTop 3 BEARISH signal combos:")
for _, r in top_bearish.iterrows():
    print(
        f'  [{int(r["Level"])}] {r["Signal"]:<55} '
        f'P(DOWN)={r["P_Down"]:.1f}%  Edge=+{r["Edge"]:.1f}%  N={int(r["N"])}'
    )

print("\nTop 3 BULLISH signal combos:")
for _, r in top_bullish.iterrows():
    print(
        f'  [{int(r["Level"])}] {r["Signal"]:<55} '
        f'P(UP)={100 - r["P_Down"]:.1f}%  Edge=+{abs(r["Edge"]):.1f}%  N={int(r["N"])}'
    )

# ── Cell 3: Load NIFTY minute data from cache ──────────────────────────────────
all_chunks = []
for pkl_path in sorted(MINUTE_CACHE.glob("minute_256265_*.pkl")):
    with open(pkl_path, "rb") as f:
        chunk = pickle.load(f)

    chunk.index = pd.to_datetime(chunk.index)

    if chunk.index.tzinfo is None:
        chunk.index = chunk.index.tz_localize("Asia/Kolkata")

    lo = pd.Timestamp(start_date) - pd.Timedelta(days=1)
    hi = pd.Timestamp(end_date) + pd.Timedelta(days=1)

    mask = (chunk.index >= lo.tz_localize("Asia/Kolkata")) & (chunk.index <= hi.tz_localize("Asia/Kolkata"))
    if mask.sum() > 0:
        all_chunks.append(chunk[mask])

if all_chunks:
    minute_all = pd.concat(all_chunks).sort_index()
    print(f"\nMinute data loaded : {len(minute_all):,} rows")
    print(f"Date range         : {minute_all.index[0].date()}  to  {minute_all.index[-1].date()}")
    print(f"Columns            : {list(minute_all.columns)}")
else:
    print("WARNING: No minute data found in cache for backtest range.")
    minute_all = pd.DataFrame()

# ── Cell 4: Compute binary signals + classify each backtest day ─────────────────
GAP_THR   = 0.0015
GAP_LARGE = 0.0050

def compute_signals(row):
    return {
        "Gap Up"          : float(row["gap_pct"]) >  GAP_THR,
        "Gap Up Strong"   : float(row["gap_pct"]) >  GAP_LARGE,
        "Gap Down"        : float(row["gap_pct"]) < -GAP_THR,
        "Prev India UP"   : float(row["prev_india_ret"]) > 0,
        "Prev India DOWN" : float(row["prev_india_ret"]) < 0,
        "US UP"           : float(row["SP500_ret"]) > 0,
        "US DOWN"         : float(row["SP500_ret"]) < 0,
        "SGX UP"          : float(row["SGX_ret"]) > 0,
        "SGX DOWN"        : float(row["SGX_ret"]) < 0,
        "DAX UP"          : float(row["DAX_ret"]) > 0,
        "VIX Rising"      : float(row["VIX_US_ret"]) > 0.03,
        "VIX Falling"     : float(row["VIX_US_ret"]) < 0,
        "VIX Spike"       : float(row["VIX_US_ret"]) > 0.05,
    }

def check_combo(signals, signal_str):
    return all(signals.get(s.strip(), False) for s in signal_str.split("+"))

bear_combos = list(top_bearish["Signal"])
bull_combos = list(top_bullish["Signal"])

trade_days = []
for _, row in backtest_df.iterrows():
    sigs = compute_signals(row)

    # Evaluate which combos fire, then filter by SIGNAL_MODE
    bear_fired = [c for c in bear_combos if check_combo(sigs, c)] if SIGNAL_MODE != "BULLISH_ONLY" else []
    bull_fired = [c for c in bull_combos if check_combo(sigs, c)] if SIGNAL_MODE != "BEARISH_ONLY" else []

    if bear_fired and bull_fired:
        action, combo_fired = "CONFLICT", None
    elif bear_fired:
        action, combo_fired = "BEARISH", bear_fired[0]
    elif bull_fired:
        action, combo_fired = "BULLISH", bull_fired[0]
    else:
        action, combo_fired = "NO_SIGNAL", None

    trade_days.append({
        "india_date"  : row["india_date"],
        "india_open"  : float(row["india_open"]),
        "gap_pct"     : float(row["gap_pct"]),
        "vix_india"   : float(row["VIX_INDIA_level"]),
        "dir_60"      : int(row["dir_60"]),
        "ret_60"      : float(row["ret_60"]),
        "action"      : action,
        "combo_fired" : combo_fired,
    })

trade_days_df = pd.DataFrame(trade_days)

print("\nSignal distribution across backtest period:")
for k, v in trade_days_df["action"].value_counts().items():
    print(f"  {k:<12}: {v:>3} days  ({v/len(trade_days_df)*100:.1f}%)")
print(f"\nTrade-able days : {(trade_days_df['action'].isin(['BEARISH', 'BULLISH'])).sum()}")

# ── Cell 5: Black-Scholes pricing + trade simulation function ──────────────────
def bs_price(S, K, T, r, sigma, opt_type="CE"):
    """Black-Scholes price in index points. opt_type = CE or PE."""
    if T <= 1e-7:
        return max(0.0, S - K) if opt_type == "CE" else max(0.0, K - S)

    sq = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / sq
    d2 = d1 - sq

    if opt_type == "CE":
        return float(S * _norm.cdf(d1) - K * np.exp(-r * T) * _norm.cdf(d2))
    return float(K * np.exp(-r * T) * _norm.cdf(-d2) - S * _norm.cdf(-d1))

def nearest_thursday(d):
    """Current-or-next Thursday. If d is Thursday, returns same day (DTE=0)."""
    days = (3 - d.weekday()) % 7
    return d + timedelta(days=days)

def simulate_trade(trade_date, action, nifty_open, vix_india, minute_df):
    """
    Simulate one options trade minute-by-minute using BS pricing.
    Returns dict with trade details + P&L, or None if degenerate.
    """
    if isinstance(trade_date, pd.Timestamp):
        trade_date = trade_date.date()

    expiry = nearest_thursday(trade_date)
    dte = (expiry - trade_date).days

    atm = round(nifty_open / STRIKE_STEP) * STRIKE_STEP
    if action == "BEARISH":
        strike = atm - STRIKE_STEP * STRIKES_OTM
        opt_type = "PE"
    else:
        strike = atm + STRIKE_STEP * STRIKES_OTM
        opt_type = "CE"

    iv_raw = vix_india / 100.0
    iv = iv_raw * (1.30 if dte <= 2 else 1.15 if dte <= 4 else 1.05)

    def tte(t_obj):
        """Time to expiry in years from t_obj (time) on trade_date."""
        expiry_dt = datetime.combine(expiry, dtime(15, 30))
        current_dt = datetime.combine(trade_date, t_obj)
        secs = (expiry_dt - current_dt).total_seconds()
        return max(secs, 0.0) / (365.25 * 24 * 3600)

    entry_price = bs_price(nifty_open, strike, tte(dtime(9, 15)), RISK_FREE_RATE, iv, opt_type)
    if entry_price < 0.5:
        return None

    sl_price = entry_price * (1 - STOP_LOSS_PCT)
    tp_price = entry_price * (1 + PROFIT_TARGET_PCT)

    day_min = minute_df[minute_df.index.date == trade_date]
    day_min = day_min.between_time("09:16", "10:15")

    exit_price = None
    exit_reason = "10:15 exit"
    exit_time = "10:15"

    for ts, m in day_min.iterrows():
        spot = float(m["close"])
        t_now = ts.to_pydatetime().replace(tzinfo=None).time()
        price = bs_price(spot, strike, tte(t_now), RISK_FREE_RATE, iv, opt_type)

        if price <= sl_price:
            exit_price, exit_reason, exit_time = sl_price, "Stop Loss", str(t_now)[:5]
            break
        if price >= tp_price:
            exit_price, exit_reason, exit_time = tp_price, "Target Hit", str(t_now)[:5]
            break

    if exit_price is None:
        spot_last = float(day_min.iloc[-1]["close"]) if len(day_min) > 0 else nifty_open
        exit_price = bs_price(spot_last, strike, tte(dtime(10, 15)), RISK_FREE_RATE, iv, opt_type)

    pnl_pts = exit_price - entry_price
    pnl_rs = pnl_pts * LOT_SIZE - BROKERAGE

    return {
        "expiry"     : expiry,
        "dte"        : dte,
        "opt_type"   : opt_type,
        "strike"     : int(strike),
        "atm"        : int(atm),
        "iv_pct"     : round(iv * 100, 1),
        "entry_pts"  : round(entry_price, 2),
        "exit_pts"   : round(exit_price, 2),
        "exit_reason": exit_reason,
        "exit_time"  : exit_time,
        "pnl_pts"    : round(pnl_pts, 2),
        "pnl_rs"     : round(pnl_rs, 2),
    }

_chk = bs_price(22000, 21950, 5/365, RISK_FREE_RATE, 0.15, "PE")
print(f"\nBS sanity check: NIFTY=22000, 1-OTM PUT (21950), DTE=5, VIX=15% -> {_chk:.1f} pts")
print("  (Expected: ~100-150 pts for weekly OTM put)")

# ── Cell 6: Run the backtest ───────────────────────────────────────────────────
tradeable = trade_days_df[trade_days_df["action"].isin(["BEARISH", "BULLISH"])].copy()
print(f"\nRunning backtest on {len(tradeable)} tradeable days...")

results = []
skipped = 0

for _, trow in tradeable.iterrows():
    res = simulate_trade(
        trade_date = trow["india_date"],
        action     = trow["action"],
        nifty_open = trow["india_open"],
        vix_india  = trow["vix_india"],
        minute_df  = minute_all,
    )
    if res is None:
        skipped += 1
        continue

    actual_dir = int(trow["dir_60"])
    pred_dir = -1 if trow["action"] == "BEARISH" else +1
    correct = (pred_dir == actual_dir)

    results.append({
        "Date"        : trow["india_date"].date(),
        "Signal"      : trow["action"],
        "Combo"       : trow["combo_fired"],
        "NIFTY Open"  : int(round(trow["india_open"])),
        "Gap%"        : f"{trow['gap_pct']:+.2%}",
        "Strike"      : f"{res['strike']} {res['opt_type']}",
        "ATM"         : res["atm"],
        "DTE"         : res["dte"],
        "IV%"         : res["iv_pct"],
        "Entry (pts)" : res["entry_pts"],
        "Exit (pts)"  : res["exit_pts"],
        "Exit Reason" : res["exit_reason"],
        "Exit Time"   : res["exit_time"],
        "P&L (pts)"   : res["pnl_pts"],
        "P&L (Rs)"    : res["pnl_rs"],
        "Actual"      : "DOWN" if actual_dir == -1 else "UP",
        "Actual Ret%" : f"{trow['ret_60']:+.2%}",
        "Correct?"    : "YES" if correct else "NO",
    })

results_df = pd.DataFrame(results)

print(f"Done. Trades simulated : {len(results_df)}")
if skipped:
    print(f"Skipped (degenerate)   : {skipped}")
if len(results_df) > 0:
    wins = (results_df["P&L (Rs)"] > 0).sum()
    pnl = results_df["P&L (Rs)"].sum()
    print(f"Wins / Losses          : {wins} / {len(results_df)-wins}")
    print(f"Total P&L              : Rs{pnl:,.0f}")

# ── Cell 7: Trade log table ─────────────────────────────────────────────────────
pd.set_option("display.max_rows", 200)
pd.set_option("display.max_columns", 25)
pd.set_option("display.width", 220)

if len(results_df) == 0:
    print("No trades to display.")
else:
    display_cols = [
        "Date", "Signal", "NIFTY Open", "Gap%", "Strike", "DTE", "IV%",
        "Entry (pts)", "Exit (pts)", "Exit Reason", "Exit Time",
        "P&L (pts)", "P&L (Rs)", "Actual", "Actual Ret%", "Correct?"
    ]
    log = results_df[display_cols].copy()

    sep = "=" * 200
    h1 = "NIFTY OPTIONS BACKTEST — FULL TRADE LOG"
    h2 = f"Mode={SIGNAL_MODE}  |  SL={STOP_LOSS_PCT:.0%} premium  |  Target={PROFIT_TARGET_PCT:.0%} premium  |  {STRIKES_OTM}-strike OTM  |  Exit at SL / Target / 10:15 AM  |  MaxLots={MAX_LOTS} (DTE0={DTE0_MAX_LOTS})"
    print(sep)
    print(f"{h1:^200}")
    print(f"{h2:^200}")
    print(sep)
    print(log.to_string(index=False))
    print(sep)

    bear_log = results_df[results_df["Signal"] == "BEARISH"]
    bull_log = results_df[results_df["Signal"] == "BULLISH"]

    for lbl, sub in [("ALL", results_df), ("BEARISH", bear_log), ("BULLISH", bull_log)]:
        if len(sub) == 0:
            continue
        wr = (sub["P&L (Rs)"] > 0).mean() * 100
        acc = (sub["Correct?"] == "YES").mean() * 100
        tot = sub["P&L (Rs)"].sum()
        print(f"  {lbl:<8}: {len(sub):>3} trades  |  Win rate {wr:.1f}%  |  Pred accuracy {acc:.1f}%  |  Total P&L Rs{tot:,.0f}")

# ── Cell 8: Performance metrics + session-wise ledger ──────────────────────────
def compute_xirr(cash_flows, dates):
    def xnpv(rate):
        return sum(cf / ((1 + rate) ** ((d - dates[0]).days / 365.0)) for cf, d in zip(cash_flows, dates))

    try:
        return newton(xnpv, 0.1)
    except Exception:
        return None

def metrics_block(df, label, save_prefix=None):
    """
    Compounding capital tracker with:
      - Minimum 5 lots per trade
      - Lot scaling by available capital
      - DTE=0 cap at DTE0_MAX_LOTS
      - Global hard cap at MAX_LOTS (prevents runaway lot sizes on any DTE)
    Returns:
        cap_curve: list of equity values after each trade
        session_df: per-trade ledger with lots/refills/capital tracking
    """
    if len(df) == 0:
        print(f"  {label}: no trades.")
        return [0.0], pd.DataFrame()

    capital = None
    cap_curve = []

    FIXED_LOTS = 5
    refill_count = 0
    total_refilled = 0.0
    refill_events = []

    cash_flows = []
    cash_dates = []

    session_log = []

    for i in range(len(df)):
        row = df.iloc[i]
        trade_date = pd.to_datetime(row["Date"])

        entry_pts = float(row["Entry (pts)"])
        pnl_pts   = float(row["P&L (pts)"])
        exit_pts  = float(row["Exit (pts)"])

        cost_per_lot = entry_pts * LOT_SIZE
        if cost_per_lot <= 0:
            continue

        if capital is None:
            capital = cost_per_lot * FIXED_LOTS
            initial_capital = capital
            cash_flows.append(-initial_capital)
            cash_dates.append(trade_date)

        capital_before = capital
        required_capital = cost_per_lot * FIXED_LOTS

        refill_amt = 0.0
        if capital_before < required_capital:
            refill_amt = required_capital - capital_before
            capital_before += refill_amt
            capital = capital_before

            refill_count += 1
            total_refilled += refill_amt
            refill_events.append((i, refill_amt))

            cash_flows.append(-refill_amt)
            cash_dates.append(trade_date)

        capital_after_refill = capital_before

        # ── Lot sizing with caps ───────────────────────────────────────────────
        uncapped_lots = max(FIXED_LOTS, int(capital_after_refill / cost_per_lot))
        dte_val = int(row["DTE"])

        # Step 1: apply DTE=0 specific cap
        dte0_limited = min(uncapped_lots, DTE0_MAX_LOTS) if dte_val == 0 else uncapped_lots

        # Step 2: apply global hard cap (protects against runaway on any DTE)
        lots = min(dte0_limited, MAX_LOTS)

        lot_cap_applied = uncapped_lots > lots
        cap_reason = ""
        if lot_cap_applied:
            if dte_val == 0 and uncapped_lots > DTE0_MAX_LOTS:
                cap_reason = f"DTE0 cap (would be {uncapped_lots})"
            else:
                cap_reason = f"Global cap (would be {uncapped_lots})"
        # ──────────────────────────────────────────────────────────────────────

        trade_pnl = pnl_pts * LOT_SIZE * lots - BROKERAGE * lots
        capital_after_trade = capital_after_refill + trade_pnl
        capital = capital_after_trade

        cap_curve.append(round(capital_after_trade, 2))

        session_log.append({
            "Trade #"             : i + 1,
            "Date"                : trade_date.date(),
            "Signal"              : row["Signal"],
            "Combo"               : row["Combo"],
            "NIFTY Open"          : row["NIFTY Open"],
            "Strike"              : row["Strike"],
            "ATM"                 : row["ATM"],
            "DTE"                 : row["DTE"],
            "IV%"                 : row["IV%"],
            "Entry (pts)"         : entry_pts,
            "Exit (pts)"          : exit_pts,
            "P&L (pts)"           : pnl_pts,
            "Cost / lot (Rs)"     : round(cost_per_lot, 2),
            "Uncapped Lots"       : uncapped_lots,
            "Lots"                : lots,
            "Lot Cap Applied?"    : "YES" if lot_cap_applied else "no",
            "Cap Reason"          : cap_reason,
            "Capital Before"      : round(capital_before - refill_amt, 2),
            "Refill Amount"       : round(refill_amt, 2),
            "Capital After Refill": round(capital_after_refill, 2),
            "Trade P&L (Rs)"      : round(trade_pnl, 2),
            "Capital After Trade" : round(capital_after_trade, 2),
            "Cumulative Refill"   : round(total_refilled, 2),
            "Refill Count"        : refill_count,
            "Exit Reason"         : row["Exit Reason"],
            "Exit Time"           : row["Exit Time"],
            "Correct?"            : row["Correct?"],
            "Actual"              : row["Actual"],
            "Actual Ret%"         : row["Actual Ret%"],
        })

    cash_flows.append(capital)
    cash_dates.append(pd.to_datetime(df.iloc[-1]["Date"]))

    total_invested = initial_capital + total_refilled
    total_profit = capital - total_invested
    net_return = (total_profit / total_invested) * 100 if total_invested > 0 else 0

    xirr = compute_xirr(cash_flows, cash_dates)

    print(f'\n{"="*58}')
    print(f'  {label} — CAPITAL SUMMARY')
    print(f'{"="*58}')
    print(f'  Initial capital    : Rs{initial_capital:,.0f}')
    print(f'  Total invested     : Rs{total_invested:,.0f}')
    print(f'  Total profit       : Rs{total_profit:,.0f}')
    print(f'  Final capital      : Rs{capital:,.0f}')
    print(f'  Total refilled     : Rs{total_refilled:,.0f}')
    print(f'  Net return         : {net_return:+.2f}%')
    print(f'  Refill count       : {refill_count}')
    print(f'  Lot cap (DTE0/Max) : {DTE0_MAX_LOTS} / {MAX_LOTS}')

    if xirr is not None:
        print(f'  XIRR               : {xirr*100:.2f}%')
    else:
        print('  XIRR               : Could not compute')

    print(f'{"="*58}')

    if refill_events:
        print("\n  Refill events:")
        for idx, amt in refill_events:
            print(f"    Trade {idx + 1}: +Rs{amt:,.0f}")

    session_df = pd.DataFrame(session_log)

    return cap_curve, session_df


curves = {}
ledgers = {}

curves["ALL"], ledgers["ALL"] = metrics_block(results_df, "ALL TRADES", save_prefix="ALL")

bear_df = results_df[results_df["Signal"] == "BEARISH"].reset_index(drop=True)
bull_df = results_df[results_df["Signal"] == "BULLISH"].reset_index(drop=True)

curves["BEARISH"], ledgers["BEARISH"] = metrics_block(bear_df, "BEARISH ONLY", save_prefix="BEARISH")
curves["BULLISH"], ledgers["BULLISH"] = metrics_block(bull_df, "BULLISH ONLY", save_prefix="BULLISH")

# ── Cell 9: Charts ─────────────────────────────────────────────────────────────
if len(results_df) > 0:
    fig = plt.figure(figsize=(20, 13))
    gs = gridspec.GridSpec(2, 3, figure=fig)

    subsets = {
        "ALL": results_df,
        "BEARISH": bear_df,
        "BULLISH": bull_df,
    }

    for i, key in enumerate(["ALL", "BEARISH", "BULLISH"]):
        ax = fig.add_subplot(gs[0, i])
        cap = curves[key]
        if cap and cap != [0.0]:
            ax.plot(cap, color=("purple" if key == "ALL" else "red" if key == "BEARISH" else "green"))
            ax.set_title(f"{key} — Equity Curve")
            ax.set_xlabel("Trade #")
            ax.set_ylabel("Capital (Rs)")
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"₹{x:,.0f}"))
            ax.grid(True, alpha=0.3)

    for i, key in enumerate(["ALL", "BEARISH", "BULLISH"]):
        ax = fig.add_subplot(gs[1, i])
        sub = subsets[key]
        if len(sub) > 0:
            colors = ["green" if p > 0 else "red" for p in sub["P&L (Rs)"]]
            ax.bar(range(len(sub)), sub["P&L (Rs)"], color=colors, alpha=0.7)
            ax.axhline(0, color="black", linewidth=0.8)
            ax.set_title(f"{key} — Per-Trade P&L")
            ax.set_xlabel("Trade #")
            ax.set_ylabel("P&L (Rs)")
            ax.grid(True, alpha=0.3)

    fig.suptitle(
        f"NIFTY Backtest  |  Mode: {SIGNAL_MODE}  |  SL={STOP_LOSS_PCT:.0%}  TP={PROFIT_TARGET_PCT:.0%}  |  MaxLots={MAX_LOTS}  DTE0cap={DTE0_MAX_LOTS}",
        fontsize=13, fontweight="bold"
    )
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "backtest_charts.png", dpi=150, bbox_inches="tight")
    plt.show()

# ── FINAL: Save everything into ONE Excel file ────────────────────────────────

output_file = OUTPUT_DIR / "backtest_report.xlsx"

with pd.ExcelWriter(output_file, engine="openpyxl") as writer:

    # 0. Config sheet — so the Excel is self-documenting
    config_df = pd.DataFrame([
        {"Parameter": "SIGNAL_MODE",       "Value": SIGNAL_MODE},
        {"Parameter": "BACKTEST_DAYS",     "Value": BACKTEST_DAYS},
        {"Parameter": "STOP_LOSS_PCT",     "Value": f"{STOP_LOSS_PCT:.0%}"},
        {"Parameter": "PROFIT_TARGET_PCT", "Value": f"{PROFIT_TARGET_PCT:.0%}"},
        {"Parameter": "DTE0_MAX_LOTS",     "Value": DTE0_MAX_LOTS},
        {"Parameter": "MAX_LOTS",          "Value": MAX_LOTS},
        {"Parameter": "LOT_SIZE",          "Value": LOT_SIZE},
        {"Parameter": "STRIKES_OTM",       "Value": STRIKES_OTM},
        {"Parameter": "RISK_FREE_RATE",    "Value": RISK_FREE_RATE},
        {"Parameter": "BROKERAGE",         "Value": BROKERAGE},
        {"Parameter": "Backtest start",    "Value": str(start_date)},
        {"Parameter": "Backtest end",      "Value": str(end_date)},
    ])
    config_df.to_excel(writer, sheet_name="Config", index=False)

    # 1. Full trade log
    if len(results_df) > 0:
        results_df.to_excel(writer, sheet_name="Trade Log", index=False)

    # 2. Session ledger — ALL trades
    if "ALL" in ledgers and len(ledgers["ALL"]) > 0:
        ledgers["ALL"].to_excel(writer, sheet_name="Session Ledger (ALL)", index=False)

    # 3. Session ledger — BEARISH only
    if "BEARISH" in ledgers and len(ledgers["BEARISH"]) > 0:
        ledgers["BEARISH"].to_excel(writer, sheet_name="Session Ledger (BEAR)", index=False)

    # 4. Session ledger — BULLISH only
    if "BULLISH" in ledgers and len(ledgers["BULLISH"]) > 0:
        ledgers["BULLISH"].to_excel(writer, sheet_name="Session Ledger (BULL)", index=False)

    # 5. Summary
    summary_data = []
    for key in ["ALL", "BEARISH", "BULLISH"]:
        df = results_df if key == "ALL" else (bear_df if key == "BEARISH" else bull_df)
        if len(df) == 0:
            continue

        total_trades = len(df)
        wins = (df["P&L (Rs)"] > 0).sum()
        total_pnl = df["P&L (Rs)"].sum()
        win_rate = (wins / total_trades) * 100
        acc = (df["Correct?"] == "YES").mean() * 100

        led = ledgers.get(key)
        final_capital = led["Capital After Trade"].iloc[-1] if led is not None and len(led) > 0 else None
        initial_capital = led["Capital After Refill"].iloc[0] - led["Refill Amount"].iloc[0] + led["Cost / lot (Rs)"].iloc[0] * 5 if led is not None and len(led) > 0 else None
        total_invested = (led["Capital Before"].iloc[0] + led["Cumulative Refill"].iloc[-1]) if led is not None and len(led) > 0 else None

        summary_data.append({
            "Type"              : key,
            "Trades"            : total_trades,
            "Wins"              : int(wins),
            "Win Rate %"        : round(win_rate, 2),
            "Pred Accuracy %"   : round(acc, 2),
            "Total PnL 1-lot (Rs)": round(total_pnl, 2),
            "Final Capital (Rs)": round(final_capital, 2) if final_capital else "N/A",
            "Total Invested (Rs)": round(total_invested, 2) if total_invested else "N/A",
        })

    summary_df = pd.DataFrame(summary_data)
    if len(summary_df) > 0:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)

    # 6. Equity curves
    equity_data = {}
    for key, curve in curves.items():
        if curve and curve != [0.0]:
            equity_data[key] = pd.Series(curve, name=key)

    if equity_data:
        equity_df = pd.concat(equity_data.values(), axis=1)
        equity_df.index.name = "Trade #"
        equity_df.to_excel(writer, sheet_name="Equity Curves", index=True)

print(f"\n✅ Excel report saved: {output_file}")
print(f"   Signal mode : {SIGNAL_MODE}")
print(f"   Trades      : {len(results_df)}")
if len(results_df) > 0:
    print(f"   Win rate    : {(results_df['P&L (Rs)'] > 0).mean()*100:.1f}%")
    print(f"   Total P&L   : Rs{results_df['P&L (Rs)'].sum():,.0f}")