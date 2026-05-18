"""Short strangle: SELL OTM CE + SELL OTM PE.

Wing width is the number of strike steps away from ATM.
Default width=1 means 1-OTM on each side.
"""
from .base import StrategyLeg

NAME = "Short Strangle"
DEFAULT_WIDTH = 1  # strike steps from ATM


def get_legs(atm_strike: int, strike_step: int, lots: int = 1, width: int = DEFAULT_WIDTH) -> list[StrategyLeg]:
    return [
        StrategyLeg(right="CE", action="SELL", strike=atm_strike + width * strike_step, lots=lots),
        StrategyLeg(right="PE", action="SELL", strike=atm_strike - width * strike_step, lots=lots),
    ]
