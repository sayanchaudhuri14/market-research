# NIFTY Gap Strategy — Live Paper Trading (v4.3)

Buys a 1-OTM NIFTY PUT at 9:25 AM on days when a bearish signal combo fires.
Monitors SL (–15%) / TP (+40%) until 11:15 AM hard exit.
Runs Tue–Fri (skips Monday, NSE holidays, RBI MPC / Budget days).

**Signal version**: v4.3 — SGX signal uses `^N225` trade-day Open (Tokyo 09:00 JST ≈ 05:30 IST)
instead of NKD=F D-1 close. This captures 4+ hours of live Tokyo price action before the
9:25 IST entry, with no lookahead bias.

See `cron/v2/` for the original NKD=F D-1 close version.

---

## Key change vs v2

| | v2 | v4.3 |
|--|----|----|
| SGX ticker | `NKD=F` (CME futures, USD) | `^N225` (Nikkei 225 cash, JPY) |
| SGX timestamp | D-1 close | Trade-day Open (5:30 IST) |
| Fallback | D-1 NKD=F close | D-1 ^N225 close-to-close return |

The `SGX UP` / `SGX DOWN` signal labels are unchanged — the same signal combos in
`v2_reliable_signals.csv` are used. Only the underlying price series changes.

---

## Files

| File | Purpose |
|------|---------|
| `entry.py` | 9:25 AM — checks signals (with N225 open), buys 1-OTM NIFTY PE |
| `exit.py` | 9:27 AM — polls premium until SL/TP hit or 11:15 hard exit |
| `config.py` | All parameters (same as v2) |
| `kite_auth.py` | Zerodha Kite Connect token management |
| `kite_data.py` | Kite API helpers (spot price, option premium, 9:15 candle) |
| `v2_reliable_signals.csv` | Signal combo definitions (same as v2) |
| `.env` | `api_key`, `api_secret`, `user_id`, `password`, `totp_secret` |

---

## Setup

### 1. Install dependencies
```bash
pip install kiteconnect pyotp yfinance pandas pytz
```

### 2. Configure credentials
Copy `.env.example` to `.env` and fill in your values:
```
api_key      = <Kite Connect app API key>
api_secret   = <Kite Connect app API secret>
user_id      = <Zerodha client ID, e.g. AB1234>
password     = <Zerodha login password>
totp_secret  = <base32 TOTP seed>
```

### 3. Test authentication
```bash
python -c "from kite_auth import get_kite; k = get_kite(); print(k.profile()['user_name'])"
```

---

## Cron setup (EC2, Asia/Kolkata timezone)

Use a **separate log file** from v2 so both versions can run side-by-side:

```cron
# v4.3 Entry: 9:25 AM Tue–Fri
25 9 * * 2-5  cd /path/to/cron_v43 && python entry.py >> logs/cron_v43.log 2>&1

# v4.3 Exit monitor: 9:27 AM Tue–Fri
27 9 * * 2-5  cd /path/to/cron_v43 && python exit.py >> logs/exit_v43.log 2>&1
```

Ensure the EC2 timezone is set to IST:
```bash
sudo timedatectl set-timezone Asia/Kolkata
```

---

## Running both v2 and v4.3 simultaneously

Both versions write to their own `data/` subdirectory (relative to their own directory),
so `positions.json`, `state.json`, and `trade_log.jsonl` do not conflict as long as each
version is deployed to a separate folder on EC2.

Recommended EC2 layout:
```
/home/ec2-user/
├── cron_v2/          ← deploy gap_trading/cron/v2/
│   ├── data/
│   └── logs/
└── cron_v43/         ← deploy gap_trading/cron/v4.3/
    ├── data/
    └── logs/
```

---

## Runtime files (auto-created, not committed)

| File | Contents |
|------|----------|
| `kite_token.json` | Cached `access_token` for today |
| `kite_nfo_instruments.json` | NFO instruments list cached daily |
| `positions.json` | Current open position written by `entry.py` |
| `state.json` | Running capital updated after each exit |
| `logs/` | `trade_log.jsonl` (all events), `cron_v43.log`, `exit_v43.log` |
