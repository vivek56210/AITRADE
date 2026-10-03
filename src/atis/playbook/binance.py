"""Real order flow for crypto: Binance USD-M futures 1-minute klines with taker-buy volume.

Binance publishes free monthly (and daily) kline archives at data.binance.vision. Each candle
carries `taker_buy_volume`, the volume of trades where the buyer was the aggressor, so every bar
gets a true buy/sell split (buy = taker buy, sell = volume - taker buy) instead of the tick-rule
estimate. With that split the engine's delta, CVD-divergence and absorption checks use real
aggressor data. Prices track Delta Exchange India's BTCUSD/ETHUSD perpetuals closely, so signals
from this data are scored with Delta's fees.
"""

from __future__ import annotations

import csv
import io
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .models import Bar
from .upstox import USER_AGENT, month_ranges

BASE = "https://data.binance.vision/data/futures/um"
SYMBOLS = {"BTCUSD": "BTCUSDT", "ETHUSD": "ETHUSDT"}  # Delta symbol -> Binance perpetual
EARLIEST = date(2020, 1, 1)


def _download(url: str, retries: int = 4) -> bytes | None:
    """Zip bytes, or None when the archive does not exist (yet)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if attempt == retries - 1:
                raise
        except Exception:
            if attempt == retries - 1:
                raise
        time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def parse_klines(data: bytes) -> list[Bar]:
    """Kline zip -> Bars in naive UTC with buy/sell (aggressor) volume. Handles files with or without a header."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        text = z.read(z.namelist()[0]).decode()
    bars = []
    for row in csv.reader(io.StringIO(text)):
        if not row or not row[0].strip().isdigit():
            continue
        vol, buy = float(row[5]), float(row[9])
        ts = datetime.fromtimestamp(int(row[0]) / 1000, timezone.utc).replace(tzinfo=None)
        bars.append(Bar(ts, float(row[1]), float(row[2]), float(row[3]), float(row[4]), vol,
                        buy_volume=buy, sell_volume=max(vol - buy, 0.0)))
    return sorted(bars, key=lambda b: b.ts)


def _write(path: Path, bars: list[Bar]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp_utc", "open", "high", "low", "close", "volume", "buy_volume"])
        for b in bars:
            w.writerow([b.ts.isoformat(sep=" "), b.open, b.high, b.low, b.close, b.volume, b.buy_volume])
    tmp.replace(path)


def _read(path: Path) -> list[Bar]:
    out = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            vol, buy = float(r["volume"]), float(r["buy_volume"])
            out.append(Bar(datetime.fromisoformat(r["timestamp_utc"]), float(r["open"]), float(r["high"]),
                           float(r["low"]), float(r["close"]), vol, buy, max(vol - buy, 0.0)))
    return out


def fetch_month(pair: str, month: date, today: date, download: Callable[[str], bytes | None] = _download) -> list[Bar]:
    """One month: the monthly archive, or the daily archives while the monthly one is not published."""
    data = download(f"{BASE}/monthly/klines/{pair}/1m/{pair}-1m-{month:%Y-%m}.zip")
    if data is not None:
        return parse_klines(data)
    bars: list[Bar] = []
    d = month
    while d.month == month.month and d < today:
        day = download(f"{BASE}/daily/klines/{pair}/1m/{pair}-1m-{d:%Y-%m-%d}.zip")
        if day is not None:
            bars += parse_klines(day)
        d += timedelta(days=1)
    return bars


def fetch_flow_1m(symbol: str, start: date, end: date, cache_dir: Path | None = None,
                  download: Callable[[str], bytes | None] = _download, today: date | None = None,
                  on_month: Callable[[date, int], None] | None = None) -> list[Bar]:
    """1-minute UTC bars with real buy/sell volume for the UTC dates [start, end]; complete months are cached."""
    pair = SYMBOLS.get(symbol, symbol)
    today = today or datetime.now(timezone.utc).date()
    start, end = max(start, EARLIEST), min(end, today - timedelta(days=1))
    if start > end:
        raise ValueError("empty date range (Binance archives are published the day after)")
    bars: list[Bar] = []
    for s, e in month_ranges(start, end):
        month = s.replace(day=1)
        month_end = (month + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        complete = month_end < today
        path = cache_dir / pair / f"{month:%Y-%m}.csv" if cache_dir else None
        if path and complete and path.exists():
            rows = _read(path)
        else:
            rows = fetch_month(pair, month, today, download)
            if path and complete and rows:
                _write(path, rows)
        if on_month:
            on_month(month, len(rows))
        bars += [b for b in rows if s <= b.ts.date() <= e]
    return bars
