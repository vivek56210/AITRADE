"""Download 1-minute NSE index candles from Upstox's public v3 historical-candle API, cached per month.

No account or key is needed. The endpoint rejects Python's default User-Agent, so a browser one is sent.
Index (spot) candles carry no volume; callers weight each minute equally (time-at-price profile).
"""

from __future__ import annotations

import csv
import json
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path

from .models import Bar

API = "https://api.upstox.com/v3/historical-candle"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
INSTRUMENT_KEYS = {"NIFTY": "NSE_INDEX|Nifty 50", "BANKNIFTY": "NSE_INDEX|Nifty Bank"}
EARLIEST = date(2022, 1, 1)


def month_ranges(start: date, end: date) -> list[tuple[date, date]]:
    out, s = [], start
    while s <= end:
        month_end = (s.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        e = min(end, month_end)
        out.append((s, e))
        s = e + timedelta(days=1)
    return out


def parse_candles(payload: dict) -> list[Bar]:
    if payload.get("status") != "success":
        raise ValueError(f"Upstox error: {payload.get('errors') or payload}")
    bars = []
    for c in payload["data"]["candles"]:
        ts = datetime.fromisoformat(c[0]).replace(tzinfo=None)
        bars.append(Bar(ts, float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])))
    return sorted(bars, key=lambda b: b.ts)


def _get(url: str, retries: int = 4) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def fetch_month(symbol: str, start: date, end: date, get: Callable[[str], dict] = _get) -> list[Bar]:
    key = urllib.parse.quote(INSTRUMENT_KEYS[symbol], safe="")
    return parse_candles(get(f"{API}/{key}/minutes/1/{end}/{start}"))


def _write(path: Path, bars: list[Bar]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for b in bars:
            w.writerow([b.ts.isoformat(sep=" "), b.open, b.high, b.low, b.close, b.volume])
    tmp.replace(path)


def _read(path: Path) -> list[Bar]:
    with open(path, newline="") as f:
        return [Bar(datetime.fromisoformat(r["timestamp"]), float(r["open"]), float(r["high"]), float(r["low"]),
                    float(r["close"]), float(r["volume"])) for r in csv.DictReader(f)]


def fetch_index_1m(symbol: str, start: date, end: date, cache_dir: Path | None = None,
                   get: Callable[[str], dict] = _get, today: date | None = None,
                   on_month: Callable[[date, int], None] | None = None) -> list[Bar]:
    """1-minute bars for [start, end]. Completed months are cached; the current month is always refetched."""
    if symbol not in INSTRUMENT_KEYS:
        raise ValueError(f"unknown symbol {symbol}; expected one of {', '.join(INSTRUMENT_KEYS)}")
    today = today or date.today()
    start, end = max(start, EARLIEST), min(end, today)
    if start > end:
        raise ValueError(f"empty date range (Upstox 1-minute history starts {EARLIEST})")
    bars: list[Bar] = []
    for s, e in month_ranges(start, end):
        month_start = s.replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        complete = month_end < today
        path = cache_dir / symbol / f"{month_start:%Y-%m}.csv" if cache_dir else None
        if path and complete and path.exists():
            month = _read(path)
        else:
            month = fetch_month(symbol, month_start, min(month_end, today), get)
            if path and complete:
                _write(path, month)
            if get is _get:
                time.sleep(0.3)
        if on_month:
            on_month(month_start, len(month))
        bars += [b for b in month if s <= b.ts.date() <= e]
    return bars
