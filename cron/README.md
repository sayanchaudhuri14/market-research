# NIFTY Gap Strategy — Live Paper Trading

Buys a 1-OTM NIFTY PUT at 9:25 AM on days when a bearish signal combo fires.
Monitors SL (–15%) / TP (+40%) until 11:15 AM hard exit.
Runs Tue–Fri (skips Monday, NSE holidays, RBI MPC / Budget days).

---

## Files

| File | Purpose |
|------|---------|
| `entry.py` | Runs at 9:25 AM — checks signals, fetches live data via Kite, writes `positions.json` |
| `exit.py` | Runs after entry — polls option LTP via Kite every 2 min, hard exits at 11:15 AM |
| `config.py` | All strategy constants (capital, SL/TP %, lot size, holidays, etc.) |
| `kite_auth.py` | Automated Kite Connect login (credentials + TOTP → access token, cached daily) |
| `kite_data.py` | Kite API helpers: NIFTY spot, 9:15 open candle, option LTP |
| `v2_reliable_signals.csv` | Top-10 bearish signal combos from backtest (loaded at runtime) |

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
totp_secret  = <base32 TOTP seed — see note below>
```

**Getting your TOTP secret:**
Go to Kite → My Profile → Password & Security → Two-factor authentication → Setup TOTP → "Can't scan? Enter code manually". Copy the base32 key shown there.
If 2FA is already active, reset it to get a fresh secret.

### 3. Test authentication
```bash
python -c "from kite_auth import get_kite; k = get_kite(); print(k.profile()['user_name'])"
```

---

## Cron setup (EC2, Asia/Kolkata timezone)

```cron
# Entry: 9:25 AM Tue–Fri
25 9 * * 2-5  cd /path/to/cron && python entry.py >> logs/cron.log 2>&1

# Exit monitor: 9:27 AM Tue–Fri (starts 2 min after entry)
27 9 * * 2-5  cd /path/to/cron && python exit.py >> logs/exit.log 2>&1
```

Ensure the EC2 timezone is set to IST:
```bash
sudo timedatectl set-timezone Asia/Kolkata
```

---

## How authentication works

`kite_auth.py` automates the full Kite Connect login flow using plain HTTP — no browser needed:

1. POST credentials → get `request_id`
2. POST TOTP (auto-generated from `totp_secret` using `pyotp`) → session cookie set
3. Follow Kite Connect redirect manually, stop when `request_token` appears in `Location` header
4. Exchange `request_token` for `access_token` via `kite.generate_session()`
5. Cache `access_token` in `kite_token.json` — reused for the rest of the day

Both `entry.py` and `exit.py` call `get_kite()` — if the token was already cached by `entry.py` at 9:25 AM, `exit.py` at 9:27 AM reuses it with no second login.

---

## Runtime files (auto-created, not committed)

| File | Contents |
|------|----------|
| `kite_token.json` | Cached `access_token` for today |
| `kite_nfo_instruments.json` | NFO instruments list cached daily (~4k NIFTY options) |
| `positions.json` | Current open position written by `entry.py` |
| `state.json` | Running capital updated after each exit |
| `logs/` | `trade_log.jsonl` (all events), `cron.log`, `exit.log` |