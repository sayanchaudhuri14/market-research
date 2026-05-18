"""Bear Put Spread: BUY higher PE + SELL lower PE. Net debit, bearish.

Maximum profit = (buy_strike - sell_strike) × lot_size - net_debit
                 achieved when spot closes below sell_strike at expiry.
Maximum loss   = net_debit paid (when spot closes above buy_strike).

width : strike steps between the two legs (buy ATM PE, sell ATM - width PE).
"""
from .base import StrategyLeg

NAME = "Bear Put Spread"
DEFAULT_WIDTH = 4   # 200 pts


def get_legs(
    atm_strike: int,
    strike_step: int,
    lots: int = 1,
    width: int = DEFAULT_WIDTH,
) -> list[StrategyLeg]:
    return [
        StrategyLeg(right="PE", action="BUY",  strike=atm_strike,                   lots=lots),
        StrategyLeg(right="PE", action="SELL", strike=atm_strike - width * strike_step, lots=lots),
    ]
