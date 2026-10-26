"""The bot's two jobs: a daily rebalance just after 00:00 UTC, and an hourly risk watch.

rebalance: read Delta's completed daily candles, compute each coin's target, run the risk checks,
           trade the difference (reductions first, all reduce-only), then re-read positions and
           report. A day is rebalanced at most once, keyed by its UTC date.
watch:     re-mark the account; if a kill switch trips, flatten everything and halt until a
           person runs `resume`.
Every run appends one JSON line to the journal and sends one Telegram message.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .broker import Broker, BrokerError
from .config import MARKETS, BotConfig
from .data import delta_candles
from .risk import RiskManager, RiskState
from .signals import Candle, needs_rebalance, target_exposure, volume_profile


@dataclass
class CoinPlan:
    symbol: str
    score: float | None = None
    vol: float | None = None
    signal_close: float | None = None
    last_price: float | None = None  # latest hourly close: the reference the mark is checked against
    data_age_h: float | None = None
    mark: float | None = None
    target_exposure: float = 0.0
    current: int = 0
    target: int = 0
    order: int = 0
    note: str = ""
    profile: tuple[float, float, float] | None = None
    fills: list = field(default_factory=list)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CryptoBot:
    def __init__(self, broker: Broker, state_dir: Path, cfg: BotConfig = BotConfig(),
                 notify: Callable[[str], bool] = lambda m: True,
                 candles: Callable[[str, str, datetime, datetime], list[Candle]] = delta_candles,
                 now: Callable[[], datetime] = utcnow):
        self.broker, self.dir, self.cfg, self.notify = broker, state_dir, cfg, notify
        self.candles, self.now = candles, now
        self.state_path = state_dir / f"crypto-risk-{broker.name}.json"
        self.journal = state_dir / f"crypto-journal-{broker.name}.jsonl"
        self.risk = RiskManager(cfg.risk, RiskState.load(self.state_path))

    def _log(self, kind: str, **data) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self.journal, "a") as f:
            f.write(json.dumps({"t": self.now().isoformat(timespec="seconds"), "kind": kind,
                                "broker": self.broker.name, **data}, default=str) + "\n")

    # ---- shared ------------------------------------------------------------------------------

    def flatten(self, why: str) -> list:
        fills = []
        for sym, n in self.broker.positions().items():
            fills.append(self.broker.market_order(sym, -n, reduce_only=True,
                                                  client_id=f"flat-{sym}-{self.now():%Y%m%d%H%M}"))
        self._log("flatten", reason=why, fills=[f.__dict__ for f in fills])
        return fills

    def _guard(self) -> tuple[float, str | None]:
        equity = self.broker.equity()
        tripped = self.risk.update(equity, self.now().date())
        self.risk.state.save(self.state_path)
        return equity, tripped

    # ---- daily rebalance ---------------------------------------------------------------------

    def plan(self, coin: str) -> CoinPlan:
        now = self.now()
        today = datetime(now.year, now.month, now.day)
        p = CoinPlan(coin)
        days = max(self.cfg.trend.lookbacks) + self.cfg.trend.vol_window + 10
        daily = [c for c in self.candles(coin, "1d", today - timedelta(days=days), today) if c.ts < today]
        if not daily:
            p.note = "no daily candles"
            return p
        last_close_time = daily[-1].ts + timedelta(days=1)
        p.data_age_h = (now - last_close_time).total_seconds() / 3600
        p.signal_close = daily[-1].close
        t = target_exposure([c.close for c in daily], self.cfg.trend)
        if t is None:
            p.note = f"only {len(daily)} daily candles"
            return p
        p.score, p.vol = t.score, t.vol
        p.target_exposure = t.exposure * self.cfg.weights.get(coin, 0.0)
        hourly = self.candles(coin, "1h", today - timedelta(days=20), now)
        p.last_price = hourly[-1].close if hourly else None
        prof = volume_profile([c for c in hourly if c.ts < today])
        p.profile = (prof.poc, prof.vah, prof.val) if prof else None
        return p

    def rebalance(self, force: bool = False) -> list[CoinPlan]:
        day = self.now().date().isoformat()
        if self.risk.state.last_rebalance_day == day and not force:
            self.notify(f"<b>Crypto bot</b> ({self.broker.name}): already rebalanced for {day}; nothing to do.")
            return []
        equity, tripped = self._guard()
        if tripped or self.risk.state.halted:
            fills = self.flatten(tripped or self.risk.state.halt_reason)
            self.notify(f"<b>Crypto bot HALTED</b> ({self.broker.name}): {self.risk.state.halt_reason}. "
                        f"Positions closed: {len(fills)}. Run <code>atis-crypto resume</code> after reviewing.")
            return []
        plans = [self.plan(c) for c in self.cfg.markets]
        held = self.broker.positions()
        for p in plans:
            p.current = held.get(p.symbol, 0)
            try:
                p.mark = self.broker.mark_price(p.symbol)
            except Exception as exc:
                p.note = f"mark price unavailable ({exc})"
        checks = self.risk.check_orders(
            equity,
            {p.symbol: p.target_exposure * equity for p in plans if p.score is not None},
            {p.symbol: p.mark for p in plans if p.mark}, {p.symbol: p.last_price for p in plans if p.last_price},
            {p.symbol: p.data_age_h for p in plans if p.data_age_h is not None})
        approved = {c.symbol: c for c in checks}
        for p in plans:
            c = approved.get(p.symbol)
            if c is None or c.reason:
                p.note = p.note or (c.reason if c else "no signal") + " - position left unchanged"
                p.target = p.current
                continue
            cv = MARKETS[p.symbol].contract_value
            p.target = int(round(c.target_notional / (p.mark * cv)))
            have = p.current * cv * p.mark / equity
            want = p.target * cv * p.mark / equity
            if not needs_rebalance(want, have, self.cfg.trend.band) or p.target == p.current:
                p.note = p.note or "within the rebalance band - no trade"
                p.target = p.current
            p.order = p.target - p.current
        # reductions first (frees margin), then increases; a flip is a reduce-only close plus an open
        for p in sorted(plans, key=lambda x: abs(x.target) >= abs(x.current), reverse=False):
            if not p.order:
                continue
            try:
                self.broker.prepare(p.symbol, self.cfg.risk.exchange_leverage)
                tag = f"{day.replace('-', '')}-{p.symbol}"
                if p.current and (p.target == 0 or (p.target > 0) != (p.current > 0) or abs(p.target) < abs(p.current)):
                    close = -p.current if (p.target == 0 or (p.target > 0) != (p.current > 0)) else p.target - p.current
                    p.fills.append(self.broker.market_order(p.symbol, close, True, f"r{tag}"))
                    rest = p.order - close
                else:
                    rest = p.order
                if rest:
                    p.fills.append(self.broker.market_order(p.symbol, rest, False, f"o{tag}"))
            except BrokerError as exc:
                p.note = f"order failed: {exc}"
        after = self.broker.positions()
        mismatch = [p.symbol for p in plans if after.get(p.symbol, 0) != p.target]
        self.risk.state.last_rebalance_day = day
        self.risk.state.save(self.state_path)
        equity_after = self.broker.equity()
        self._log("rebalance", equity=equity_after, plans=[{**p.__dict__, "fills": [f.__dict__ for f in p.fills]}
                                                         for p in plans], mismatch=mismatch)
        self.notify(self.message(plans, equity_after, mismatch))
        return plans

    def message(self, plans: list[CoinPlan], equity: float, mismatch: list[str]) -> str:
        s = self.risk.state
        dd = equity / s.peak_equity - 1 if s.peak_equity else 0.0
        lines = [f"<b>Crypto trend bot</b> - {self.now():%Y-%m-%d} rebalance ({self.broker.name})",
                 f"Equity {equity:,.2f} | drawdown from peak {dd:+.1%} | day start {s.day_start_equity:,.2f}"]
        for p in plans:
            cv = MARKETS[p.symbol].contract_value
            side = "LONG" if p.target > 0 else "SHORT" if p.target < 0 else "FLAT"
            lines.append("")
            lines.append(f"<b>{p.symbol}</b> {side} {abs(p.target)} contracts ({abs(p.target) * cv:g} coin)"
                         + (f", traded {p.order:+d}" if p.order else ""))
            if p.score is not None:
                lines.append(f"trend {p.score:+.2f} (20/60/120d) | vol {p.vol:.0%} | target {p.target_exposure:+.2f}x equity")
            if p.profile:
                lines.append(f"20d volume profile: POC {p.profile[0]:,.0f} VAH {p.profile[1]:,.0f} VAL {p.profile[2]:,.0f}")
            if p.note:
                lines.append(f"note: {p.note}")
        if mismatch:
            lines.append("")
            lines.append(f"<b>CHECK POSITIONS</b>: exchange position differs from target for {', '.join(mismatch)}")
        return "\n".join(lines)

    # ---- hourly watch ------------------------------------------------------------------------

    def watch(self) -> str | None:
        equity, tripped = self._guard()
        self._log("watch", equity=equity, peak=self.risk.state.peak_equity,
                  day_start=self.risk.state.day_start_equity, halted=self.risk.state.halted)
        if tripped and self.broker.positions():
            fills = self.flatten(tripped)
            self.notify(f"<b>Crypto bot HALTED</b> ({self.broker.name}): {tripped}. Closed {len(fills)} "
                        f"position(s). Equity {equity:,.2f}. Run <code>atis-crypto resume</code> after reviewing.")
        (self.dir / f"crypto-heartbeat-{self.broker.name}.json").write_text(
            json.dumps({"t": self.now().isoformat(timespec="seconds"), "equity": equity,
                        "halted": self.risk.state.halted}))
        return tripped

    def resume(self) -> float:
        equity = self.broker.equity()
        self.risk.resume(equity)
        self.risk.state.save(self.state_path)
        self._log("resume", equity=equity)
        self.notify(f"<b>Crypto bot resumed</b> ({self.broker.name}) at equity {equity:,.2f}.")
        return equity
