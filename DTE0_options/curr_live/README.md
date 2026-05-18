# curr_live/ — Live Paper Trading System

The production paper trading system. Runs daily on EC2 at 9:25 AM, monitors positions until SL/TP or 15:20 hard exit, persists state in JSON files. No real orders placed — uses Kite LTP for real market prices.

---

## Folder Map

| Folder/File | Purpose |
|---|---|
| `cron/paper_trader.py` | Main cron script — entry, monitoring, exit |
| `cron/kite_data.py` | Kite LTP helpers |
| `strategies/` | Deployed copies of strategy leg definitions (same interface as root `strategies/`) |
| `logs/` | Per-strategy JSON state files + trade history |

---

## Deployed Strategies

10 strategies run simultaneously, each with independent capital (Rs 1,00,000 starting), lot sizing, and DD circuit-breaker.

| Strategy ID | Type | DTE | SL | TP | Basis |
|---|---|---|---|---|---|
| BCS_DTE1 | Bear Call Spread | 1 | 50% | 100% | Grid search |
| BCS_DTE2 | Bear Call Spread | 2 | 50% | 100% | Grid search #1 |
| BCS_DTE3 | Bear Call Spread | 3 | 50% | 100% | Grid search #2 |
| BCS_DTE4 | Bear Call Spread | 4 | 75% | 75% | Grid search #3 |
| BPS_DTE2 | Bull Put Spread | 2 | 50% | 100% | Symmetric to BCS |
| BPS_DTE3 | Bull Put Spread | 3 | 50% | 100% | Symmetric to BCS |
| BPS_DTE4 | Bull Put Spread | 4 | 75% | 75% | Symmetric to BCS |
| STRIP_DTE4 | Strip | 4 | 100% | 25% | Earlier research |
| BAT_DTE2 | Batman | 2 | 100% | 25% | Earlier research |
| STAD_DTE1 | Long Straddle | 1 | 50% | 100% | Earlier research |

BCS width = 4 strike steps = 200 pts.

---

## Live Performance (Apr 23 – May 15, 2026, ~3 weeks)

| Strategy | Capital | ROI | Trades | Status |
|---|---|---|---|---|
| STRIP_DTE4 | Rs 1,33,718 | +33.7% | 2 + open | Active |
| BCS_DTE1 | Rs 1,15,240 | +15.2% | 3 | Active |
| BCS_DTE4 | Rs 1,12,400 | +12.4% | 2 + open | Active |
| BCS_DTE2 | Rs 1,10,200 | +10.2% | 2 | Active |
| BCS_DTE3 | Rs 95,867 | -4.1% | 3 | Active |
| BPS_DTE2 | Rs 87,500 | -12.5% | 2 | **PAUSED** (DD) |
| BPS_DTE4 | Rs 84,000 | -16.0% | 2 | **PAUSED** |
| BPS_DTE3 | Rs 82,000 | -18.0% | 1 | **PAUSED** |
| BAT_DTE2 | Rs 66,940 | -33.1% | 2 | **PAUSED** (DD, resumes Jun 9) |
| STAD_DTE1 | Rs 69,600 | -30.4% | 1 | **PAUSED** |

3 weeks / 1–3 trades per strategy is not sufficient for statistical conclusions. Directionally consistent with grid search (BCS works, others don't).

---

## System Design

**Entry** (`paper_trader.py`):
1. Runs at 9:25 AM Tue–Fri via cron
2. Computes today's entry date for each strategy (DTE trading days before expiry)
3. Fetches NIFTY spot from Kite → ATM strike (rounded to 50)
4. Builds legs via strategy module → fetches leg LTPs
5. Computes max loss, sets SL/TP thresholds on net credit
6. Writes open position to `logs/{STRATEGY_ID}.json`

**Monitoring** (same process, runs until exit):
- Polls Kite every 30s
- Exits if net PnL ≤ SL threshold or ≥ TP threshold
- Hard exits at 15:20 on expiry day

**Lot sizing** (compounding):
- `current_lots = max(1, floor(current_capital / (max_loss_per_lot × MARGIN_BUF)))`
- Capped at `max_lots` (5 per strategy config)
- Recalculated monthly

**15% DD circuit-breaker**:
- Pauses strategy for 4 weeks if `(capital - peak_capital) / peak_capital < -0.15`
- `pause_until` date written to JSON; entry skipped until then

**Kite auth**:
- Token read from `/home/ec2-user/Authorize_Kite/kite_token.json`
- Written by separate kite_auth cron at 9:15 AM

---

## Cron (EC2)

```
25 9 * * 2-5  /home/ec2-user/venv/bin/python3 /home/ec2-user/Gap_Trading_Strategy/options/paper_trader/paper_trader.py >> .../logs/cron.log 2>&1
```
