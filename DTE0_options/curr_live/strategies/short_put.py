"""Single-leg short put: SELL 1-OTM PE."""
from .base import StrategyLeg

NAME = "Short Put"


def get_legs(atm_strike: int, strike_step: int, lots: int = 1) -> list[StrategyLeg]:
    return [
        StrategyLeg(right="PE", action="SELL", strike=atm_strike - strike_step, lots=lots),
    ]
