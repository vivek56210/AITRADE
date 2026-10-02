"""Replay backtest on futures bars.

Directional signals are scored in R (futures points / initial risk); premium-selling signals are
scored by whether futures stayed inside the short strikes. Neither is option P&L - that needs
historical option-chain data.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date

from .config import InstrumentSpec
from .engine import PlaybookEngine, SessionReport
from .models import Bar, Session, SetupSignal
from .state import DayContext


@dataclass
class TradeOutcome:
    signal: SetupSignal
    r_multiple: float | None = None
    contained: bool | None = None
    exit_reason: str = ""


@dataclass
class SetupStats:
    setup_id: str
    trades: int = 0
    wins: int = 0
    total_r: float = 0.0
    premium_trades: int = 0
    contained: int = 0

    @property
    def win_rate(self) -> float | None:
        return self.wins / self.trades if self.trades else None

    @property
    def avg_r(self) -> float | None:
        return self.total_r / self.trades if self.trades else None

    @property
    def containment_rate(self) -> float | None:
        return self.contained / self.premium_trades if self.premium_trades else None


@dataclass
class BacktestResult:
    reports: list[SessionReport]
    outcomes: list[TradeOutcome]
    stats: dict[str, SetupStats] = field(default_factory=dict)


def simulate_directional(sig: SetupSignal, bars: list[Bar]) -> TradeOutcome:
    sgn = sig.direction.sign
    risk = abs(sig.entry - sig.stop) if sig.stop is not None else 0.0
    if risk <= 0 or not sig.targets:
        return TradeOutcome(sig, None, None, "no stop/targets")
    stop, remaining, realized = sig.stop, 1.0, 0.0
    targets = list(sig.targets)
    live = [b for b in bars if b.ts >= sig.ts and (sig.exit_by is None or b.ts < sig.exit_by)]
    for b in live:
        adverse = b.low if sgn > 0 else b.high
        if sgn * (adverse - stop) <= 0:
            realized += remaining * sgn * (stop - sig.entry)
            return TradeOutcome(sig, round(realized / risk, 3), None, "stop" if stop != sig.entry else "breakeven")
        favourable = b.high if sgn > 0 else b.low
        while targets and sgn * (favourable - targets[0].price) >= 0:
            t = targets.pop(0)
            part = min(remaining, t.size_pct / 100.0)
            realized += part * sgn * (t.price - sig.entry)
            remaining -= part
            stop = sig.entry
        if remaining <= 1e-9:
            return TradeOutcome(sig, round(realized / risk, 3), None, "targets")
    last = live[-1].close if live else sig.entry
    realized += remaining * sgn * (last - sig.entry)
    return TradeOutcome(sig, round(realized / risk, 3), None, "time exit")


def simulate_premium(sig: SetupSignal, bars: list[Bar], basis: float = 0.0) -> TradeOutcome:
    shorts = [l for l in sig.option_plan.legs if l.side == "SELL"]
    upper = min((l.strike for l in shorts if l.right == "CE"), default=None)
    lower = max((l.strike for l in shorts if l.right == "PE"), default=None)
    live = [b for b in bars if b.ts >= sig.ts and (sig.exit_by is None or b.ts < sig.exit_by)]
    for b in live:
        if upper is not None and b.high - basis >= upper:
            return TradeOutcome(sig, None, False, "call side breached")
        if lower is not None and b.low - basis <= lower:
            return TradeOutcome(sig, None, False, "put side breached")
    return TradeOutcome(sig, None, True, "contained to exit" if sig.horizon == "intraday" else "contained to session end")


def backtest(sessions: Iterable[Session], spec: InstrumentSpec, engine: PlaybookEngine | None = None,
             contexts: Mapping[date, DayContext] | None = None, warmup: int = 3) -> BacktestResult:
    engine = engine or PlaybookEngine(spec)
    sessions = sorted(sessions, key=lambda s: s.date)
    by_date = {s.date: s for s in sessions}
    reports = engine.run(sessions, contexts, warmup=warmup)
    outcomes: list[TradeOutcome] = []
    stats: dict[str, SetupStats] = defaultdict(lambda: SetupStats(""))
    for rep in reports:
        bars = by_date[rep.date].bars
        basis = (contexts or {}).get(rep.date, DayContext()).basis
        for sig in rep.signals:
            st = stats[sig.setup_id]
            st.setup_id = sig.setup_id
            if sig.option_plan.structure.is_short_premium:
                out = simulate_premium(sig, bars, basis)
                st.premium_trades += 1
                st.contained += bool(out.contained)
            else:
                out = simulate_directional(sig, bars)
                if out.r_multiple is not None:
                    st.trades += 1
                    st.total_r += out.r_multiple
                    st.wins += out.r_multiple > 0
            outcomes.append(out)
    return BacktestResult(reports, outcomes, dict(sorted(stats.items())))
