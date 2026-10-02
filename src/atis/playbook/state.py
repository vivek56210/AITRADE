from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

from .config import InstrumentSpec, PlaybookParams, SessionTimes
from .models import Bar, DayType, IBClass, OpenLocation, PeriodStat
from .profile import TPOProfile, VolumeProfile
from .structure import Balance, SessionProfile, classify_day_type, open_location


@dataclass(frozen=True)
class DayContext:
    """Inputs the bars cannot provide: calendar, events, volatility and option-chain hints."""

    holidays: frozenset[date] = frozenset()
    events: tuple[datetime, ...] = ()
    vix_rising: bool = False
    basis: float = 0.0
    iv: float | None = None
    rate: float = 0.065
    max_oi_strike: float | None = None


@dataclass
class BarEvent:
    bar: Bar
    now: datetime
    period_closed: PeriodStat | None = None
    candle15_closed: PeriodStat | None = None


@dataclass
class SessionState:
    spec: InstrumentSpec
    params: PlaybookParams
    times: SessionTimes
    date: date
    ctx: DayContext
    prior: SessionProfile | None
    history: list[SessionProfile]
    balance: Balance | None
    migration: int
    avg_ib: float
    avg_range: float | None
    avg_va_width: float | None
    is_expiry: bool
    vp: VolumeProfile = None
    tpo: TPOProfile = None
    bars: list[Bar] = field(default_factory=list)
    deltas: list[float] = field(default_factory=list)
    flow_estimated: bool = False
    open: float | None = None
    high: float = float("-inf")
    low: float = float("inf")
    last: float | None = None
    periods: list[PeriodStat] = field(default_factory=list)
    candles15: list[PeriodStat] = field(default_factory=list)
    ib_high: float | None = None
    ib_low: float | None = None
    ib_class: IBClass | None = None
    dpoc_at_period: list[float] = field(default_factory=list)
    flags: dict[str, Any] = field(default_factory=dict)
    now: datetime | None = None
    skips: list[tuple[datetime | None, str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.vp = VolumeProfile(self.spec.row_size)
        self.tpo = TPOProfile(self.spec.row_size)
        self._skip_keys: set[tuple[str, str]] = set()

    def skip(self, setup_id: str, reason: str) -> None:
        """Record why a setup was considered and rejected (once per setup/reason per session)."""
        if (setup_id, reason) not in self._skip_keys:
            self._skip_keys.add((setup_id, reason))
            self.skips.append((self.now, setup_id, reason))

    @property
    def row(self) -> float:
        return self.spec.row_size

    @property
    def retrace_tol(self) -> float:
        return self.params.retrace_tolerance * self.avg_ib

    @property
    def ref_tol(self) -> float:
        return self.params.reference_tolerance * self.avg_ib

    @property
    def drive_min(self) -> float:
        return self.params.drive_min_fraction * self.avg_ib

    def at(self, t: time) -> datetime:
        return datetime.combine(self.date, t)

    @property
    def ib_complete(self) -> bool:
        return self.ib_high is not None

    @property
    def ib_range(self) -> float:
        return self.ib_high - self.ib_low

    @property
    def ib_mid(self) -> float:
        return (self.ib_high + self.ib_low) / 2

    @property
    def open_loc(self) -> OpenLocation | None:
        if self.prior is None or self.open is None:
            return None
        return open_location(self.open, self.prior.value_area)

    def dpoc(self) -> float | None:
        return self.vp.poc()

    def bars_since(self, ts: datetime) -> list[Bar]:
        return [b for b in self.bars if b.ts >= ts]

    def first_bar_index(self, pred) -> int | None:
        return next((i for i, b in enumerate(self.bars) if pred(b)), None)

    def developing_day_type(self) -> DayType | None:
        if not self.ib_complete or self.last is None:
            return None
        return classify_day_type(self.open, self.high, self.low, self.last, self.ib_high, self.ib_low,
                                 self.tpo, self.params, self.row)

    def event_within(self, now: datetime, minutes: int) -> datetime | None:
        return next((e for e in self.ctx.events if now <= e and (e - now).total_seconds() <= minutes * 60), None)
