from dataclasses import dataclass


@dataclass
class StrategyLeg:
    right: str    # "CE" or "PE"
    action: str   # "BUY" or "SELL"
    strike: int   # absolute strike price
    lots: int     # number of lots


def get_legs(atm_strike: int, strike_step: int, lots: int = 1) -> list[StrategyLeg]:
    """Override this in each strategy module."""
    raise NotImplementedError
