"""Bull Call Spread: BUY lower CE + SELL higher CE. Net debit, bullish.

Maximum profit = (sell_strike - buy_strike) × lot_size - net_debit
                 achieved when spot closes above sell_strike at expiry.
Maximum loss   = net_debit paid (when spot closes below buy_strike).

width : strike steps between the two legs (buy ATM, sell ATM + width).
"""
from .base import StrategyLeg

NAME = "Bull Call Spread"
DEFAULT_WIDTH = 4   # 200 pts


def get_legs(
    atm_strike: int,
    strike_step: int,
    lots: int = 1,
    width: int = DEFAULT_WIDTH,
) -> list[StrategyLeg]:
    return [
        StrategyLeg(right="CE", action="BUY",  strike=atm_strike,                   lots=lots),
        StrategyLeg(right="CE", action="SELL", strike=atm_strike + width * strike_step, lots=lots),
    ]
