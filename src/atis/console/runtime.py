"""Console runtime: a background replay worker driving the playbook engine, plus jobs, events and a journal.

All mutable state is guarded by one re-entrant lock; read models return plain JSON-able dicts.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import threading
import time as _time
import traceback
import uuid
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from ..playbook.backtest import backtest
from ..playbook.config import INSTRUMENTS
from ..playbook.data import load_csv, synthetic_sessions, to_sessions
from ..playbook.engine import PlaybookEngine, SessionReport, infer_bar_minutes
from ..playbook.models import Session, SetupSignal
from ..playbook.report import to_jsonable
from ..playbook.state import DayContext
from ..playbook.structure import SessionProfile
from .catalog import GROUPS, SETUPS
from .settings import LIVE_KEYS, ConsoleSettings, load_settings, save_settings, settings_from_dict, \
    settings_to_dict, schema

MAX_BATCH = 200


class RunState(str, Enum):
    IDLE = "idle"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    FINISHED = "finished"
    ERROR = "error"


class ConflictError(RuntimeError):
    pass


class _Cancelled(Exception):
    pass


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"
    done: int = 0
    total: int = 0
    created: float = field(default_factory=_time.time)
    started: float | None = None
    finished: float | None = None
    error: str | None = None
    result: dict[str, Any] | None = None
    cancel_requested: bool = False

    def summary(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "status": self.status, "done": self.done, "total": self.total,
                "progress": self.done / self.total if self.total else 0.0, "created": _iso(self.created),
                "started": _iso(self.started), "finished": _iso(self.finished),
                "duration_s": round((self.finished or _time.time()) - self.started, 2) if self.started else None,
                "error": self.error}


def _iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds") if ts else None


def signal_key(sig: SetupSignal) -> str:
    return f"{sig.ts.date()}|{sig.setup_id}|{sig.ts:%H:%M}"


def _histogram(profile) -> list[list[float]]:
    start, vols = profile.dense()
    return [[profile.price(start + i), round(v, 1)] for i, v in enumerate(vols) if v > 0]


def _levels(p: SessionProfile | None) -> dict[str, Any] | None:
    if p is None:
        return None
    return {"date": p.date.isoformat(), "open": p.open, "high": p.high, "low": p.low, "close": p.close,
            "poc": p.poc, "vah": p.vah, "val": p.val, "ib_high": p.ib_high, "ib_low": p.ib_low,
            "hvns": list(p.hvns), "lvns": list(p.lvns), "single_prints": [list(z) for z in p.single_prints],
            "poor_high": p.poor_high, "poor_low": p.poor_low, "day_type": p.day_type.value,
            "shape": p.shape.value, "open_type": p.open_type.value if p.open_type else None}


class Runtime:
    def __init__(self, settings_path: Path | None = None, journal_path: Path | None = None,
                 settings: ConsoleSettings | None = None, start_worker: bool = True):
        self.settings_path = settings_path
        self.journal_path = journal_path
        self.settings = settings or (load_settings(settings_path) if settings_path else ConsoleSettings())
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._shutdown = False
        self.state = RunState.IDLE
        self.applied: dict[str, Any] | None = None
        self.sessions: list[Session] = []
        self.engine: PlaybookEngine | None = None
        self.session_idx = 0
        self.bar_idx = 0
        self.warmup = 0
        self.in_session = False
        self.reports: list[SessionReport] = []
        self.started_at = _time.time()
        self.bars_processed = 0
        self.last_bar_ts: datetime | None = None
        self.rate = 0.0
        self.last_error: str | None = None
        self.heartbeat = _time.time()
        self._seen: dict[str, Any] = {}
        self._events: deque[dict[str, Any]] = deque(maxlen=5000)
        self._next_event = 1
        self.jobs: dict[str, Job] = {}
        self.last_backtest: str | None = None
        self.journal: dict[str, dict[str, Any]] = self._load_journal()
        self.log("info", "system", "console started")
        self._worker = threading.Thread(target=self._run, name="replay-worker", daemon=True)
        if start_worker:
            self._worker.start()

    # ---- logging ---------------------------------------------------------------------------

    def log(self, level: str, kind: str, message: str, market: datetime | None = None, **data: Any) -> None:
        with self._lock:
            self._events.append({"id": self._next_event, "wall": datetime.now().isoformat(timespec="seconds"),
                                 "market": market.isoformat(timespec="minutes") if market else None,
                                 "level": level, "kind": kind, "message": message, "data": to_jsonable(data)})
            self._next_event += 1

    def events(self, since: int = 0, limit: int = 200, level: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            out = [e for e in self._events if e["id"] > since and (level is None or e["level"] == level)]
            return out[-limit:]

    # ---- data / engine ---------------------------------------------------------------------

    def _context(self) -> DayContext:
        return self.settings.context.to_day_context()

    def _make_sessions(self, s: ConsoleSettings) -> list[Session]:
        if s.data_source == "csv":
            sessions = to_sessions(load_csv(Path(s.csv_path).expanduser()), s.times.open, s.times.close)
        else:
            base = 24000.0 if s.symbol == "NIFTY" else 52000.0
            sessions = synthetic_sessions(date.fromisoformat(s.synthetic_start), s.synthetic_days,
                                          base=base, seed=s.synthetic_seed)
        if len(sessions) < 2:
            raise ValueError("need at least 2 sessions of data (1 for history, 1 to trade)")
        return sessions

    def _make_engine(self, s: ConsoleSettings) -> PlaybookEngine:
        return PlaybookEngine(INSTRUMENTS[s.symbol], s.params, s.times, s.risk,
                              disabled_setups=s.disabled_setups)

    def _load(self) -> None:
        s = self.settings
        self.sessions = self._make_sessions(s)
        self.engine = self._make_engine(s)
        self.warmup = min(s.warmup_sessions, len(self.sessions) - 1)
        ctx = self._context()
        self.engine.run(self.sessions[:self.warmup], {x.date: ctx for x in self.sessions}, warmup=self.warmup)
        self.session_idx, self.bar_idx, self.in_session = self.warmup, 0, False
        self.reports, self.bars_processed, self.last_bar_ts, self.last_error = [], 0, None, None
        self.applied = settings_to_dict(s)
        self.state = RunState.READY
        self.log("info", "data", f"loaded {len(self.sessions)} {s.symbol} sessions "
                 f"({s.data_source}); {self.warmup} used as history",
                 first=self.sessions[0].date, last=self.sessions[-1].date)

    def _safe_load(self) -> None:
        try:
            self._load()
        except Exception as exc:
            self.state = RunState.ERROR
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.log("error", "data", f"failed to load data: {self.last_error}")
            raise

    def _advance(self) -> bool:
        """Process one bar. Returns False when there is nothing more to process."""
        if self.session_idx >= len(self.sessions):
            if self.state != RunState.FINISHED:
                self.state = RunState.FINISHED
                self.log("info", "replay", f"replay finished: {len(self.reports)} sessions, "
                         f"{sum(len(r.signals) for r in self.reports)} signals")
            return False
        session = self.sessions[self.session_idx]
        eng = self.engine
        if not self.in_session:
            eng.bar_minutes = infer_bar_minutes(session.bars)
            plan = eng.start_session(session.date, self._context())
            self.in_session = True
            self._seen = {"skips": 0, "open": False, "ib": False, "daytype": False}
            self.log("info", "session", f"session {session.date} started"
                     + (" (EXPIRY DAY)" if plan.is_expiry else ""), warnings=plan.warnings[:-1])
        bar = session.bars[self.bar_idx]
        try:
            signals = eng.on_bar(bar)
        except Exception as exc:
            self.state = RunState.ERROR
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.log("error", "engine", f"engine error on {bar.ts}: {self.last_error}",
                     trace=traceback.format_exc(limit=5))
            return False
        self.bars_processed += 1
        self.last_bar_ts = bar.ts
        self._diff_state(bar.ts)
        for sig in signals:
            self.log("signal", "signal", f"{sig.setup_id} {sig.name}: {sig.direction.value} "
                     f"@ {sig.entry:g}, {sig.lots} lot(s)", market=sig.ts, key=signal_key(sig))
        self.bar_idx += 1
        if self.bar_idx >= len(session.bars):
            rep = eng.end_session()
            self.reports.append(rep)
            self.log("info", "session", f"session {rep.date} closed: {rep.profile.day_type.value} day, "
                     f"{len(rep.signals)} signal(s)", market=bar.ts)
            self.session_idx += 1
            self.bar_idx = 0
            self.in_session = False
        return True

    def _diff_state(self, ts: datetime) -> None:
        eng, seen = self.engine, self._seen
        st = eng.state
        if not seen["open"] and eng.open_type:
            seen["open"] = True
            self.log("info", "structure", f"open type {eng.open_type.value} "
                     f"({st.open_loc.value if st.open_loc else 'no prior value'})", market=ts)
        if not seen["ib"] and st.ib_complete:
            seen["ib"] = True
            self.log("info", "structure", f"IB complete {st.ib_low:g}-{st.ib_high:g} "
                     f"({st.ib_class.value})", market=ts)
        if not seen["daytype"] and eng.day_type_check:
            seen["daytype"] = True
            self.log("info", "structure", f"day type at 11:30: {eng.day_type_check.value}", market=ts)
        for when, sid, reason in st.skips[seen["skips"]:]:
            self.log("skip", "skip", f"{sid}: {reason}", market=when or ts, setup=sid)
        seen["skips"] = len(st.skips)

    def _run(self) -> None:
        last = _time.time()
        while not self._shutdown:
            self.heartbeat = _time.time()
            with self._lock:
                running = self.state == RunState.RUNNING
                speed = self.settings.replay_speed
            if not running:
                self._wake.wait(0.5)
                self._wake.clear()
                continue
            n = 0
            with self._lock:
                for _ in range(MAX_BATCH if speed == 0 else 1):
                    if self.state != RunState.RUNNING or not self._advance():
                        break
                    n += 1
            now = _time.time()
            if n:
                inst = n / max(now - last, 1e-6)
                self.rate = inst if self.rate == 0 else 0.8 * self.rate + 0.2 * inst
            last = now
            if speed > 0:
                self._wake.wait(1.0 / speed)
                self._wake.clear()

    def shutdown(self) -> None:
        self._shutdown = True
        self._wake.set()

    # ---- control actions -------------------------------------------------------------------

    def start(self) -> None:
        with self._lock:
            if self.state in (RunState.IDLE, RunState.STOPPED, RunState.FINISHED, RunState.ERROR):
                self._safe_load()
            if self.state in (RunState.READY, RunState.PAUSED):
                self.state = RunState.RUNNING
                self.log("info", "control", "replay started")
        self._wake.set()

    def pause(self) -> None:
        with self._lock:
            if self.state != RunState.RUNNING:
                raise ConflictError(f"cannot pause while {self.state.value}")
            self.state = RunState.PAUSED
            self.log("info", "control", "replay paused")

    def stop(self) -> None:
        with self._lock:
            if self.state in (RunState.IDLE, RunState.STOPPED):
                raise ConflictError(f"already {self.state.value}")
            self.state = RunState.STOPPED
            self.rate = 0.0
            self.log("info", "control", "replay stopped (results kept until the next start)")

    def reset(self) -> None:
        with self._lock:
            self._safe_load()
            self.log("info", "control", "reset: data reloaded with current settings")

    def step(self, count: int = 1) -> int:
        with self._lock:
            if self.state == RunState.RUNNING:
                raise ConflictError("pause the replay before stepping")
            if self.state in (RunState.IDLE, RunState.STOPPED, RunState.FINISHED, RunState.ERROR):
                self._safe_load()
            done = 0
            for _ in range(max(1, min(count, 5000))):
                if not self._advance():
                    break
                done += 1
            if self.state not in (RunState.FINISHED, RunState.ERROR):
                self.state = RunState.PAUSED
            return done

    def set_speed(self, bars_per_second: float) -> None:
        with self._lock:
            self.update_settings({"replay_speed": bars_per_second})
        self._wake.set()

    def set_setup_enabled(self, setup_id: str, enabled: bool) -> None:
        with self._lock:
            disabled = set(self.settings.disabled_setups)
            disabled.discard(setup_id) if enabled else disabled.add(setup_id)
            self.update_settings({"disabled_setups": sorted(disabled)})
            if self.engine:
                self.engine.disabled_setups = set(self.settings.disabled_setups)
            self.log("info", "config", f"setup {setup_id} {'enabled' if enabled else 'disabled'}")

    def update_settings(self, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self.settings = settings_from_dict(data, self.settings)
            if self.settings_path:
                save_settings(self.settings_path, self.settings)
            if not set(data) <= LIVE_KEYS:
                self.log("info", "config", "settings saved" + (" - reset to apply" if self.pending_restart else ""))
            return self.settings_view()

    def restore_defaults(self) -> dict[str, Any]:
        with self._lock:
            return self.update_settings(settings_to_dict(ConsoleSettings()))

    @property
    def pending_restart(self) -> bool:
        if self.applied is None:
            return False
        now = settings_to_dict(self.settings)
        return any(now[k] != self.applied.get(k) for k in now if k not in LIVE_KEYS)

    # ---- jobs ------------------------------------------------------------------------------

    def start_backtest(self) -> Job:
        with self._lock:
            if any(j.kind == "backtest" and j.status in ("queued", "running") for j in self.jobs.values()):
                raise ConflictError("a backtest is already running")
            job = Job(uuid.uuid4().hex[:8], "backtest")
            self.jobs[job.id] = job
            snapshot = settings_from_dict(settings_to_dict(self.settings))
        threading.Thread(target=self._run_backtest, args=(job, snapshot), name=f"backtest-{job.id}",
                         daemon=True).start()
        self.log("info", "job", f"backtest {job.id} queued")
        return job

    def cancel_job(self, job_id: str) -> Job:
        with self._lock:
            job = self.jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            if job.status not in ("queued", "running"):
                raise ConflictError(f"job is {job.status}")
            job.cancel_requested = True
            return job

    def _run_backtest(self, job: Job, s: ConsoleSettings) -> None:
        job.status, job.started = "running", _time.time()
        try:
            sessions = self._make_sessions(s)
            warmup = min(s.warmup_sessions, len(sessions) - 1)
            job.total = len(sessions) - warmup
            ctx = s.context.to_day_context()

            def progress(done: int, total: int) -> None:
                job.done = done
                if job.cancel_requested:
                    raise _Cancelled()

            res = backtest(sessions, INSTRUMENTS[s.symbol], self._make_engine(s),
                           {x.date: ctx for x in sessions}, warmup=warmup, on_progress=progress)
            cum, curve, trades = 0.0, [], []
            for o in res.outcomes:
                sig = o.signal
                if o.r_multiple is not None:
                    cum += o.r_multiple
                    curve.append({"n": len(curve) + 1, "date": sig.ts.date().isoformat(), "cum_r": round(cum, 3)})
                trades.append({"date": sig.ts.date().isoformat(), "time": f"{sig.ts:%H:%M}",
                               "setup": sig.setup_id, "direction": sig.direction.value,
                               "structure": sig.option_plan.structure.value, "entry": sig.entry,
                               "stop": sig.stop, "r": o.r_multiple, "contained": o.contained,
                               "exit": o.exit_reason})
            stats = [{"setup": k, "trades": v.trades, "win_rate": v.win_rate, "avg_r": v.avg_r,
                      "total_r": round(v.total_r, 3), "premium_trades": v.premium_trades,
                      "containment_rate": v.containment_rate} for k, v in res.stats.items()]
            directional = [t for t in trades if t["r"] is not None]
            job.result = {
                "symbol": s.symbol, "sessions": len(res.reports), "signals": len(trades),
                "total_r": round(cum, 3),
                "win_rate": (sum(t["r"] > 0 for t in directional) / len(directional)) if directional else None,
                "stats": stats, "equity": curve, "trades": trades,
                "note": "futures replay: R multiples and condor containment, not option P&L",
            }
            job.status = "done"
            self.last_backtest = job.id
            self.log("info", "job", f"backtest {job.id} done: {len(trades)} signals, {cum:+.2f}R")
        except _Cancelled:
            job.status = "cancelled"
            self.log("warn", "job", f"backtest {job.id} cancelled")
        except Exception as exc:
            job.status, job.error = "failed", f"{type(exc).__name__}: {exc}"
            self.log("error", "job", f"backtest {job.id} failed: {job.error}")
        finally:
            job.finished = _time.time()

    # ---- journal ---------------------------------------------------------------------------

    def _load_journal(self) -> dict[str, dict[str, Any]]:
        if self.journal_path and self.journal_path.exists():
            return json.loads(self.journal_path.read_text())
        return {}

    def set_journal(self, key: str, status: str, note: str = "") -> dict[str, Any]:
        if status not in ("taken", "ignored", "open"):
            raise ValueError("status must be taken, ignored or open")
        with self._lock:
            if status == "open" and not note:
                self.journal.pop(key, None)
            else:
                self.journal[key] = {"status": status, "note": note[:500],
                                     "updated": datetime.now().isoformat(timespec="seconds")}
            if self.journal_path:
                tmp = self.journal_path.with_suffix(".tmp")
                tmp.write_text(json.dumps(self.journal, indent=2))
                os.replace(tmp, self.journal_path)
            self.log("info", "journal", f"signal {key} marked {status}")
            return self.journal.get(key, {"status": "open", "note": ""})

    # ---- read models -----------------------------------------------------------------------

    def _all_signals(self) -> list[SetupSignal]:
        out = [s for r in self.reports for s in r.signals]
        if self.in_session and self.engine:
            out += self.engine.signals
        return out

    def _signal_view(self, sig: SetupSignal) -> dict[str, Any]:
        key = signal_key(sig)
        d = to_jsonable(sig)
        d["key"] = key
        d["journal"] = self.journal.get(key, {"status": "open", "note": ""})
        return d

    def status(self) -> dict[str, Any]:
        with self._lock:
            s = self.settings
            session = self.sessions[self.session_idx] if self.session_idx < len(self.sessions) else None
            return {
                "state": self.state.value, "symbol": s.symbol, "data_source": s.data_source,
                "replay_speed": s.replay_speed, "sessions_total": max(len(self.sessions) - self.warmup, 0),
                "sessions_done": len(self.reports), "warmup_sessions": self.warmup,
                "current_date": session.date.isoformat() if session and self.in_session else None,
                "bar_index": self.bar_idx, "bars_in_session": len(session.bars) if session else 0,
                "last_bar_ts": self.last_bar_ts.isoformat(timespec="minutes") if self.last_bar_ts else None,
                "bars_processed": self.bars_processed, "bars_per_second": round(self.rate, 1),
                "uptime_s": round(_time.time() - self.started_at),
                "worker_alive": self._worker.is_alive(), "heartbeat_age_s": round(_time.time() - self.heartbeat, 2),
                "pending_restart": self.pending_restart, "last_error": self.last_error,
                "signals_total": len(self._all_signals()),
                "jobs_running": sum(j.status in ("queued", "running") for j in self.jobs.values()),
                "disabled_setups": list(s.disabled_setups),
            }

    def session_view(self, d: str | None = None) -> dict[str, Any] | None:
        """Live view of the session in progress, or a completed session by date (latest if none)."""
        with self._lock:
            live = self.in_session and self.engine is not None and (
                d is None or d == self.sessions[self.session_idx].date.isoformat())
            if live:
                eng, st = self.engine, self.engine.state
                plan, bars = eng.plan, st.bars
                va = st.vp.value_area(self.settings.params.value_area_pct)
                today = {"open": st.open, "high": st.high, "low": st.low, "last": st.last,
                         "ib_high": st.ib_high, "ib_low": st.ib_low,
                         "ib_class": st.ib_class.value if st.ib_class else None,
                         "dpoc": st.dpoc(), "vah": va.vah if va else None, "val": va.val if va else None,
                         "open_type": eng.open_type.value if eng.open_type else None,
                         "open_location": st.open_loc.value if st.open_loc else None,
                         "day_type": (st.developing_day_type() or eng.day_type_check or None),
                         "is_expiry": st.is_expiry}
                if today["day_type"] is not None:
                    today["day_type"] = today["day_type"].value
                profile, signals, skips = _histogram(st.vp), eng.signals, list(st.skips)
                session_date = st.date
            else:
                rep = next((r for r in reversed(self.reports) if d is None or r.date.isoformat() == d), None)
                if rep is None:
                    return None
                p = rep.profile
                plan, session_date = rep.plan, rep.date
                bars = next(x.bars for x in self.sessions if x.date == rep.date)
                today = {"open": p.open, "high": p.high, "low": p.low, "last": p.close,
                         "ib_high": rep.ib_high, "ib_low": rep.ib_low,
                         "ib_class": rep.ib_class.value if rep.ib_class else None,
                         "dpoc": p.poc, "vah": p.vah, "val": p.val,
                         "open_type": rep.open_type.value if rep.open_type else None,
                         "open_location": rep.open_location.value if rep.open_location else None,
                         "day_type": p.day_type.value, "is_expiry": plan.is_expiry}
                profile, signals, skips = _histogram(p.profile), rep.signals, rep.skipped
            prior = plan.prior
            return {
                "date": session_date.isoformat(), "live": live, "symbol": self.settings.symbol,
                "bars": [[b.ts.isoformat(timespec="minutes"), b.open, b.high, b.low, b.close, b.volume] for b in bars],
                "today": today, "prior": _levels(prior),
                "prior_profile": _histogram(prior.profile) if prior else [],
                "profile": profile,
                "balance": to_jsonable(plan.balance) if plan.balance else None,
                "plan": {"scenarios": plan.scenarios, "warnings": plan.warnings, "avg_ib": round(plan.avg_ib, 1),
                         "nearest_expiry": plan.nearest_expiry.isoformat(), "is_expiry": plan.is_expiry},
                "signals": [self._signal_view(s) for s in signals],
                "skips": [{"time": t.strftime("%H:%M") if t else None, "setup": sid, "reason": why}
                          for t, sid, why in skips],
            }

    def sessions_list(self) -> list[dict[str, Any]]:
        with self._lock:
            out = [{"date": r.date.isoformat(), "live": False, "day_type": r.profile.day_type.value,
                    "open_type": r.open_type.value if r.open_type else None,
                    "ib_class": r.ib_class.value if r.ib_class else None,
                    "signals": len(r.signals), "skips": len(r.skipped)} for r in self.reports]
            if self.in_session:
                out.append({"date": self.sessions[self.session_idx].date.isoformat(), "live": True,
                            "day_type": None, "open_type": None, "ib_class": None,
                            "signals": len(self.engine.signals), "skips": len(self.engine.state.skips)})
            return out

    def signals(self, d: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            return [self._signal_view(s) for s in self._all_signals() if d is None or s.ts.date().isoformat() == d]

    def setups(self) -> dict[str, Any]:
        with self._lock:
            fired = Counter(s.setup_id for s in self._all_signals())
            skips: dict[str, Counter] = {}
            all_skips = [x for r in self.reports for x in r.skipped]
            if self.in_session:
                all_skips += self.engine.state.skips
            for _, sid, why in all_skips:
                skips.setdefault(sid, Counter())[why] += 1
            today_signals = {s.setup_id for s in self.engine.signals} if self.in_session else set()
            today_skips = {sid: why for _, sid, why in self.engine.state.skips} if self.in_session else {}
            bt = self.jobs[self.last_backtest].result if self.last_backtest else None
            bt_stats = {x["setup"]: x for x in bt["stats"]} if bt else {}
            out = []
            for item in SETUPS:
                sid = item["id"]
                disabled = sid in self.settings.disabled_setups
                today = ("disabled" if disabled else "fired" if sid in today_signals
                         else "skipped" if sid in today_skips else "watching" if self.in_session else "idle")
                out.append({**item, "group_name": GROUPS[item["group"]], "enabled": not disabled,
                            "fired": fired.get(sid, 0), "skipped": sum(skips.get(sid, Counter()).values()),
                            "top_skip_reasons": [{"reason": r, "count": c}
                                                 for r, c in skips.get(sid, Counter()).most_common(3)],
                            "today": today, "today_reason": today_skips.get(sid),
                            "backtest": bt_stats.get(sid)})
            return {"groups": GROUPS, "setups": out, "global_skips": [
                {"reason": r, "count": c} for r, c in skips.get("*", Counter()).most_common(5)]}

    def dashboard(self) -> dict[str, Any]:
        with self._lock:
            view = self.session_view()
            sigs = self._all_signals()
            journal = Counter(self.journal.get(signal_key(s), {}).get("status", "open") for s in sigs)
            bt = self.jobs[self.last_backtest] if self.last_backtest else None
            return {
                "status": self.status(),
                "session": None if view is None else {k: view[k] for k in ("date", "live", "today", "prior", "plan")}
                | {"signals": len(view["signals"]), "skips": len(view["skips"])},
                "signals_by_setup": dict(Counter(s.setup_id for s in sigs)),
                "signals_by_group": dict(Counter(s.group for s in sigs)),
                "journal": dict(journal),
                "recent_signals": [self._signal_view(s) for s in sigs[-8:]][::-1],
                "recent_events": self.events(limit=12)[::-1],
                "backtest": None if bt is None else {**bt.summary(), **{k: bt.result[k] for k in
                                                     ("total_r", "win_rate", "signals", "sessions", "equity")}},
            }

    def jobs_view(self) -> list[dict[str, Any]]:
        with self._lock:
            return [j.summary() for j in sorted(self.jobs.values(), key=lambda j: -j.created)]

    def job_view(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self.jobs[job_id]
            return {**job.summary(), "result": job.result}

    def settings_view(self) -> dict[str, Any]:
        with self._lock:
            return {"settings": settings_to_dict(self.settings), "schema": schema(self.settings),
                    "pending_restart": self.pending_restart,
                    "settings_path": str(self.settings_path) if self.settings_path else None}

    def system(self) -> dict[str, Any]:
        try:
            import resource
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            rss_mb = rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024
        except ImportError:
            rss_mb = None
        with self._lock:
            return {
                "pid": os.getpid(), "python": sys.version.split()[0], "platform": platform.platform(),
                "peak_rss_mb": round(rss_mb, 1) if rss_mb else None, "cpu_s": round(_time.process_time(), 2),
                "threads": [{"name": t.name, "alive": t.is_alive(), "daemon": t.daemon}
                            for t in threading.enumerate()],
                "settings_path": str(self.settings_path) if self.settings_path else None,
                "journal_path": str(self.journal_path) if self.journal_path else None,
                "events_buffered": len(self._events), "started": _iso(self.started_at),
            }

    def export_signals_csv(self) -> str:
        import csv
        import io
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["date", "time", "setup", "name", "direction", "entry", "stop", "targets", "structure",
                    "legs", "expiry", "lots", "risk_total", "exit_by", "journal", "note"])
        with self._lock:
            for s in self._all_signals():
                j = self.journal.get(signal_key(s), {})
                p = s.option_plan
                w.writerow([s.ts.date(), f"{s.ts:%H:%M}", s.setup_id, s.name, s.direction.value, s.entry, s.stop,
                            " ".join(f"{t.price:g}" for t in s.targets), p.structure.value,
                            " ".join(f"{l.side}:{l.strike:g}{l.right}" for l in p.legs), p.expiry, s.lots,
                            s.risk_total, s.exit_by.strftime("%H:%M") if s.exit_by else "",
                            j.get("status", "open"), j.get("note", "")])
        return buf.getvalue()
