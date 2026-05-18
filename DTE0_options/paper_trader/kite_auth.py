"""
kite_auth.py — Automated Kite Connect authentication using requests + pyotp.

No browser required. Full flow:
  1. POST credentials  → get request_id
  2. POST TOTP (auto-generated from TOTP secret)  → sets session cookie
  3. GET kite.trade/connect/login?api_key=...  → follows redirect → extract request_token
  4. generate_session(request_token, api_secret)  → access_token
  5. Cache access_token to kite_token.json (valid for the trading day)

Required .env keys (overnight_drift_Strategy/.env):
    api_key       = <your Kite Connect app API key>
    api_secret    = <your Kite Connect app API secret>
    user_id       = <your Zerodha client ID, e.g. AB1234>
    password      = <your Zerodha login password>
    totp_secret   = <base32 TOTP seed shown when you set up Zerodha authenticator>
                    (NOT the 6-digit code — the secret used to generate codes)
"""

import json
import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from typing import Optional

import requests
import pyotp
from kiteconnect import KiteConnect

# Paths
_CRON_DIR    = Path(__file__).parent
_ENV_FILE    = _CRON_DIR / ".env"
_TOKEN_FILE  = _CRON_DIR.parent / "kite_token.json"   # shared across v2 and v4.3

_LOGIN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":       "application/json, text/plain, */*",
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer":      "https://kite.zerodha.com/",
    "Origin":       "https://kite.zerodha.com",
}


def _read_env() -> dict:
    """Parse key = value pairs from the .env file."""
    env = {}
    with open(_ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def _fetch_fresh_access_token(env: dict) -> str:
    """
    Full automated login flow → returns a fresh access_token.
    Raises on any failure so the caller can surface the exact error.
    """
    api_key     = env["api_key"]
    api_secret  = env["api_secret"]
    user_id     = env["user_id"]
    password    = env["password"]
    totp_secret = env["totp_secret"]

    session = requests.Session()
    session.headers.update(_LOGIN_HEADERS)

    # ── Step 1: Submit credentials ──────────────────────────────────────────────
    resp = session.post(
        "https://kite.zerodha.com/api/login",
        data={"user_id": user_id, "password": password},
        timeout=15,
    )
    resp.raise_for_status()
    login_json = resp.json()
    if login_json.get("status") != "success":
        raise RuntimeError(f"Kite credential login failed: {login_json.get('message', login_json)}")
    request_id = login_json["data"]["request_id"]

    # ── Step 2: Submit TOTP ─────────────────────────────────────────────────────
    totp_code = pyotp.TOTP(totp_secret).now()
    resp = session.post(
        "https://kite.zerodha.com/api/twofa",
        data={
            "user_id":     user_id,
            "request_id":  request_id,
            "twofa_value": totp_code,
            "twofa_type":  "totp",
        },
        timeout=15,
    )
    resp.raise_for_status()
    twofa_json = resp.json()
    if twofa_json.get("status") != "success":
        raise RuntimeError(f"Kite TOTP verification failed: {twofa_json.get('message', twofa_json)}")

    # ── Step 3: Follow Kite Connect redirect to grab request_token ──────────────
    # We follow redirects manually so we stop as soon as the request_token appears
    # in the Location header — before requests tries to connect to the redirect_url
    # (which may be localhost or a domain with no server running).
    connect_url = f"https://kite.trade/connect/login?api_key={api_key}&v=3"
    url = connect_url
    final_url = None
    for _ in range(10):
        r = session.get(url, allow_redirects=False, timeout=15)
        location = r.headers.get("Location", "")
        if "request_token" in location:
            final_url = location
            break
        if not location:
            final_url = url
            break
        # Make relative redirects absolute
        if location.startswith("/"):
            parsed = urlparse(url)
            location = f"{parsed.scheme}://{parsed.netloc}{location}"
        url = location

    if not final_url:
        raise RuntimeError("Kite Connect redirect chain ended without a request_token.")

    params = parse_qs(urlparse(final_url).query)
    request_token: Optional[str] = params.get("request_token", [None])[0]
    if not request_token:
        raise RuntimeError(
            f"Could not extract request_token from redirect URL: {final_url}\n"
            "Check that your Kite Connect app redirect_url is set correctly."
        )

    # ── Step 4: Exchange request_token for access_token ─────────────────────────
    kite = KiteConnect(api_key=api_key)
    sess_data = kite.generate_session(request_token, api_secret=api_secret)
    return str(sess_data["access_token"])


def get_access_token(force_refresh: bool = False) -> str:
    """
    Return a valid access_token for today.
    Uses disk cache (kite_token.json); fetches fresh token if stale or missing.
    """
    today = datetime.date.today().isoformat()

    if not force_refresh and _TOKEN_FILE.exists():
        try:
            cached = json.loads(_TOKEN_FILE.read_text())
            if cached.get("date") == today and cached.get("access_token"):
                return cached["access_token"]
        except (json.JSONDecodeError, KeyError):
            pass  # corrupt cache → fall through to fresh login

    print("  [kite_auth] Logging in to Kite Connect ...", end=" ", flush=True)
    env = _read_env()
    access_token = _fetch_fresh_access_token(env)
    _TOKEN_FILE.write_text(json.dumps({"date": today, "access_token": access_token}))
    print("done.")
    return access_token


def get_kite(force_refresh: bool = False) -> KiteConnect:
    """Return a fully authenticated KiteConnect instance, ready to use."""
    env = _read_env()
    kite = KiteConnect(api_key=env["api_key"])
    kite.set_access_token(get_access_token(force_refresh=force_refresh))
    return kite
