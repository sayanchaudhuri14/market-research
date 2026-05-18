"""Bear Call Spread: SELL lower CE + BUY higher CE. Net credit, mildly bearish.

Maximum profit = net credit received (when spot closes below sell_strike at expiry).
Maximum loss   = (buy_strike - sell_strike) × lot_size - net_credit
                 (when spot closes above buy_strike).

width : strike steps between the two legs (sell ATM CE, buy ATM + width CE).
"""
from .base import StrategyLeg

NAME = "Bear Call Spread"
DEFAULT_WIDTH = 4   # 200 pts


def get_legs(
    atm_strike: int,
    strike_step: int,
    lots: int = 1,
    width: int = DEFAULT_WIDTH,
) -> list[StrategyLeg]:
    return [
        StrategyLeg(right="CE", action="SELL", strike=atm_strike,                   lots=lots),
        StrategyLeg(right="CE", action="BUY",  strike=atm_strike + width * strike_step, lots=lots),
    ]
