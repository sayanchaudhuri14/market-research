"""Short straddle: SELL ATM CE + SELL ATM PE."""
from .base import StrategyLeg

NAME = "Short Straddle"


def get_legs(atm_strike: int, strike_step: int, lots: int = 1) -> list[StrategyLeg]:
    return [
        StrategyLeg(right="CE", action="SELL", strike=atm_strike, lots=lots),
        StrategyLeg(right="PE", action="SELL", strike=atm_strike, lots=lots),
    ]
