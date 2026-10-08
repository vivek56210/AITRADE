"""Live 1-minute bars and a wall clock in IST, plus replay stand-ins for testing a past day end to end."""

from __future__ import annotations

import time as _time
import urllib.parse
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone

from ..playbook.models import Bar
from ..playbook.upstox import INSTRUMENT_KEYS, _get, parse_candles

IST = timezone(timedelta(hours=5, minutes=30))
INTRADAY_API = "https://api.upstox.com/v3/historical-candle/intraday"


def completed(bars: list[Bar], now: datetime, bar_minutes: int = 1) -> list[Bar]:
    """Drop the candle still forming, and give volume-less (spot) bars equal weight like the backtest."""
    out = [b for b in bars if b.ts + timedelta(minutes=bar_minutes) <= now]
    return [replace(b, volume=1.0) if b.volume <= 0 else b for b in out]


class UpstoxIntradayFeed:
    """Today's 1-minute index candles from Upstox's public intraday endpoint (no login needed)."""

    def __init__(self, get=_get):
        self._get = get

    def poll(self, symbol: str, day: date, now: datetime) -> list[Bar]:
        key = urllib.parse.quote(INSTRUMENT_KEYS[symbol], safe="")
        bars = parse_candles(self._get(f"{INTRADAY_API}/{key}/minutes/1"))
        return completed([b for b in bars if b.ts.date() == day], now)


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(IST).replace(tzinfo=None)

    def sleep(self, seconds: float) -> None:
        _time.sleep(seconds)

    def sleep_until(self, target: datetime) -> None:
        """Wait in short steps against the wall clock: a laptop that sleeps pauses a single long
        time.sleep() on Windows, which would make the runner wake hours late."""
        while (left := (target - self.now()).total_seconds()) > 0:
            self.sleep(min(left, 30.0))


@dataclass
class VirtualClock:
    """Simulated time: sleep() advances the clock instantly."""

    current: datetime

    def now(self) -> datetime:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)

    def sleep_until(self, target: datetime) -> None:
        self.current = max(self.current, target)


@dataclass
class ReplayFeed:
    """Serves a past day's bars as if they were arriving live."""

    bars: dict[str, list[Bar]] = field(default_factory=dict)

    def poll(self, symbol: str, day: date, now: datetime) -> list[Bar]:
        return completed([b for b in self.bars.get(symbol, []) if b.ts.date() == day], now)
