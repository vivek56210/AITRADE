"""Market data: Binance public archives for the long backtest, Delta Exchange India candles for live.

Binance spot hourly candles go back to 2017-08 and USD-M funding to 2019-09, which covers the 2018
and 2022 bear markets. Delta's BTCUSD perpetual only starts on 2023-12-18, so it cannot. The live bot
reads Delta's own candles, so its signal is computed on the instrument it trades.
"""

from __future__ import annotations

import csv
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .signals import Candle

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
BINANCE = "https://data.binance.vision/data"
DELTA_CANDLES = "https://api.india.delta.exchange/v2/history/candles"
FIRST_MONTH = date(2017, 8, 1)


def _get_bytes(url: str, retries: int = 4) -> bytes | None:
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
        except OSError:
            if attempt == retries - 1:
                raise
        time.sleep(2 ** attempt)
    return None


def _months(start: date, end: date) -> list[date]:
    out, m = [], start.replace(day=1)
    while m <= end:
        out.append(m)
        m = (m + timedelta(days=32)).replace(day=1)
    return out


def _unzip(blob: bytes) -> str:
    z = zipfile.ZipFile(io.BytesIO(blob))
    return z.read(z.namelist()[0]).decode()


def sync_binance(symbol: str, cache: Path, today: date | None = None,
                 log: Callable[[str], None] = lambda m: None) -> None:
    """Cache Binance spot 1h klines and USD-M funding per month; the current month comes from daily files."""
    today = today or datetime.now(timezone.utc).date()
    this_month = today.replace(day=1)
    for kind, tmpl in (("spot1h", f"{BINANCE}/spot/monthly/klines/{symbol}/1h/{symbol}-1h-{{m}}.zip"),
                       ("funding", f"{BINANCE}/futures/um/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{{m}}.zip")):
        folder = cache / kind / symbol
        folder.mkdir(parents=True, exist_ok=True)
        for m in _months(FIRST_MONTH, this_month - timedelta(days=1)):
            path = folder / f"{m:%Y-%m}.csv"
            if path.exists():
                continue
            blob = _get_bytes(tmpl.format(m=f"{m:%Y-%m}"))
            if blob is not None:
                path.write_text(_unzip(blob))
                log(f"{symbol} {kind} {m:%Y-%m}")
    rows, d = [], this_month
    while d < today:
        blob = _get_bytes(f"{BINANCE}/spot/daily/klines/{symbol}/1h/{symbol}-1h-{d}.zip")
        if blob is not None:
            rows.append(_unzip(blob))
        d += timedelta(days=1)
    (cache / "spot1h" / symbol / f"{this_month:%Y-%m}.csv").write_text("".join(rows))


def _ts(raw: str) -> datetime:
    v = int(raw)
    if v > 10 ** 14:  # archives from 2025 on are in microseconds
        v //= 1000
    return datetime.fromtimestamp(v / 1000, timezone.utc).replace(tzinfo=None)


def load_binance_hourly(symbol: str, cache: Path) -> list[Candle]:
    seen: dict[datetime, Candle] = {}
    for path in sorted((cache / "spot1h" / symbol).glob("*.csv")):
        for row in csv.reader(io.StringIO(path.read_text())):
            if not row or not row[0].isdigit():
                continue
            ts = _ts(row[0])
            seen[ts] = Candle(ts, float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]))
    return [seen[k] for k in sorted(seen)]


def load_binance_funding(symbol: str, cache: Path) -> dict[datetime, float]:
    """Funding rate per 8-hour settlement, keyed by the hour it is charged (naive UTC)."""
    out: dict[datetime, float] = {}
    for path in sorted((cache / "funding" / symbol).glob("*.csv")):
        for row in csv.reader(io.StringIO(path.read_text())):
            if not row or not row[0].isdigit():
                continue
            ts = _ts(row[0]).replace(minute=0, second=0, microsecond=0)
            out[ts] = float(row[2])
    return out


def _get_json(url: str, retries: int = 4) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except OSError:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def delta_candles(symbol: str, resolution: str, start: datetime, end: datetime,
                  get: Callable[[str], dict] = _get_json) -> list[Candle]:
    """Delta India candles (`1h` or `1d`) with start <= ts < end, oldest first, naive UTC.

    Requests are paged under the API's 4,000-candle cap.
    """
    step = timedelta(hours=3000) if resolution == "1h" else timedelta(days=3000)
    out: dict[datetime, Candle] = {}
    t = start
    while t < end:
        stop = min(end, t + step)
        q = urllib.parse.urlencode({"resolution": resolution, "symbol": symbol,
                                    "start": int(t.replace(tzinfo=timezone.utc).timestamp()),
                                    "end": int(stop.replace(tzinfo=timezone.utc).timestamp())})
        payload = get(f"{DELTA_CANDLES}?{q}")
        if not payload.get("success"):
            raise RuntimeError(f"Delta candles error: {payload.get('error') or payload}")
        for c in payload["result"]:
            ts = datetime.fromtimestamp(c["time"], timezone.utc).replace(tzinfo=None)
            if t <= ts < stop:
                out[ts] = Candle(ts, float(c["open"]), float(c["high"]), float(c["low"]), float(c["close"]),
                                 float(c.get("volume") or 0.0))
        t = stop
    return [out[k] for k in sorted(out)]
