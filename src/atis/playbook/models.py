from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"

    @property
    def sign(self) -> int:
        return {"long": 1, "short": -1, "neutral": 0}[self.value]


class OpenType(str, Enum):
    OPEN_DRIVE = "OD"
    OPEN_TEST_DRIVE = "OTD"
    OPEN_REJECTION_REVERSE = "ORR"
    OPEN_AUCTION_IN_RANGE = "OA-in-range"
    OPEN_AUCTION_OUT_OF_RANGE = "OA-out-of-range"


class OpenLocation(str, Enum):
    ABOVE_VALUE = "above-value"
    INSIDE_VALUE = "inside-value"
    BELOW_VALUE = "below-value"


class DayType(str, Enum):
    TREND = "trend"
    DOUBLE_DISTRIBUTION = "double-distribution"
    NORMAL_VARIATION = "normal-variation"
    NORMAL = "normal"
    NEUTRAL = "neutral"
    NEUTRAL_EXTREME = "neutral-extreme"
    NON_TREND = "non-trend"


class IBClass(str, Enum):
    NARROW = "narrow"
    NORMAL = "normal"
    WIDE = "wide"


class ProfileShape(str, Enum):
    P = "P"
    B = "b"
    D = "D"


class Structure(str, Enum):
    LONG_OPTION = "long-option"
    DEBIT_SPREAD = "debit-spread"
    CREDIT_SPREAD = "credit-spread"
    IRON_CONDOR = "iron-condor"
    IRON_FLY = "iron-fly"

    @property
    def is_short_premium(self) -> bool:
        return self in (Structure.CREDIT_SPREAD, Structure.IRON_CONDOR, Structure.IRON_FLY)


@dataclass(frozen=True)
class Bar:
    """One OHLCV bar of index futures; ts is the bar start in naive IST."""

    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    buy_volume: float | None = None
    sell_volume: float | None = None
    oi: float | None = None


@dataclass
class Session:
    date: date
    bars: list[Bar]

    @property
    def open(self) -> float:
        return self.bars[0].open

    @property
    def close(self) -> float:
        return self.bars[-1].close

    @property
    def high(self) -> float:
        return max(b.high for b in self.bars)

    @property
    def low(self) -> float:
        return min(b.low for b in self.bars)


@dataclass
class PeriodStat:
    """A 30-minute TPO period (letter A, B, ...) or a 15-minute candle (letter '')."""

    index: int
    letter: str
    start: datetime
    end: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    delta: float = 0.0

    def update(self, bar: Bar, delta: float) -> None:
        self.high = max(self.high, bar.high)
        self.low = min(self.low, bar.low)
        self.close = bar.close
        self.volume += bar.volume
        self.delta += delta


@dataclass(frozen=True)
class Target:
    price: float
    label: str
    size_pct: float


@dataclass(frozen=True)
class OptionLeg:
    side: str  # BUY / SELL
    right: str  # CE / PE
    strike: float
    expiry: date
    delta: float | None = None
    premium: float | None = None


@dataclass(frozen=True)
class OptionPlan:
    structure: Structure
    legs: tuple[OptionLeg, ...]
    expiry: date
    net_premium: float | None  # positive = debit paid, negative = credit received (per unit)
    max_loss_per_lot: float | None
    max_profit_per_lot: float | None
    notes: tuple[str, ...] = ()


@dataclass
class Candidate:
    """What a setup detector proposes; the engine gates, prices and sizes it."""

    setup_id: str
    name: str
    group: str
    direction: Direction
    entry: float
    stop: float | None
    stop_rule: str
    targets: list[Target]
    structure: Structure
    upper_level: float | None = None
    lower_level: float | None = None
    spread_target: float | None = None
    pin_strike: float | None = None
    itm: bool = False
    horizon: str = "intraday"
    expiry_hint: date | None = None
    size_multiplier: float = 1.0
    confirmations: dict[str, bool | None] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class SetupSignal:
    setup_id: str
    name: str
    group: str
    symbol: str
    ts: datetime
    direction: Direction
    entry: float
    stop: float | None
    stop_rule: str
    targets: list[Target]
    option_plan: OptionPlan
    lots: int
    risk_per_lot: float | None
    risk_total: float | None
    sizing_basis: str
    exit_by: datetime | None
    horizon: str
    size_multiplier: float
    est_costs: float | None
    confirmations: dict[str, bool | None]
    notes: list[str]
    validation_status: str = "CANDIDATE"
