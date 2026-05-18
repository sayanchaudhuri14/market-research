# paper_trader/ — Earlier Paper Trader (Superseded)

An earlier version of the paper trading system. **Superseded by `curr_live/`** — do not use for new work.

---

## Files

| File | Purpose |
|---|---|
| `paper_trader.py` | Original 10-strategy paper trader (reads Kite token from gap trading's kite_token.json via `.env`) |
| `paper_Trader_live.py` | Live variant of the original paper trader |
| `kite_data.py` | Kite LTP helpers (older version) |
| `kite_auth.py` | Kite auth (older version, uses `.env` for API key) |
| `.env.example` | Template for environment variables |

---

## Differences vs curr_live/

| Aspect | paper_trader/ | curr_live/ |
|---|---|---|
| Auth | `.env` file + own `kite_auth.py` | `/home/ec2-user/Authorize_Kite/` shared auth |
| Kite token path | Configured via `KITE_TOKEN_PATH` env var | Hard-coded shared path |
| Strategies | 10 strategies (same set) | Same 10 strategies |
| Monitor interval | 60s | 30s |
| Status | Superseded | Active |

The `curr_live/` version was created to use the shared Authorize_Kite infrastructure that gap_trading also uses, avoiding duplicate auth management.
