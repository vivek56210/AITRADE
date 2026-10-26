"""Download 1-minute crypto perpetual candles from Delta Exchange India's public API, cached per month.

No account or key is needed for market data. Candles carry real traded volume (in contracts:
0.001 BTC for BTCUSD, 0.01 ETH for ETHUSD). The API returns at most 4,000 candles per request, so
requests are paged in 2.5-day windows. Timestamps are stored in UTC; `in_timezone` converts them to
the clock a session definition uses (UTC, New York, IST).
"""

from __future__ import annotations

import csv
import json
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from datetime import time as clock
from pathlib import Path
from zoneinfo import ZoneInfo

from .data import drop_short_sessions, to_sessions
from .models import Bar, Session
from .upstox import USER_AGENT, month_ranges

API = "https://api.india.delta.exchange/v2/history/candles"
LAUNCH = {"BTCUSD": date(2023, 12, 18), "ETHUSD": date(2024, 2, 5)}
PAGE_MINUTES = 3600  # below the API's 4,000-candle cap


class DeltaError(RuntimeError):
    pass


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


def parse_candles(payload: dict) -> list[Bar]:
    """Delta candles (newest first, epoch seconds) -> Bars in naive UTC, oldest first."""
    if not payload.get("success"):
        raise DeltaError(f"Delta error: {payload.get('error') or payload}")
    bars = [Bar(datetime.fromtimestamp(c["time"], timezone.utc).replace(tzinfo=None), float(c["open"]),
                float(c["high"]), float(c["low"]), float(c["close"]), float(c.get("volume") or 0.0))
            for c in payload["result"]]
    return sorted(bars, key=lambda b: b.ts)


def fetch_range(symbol: str, start: datetime, end: datetime, get: Callable[[str], dict] = _get) -> list[Bar]:
    """1-minute bars with start <= ts < end (naive UTC), paging under the API's cap."""
    out: dict[datetime, Bar] = {}
    t = start
    while t < end:
        stop = min(end, t + timedelta(minutes=PAGE_MINUTES))
        q = urllib.parse.urlencode({"resolution": "1m", "symbol": symbol,
                                    "start": int(t.replace(tzinfo=timezone.utc).timestamp()),
                                    "end": int(stop.replace(tzinfo=timezone.utc).timestamp())})
        for b in parse_candles(get(f"{API}?{q}")):
            if t <= b.ts < stop:
                out[b.ts] = b
        t = stop
        if get is _get:
            time.sleep(0.15)
    return [out[k] for k in sorted(out)]


def _write(path: Path, bars: list[Bar]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp_utc", "open", "high", "low", "close", "volume"])
        for b in bars:
            w.writerow([b.ts.isoformat(sep=" "), b.open, b.high, b.low, b.close, b.volume])
    tmp.replace(path)


def _read(path: Path) -> list[Bar]:
    with open(path, newline="") as f:
        return [Bar(datetime.fromisoformat(r["timestamp_utc"]), float(r["open"]), float(r["high"]),
                    float(r["low"]), float(r["close"]), float(r["volume"])) for r in csv.DictReader(f)]


def fetch_perp_1m(symbol: str, start: date, end: date, cache_dir: Path | None = None,
                  get: Callable[[str], dict] = _get, today: date | None = None,
                  on_month: Callable[[date, int], None] | None = None) -> list[Bar]:
    """1-minute UTC bars for the UTC dates [start, end]. Completed months are cached; the current month is refetched."""
    if symbol not in LAUNCH:
        raise ValueError(f"unknown symbol {symbol}; expected one of {', '.join(LAUNCH)}")
    today = today or datetime.now(timezone.utc).date()
    start, end = max(start, LAUNCH[symbol]), min(end, today)
    if start > end:
        raise ValueError(f"empty date range ({symbol} history starts {LAUNCH[symbol]})")
    bars: list[Bar] = []
    for s, e in month_ranges(start, end):
        month_start = s.replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        complete = month_end < today
        path = cache_dir / symbol / f"{month_start:%Y-%m}.csv" if cache_dir else None
        if path and complete and path.exists():
            month = _read(path)
        else:
            lo = datetime.combine(max(month_start, LAUNCH[symbol]), datetime.min.time())
            hi = datetime.combine(min(month_end, today) + timedelta(days=1), datetime.min.time())
            month = fetch_range(symbol, lo, hi, get)
            if path and complete:
                _write(path, month)
        if on_month:
            on_month(month_start, len(month))
        bars += [b for b in month if s <= b.ts.date() <= e]
    return bars


def in_timezone(bars: list[Bar], tz: str) -> list[Bar]:
    """Naive-UTC bars -> naive local-time bars in `tz` (an IANA name such as America/New_York)."""
    zone = ZoneInfo(tz)
    return [replace(b, ts=b.ts.replace(tzinfo=timezone.utc).astimezone(zone).replace(tzinfo=None)) for b in bars]


def crypto_sessions(bars_utc: list[Bar], tz: str, open_: clock, close: clock,
                    min_fraction: float = 0.8) -> list[Session]:
    """Split UTC bars into sessions on the local clock of `tz`; drop partial days and outage days."""
    return drop_short_sessions(to_sessions(in_timezone(bars_utc, tz), open_, close), min_fraction)
