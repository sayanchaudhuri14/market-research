"""Long Strangle: BUY OTM CE + BUY OTM PE. Net debit, long volatility.

Cheaper than Long Straddle; requires a larger move to profit.
Maximum loss = net debit paid (when spot stays between the two strikes).
Breakeven     = sell_strike ± net_debit / lot_size (roughly).

width : strike steps OTM for both legs (buy ATM+width CE, buy ATM-width PE).
"""
from .base import StrategyLeg

NAME = "Long Strangle"
DEFAULT_WIDTH = 2   # 100 pts OTM each side


def get_legs(
    atm_strike: int,
    strike_step: int,
    lots: int = 1,
    width: int = DEFAULT_WIDTH,
) -> list[StrategyLeg]:
    return [
        StrategyLeg(right="CE", action="BUY", strike=atm_strike + width * strike_step, lots=lots),
        StrategyLeg(right="PE", action="BUY", strike=atm_strike - width * strike_step, lots=lots),
    ]
