# strategies/ — Strategy Leg Definitions

Shared library of NIFTY options strategy modules. Used by both `backtest_notebooks/` (historical research) and `curr_live/` (live paper trader). Each module exports a single `get_legs()` function.

---

## Files

| File | Strategy | Structure | Bias |
|---|---|---|---|
| `base.py` | Base types | `StrategyLeg` dataclass | — |
| `bear_call_spread.py` | Bear Call Spread | SELL ATM CE + BUY (ATM + width) CE | Mildly bearish |
| `bear_put_spread.py` | Bear Put Spread | BUY ATM PE + SELL (ATM − width) PE | Bearish |
| `bull_call_spread.py` | Bull Call Spread | BUY ATM CE + SELL (ATM + width) CE | Bullish |
| `bull_put_spread.py` | Bull Put Spread | SELL ATM PE + BUY (ATM − width) PE | Mildly bullish |
| `iron_condor.py` | Iron Condor | BPS + BCS combined | Market-neutral |
| `iron_butterfly.py` | Iron Butterfly | ATM SELL straddle + wing hedges | Market-neutral |
| `batman.py` | Batman | Wide iron condor with double-wide wings | Market-neutral |
| `strip.py` | Strip | BUY 1 CE + BUY 2 PE (at ATM) | Bearish straddle |
| `long_straddle.py` | Long Straddle | BUY ATM CE + BUY ATM PE | Breakout (long vol) |
| `long_strangle.py` | Long Strangle | BUY OTM CE + BUY OTM PE | Breakout (long vol) |
| `short_straddle.py` | Short Straddle | SELL ATM CE + SELL ATM PE | Range-bound (short vol) |
| `short_strangle.py` | Short Strangle | SELL OTM CE + SELL OTM PE | Range-bound (short vol) |
| `short_put.py` | Short Put | SELL ATM PE | Mildly bullish |
| `__init__.py` | Package init | — | — |

---

## Interface

All strategy modules follow this interface:

```python
def get_legs(atm_strike: int, strike_step: int, lots: int = 1, **kwargs) -> list[StrategyLeg]:
    ...
```

`StrategyLeg` is defined in `base.py`:

```python
@dataclass
class StrategyLeg:
    right: str    # "CE" or "PE"
    action: str   # "BUY" or "SELL"
    strike: int   # absolute strike price
    lots: int     # number of lots
```

`strike_step` is 50 for NIFTY (each strike is 50 apart). `atm_strike` is rounded to the nearest 50.

---

## Backtest Conclusions

From the grid search (400 combos, Jan 2024–Mar 2026, corrected sign):

- **Bear Call Spread** — top 30 results all BCS. Only strategy with backtest support.
- **Bull Put Spread** — paused in live paper trading after 15% DD within 3 weeks.
- **Batman** — paused in live after single large stop loss (-Rs 46k on 1 lot).
- **Strip** — strong live performance (+33.7% in 3 weeks) but too few trades to conclude.
- **Long Straddle** — paused after -30.4% on first trade.
- **Iron Condor, Short Straddle, Short Strangle, Short Put** — not deployed live.
