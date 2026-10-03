"""Replay backtest on futures bars.

Directional signals are scored in R (futures points / initial risk); premium-selling signals are
scored by whether futures stayed inside the short strikes. Neither is option P&L - that needs
historical option-chain data. When the instrument has an exchange fee (crypto perpetuals), each
directional trade also carries its round-trip fee in R, and the summary reports net figures.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date

from .config import InstrumentSpec
from .engine import PlaybookEngine, SessionReport
from .models import Bar, Session, SetupSignal
from .state import DayContext
from .trade import TradeState


@dataclass
class TradeOutcome:
    signal: SetupSignal
    r_multiple: float | None = None
    contained: bool | None = None
    exit_reason: str = ""
    cost_r: float = 0.0  # round-trip exchange fee in R (0 when the spec has no fee)

    @property
    def net_r(self) -> float | None:
        return None if self.r_multiple is None else round(self.r_multiple - self.cost_r, 3)


@dataclass
class SetupStats:
    setup_id: str
    trades: int = 0
    wins: int = 0
    total_r: float = 0.0
    premium_trades: int = 0
    contained: int = 0
    total_cost_r: float = 0.0

    @property
    def win_rate(self) -> float | None:
        return self.wins / self.trades if self.trades else None

    @property
    def avg_r(self) -> float | None:
        return self.total_r / self.trades if self.trades else None

    @property
    def total_net_r(self) -> float:
        return self.total_r - self.total_cost_r

    @property
    def containment_rate(self) -> float | None:
        return self.contained / self.premium_trades if self.premium_trades else None


@dataclass
class BacktestResult:
    reports: list[SessionReport]
    outcomes: list[TradeOutcome]
    stats: dict[str, SetupStats] = field(default_factory=dict)

    def summary(self) -> dict:
        """Totals over directional trades (R) plus premium containment, drawdown and monthly R."""
        rs = [(o.signal.ts, o.r_multiple) for o in self.outcomes if o.r_multiple is not None]
        cum = peak = max_dd = 0.0
        monthly: dict[str, float] = defaultdict(float)
        for ts, r in rs:
            cum += r
            peak = max(peak, cum)
            max_dd = min(max_dd, cum - peak)
            monthly[ts.strftime("%Y-%m")] += r
        gains = sum(r for _, r in rs if r > 0)
        losses = -sum(r for _, r in rs if r < 0)
        premium = [o for o in self.outcomes if o.contained is not None]
        net = _curve([o.net_r for o in self.outcomes if o.r_multiple is not None])
        return {
            "sessions": len(self.reports), "signals": len(self.outcomes), "directional_trades": len(rs),
            "total_r": round(cum, 3), "win_rate": sum(r > 0 for _, r in rs) / len(rs) if rs else None,
            "avg_r": cum / len(rs) if rs else None, "profit_factor": gains / losses if losses else None,
            "max_drawdown_r": round(max_dd, 3), "premium_trades": len(premium),
            "premium_contained": sum(bool(o.contained) for o in premium),
            "monthly_r": {k: round(v, 2) for k, v in sorted(monthly.items())},
            "total_cost_r": round(cum - net["total"], 3), "total_r_net": net["total"],
            "win_rate_net": net["win_rate"], "profit_factor_net": net["profit_factor"],
            "max_drawdown_r_net": net["max_drawdown"],
        }


def _curve(rs: list[float]) -> dict:
    cum = peak = max_dd = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)
    gains, losses = sum(r for r in rs if r > 0), -sum(r for r in rs if r < 0)
    return {"total": round(cum, 3), "win_rate": sum(r > 0 for r in rs) / len(rs) if rs else None,
            "profit_factor": gains / losses if losses else None, "max_drawdown": round(max_dd, 3)}


def fee_in_r(sig: SetupSignal, fee_per_side: float) -> float:
    """Entry plus exit fee on the traded notional, in units of the initial risk."""
    risk = abs(sig.entry - sig.stop) if sig.stop is not None else 0.0
    return round(2 * fee_per_side * sig.entry / risk, 3) if fee_per_side and risk > 0 else 0.0


def simulate_directional(sig: SetupSignal, bars: list[Bar]) -> TradeOutcome:
    trade = TradeState(sig)
    if not trade.valid:
        return TradeOutcome(sig, None, None, "no stop/targets")
    for b in bars:
        if trade.update(b):
            break
    trade.finish()
    return TradeOutcome(sig, trade.r, None, trade.reason)


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
             contexts: Mapping[date, DayContext] | None = None, warmup: int = 3,
             on_progress: Callable[[int, int], None] | None = None) -> BacktestResult:
    engine = engine or PlaybookEngine(spec)
    sessions = sorted(sessions, key=lambda s: s.date)
    contexts = contexts or {}
    engine.run(sessions[:warmup], contexts, warmup=warmup)
    todo = sessions[warmup:]
    reports: list[SessionReport] = []
    outcomes: list[TradeOutcome] = []
    stats: dict[str, SetupStats] = defaultdict(lambda: SetupStats(""))
    for i, session in enumerate(todo, 1):
        ctx = contexts.get(session.date, DayContext())
        rep = engine.run_session(session, ctx)
        reports.append(rep)
        for sig in rep.signals:
            st = stats[sig.setup_id]
            st.setup_id = sig.setup_id
            if sig.option_plan.structure.is_short_premium:
                out = simulate_premium(sig, session.bars, ctx.basis)
                st.premium_trades += 1
                st.contained += bool(out.contained)
            else:
                out = simulate_directional(sig, session.bars)
                if out.r_multiple is not None:
                    out.cost_r = fee_in_r(sig, spec.fee_per_side)
                    st.trades += 1
                    st.total_r += out.r_multiple
                    st.total_cost_r += out.cost_r
                    st.wins += out.r_multiple > 0
            outcomes.append(out)
        if on_progress:
            on_progress(i, len(todo))
    return BacktestResult(reports, outcomes, dict(sorted(stats.items())))
