"""Risk manager: account-level kill switches and per-order sanity checks.

State lives in a JSON file so a restart cannot forget a halt, today's starting equity, or the
equity peak. Once halted, the bot only flattens until a person runs `atis-crypto resume`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from .config import RiskLimits


@dataclass
class RiskState:
    peak_equity: float = 0.0
    day: str = ""
    day_start_equity: float = 0.0
    halted: bool = False
    halt_reason: str = ""
    last_rebalance_day: str = ""

    @classmethod
    def load(cls, path: Path) -> RiskState:
        if path.exists():
            return cls(**json.loads(path.read_text()))
        return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=1))
        tmp.replace(path)


@dataclass(frozen=True)
class OrderCheck:
    symbol: str
    target_notional: float
    reason: str | None  # None = approved


class RiskManager:
    def __init__(self, limits: RiskLimits, state: RiskState):
        self.limits, self.state = limits, state

    def update(self, equity: float, today: date) -> str | None:
        """Record equity; returns a halt reason when a kill switch trips (and latches the halt)."""
        s, lim = self.state, self.limits
        if s.day != today.isoformat():
            s.day, s.day_start_equity = today.isoformat(), equity
        s.peak_equity = max(s.peak_equity, equity)
        if s.halted:
            return s.halt_reason
        reason = None
        if s.day_start_equity > 0 and equity <= s.day_start_equity * (1 - lim.daily_loss_halt):
            reason = (f"daily loss {equity / s.day_start_equity - 1:+.1%} breached the "
                      f"-{lim.daily_loss_halt:.0%} limit")
        elif s.peak_equity > 0 and equity <= s.peak_equity * (1 - lim.drawdown_halt):
            reason = (f"drawdown {equity / s.peak_equity - 1:+.1%} from peak breached the "
                      f"-{lim.drawdown_halt:.0%} limit")
        if reason:
            s.halted, s.halt_reason = True, reason
        return reason

    def resume(self, equity: float) -> None:
        """Manual reset after a halt: the current equity becomes the new peak and day start."""
        s = self.state
        s.halted, s.halt_reason = False, ""
        s.peak_equity = s.day_start_equity = equity

    def check_orders(self, equity: float, targets: dict[str, float], marks: dict[str, float],
                     signal_prices: dict[str, float], data_age_hours: dict[str, float]) -> list[OrderCheck]:
        """Approve or reject each coin's target notional; scale everything down if gross is too high."""
        lim = self.limits
        out: dict[str, OrderCheck] = {}
        for sym, notional in targets.items():
            reason = None
            if self.state.halted:
                reason = f"halted: {self.state.halt_reason}"
            elif data_age_hours.get(sym, 1e9) > lim.max_data_age_hours:
                reason = f"stale data: last daily candle {data_age_hours.get(sym, 0):.0f}h old"
            elif not marks.get(sym) or not signal_prices.get(sym):
                reason = "no price"
            elif abs(marks[sym] / signal_prices[sym] - 1) > lim.max_price_deviation:
                reason = (f"mark {marks[sym]:,.1f} is {marks[sym] / signal_prices[sym] - 1:+.1%} from the "
                          f"latest traded price {signal_prices[sym]:,.1f}")
            out[sym] = OrderCheck(sym, notional, reason)
        approved = [c for c in out.values() if c.reason is None]
        gross = sum(abs(c.target_notional) for c in approved) / equity if equity > 0 else 0.0
        if gross > lim.max_gross_exposure:
            k = lim.max_gross_exposure / gross
            for c in approved:
                out[c.symbol] = OrderCheck(c.symbol, c.target_notional * k, None)
        return list(out.values())
