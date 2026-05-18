"""Bull Put Spread: SELL higher PE + BUY lower PE. Net credit, mildly bullish.

Maximum profit = net credit received (when spot closes above sell_strike at expiry).
Maximum loss   = (sell_strike - buy_strike) × lot_size - net_credit
                 (when spot closes below buy_strike).

width : strike steps between the two legs (sell ATM PE, buy ATM - width PE).
"""
from .base import StrategyLeg

NAME = "Bull Put Spread"
DEFAULT_WIDTH = 4   # 200 pts


def get_legs(
    atm_strike: int,
    strike_step: int,
    lots: int = 1,
    width: int = DEFAULT_WIDTH,
) -> list[StrategyLeg]:
    return [
        StrategyLeg(right="PE", action="SELL", strike=atm_strike,                   lots=lots),
        StrategyLeg(right="PE", action="BUY",  strike=atm_strike - width * strike_step, lots=lots),
    ]
