"""Order-flow overlay. Uses real aggressor split when bars carry buy/sell volume, else the tick rule."""

from __future__ import annotations

from itertools import accumulate

from .models import Bar


def bar_delta(bar: Bar, prev_close: float | None) -> tuple[float, bool]:
    """Return (delta, estimated)."""
    if bar.buy_volume is not None and bar.sell_volume is not None:
        return bar.buy_volume - bar.sell_volume, False
    ref = prev_close if prev_close is not None else bar.open
    if bar.close > ref:
        return bar.volume, True
    if bar.close < ref:
        return -bar.volume, True
    return 0.0, True


def delta_divergence(bars: list[Bar], deltas: list[float], up: bool, lookback: int = 20) -> bool:
    """Latest price extreme not confirmed by cumulative delta versus the prior swing extreme."""
    if len(bars) < 4:
        return False
    cvd = list(accumulate(deltas))
    if up:
        i = max(range(len(bars)), key=lambda k: (bars[k].high, k))
        window = range(max(0, i - lookback), i - 1)
        if not window:
            return False
        j = max(window, key=lambda k: bars[k].high)
        return bars[i].high > bars[j].high and cvd[i] < cvd[j]
    i = min(range(len(bars)), key=lambda k: (bars[k].low, -k))
    window = range(max(0, i - lookback), i - 1)
    if not window:
        return False
    j = min(window, key=lambda k: bars[k].low)
    return bars[i].low < bars[j].low and cvd[i] > cvd[j]


def absorption(bars: list[Bar], level: float, tol: float, min_bars: int = 3,
               volume_ratio: float = 1.5) -> bool:
    """Heavy volume traded near a level while price made little progress through it."""
    if not bars:
        return False
    near = [b for b in bars if b.low <= level + tol and b.high >= level - tol]
    if len(near) < min_bars:
        return False
    mean_all = sum(b.volume for b in bars) / len(bars)
    mean_near = sum(b.volume for b in near) / len(near)
    progress = max(b.close for b in near) - min(b.close for b in near)
    return mean_near >= volume_ratio * mean_all and progress <= 2 * tol
