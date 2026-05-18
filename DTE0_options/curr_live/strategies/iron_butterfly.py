"""Iron butterfly: SELL ATM CE + SELL ATM PE + BUY OTM CE + BUY OTM PE.

Same as iron condor except both sold legs are at ATM (same strike).
Maximum profit if spot closes exactly at ATM; capped loss on both sides.

wing_width : strike steps from ATM for the bought hedge legs.
"""
from .base import StrategyLeg

NAME = "Iron Butterfly"
DEFAULT_WING_WIDTH = 2


def get_legs(
    atm_strike: int,
    strike_step: int,
    lots: int = 1,
    wing_width: int = DEFAULT_WING_WIDTH,
) -> list[StrategyLeg]:
    return [
        StrategyLeg(right="CE", action="SELL", strike=atm_strike, lots=lots),
        StrategyLeg(right="PE", action="SELL", strike=atm_strike, lots=lots),
        StrategyLeg(right="CE", action="BUY",  strike=atm_strike + wing_width * strike_step, lots=lots),
        StrategyLeg(right="PE", action="BUY",  strike=atm_strike - wing_width * strike_step, lots=lots),
    ]
