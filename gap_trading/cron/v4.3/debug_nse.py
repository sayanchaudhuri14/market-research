#!/usr/bin/env python3
"""Quick debug: test NSE session warm-up and option chain response."""
import time
import requests

NSE_BASE_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'sec-ch-ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
}

session = requests.Session()
session.headers.update(NSE_BASE_HEADERS)

print("Step 1: option-chain page (browser-like navigate)...")
session.headers['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
session.headers['sec-fetch-dest'] = 'document'
session.headers['sec-fetch-mode'] = 'navigate'
session.headers['sec-fetch-site'] = 'none'
r1 = session.get('https://www.nseindia.com/option-chain', timeout=15)
print(f"  status={r1.status_code}  cookies={list(session.cookies.keys())}")
time.sleep(2)

print("Step 2: marketStatus API (XHR warm-up)...")
session.headers['Accept'] = 'application/json, text/plain, */*'
session.headers['Referer'] = 'https://www.nseindia.com/option-chain'
session.headers['sec-fetch-dest'] = 'empty'
session.headers['sec-fetch-mode'] = 'cors'
session.headers['sec-fetch-site'] = 'same-origin'
r2 = session.get('https://www.nseindia.com/api/marketStatus', timeout=15)
print(f"  status={r2.status_code}  cookies={list(session.cookies.keys())}")
time.sleep(1)

print("Step 3: option-chain API...")
r3 = session.get('https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY', timeout=15)
print(f"  status={r3.status_code}")
print(f"  content-type={r3.headers.get('content-type')}")
print(f"  raw response (first 300 chars):\n{r3.text[:300]}")

try:
    data = r3.json()
    print(f"\n  top-level keys: {list(data.keys())}")
    if 'records' in data:
        print(f"  records keys: {list(data['records'].keys())}")
        print(f"  underlyingValue: {data['records'].get('underlyingValue')}")
    else:
        print("  'records' key not found in response")
except Exception as e:
    print(f"  JSON parse failed: {e}")
