"""Load futures bars from CSV, split into sessions, and generate synthetic sessions for demos/tests."""

from __future__ import annotations

import csv
import math
import random
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from .models import Bar, Session

IST = timezone(timedelta(hours=5, minutes=30))


def _parse_ts(raw: str) -> datetime:
    ts = datetime.fromisoformat(raw.strip())
    return ts.astimezone(IST).replace(tzinfo=None) if ts.tzinfo else ts


def _opt(row: dict[str, str], key: str) -> float | None:
    v = (row.get(key) or "").strip()
    return float(v) if v else None


def load_csv(path: str | Path) -> list[Bar]:
    """Columns: timestamp, open, high, low, close, volume[, buy_volume, sell_volume, oi]."""
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        rows = [{k.strip().lower(): v for k, v in r.items()} for r in reader]
    ts_key = next(k for k in ("timestamp", "datetime", "ts", "date") if k in rows[0])
    bars = [Bar(_parse_ts(r[ts_key]), float(r["open"]), float(r["high"]), float(r["low"]),
                float(r["close"]), float(r["volume"]), _opt(r, "buy_volume"), _opt(r, "sell_volume"), _opt(r, "oi"))
            for r in rows]
    return sorted(bars, key=lambda b: b.ts)


def to_sessions(bars: Iterable[Bar], start: time = time(9, 15), end: time = time(15, 30)) -> list[Session]:
    by_day: dict[date, list[Bar]] = defaultdict(list)
    for b in bars:
        if start <= b.ts.time() < end:
            by_day[b.ts.date()].append(b)
    return [Session(d, sorted(bs, key=lambda b: b.ts)) for d, bs in sorted(by_day.items())]


def time_weighted(bars: list[Bar]) -> list[Bar]:
    """Spot indices carry no volume: weight every bar equally so profiles become time-at-price (TPO)."""
    if bars and all(b.volume <= 0 for b in bars):
        return [replace(b, volume=1.0) for b in bars]
    return bars


def drop_short_sessions(sessions: list[Session], min_fraction: float = 0.8) -> list[Session]:
    """Drop special sessions (e.g. Muhurat trading) far shorter than a normal day."""
    if not sessions:
        return sessions
    counts = sorted(len(s.bars) for s in sessions)
    median = counts[len(counts) // 2]
    return [s for s in sessions if len(s.bars) >= min_fraction * median]


def infer_holidays(sessions: list[Session]) -> frozenset[date]:
    """Weekdays inside the data's date range with no session are treated as exchange holidays."""
    if not sessions:
        return frozenset()
    have = {s.date for s in sessions}
    out, d = set(), sessions[0].date
    while d <= sessions[-1].date:
        if d.weekday() < 5 and d not in have:
            out.add(d)
        d += timedelta(days=1)
    return frozenset(out)


def prepare_sessions(bars: list[Bar], start: time = time(9, 15),
                     end: time = time(15, 30)) -> tuple[list[Session], frozenset[date]]:
    """Bars -> clean sessions plus the exchange holidays inferred from gaps."""
    sessions = drop_short_sessions(to_sessions(time_weighted(bars), start, end))
    return sessions, infer_holidays(sessions)


def write_csv(path: str | Path, bars: Iterable[Bar]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "open", "high", "low", "close", "volume", "oi"])
        for b in bars:
            w.writerow([b.ts.isoformat(sep=" "), b.open, b.high, b.low, b.close, b.volume,
                        "" if b.oi is None else b.oi])


def path_session(d: date, waypoints: list[tuple[str, float]], volume: float = 1000.0,
                 end: str = "15:30") -> Session:
    """1-minute bars that move linearly between (HH:MM, price) waypoints, then hold the last price."""
    pts = [(datetime.combine(d, time.fromisoformat(t)), p) for t, p in waypoints]
    close_dt = datetime.combine(d, time.fromisoformat(end))
    bars, ts = [], pts[0][0]
    prev = pts[0][1]
    while ts < close_dt:
        nxt = ts + timedelta(minutes=1)
        price = _interp(pts, nxt)
        bars.append(Bar(ts, prev, max(prev, price), min(prev, price), price, volume))
        prev, ts = price, nxt
    return Session(d, bars)


def _interp(pts: list[tuple[datetime, float]], ts: datetime) -> float:
    if ts <= pts[0][0]:
        return pts[0][1]
    for (t0, p0), (t1, p1) in zip(pts, pts[1:]):
        if t0 <= ts <= t1:
            return round(p0 + (p1 - p0) * (ts - t0) / (t1 - t0), 2)
    return pts[-1][1]


def oscillating_session(d: date, low: float, high: float, half_cycle_minutes: int = 30,
                        volume: float = 1000.0) -> Session:
    """Balanced rotation between low and high, starting at the midpoint."""
    mid = (low + high) / 2
    t = datetime.combine(d, time(9, 15))
    wps, price, up = [("09:15", mid)], mid, True
    t += timedelta(minutes=half_cycle_minutes // 2)
    while t < datetime.combine(d, time(15, 30)):
        price = high if up else low
        wps.append((t.strftime("%H:%M"), price))
        up = not up
        t += timedelta(minutes=half_cycle_minutes)
    return path_session(d, wps, volume)


def synthetic_sessions(start: date, days: int, base: float = 24000.0, seed: int = 7,
                       daily_vol: float = 0.009) -> list[Session]:
    """Random sessions mixing balance and trend days, with a U-shaped intraday volume curve."""
    rng = random.Random(seed)
    sessions, d, price = [], start, base
    while len(sessions) < days:
        if d.weekday() < 5:
            trend = rng.random() < 0.35
            drift = rng.choice((-1, 1)) * daily_vol * price * rng.uniform(0.6, 1.4) if trend else 0.0
            gap = rng.gauss(0, 0.0025) * price
            sessions.append(_random_session(d, price + gap, drift, daily_vol * price, rng))
            price = sessions[-1].close
        d += timedelta(days=1)
    return sessions


def _random_session(d: date, open_: float, drift: float, day_sigma: float, rng: random.Random) -> Session:
    n = 375
    sigma = day_sigma / math.sqrt(n) * 0.8
    anchor, price = open_, open_
    bars = []
    t = datetime.combine(d, time(9, 15))
    for i in range(n):
        anchor += drift / n
        price += 0.04 * (anchor - price) + rng.gauss(0, sigma)
        o = bars[-1].close if bars else open_
        c = round(price, 2)
        wick = abs(rng.gauss(0, sigma * 0.6))
        u = i / (n - 1)
        vol = round(1000 * (1.8 - 3.2 * u * (1 - u)) * rng.uniform(0.7, 1.3))
        bars.append(Bar(t + timedelta(minutes=i), o, round(max(o, c) + wick, 2), round(min(o, c) - wick, 2), c, vol))
    return Session(d, bars)
