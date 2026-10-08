from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from .models import Bar


def to_row(price: float, row_size: float) -> int:
    return math.floor(price / row_size + 1e-9)


@dataclass(frozen=True)
class ValueArea:
    poc: float
    vah: float
    val: float

    @property
    def width(self) -> float:
        return self.vah - self.val

    def contains(self, price: float) -> bool:
        return self.val <= price <= self.vah


class VolumeProfile:
    """Volume-at-price histogram; each bar's volume is spread evenly over the rows it spans."""

    def __init__(self, row_size: float):
        self.row_size = row_size
        self._vol: dict[int, float] = {}
        self.total = 0.0

    @classmethod
    def from_bars(cls, bars: Iterable[Bar], row_size: float) -> VolumeProfile:
        vp = cls(row_size)
        for b in bars:
            vp.add_bar(b)
        return vp

    @classmethod
    def combine(cls, profiles: Iterable[VolumeProfile]) -> VolumeProfile:
        profiles = list(profiles)
        out = cls(profiles[0].row_size)
        for p in profiles:
            if p.row_size != out.row_size:
                raise ValueError("cannot combine profiles with different row sizes")
            for r, v in p._vol.items():
                out._vol[r] = out._vol.get(r, 0.0) + v
            out.total += p.total
        return out

    def add(self, low: float, high: float, volume: float) -> None:
        if volume <= 0:
            return
        lo, hi = to_row(low, self.row_size), to_row(high, self.row_size)
        share = volume / (hi - lo + 1)
        for r in range(lo, hi + 1):
            self._vol[r] = self._vol.get(r, 0.0) + share
        self.total += volume

    def add_bar(self, bar: Bar) -> None:
        self.add(bar.low, bar.high, bar.volume)

    def price(self, row: int) -> float:
        return round(row * self.row_size, 6)

    def dense(self) -> tuple[int, list[float]]:
        if not self._vol:
            return 0, []
        lo, hi = min(self._vol), max(self._vol)
        return lo, [self._vol.get(r, 0.0) for r in range(lo, hi + 1)]

    @property
    def empty(self) -> bool:
        return not self._vol

    def row_volume(self, price: float) -> float:
        return self._vol.get(to_row(price, self.row_size), 0.0)

    def mean_row_volume(self) -> float:
        _, vols = self.dense()
        return sum(vols) / len(vols) if vols else 0.0

    def volume_between(self, low: float, high: float) -> float:
        lo, hi = to_row(low, self.row_size), to_row(high, self.row_size)
        return sum(v for r, v in self._vol.items() if lo <= r <= hi)

    def volume_above(self, price: float) -> float:
        r0 = to_row(price, self.row_size)
        return sum(v for r, v in self._vol.items() if r > r0)

    def volume_below(self, price: float) -> float:
        r0 = to_row(price, self.row_size)
        return sum(v for r, v in self._vol.items() if r < r0)

    def _poc_index(self, vols: list[float]) -> int:
        peak = max(vols)
        mid = (len(vols) - 1) / 2
        candidates = [i for i, v in enumerate(vols) if v == peak]
        return min(candidates, key=lambda i: (abs(i - mid), i))

    def poc(self) -> float | None:
        start, vols = self.dense()
        if not vols:
            return None
        return self.price(start + self._poc_index(vols))

    def value_area(self, pct: float = 0.70) -> ValueArea | None:
        start, vols = self.dense()
        if not vols:
            return None
        p = self._poc_index(vols)
        lo = hi = p
        acc, target = vols[p], pct * sum(vols)
        n = len(vols)
        while acc < target and (lo > 0 or hi < n - 1):
            up = vols[hi + 1] if hi < n - 1 else -1.0
            dn = vols[lo - 1] if lo > 0 else -1.0
            if up >= dn:
                hi += 1
                acc += up
            else:
                lo -= 1
                acc += dn
        return ValueArea(self.price(start + p), self.price(start + hi), self.price(start + lo))

    def nodes(self, smoothing: int = 2, prominence: float = 0.15) -> tuple[list[float], list[float]]:
        """Return (HVNs, LVNs) as prominence-filtered extrema of the smoothed histogram."""
        start, vols = self.dense()
        n = len(vols)
        if n < 3:
            return [], []
        s = [sum(vols[max(0, i - smoothing):i + smoothing + 1]) /
             len(vols[max(0, i - smoothing):i + smoothing + 1]) for i in range(n)]
        thr = prominence * max(s)
        hvns, lvns = [], []
        for i in range(1, n - 1):
            if s[i] > s[i - 1] and s[i] >= s[i + 1]:
                left_min = min(s[j] for j in _walk(s, i, -1, lambda a, b: a <= b))
                right_min = min(s[j] for j in _walk(s, i, 1, lambda a, b: a <= b))
                if s[i] - max(left_min, right_min) >= thr:
                    hvns.append(self.price(start + i))
            elif s[i] < s[i - 1] and s[i] <= s[i + 1]:
                left_max = max(s[j] for j in _walk(s, i, -1, lambda a, b: a >= b))
                right_max = max(s[j] for j in _walk(s, i, 1, lambda a, b: a >= b))
                if min(left_max, right_max) - s[i] >= thr:
                    lvns.append(self.price(start + i))
        return hvns, lvns


def _walk(s: list[float], i: int, step: int, keep) -> list[int]:
    """Indices from i outward while keep(s[j], s[i]) holds, plus the first index that breaks it."""
    out = [i]
    j = i + step
    while 0 <= j < len(s):
        out.append(j)
        if not keep(s[j], s[i]):
            break
        j += step
    return out


class TPOProfile:
    """Time-price opportunity profile: which 30-minute periods traded at each row."""

    def __init__(self, row_size: float):
        self.row_size = row_size
        self.period_rows: dict[int, set[int]] = {}

    def add(self, period: int, low: float, high: float) -> None:
        rows = self.period_rows.setdefault(period, set())
        rows.update(range(to_row(low, self.row_size), to_row(high, self.row_size) + 1))

    def price(self, row: int) -> float:
        return round(row * self.row_size, 6)

    def counts(self) -> tuple[int, list[int]]:
        all_rows = set().union(*self.period_rows.values()) if self.period_rows else set()
        if not all_rows:
            return 0, []
        lo, hi = min(all_rows), max(all_rows)
        counts = [0] * (hi - lo + 1)
        for rows in self.period_rows.values():
            for r in rows:
                counts[r - lo] += 1
        return lo, counts

    def _edge_run(self, counts: list[int], from_top: bool) -> int:
        seq = reversed(counts) if from_top else iter(counts)
        n = 0
        for c in seq:
            if c > 1:
                break
            n += 1
        return n

    def tails(self, min_rows: int) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
        """(buying_tail, selling_tail) as (low, high) price ranges of single-TPO extremes."""
        start, counts = self.counts()
        if len(self.period_rows) < 2 or not counts:
            return None, None
        top, bottom = self._edge_run(counts, True), self._edge_run(counts, False)
        hi_row = start + len(counts) - 1
        buying = (self.price(start), self.price(start + bottom - 1)) if bottom >= min_rows else None
        selling = (self.price(hi_row - top + 1), self.price(hi_row)) if top >= min_rows else None
        return buying, selling

    def poor_extremes(self) -> tuple[bool, bool]:
        """(poor_low, poor_high): flat extremes touched by two or more periods."""
        _, counts = self.counts()
        if not counts:
            return False, False
        return counts[0] >= 2, counts[-1] >= 2

    def single_prints(self, min_rows: int) -> list[tuple[float, float]]:
        start, counts = self.counts()
        if not counts:
            return []
        top, bottom = self._edge_run(counts, True), self._edge_run(counts, False)
        zones, run_start = [], None
        for i in range(bottom, len(counts) - top):
            if counts[i] <= 1:
                run_start = i if run_start is None else run_start
            else:
                if run_start is not None and i - run_start >= min_rows:
                    zones.append((self.price(start + run_start), self.price(start + i - 1)))
                run_start = None
        end = len(counts) - top
        if run_start is not None and end - run_start >= min_rows:
            zones.append((self.price(start + run_start), self.price(start + end - 1)))
        return zones

    def periods_touching(self, low: float, high: float) -> int:
        lo, hi = to_row(low, self.row_size), to_row(high, self.row_size)
        return sum(1 for rows in self.period_rows.values() if any(lo <= r <= hi for r in rows))
