"""Auction structure: IB, open type, day type, profile shape, composite balance, value migration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from itertools import pairwise

from .config import InstrumentSpec, PlaybookParams, SessionTimes
from .models import Bar, DayType, IBClass, OpenLocation, OpenType, ProfileShape, Session
from .profile import TPOProfile, ValueArea, VolumeProfile, to_row

TPO_LETTERS = "ABCDEFGHIJKLMNOP"


def session_start(d: date, times: SessionTimes) -> datetime:
    return datetime.combine(d, times.open)


def period_index(ts: datetime, times: SessionTimes, minutes: int | None = None) -> int:
    minutes = minutes or times.period_minutes
    elapsed = (ts - session_start(ts.date(), times)) / timedelta(minutes=1)
    return int(elapsed // minutes)


def classify_ib(ib_range: float, avg_ib: float, params: PlaybookParams) -> IBClass:
    if avg_ib <= 0:
        return IBClass.NORMAL
    ratio = ib_range / avg_ib
    if ratio < params.narrow_ib_ratio:
        return IBClass.NARROW
    if ratio > params.wide_ib_ratio:
        return IBClass.WIDE
    return IBClass.NORMAL


def open_location(price: float, va: ValueArea) -> OpenLocation:
    if price > va.vah:
        return OpenLocation.ABOVE_VALUE
    if price < va.val:
        return OpenLocation.BELOW_VALUE
    return OpenLocation.INSIDE_VALUE


def profile_shape(poc: float, high: float, low: float, params: PlaybookParams) -> ProfileShape:
    if high <= low:
        return ProfileShape.D
    pos = (poc - low) / (high - low)
    if pos > params.shape_upper:
        return ProfileShape.P
    if pos < params.shape_lower:
        return ProfileShape.B
    return ProfileShape.D


@dataclass
class SessionProfile:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    ib_high: float
    ib_low: float
    poc: float
    vah: float
    val: float
    hvns: tuple[float, ...]
    lvns: tuple[float, ...]
    buying_tail: tuple[float, float] | None
    selling_tail: tuple[float, float] | None
    poor_low: bool
    poor_high: bool
    single_prints: tuple[tuple[float, float], ...]
    shape: ProfileShape
    day_type: DayType
    open_type: OpenType | None
    profile: VolumeProfile = field(repr=False, compare=False)

    @property
    def value_area(self) -> ValueArea:
        return ValueArea(self.poc, self.vah, self.val)

    @property
    def ib_range(self) -> float:
        return self.ib_high - self.ib_low

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def va_width(self) -> float:
        return self.vah - self.val

    def references(self) -> dict[str, float]:
        return {"prior VAH": self.vah, "prior VAL": self.val, "prior POC": self.poc,
                "prior high": self.high, "prior low": self.low}


def classify_open(bars: list[Bar], open_price: float, prior: SessionProfile | None,
                  avg_ib: float, params: PlaybookParams, row: float) -> OpenType:
    hi = max(b.high for b in bars)
    lo = min(b.low for b in bars)
    c = bars[-1].close
    tol = params.retrace_tolerance * avg_ib
    drive = params.drive_min_fraction * avg_ib
    mid = lo + 0.5 * (hi - lo)
    if lo >= open_price - tol and c - open_price >= drive and c >= mid:
        return OpenType.OPEN_DRIVE
    if hi <= open_price + tol and open_price - c >= drive and c <= mid:
        return OpenType.OPEN_DRIVE
    i_hi = next(i for i, b in enumerate(bars) if b.high == hi)
    i_lo = next(i for i, b in enumerate(bars) if b.low == lo)
    loc = open_location(open_price, prior.value_area) if prior else OpenLocation.INSIDE_VALUE
    refs = list(prior.references().values()) if prior else []
    ref_tol = params.reference_tolerance * avg_ib
    if lo <= open_price - tol and c > open_price + row and i_lo < i_hi:
        if loc == OpenLocation.BELOW_VALUE:
            return OpenType.OPEN_REJECTION_REVERSE
        if any(abs(lo - r) <= ref_tol for r in refs):
            return OpenType.OPEN_TEST_DRIVE
    if hi >= open_price + tol and c < open_price - row and i_hi < i_lo:
        if loc == OpenLocation.ABOVE_VALUE:
            return OpenType.OPEN_REJECTION_REVERSE
        if any(abs(hi - r) <= ref_tol for r in refs):
            return OpenType.OPEN_TEST_DRIVE
    if prior is None or prior.low <= open_price <= prior.high:
        return OpenType.OPEN_AUCTION_IN_RANGE
    return OpenType.OPEN_AUCTION_OUT_OF_RANGE


def extension(high: float, low: float, ib_high: float, ib_low: float, row: float) -> tuple[bool, bool]:
    eps = max(row, 0.05 * (ib_high - ib_low))
    return high > ib_high + eps, low < ib_low - eps


def classify_day_type(open_: float, high: float, low: float, close: float, ib_high: float,
                      ib_low: float, tpo: TPOProfile, params: PlaybookParams, row: float,
                      avg_range: float | None = None) -> DayType:
    ib = ib_high - ib_low
    rng = high - low
    up, down = extension(high, low, ib_high, ib_low, row)
    if up and down:
        if close >= high - params.extreme_close_fraction * rng or \
                close <= low + params.extreme_close_fraction * rng:
            return DayType.NEUTRAL_EXTREME
        return DayType.NEUTRAL
    if up or down:
        if _double_distribution(tpo, params):
            return DayType.DOUBLE_DISTRIBUTION
        big = rng >= params.trend_range_multiple * ib
        if up and big and close >= high - params.extreme_close_fraction * rng \
                and open_ <= low + params.trend_open_fraction * rng:
            return DayType.TREND
        if down and big and close <= low + params.extreme_close_fraction * rng \
                and open_ >= high - params.trend_open_fraction * rng:
            return DayType.TREND
        return DayType.NORMAL_VARIATION
    if avg_range and rng < params.non_trend_range_ratio * avg_range:
        return DayType.NON_TREND
    return DayType.NORMAL


def _double_distribution(tpo: TPOProfile, params: PlaybookParams) -> bool:
    """A single-print zone separating two distributions that each show rotation (fat TPO rows)."""
    start, counts = tpo.counts()
    total = sum(counts)
    for lo, hi in tpo.single_prints(params.single_print_min_rows):
        lo_i, hi_i = to_row(lo, tpo.row_size) - start, to_row(hi, tpo.row_size) - start
        below, above = counts[:lo_i], counts[hi_i + 1:]
        if (min(sum(below), sum(above)) >= params.double_distribution_min_share * total
                and min(max(below, default=0), max(above, default=0)) >= params.double_distribution_min_tpos):
            return True
    return False


def build_tpo(bars: list[Bar], times: SessionTimes, row: float) -> TPOProfile:
    tpo = TPOProfile(row)
    for b in bars:
        tpo.add(period_index(b.ts, times), b.low, b.high)
    return tpo


def analyze_session(session: Session, spec: InstrumentSpec, params: PlaybookParams = PlaybookParams(),
                    times: SessionTimes = SessionTimes(), prior: SessionProfile | None = None,
                    avg_ib: float | None = None, avg_range: float | None = None) -> SessionProfile:
    bars = session.bars
    row = spec.row_size
    vp = VolumeProfile.from_bars(bars, row)
    tpo = build_tpo(bars, times, row)
    ib_bars = [b for b in bars if period_index(b.ts, times) < times.ib_periods] or bars
    ib_high, ib_low = max(b.high for b in ib_bars), min(b.low for b in ib_bars)
    va = vp.value_area(params.value_area_pct)
    hvns, lvns = vp.nodes(params.node_smoothing_rows, params.node_prominence)
    buying_tail, selling_tail = tpo.tails(params.tail_min_rows)
    poor_low, poor_high = tpo.poor_extremes()
    a_bars = [b for b in bars if period_index(b.ts, times) == 0] or bars[:1]
    ref_ib = avg_ib or (prior.ib_range if prior else ib_high - ib_low) or row
    return SessionProfile(
        date=session.date, open=session.open, high=session.high, low=session.low,
        close=session.close, volume=vp.total, ib_high=ib_high, ib_low=ib_low,
        poc=va.poc, vah=va.vah, val=va.val, hvns=tuple(hvns), lvns=tuple(lvns),
        buying_tail=buying_tail, selling_tail=selling_tail,
        poor_low=poor_low and buying_tail is None, poor_high=poor_high and selling_tail is None,
        single_prints=tuple(tpo.single_prints(params.single_print_min_rows)),
        shape=profile_shape(va.poc, session.high, session.low, params),
        day_type=classify_day_type(session.open, session.high, session.low, session.close,
                                   ib_high, ib_low, tpo, params, row, avg_range),
        open_type=classify_open(a_bars, session.open, prior, ref_ib, params, row),
        profile=vp,
    )


def average_ib(history: list[SessionProfile], n: int) -> float | None:
    w = history[-n:]
    return sum(p.ib_range for p in w) / len(w) if w else None


def average_range(history: list[SessionProfile], n: int) -> float | None:
    w = history[-n:]
    return sum(p.range for p in w) / len(w) if w else None


def average_va_width(history: list[SessionProfile], n: int) -> float | None:
    w = history[-n:]
    return sum(p.va_width for p in w) / len(w) if len(w) >= 3 else None


@dataclass(frozen=True)
class Balance:
    sessions: tuple[date, ...]
    poc: float
    vah: float
    val: float
    high: float
    low: float
    hvns: tuple[float, ...]
    lvns: tuple[float, ...]
    quiet: bool

    @property
    def height(self) -> float:
        return self.vah - self.val


def _overlaps(a: SessionProfile, b: SessionProfile, min_frac: float) -> bool:
    overlap = min(a.vah, b.vah) - max(a.val, b.val)
    smaller = min(a.va_width, b.va_width)
    return smaller > 0 and overlap >= min_frac * smaller


def detect_balance(history: list[SessionProfile], params: PlaybookParams) -> Balance | None:
    """Longest run (3-7 sessions) of overlapping value ending at the latest session."""
    for k in range(min(params.composite_max_sessions, len(history)), params.composite_min_sessions - 1, -1):
        window = history[-k:]
        if not all(_overlaps(a, b, params.balance_overlap_min) for a, b in pairwise(window)):
            continue
        comp = VolumeProfile.combine(p.profile for p in window)
        va = comp.value_area(params.value_area_pct)
        hvns, lvns = comp.nodes(params.node_smoothing_rows, params.node_prominence)
        pocs = [p.poc for p in window]
        ranges = [p.range for p in window]
        quiet = (max(pocs) - min(pocs) <= params.balance_poc_spread_max * va.width
                 and ranges[-1] <= sum(ranges) / k)
        return Balance(tuple(p.date for p in window), va.poc, va.vah, va.val,
                       max(p.high for p in window), min(p.low for p in window),
                       tuple(hvns), tuple(lvns), quiet)
    return None


def value_migration(history: list[SessionProfile], n: int) -> int:
    """+1 if value migrated higher across the last n sessions, -1 if lower, else 0."""
    if len(history) < n:
        return 0
    w = history[-n:]
    if all(b.poc > a.poc and b.val >= a.val for a, b in pairwise(w)):
        return 1
    if all(b.poc < a.poc and b.vah <= a.vah for a, b in pairwise(w)):
        return -1
    return 0
