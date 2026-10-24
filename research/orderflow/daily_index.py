"""Daily NIFTY / BANKNIFTY index OHLC from Upstox v3 (public), written as daily_<SYMBOL>.json into the given folder."""
import json, sys, urllib.request
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}
out = sys.argv[1]
for n, k in [("NIFTY", "NSE_INDEX%7CNifty%2050"), ("BANKNIFTY", "NSE_INDEX%7CNifty%20Bank")]:
    rows = {}
    for a, b in [("2016-01-01", "2018-12-31"), ("2019-01-01", "2021-12-31"), ("2022-01-01", "2024-12-31"), ("2025-01-01", "2026-10-23")]:
        d = json.load(urllib.request.urlopen(urllib.request.Request(
            f"https://api.upstox.com/v3/historical-candle/{k}/days/1/{b}/{a}", headers=UA), timeout=30))
        assert d["status"] == "success", d
        for c in d["data"]["candles"]:
            rows[c[0][:10]] = c[1:5]
    json.dump(dict(sorted(rows.items())), open(f"{out}/daily_{n}.json", "w"))
    print(n, len(rows), min(rows), max(rows))
