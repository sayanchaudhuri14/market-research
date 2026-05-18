# curr_live/strategies/ — Deployed Strategy Modules

Deployed copy of the strategy library used by `paper_trader.py`. Interface is identical to the research copy in `DTE0_options/strategies/`.

This copy exists so that the EC2 cron can import strategies without depending on the research path. Any changes to strategy logic must be synced to both locations.

See [DTE0_options/strategies/README.md](../../strategies/README.md) for full documentation of each module.

---

## Deployed Subset

Only two strategies are currently active in `curr_live`:

| Module | Strategy | Used by |
|---|---|---|
| `bear_call_spread.py` | Bear Call Spread | BCS_DTE1, BCS_DTE2, BCS_DTE3, BCS_DTE4 |
| `strip.py` | Strip | STRIP_DTE4 |

All other modules (`batman.py`, `bear_put_spread.py`, `long_straddle.py`, etc.) are present but the paused strategies are not re-entering new positions until their `pause_until` date clears.
