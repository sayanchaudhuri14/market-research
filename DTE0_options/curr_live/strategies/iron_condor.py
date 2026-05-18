"""Iron condor: SELL OTM CE + BUY further OTM CE + SELL OTM PE + BUY further OTM PE.

sell_width : strike steps from ATM for the sold legs
buy_width  : strike steps from ATM for the bought (hedge) legs
"""
from .base import StrategyLeg

NAME = "Iron Condor"
DEFAULT_SELL_WIDTH = 1
DEFAULT_BUY_WIDTH  = 2


def get_legs(
    atm_strike: int,
    strike_step: int,
    lots: int = 1,
    sell_width: int = DEFAULT_SELL_WIDTH,
    buy_width: int = DEFAULT_BUY_WIDTH,
) -> list[StrategyLeg]:
    return [
        StrategyLeg(right="CE", action="SELL", strike=atm_strike + sell_width * strike_step, lots=lots),
        StrategyLeg(right="CE", action="BUY",  strike=atm_strike + buy_width  * strike_step, lots=lots),
        StrategyLeg(right="PE", action="SELL", strike=atm_strike - sell_width * strike_step, lots=lots),
        StrategyLeg(right="PE", action="BUY",  strike=atm_strike - buy_width  * strike_step, lots=lots),
    ]
