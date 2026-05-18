"""Long Straddle: BUY ATM CE + BUY ATM PE. Net debit, long volatility.

Profits when spot makes a large move in either direction by expiry.
Maximum loss = net debit paid (when spot pins exactly at ATM).
Breakeven     = ATM ± net_debit / lot_size.
"""
from .base import StrategyLeg

NAME = "Long Straddle"


def get_legs(
    atm_strike: int,
    strike_step: int,
    lots: int = 1,
) -> list[StrategyLeg]:
    return [
        StrategyLeg(right="CE", action="BUY", strike=atm_strike, lots=lots),
        StrategyLeg(right="PE", action="BUY", strike=atm_strike, lots=lots),
    ]
