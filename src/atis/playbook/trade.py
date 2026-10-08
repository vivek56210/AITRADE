"""One directional trade followed bar by bar, plus the account's realized-R ledger.

`TradeState` is the single implementation of how a directional signal plays out: scale out at each
target, move the stop to breakeven after the first target, stop out, or exit at the time limit.
The backtest replays it over a whole session; the engine updates it as each live bar arrives,
which is how it knows today's and this week's realized R for the loss limits.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .models import Bar, SetupSignal


@dataclass
class TradeState:
    sig: SetupSignal
    stop: float | None = None
    remaining: float = 1.0
    realized: float = 0.0  # price points x position fraction
    targets: list = field(default_factory=list)
    last_close: float | None = None
    r: float | None = None
    reason: str = ""
    trail_bars: int = 0  # >0: after the first target, trail the stop over the last N bars' extreme
    recent: deque = field(default_factory=deque)
    fills: list = field(default_factory=list)  # (exit time, fraction of the position, index price)
    last_end: datetime | None = None

    def __post_init__(self) -> None:
        self.stop = self.sig.stop
        self.targets = list(self.sig.targets)
        self.recent = deque(maxlen=max(self.trail_bars, 1))

    @property
    def risk(self) -> float:
        return abs(self.sig.entry - self.sig.stop) if self.sig.stop is not None else 0.0

    @property
    def valid(self) -> bool:
        return self.risk > 0 and bool(self.sig.targets)

    @property
    def closed(self) -> bool:
        return self.r is not None

    def _close(self, reason: str) -> bool:
        self.r = round(self.realized / self.risk, 3)
        self.reason = reason
        return True

    def update(self, b: Bar) -> bool:
        """Feed the next bar; returns True once the trade is closed."""
        sig = self.sig
        if self.closed or b.ts < sig.ts:
            return self.closed
        if sig.exit_by is not None and b.ts >= sig.exit_by:
            return self.finish()
        sgn = sig.direction.sign
        adverse = b.low if sgn > 0 else b.high
        end = b.ts + timedelta(minutes=1)
        if sgn * (adverse - self.stop) <= 0:
            self.fills.append((end, self.remaining, self.stop))
            self.realized += self.remaining * sgn * (self.stop - sig.entry)
            return self._close("stop" if self.stop == sig.stop else "breakeven" if self.stop == sig.entry else "trailing stop")
        favourable = b.high if sgn > 0 else b.low
        while self.targets and sgn * (favourable - self.targets[0].price) >= 0:
            t = self.targets.pop(0)
            part = min(self.remaining, t.size_pct / 100.0)
            self.fills.append((end, part, t.price))
            self.realized += part * sgn * (t.price - sig.entry)
            self.remaining -= part
            self.stop = sig.entry
        self.last_close = b.close
        self.last_end = end
        if self.remaining <= 1e-9:
            return self._close("targets")
        if self.trail_bars:
            self.recent.append(b)
            if self.remaining < 1.0 and len(self.recent) == self.trail_bars:
                level = min(x.low for x in self.recent) if sgn > 0 else max(x.high for x in self.recent)
                if sgn * (level - self.stop) > 0:
                    self.stop = level
        return False

    def finish(self) -> bool:
        """Close what is left at the last seen close (time exit / end of session)."""
        if self.closed:
            return True
        last = self.last_close if self.last_close is not None else self.sig.entry
        if self.remaining > 1e-9:
            self.fills.append((self.last_end or self.sig.ts, self.remaining, last))
        self.realized += self.remaining * self.sig.direction.sign * (last - self.sig.entry)
        return self._close("time exit")


@dataclass
class RiskLedger:
    """Realized R per trading day (each trade weighted by its size multiplier).

    One ledger can be shared by several engines (NIFTY and BANKNIFTY in the live runner), so the
    loss limits apply to the whole account rather than per symbol.
    """

    days: dict[date, float] = field(default_factory=lambda: defaultdict(float))

    def record(self, d: date, r: float) -> None:
        self.days[d] += r

    def day(self, d: date) -> float:
        return self.days.get(d, 0.0)

    def week(self, d: date) -> float:
        """Realized R from Monday of d's week up to and including d."""
        monday = d - timedelta(days=d.weekday())
        return sum(v for k, v in self.days.items() if monday <= k <= d)
