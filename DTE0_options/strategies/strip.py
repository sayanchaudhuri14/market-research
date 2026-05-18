"""Strip: BUY 1x ATM CE + BUY 2x ATM PE. Net debit, bearish long volatility.

Like a Long Straddle but with double the downside participation.
Profits from a large move in either direction; profits more on a downside move.
Maximum loss = net debit paid (when spot pins exactly at ATM at expiry).
"""
from .base import StrategyLeg

NAME = "Strip"


def get_legs(
    atm_strike: int,
    strike_step: int,
    lots: int = 1,
) -> list[StrategyLeg]:
    return [
        StrategyLeg(right="CE", action="BUY", strike=atm_strike, lots=lots),
        StrategyLeg(right="PE", action="BUY", strike=atm_strike, lots=2 * lots),
    ]
