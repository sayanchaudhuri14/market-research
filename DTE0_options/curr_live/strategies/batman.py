"""Batman: double iron butterfly — layered short positions at two levels.

Structure (all short theta, all capped):
  Inner body : SELL 2x ATM CE  + SELL 2x ATM PE          (straddle, 2 lots)
  Mid hedge  : BUY  1x mid CE  + BUY  1x mid PE           (first hedge)
  Outer sell : SELL 1x outer CE + SELL 1x outer PE         (extra premium)
  Outer hedge: BUY  1x far CE  + BUY  1x far PE           (cap the tail risk)

Payoff profile has two profit humps (near ATM and near outer sold strikes)
with a saddle in between — resembling Batman's cowl when plotted.

mid_width   : steps from ATM for the mid hedge
outer_width : steps from ATM for the outer sold strike
far_width   : steps from ATM for the far hedge (should be > outer_width)
"""
from .base import StrategyLeg

NAME = "Batman"
DEFAULT_MID_WIDTH   = 1
DEFAULT_OUTER_WIDTH = 2
DEFAULT_FAR_WIDTH   = 3


def get_legs(
    atm_strike: int,
    strike_step: int,
    lots: int = 1,
    mid_width: int   = DEFAULT_MID_WIDTH,
    outer_width: int = DEFAULT_OUTER_WIDTH,
    far_width: int   = DEFAULT_FAR_WIDTH,
) -> list[StrategyLeg]:
    s = strike_step
    return [
        # Inner body — 2 lots
        StrategyLeg(right="CE", action="SELL", strike=atm_strike,                      lots=2 * lots),
        StrategyLeg(right="PE", action="SELL", strike=atm_strike,                      lots=2 * lots),
        # Mid hedge — 1 lot
        StrategyLeg(right="CE", action="BUY",  strike=atm_strike + mid_width   * s,    lots=lots),
        StrategyLeg(right="PE", action="BUY",  strike=atm_strike - mid_width   * s,    lots=lots),
        # Outer sell — 1 lot
        StrategyLeg(right="CE", action="SELL", strike=atm_strike + outer_width * s,    lots=lots),
        StrategyLeg(right="PE", action="SELL", strike=atm_strike - outer_width * s,    lots=lots),
        # Far hedge — 1 lot (cap tail risk)
        StrategyLeg(right="CE", action="BUY",  strike=atm_strike + far_width   * s,    lots=lots),
        StrategyLeg(right="PE", action="BUY",  strike=atm_strike - far_width   * s,    lots=lots),
    ]
