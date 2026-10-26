"""Signal code shared by the backtest and the live bot: trend score, volatility sizing, volume profile.

Pure functions over plain lists, standard library only.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from .config import TrendParams

DAYS_PER_YEAR = 365


@dataclass(frozen=True)
class Candle:
    ts: datetime  # naive UTC open time
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class DailyClose:
    day: date
    close: float


def daily_closes(hourly: Sequence[Candle]) -> list[DailyClose]:
    """UTC daily closes from hourly candles (the last hourly close of each UTC day)."""
    out: dict[date, float] = {}
    for c in hourly:
        out[c.ts.date()] = c.close
    return [DailyClose(d, out[d]) for d in sorted(out)]


def realized_vol(closes: Sequence[float], window: int) -> float | None:
    """Annualised standard deviation of the last `window` daily log returns."""
    if len(closes) < window + 1:
        return None
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - window, len(closes))]
    mean = sum(rets) / window
    var = sum((r - mean) ** 2 for r in rets) / (window - 1)
    return math.sqrt(var) * math.sqrt(DAYS_PER_YEAR)


def trend_score(closes: Sequence[float], lookbacks: Sequence[int]) -> float | None:
    """Mean sign of the past returns over each lookback: -1 (all down) .. +1 (all up)."""
    if len(closes) < max(lookbacks) + 1:
        return None
    last = closes[-1]
    signs = [(last > closes[-1 - n]) - (last < closes[-1 - n]) for n in lookbacks]
    return sum(signs) / len(signs)


@dataclass(frozen=True)
class Target:
    exposure: float  # signed notional / equity for this coin (before the portfolio weight)
    score: float
    vol: float


def target_exposure(closes: Sequence[float], p: TrendParams = TrendParams()) -> Target | None:
    """Signed exposure for one coin from its daily closes up to and including the last completed day."""
    score = trend_score(closes, p.lookbacks)
    vol = realized_vol(closes, p.vol_window)
    if score is None or vol is None or vol <= 0:
        return None
    if p.long_only:
        score = max(score, 0.0)
    size = min(p.target_vol / vol, p.max_exposure) * abs(score)
    return Target(math.copysign(size, score) if score else 0.0, score, vol)


def needs_rebalance(target: float, current: float, band: float) -> bool:
    """Trade when the side changes, when flattening, or when the size moves by more than `band`."""
    if target == 0.0:
        return current != 0.0
    if current == 0.0 or (target > 0) != (current > 0):
        return True
    return abs(target - current) > band * abs(current)


@dataclass(frozen=True)
class Profile:
    poc: float
    vah: float
    val: float


def volume_profile(candles: Sequence[Candle], bins: int = 120, value_area: float = 0.70) -> Profile | None:
    """Composite volume profile: each candle's volume spread evenly across its high-low range.

    Reported with every rebalance for context. The study tested it as a signal four ways (value-area
    breakout, balance fade, POC pullback entry, size throttle); none improved the trend strategy out
    of sample, so it does not change positions.
    """
    if not candles:
        return None
    lo, hi = min(c.low for c in candles), max(c.high for c in candles)
    step = (hi - lo) / bins
    if step <= 0:
        return Profile(lo, hi, lo)
    prof = [0.0] * bins
    for c in candles:
        a = min(int((c.low - lo) / step), bins - 1)
        b = min(int((c.high - lo) / step), bins - 1)
        share = c.volume / (b - a + 1)
        for i in range(a, b + 1):
            prof[i] += share
    poc = max(range(bins), key=prof.__getitem__)
    lo_i = hi_i = poc
    total, acc = sum(prof), prof[poc]
    while acc < value_area * total and (lo_i > 0 or hi_i < bins - 1):
        up = prof[hi_i + 1] if hi_i < bins - 1 else -1.0
        dn = prof[lo_i - 1] if lo_i > 0 else -1.0
        if up >= dn:
            hi_i += 1
            acc += up
        else:
            lo_i -= 1
            acc += dn
    return Profile(lo + (poc + 0.5) * step, lo + (hi_i + 1) * step, lo + lo_i * step)
