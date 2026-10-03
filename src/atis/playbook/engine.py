"""Playbook engine: replays or streams futures bars, runs setup detectors, gates, prices and sizes signals."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .config import CostParams, InstrumentSpec, PlaybookParams, RiskParams, SessionTimes
from .expiry import is_monthly_expiry_day, nearest_expiry, sessions_until
from .models import (Bar, Candidate, DayType, IBClass, OpenLocation, OpenType, PeriodStat, Session,
                     SetupSignal, Target)
from .options import OptionPlanner
from .orderflow import bar_delta
from .risk import round_trip_costs, size_trade
from .setups import DETECTORS
from .state import BarEvent, DayContext, SessionState
from .structure import (Balance, SessionProfile, TPO_LETTERS, analyze_session, average_ib, average_range,
                        average_va_width, classify_ib, classify_open, detect_balance, period_index,
                        session_start, value_migration)


@dataclass
class PremarketPlan:
    symbol: str
    date: date
    prior: SessionProfile | None
    balance: Balance | None
    migration: int
    avg_ib: float
    is_expiry: bool
    nearest_expiry: date
    scenarios: list[str]
    warnings: list[str]


@dataclass
class SessionReport:
    symbol: str
    date: date
    plan: PremarketPlan
    open_type: OpenType | None
    open_location: OpenLocation | None
    ib_high: float | None
    ib_low: float | None
    ib_class: IBClass | None
    day_type_at_check: DayType | None
    profile: SessionProfile
    signals: list[SetupSignal] = field(default_factory=list)
    skipped: list[tuple[datetime | None, str, str]] = field(default_factory=list)


def _finished(sig: SetupSignal, bar: Bar) -> bool:
    """A directional signal stops being live once futures hit its stop or its final target."""
    sgn = sig.direction.sign
    if sgn * ((bar.low if sgn > 0 else bar.high) - sig.stop) <= 0:
        return True
    return bool(sig.targets) and sgn * ((bar.high if sgn > 0 else bar.low) - sig.targets[-1].price) >= 0


def infer_bar_minutes(bars: list[Bar]) -> int:
    gaps = [(b.ts - a.ts).total_seconds() / 60 for a, b in zip(bars, bars[1:]) if b.ts > a.ts]
    return max(1, int(round(min(gaps)))) if gaps else 1


class PlaybookEngine:
    def __init__(self, spec: InstrumentSpec, params: PlaybookParams = PlaybookParams(),
                 times: SessionTimes = SessionTimes(), risk: RiskParams = RiskParams(),
                 costs: CostParams = CostParams(), bar_minutes: int = 1,
                 history: Iterable[SessionProfile] = (), disabled_setups: Iterable[str] = ()):
        self.spec = spec
        self.params = params
        self.times = times
        self.risk = risk
        self.costs = costs
        self.bar_minutes = bar_minutes
        self.history: list[SessionProfile] = list(history)
        self.disabled_setups: set[str] = set(disabled_setups)
        self._st: SessionState | None = None

    @property
    def state(self) -> SessionState | None:
        """The live session state (read-only by convention) or None between sessions."""
        return self._st

    @property
    def plan(self) -> PremarketPlan | None:
        return self._plan if self._st is not None else None

    @property
    def open_type(self) -> OpenType | None:
        return self._open_type if self._st is not None else None

    @property
    def day_type_check(self) -> DayType | None:
        return self._day_type_check if self._st is not None else None

    @property
    def signals(self) -> list[SetupSignal]:
        return list(self._signals) if self._st is not None else []

    # ---- session lifecycle -------------------------------------------------------------------

    def start_session(self, d: date, ctx: DayContext = DayContext()) -> PremarketPlan:
        h, p = self.history, self.params
        st = SessionState(
            spec=self.spec, params=p, times=self.times, date=d, ctx=ctx,
            prior=h[-1] if h else None, history=h, balance=detect_balance(h, p),
            migration=value_migration(h, p.migration_sessions),
            avg_ib=average_ib(h, p.ib_lookback) or 0.0, avg_range=average_range(h, p.ib_lookback),
            avg_va_width=average_va_width(h, p.ib_lookback),
            is_expiry=self.spec.expiry_day_rules and nearest_expiry(self.spec, d, ctx.holidays) == d,
        )
        self._st = st
        self._period: PeriodStat | None = None
        self._candle: PeriodStat | None = None
        self._fired: set[str] = set()
        self._signals: list[SetupSignal] = []
        self._live: list[SetupSignal] = []
        self._trades = 0
        self._short_premium_taken = False
        self._directional_blocked = False
        self._day_type_check: DayType | None = None
        self._open_type: OpenType | None = None
        self._plan = self._build_plan(st)
        return self._plan

    def on_bar(self, bar: Bar) -> list[SetupSignal]:
        st = self._st
        if st is None:
            raise RuntimeError("start_session() must be called before on_bar()")
        if bar.ts.date() != st.date:
            raise ValueError(f"bar {bar.ts} is not in session {st.date}")
        if not (self.times.open <= bar.ts.time() < self.times.close):
            return []
        st.now = bar.ts + timedelta(minutes=self.bar_minutes)
        idx = period_index(bar.ts, self.times)
        idx15 = period_index(bar.ts, self.times, 15)
        if self._period is not None and self._period.index < idx:
            self._finalize_period()
        if self._candle is not None and self._candle.index < idx15:
            self._finalize_candle()

        delta, estimated = bar_delta(bar, st.last)
        st.flow_estimated |= estimated
        if st.open is None:
            st.open = bar.open
        st.high, st.low, st.last = max(st.high, bar.high), min(st.low, bar.low), bar.close
        st.bars.append(bar)
        st.deltas.append(delta)
        st.vp.add_bar(bar)
        st.tpo.add(idx, bar.low, bar.high)
        self._period = self._update_bucket(self._period, bar, delta, idx, self.times.period_minutes)
        self._candle = self._update_bucket(self._candle, bar, delta, idx15, 15)

        period_closed = self._finalize_period() if st.now >= self._period.end else None
        candle_closed = self._finalize_candle() if st.now >= self._candle.end else None
        self._live = [s for s in self._live if not _finished(s, bar)]

        if (self._day_type_check is None and st.ib_complete
                and st.now >= st.at(self.times.day_type_check)):
            self._day_type_check = st.developing_day_type()
            if self._day_type_check in (DayType.NEUTRAL, DayType.NEUTRAL_EXTREME):
                self._directional_blocked = True
                st.skip("*", f"neutral structure by {self.times.day_type_check:%H:%M} - no directional trades today")

        ev = BarEvent(bar, st.now, period_closed, candle_closed)
        out: list[SetupSignal] = []
        for sid, detect in DETECTORS:
            if sid in self._fired or sid in self.disabled_setups:
                continue
            cand = detect(st, ev)
            if cand is None:
                continue
            self._fired.add(sid)
            reason = self._gate(cand)
            if reason:
                st.skip(sid, reason)
                continue
            out.append(self._build_signal(cand, bar))
        self._signals.extend(out)
        return out

    def end_session(self) -> SessionReport:
        st = self._st
        if st is None or not st.bars:
            raise RuntimeError("no bars were processed for this session")
        profile = analyze_session(Session(st.date, st.bars), self.spec, self.params, self.times,
                                  st.prior, st.avg_ib or None, st.avg_range)
        report = SessionReport(
            symbol=self.spec.symbol, date=st.date, plan=self._plan,
            open_type=self._open_type or profile.open_type, open_location=st.open_loc,
            ib_high=st.ib_high, ib_low=st.ib_low, ib_class=st.ib_class,
            day_type_at_check=self._day_type_check, profile=profile,
            signals=list(self._signals), skipped=list(st.skips),
        )
        self.history.append(profile)
        self._st = None
        return report

    def run_session(self, session: Session, ctx: DayContext = DayContext()) -> SessionReport:
        self.bar_minutes = infer_bar_minutes(session.bars)
        self.start_session(session.date, ctx)
        for bar in session.bars:
            self.on_bar(bar)
        return self.end_session()

    def run(self, sessions: Iterable[Session], contexts: Mapping[date, DayContext] | None = None,
            warmup: int = 1) -> list[SessionReport]:
        """Run sessions in order; the first `warmup` sessions only build history."""
        reports = []
        for i, s in enumerate(sorted(sessions, key=lambda s: s.date)):
            ctx = (contexts or {}).get(s.date, DayContext())
            if i < warmup:
                prior = self.history[-1] if self.history else None
                self.history.append(analyze_session(s, self.spec, self.params, self.times, prior))
                continue
            reports.append(self.run_session(s, ctx))
        return reports

    # ---- internals ---------------------------------------------------------------------------

    def _update_bucket(self, cur: PeriodStat | None, bar: Bar, delta: float, idx: int,
                       minutes: int) -> PeriodStat:
        if cur is None:
            start = session_start(bar.ts.date(), self.times) + timedelta(minutes=idx * minutes)
            letter = TPO_LETTERS[idx] if minutes == self.times.period_minutes else ""
            cur = PeriodStat(idx, letter, start, start + timedelta(minutes=minutes),
                             bar.open, bar.high, bar.low, bar.close)
        cur.update(bar, delta)
        return cur

    def _finalize_period(self) -> PeriodStat:
        st, p = self._st, self._period
        self._period = None
        st.periods.append(p)
        st.dpoc_at_period.append(st.dpoc())
        if p.index == 0:
            a_bars = [b for b in st.bars if b.ts < p.end]
            self._open_type = classify_open(a_bars, st.open, st.prior, st.avg_ib or p.high - p.low,
                                            self.params, st.row)
        if p.index == self.times.ib_periods - 1 and st.ib_high is None:
            st.ib_high, st.ib_low = st.high, st.low
            st.ib_class = classify_ib(st.ib_range, st.avg_ib, self.params)
        return p

    def _finalize_candle(self) -> PeriodStat:
        c = self._candle
        self._candle = None
        self._st.candles15.append(c)
        return c

    def _gate(self, cand: Candidate) -> str | None:
        st, t, now = self._st, self.times, self._st.now
        short = cand.structure.is_short_premium
        if self._trades >= self.risk.max_trades_per_day:
            return "max trades per day reached"
        event = st.event_within(now, self.params.event_buffer_minutes)
        if event:
            return f"scheduled event at {event:%H:%M} within the hour"
        if short and st.ctx.vix_rising:
            return "India VIX rising - no premium selling"
        if short and self._short_premium_taken:
            return "premium-selling structure already taken today"
        if not short and self._directional_blocked:
            return f"neutral/unclear structure by {t.day_type_check:%H:%M} - no directional trades"
        opposed = next((s for s in self._live if s.direction.sign == -cand.direction.sign != 0), None)
        if opposed:
            return f"conflicts with live {opposed.setup_id} {opposed.direction.value} (its stop has not been hit)"
        if st.is_expiry:
            if cand.group == "C" and now > st.at(t.expiry_no_new_shorts_after):
                return "expiry day: no new short premium after 13:30"
            if not short and now > st.at(t.expiry_buy_only_breakout_after) and cand.setup_id != "A3":
                return "expiry day after 14:00: only small A3 breakout buys"
        if cand.horizon == "intraday" and now > st.at(t.last_entry):
            return "after the last entry time"
        return None

    def _exit_by(self, cand: Candidate) -> datetime | None:
        st, t = self._st, self.times
        if cand.horizon != "intraday":
            return None
        flat = st.at(t.expiry_flat_by if st.is_expiry else t.flat_by)
        if cand.structure.is_short_premium:
            return min(flat, st.at(t.expiry_short_exit if st.is_expiry else t.premium_exit))
        return flat

    def _build_signal(self, cand: Candidate, bar: Bar) -> SetupSignal:
        st = self._st
        notes = list(cand.notes)
        sgn = cand.direction.sign
        if sgn and cand.stop is not None and not cand.targets:
            risk = abs(cand.entry - cand.stop)
            cand.targets = [Target(round(cand.entry + sgn * risk, 2), "1R (price already beyond structural targets)", 100.0)]
        if st.is_expiry and not cand.structure.is_short_premium \
                and st.now > st.at(self.times.expiry_buy_only_breakout_after):
            cand.size_multiplier *= 0.5
            notes.append("expiry afternoon: small fixed-rupee-risk size")
        if st.is_expiry:
            notes.append("expiry day: exit before the 15:15 closing auction session")
        if st.ctx.vix_rising and not cand.structure.is_short_premium:
            notes.append("India VIX rising - confirm it is not spiking against the trade")
        planner = OptionPlanner(self.spec, self.params, st.ctx.basis, st.ctx.iv, st.ctx.rate, st.ctx.holidays)
        plan = planner.build(cand, bar.close, st.now)
        sizing = size_trade(cand, plan, self.spec.lot_size, self.risk)
        if sizing.lots == 0:
            notes.append("risk budget is too small for one lot at this stop - skip")
        self._trades += 1
        self._short_premium_taken |= cand.structure.is_short_premium
        sig = SetupSignal(
            setup_id=cand.setup_id, name=cand.name, group=cand.group, symbol=self.spec.symbol,
            ts=st.now, direction=cand.direction, entry=round(cand.entry, 2),
            stop=None if cand.stop is None else round(cand.stop, 2), stop_rule=cand.stop_rule,
            targets=cand.targets, option_plan=plan, lots=sizing.lots, risk_per_lot=sizing.risk_per_lot,
            risk_total=None if sizing.risk_per_lot is None else round(sizing.risk_per_lot * sizing.lots, 2),
            sizing_basis=sizing.basis, exit_by=self._exit_by(cand), horizon=cand.horizon,
            size_multiplier=cand.size_multiplier,
            est_costs=round_trip_costs(plan, sizing.lots, self.spec.lot_size, self.costs),
            confirmations=cand.confirmations, notes=notes,
        )
        if sig.stop is not None and sig.direction.sign:
            self._live.append(sig)
        return sig

    def _build_plan(self, st: SessionState) -> PremarketPlan:
        pr, b, hol = st.prior, st.balance, st.ctx.holidays
        scen: list[str] = []
        warn: list[str] = []
        if pr:
            scen += [
                f"Open above VAH {pr.vah:g} and drive without returning to the open -> A1 long (ATM/ITM CE)",
                f"Open below VAL {pr.val:g} and drive -> A1 short (ATM/ITM PE)",
                "Open tests prior VAH/VAL/POC/high/low, fails, drives back through the open -> A2",
                f"Gap outside value rejected back through the open and inside {pr.low:g}-{pr.high:g} "
                f"-> B1 toward POC {pr.poc:g}",
                f"Open outside value, then two 30-min closes inside {pr.val:g}-{pr.vah:g} -> B2 to the opposite edge",
                f"Open inside value -> wait for the IB ({self.times.ib_end:%H:%M}); IB inside value and not narrow -> C1 condor "
                f"beyond {pr.high:g}/{pr.low:g}",
                "Narrow IB + 30-min close beyond it -> A3 (target 2x IB); extension fails back inside -> B3",
            ]
            if pr.poor_high:
                scen.append(f"Poor high {pr.high:g} unrepaired -> B4 repair target")
            if pr.poor_low:
                scen.append(f"Poor low {pr.low:g} unrepaired -> B4 repair target")
            for lo, hi in pr.single_prints:
                scen.append(f"Single prints {lo:g}-{hi:g} -> A5 support/resistance on pullbacks")
            if pr.selling_tail:
                scen.append(f"Selling tail {pr.selling_tail[0]:g}-{pr.selling_tail[1]:g} (excess, stop anchor)")
            if pr.buying_tail:
                scen.append(f"Buying tail {pr.buying_tail[0]:g}-{pr.buying_tail[1]:g} (excess, stop anchor)")
        else:
            warn.append("no prior session in history - value-based setups are disabled today")
        if b:
            scen.append(f"Composite balance {b.val:g}-{b.vah:g} (POC {b.poc:g}, {len(b.sessions)} sessions): "
                        f"breakout + retest -> A4" + ("; quiet near POC -> C3 positional condor" if b.quiet else ""))
        if st.migration:
            warn.append(f"value migrating {'higher' if st.migration > 0 else 'lower'} for "
                        f"{self.params.migration_sessions} sessions - fades against it need strong rejection")
        expiry = nearest_expiry(self.spec, st.date, hol)
        if st.is_expiry:
            warn.append("EXPIRY DAY: defined-risk only, shorts out by 14:30, only small A3 buys after 14:00, "
                        "flat by 15:05 before the closing auction")
        if self.spec.expiry_day_rules and is_monthly_expiry_day(self.spec, st.date, hol):
            warn.append("monthly expiry: roll the futures profile to the next-month contract after today")
        if not self.spec.weekly_expiry and \
                sessions_until(st.date, expiry, hol, self.spec.trades_weekends) >= self.params.early_series_sessions:
            warn.append("BANKNIFTY early series: favour directional setups with ITM options or debit spreads")
        for e in st.ctx.events:
            if e.date() == st.date:
                warn.append(f"event at {e:%H:%M}: no new entries within {self.params.event_buffer_minutes} min before")
        if st.ctx.vix_rising:
            warn.append("India VIX rising: no premium selling today")
        warn.append("All setups are CANDIDATE (unvalidated) - backtest on futures data before risking capital")
        return PremarketPlan(self.spec.symbol, st.date, pr, b, st.migration, st.avg_ib, st.is_expiry,
                             expiry, scen, warn)
