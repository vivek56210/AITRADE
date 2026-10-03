"""Run one trading day live: poll 1-minute bars, run the playbook engine, alert on Telegram.

Alerts only - this module never places orders. Signals already sent are remembered per day in
<state_dir>/state-YYYY-MM-DD.json, so a restart mid-session replays the day without re-sending.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from ..playbook.backtest import TradeOutcome, simulate_directional, simulate_premium
from ..playbook.config import INSTRUMENTS, PlaybookParams, RiskParams, SessionTimes
from ..playbook.engine import PlaybookEngine, SessionReport
from ..playbook.models import Bar, Session, SetupSignal
from ..playbook.report import to_jsonable
from ..playbook.state import DayContext
from ..console.views import histogram, live_today, session_payload
from .messages import eod_message, plan_message, signal_message
from .telegram import esc

HistoryLoader = Callable[[str, date], tuple[list[Session], frozenset[date]]]


@dataclass
class LiveConfig:
    symbols: tuple[str, ...] = ("NIFTY", "BANKNIFTY")
    poll_seconds: float = 15.0
    stale_minutes: int = 5
    no_data_cutoff_minutes: int = 30
    state_dir: Path = Path("data/live")
    params: PlaybookParams = field(default_factory=PlaybookParams)
    risk: RiskParams = field(default_factory=RiskParams)
    times: SessionTimes = field(default_factory=SessionTimes)
    disabled_setups: tuple[str, ...] = ()
    label: str = "live"


@dataclass
class Book:
    symbol: str
    engine: PlaybookEngine
    bars: list[Bar] = field(default_factory=list)
    stale_alerted: bool = False
    errors: int = 0


def signal_key(sig: SetupSignal) -> str:
    return f"{sig.symbol}|{sig.ts:%Y-%m-%d %H:%M}|{sig.setup_id}"


class LiveRunner:
    def __init__(self, cfg: LiveConfig, feed, notifier, clock, history: HistoryLoader,
                 extra_holidays: frozenset[date] = frozenset(), log=print):
        self.cfg, self.feed, self.notifier, self.clock = cfg, feed, notifier, clock
        self.history, self.extra_holidays, self.log = history, extra_holidays, log

    # ---- state -----------------------------------------------------------------------------

    def state_path(self, day: date) -> Path:
        return self.cfg.state_dir / f"state-{self.cfg.label}-{day}.json"

    def _load_state(self, day: date) -> dict:
        p = self.state_path(day)
        return json.loads(p.read_text()) if p.exists() else {"sent": [], "notes": []}

    def _save_state(self, day: date, state: dict) -> None:
        self.cfg.state_dir.mkdir(parents=True, exist_ok=True)
        p = self.state_path(day)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1))
        tmp.replace(p)

    def _once(self, day: date, state: dict, note: str, text: str) -> None:
        """Send a message at most once per day (survives restarts)."""
        if note in state["notes"]:
            return
        if self.notifier.send(text):
            state["notes"].append(note)
            self._save_state(day, state)

    # ---- day ---------------------------------------------------------------------------------

    def _prepare(self, symbol: str, day: date) -> tuple[Book, DayContext]:
        sessions, data_holidays = self.history(symbol, day)
        sessions = [s for s in sessions if s.date < day]
        if not sessions:
            raise RuntimeError(f"no history before {day} for {symbol}")
        c = self.cfg
        engine = PlaybookEngine(INSTRUMENTS[symbol], c.params, c.times, c.risk,
                                disabled_setups=c.disabled_setups)
        engine.run(sessions, warmup=len(sessions))
        ctx = DayContext(holidays=data_holidays | self.extra_holidays)
        return Book(symbol, engine), ctx

    def run_day(self, day: date) -> dict[str, tuple[SessionReport | None, list[TradeOutcome]]]:
        t = self.cfg.times
        if day.weekday() >= 5 or day in self.extra_holidays:
            self.log(f"{day} is not a trading day; nothing to do")
            return {}
        state = self._load_state(day)
        books: dict[str, Book] = {}
        for sym in self.cfg.symbols:
            book, ctx = self._prepare(sym, day)
            plan = book.engine.start_session(day, ctx)
            books[sym] = book
            self._once(day, state, f"plan:{sym}", plan_message(plan, day))
        self._once(day, state, "started",
                   f"<b>ATIS {esc(self.cfg.label)} started</b> - {', '.join(books)} | 1-minute index data | "
                   f"alerts only, no orders")
        open_dt = datetime.combine(day, t.open)
        close_dt = datetime.combine(day, t.close)
        while True:
            now = self.clock.now()
            for book in books.values():
                self._poll(book, day, now, state)
            self._heartbeat(day, now, books, "running")
            if now >= close_dt + timedelta(minutes=1):
                break
            if (now >= open_dt + timedelta(minutes=self.cfg.no_data_cutoff_minutes)
                    and not any(b.bars for b in books.values())):
                self._once(day, state, "no-data",
                           f"<b>ATIS:</b> no market data by {now:%H:%M} on {day:%d %b} - holiday or feed problem. "
                           f"Stopping for today.")
                break
            self.clock.sleep(self.cfg.poll_seconds)
        result = {sym: self._finish(book, day, state) for sym, book in books.items()}
        self._heartbeat(day, self.clock.now(), books, "finished")
        return result

    def _heartbeat(self, day: date, now: datetime, books: dict[str, Book], status: str) -> None:
        self.cfg.state_dir.mkdir(parents=True, exist_ok=True)
        payload = {"status": status, "day": day.isoformat(), "time": now.isoformat(timespec="seconds"),
                   "symbols": {s: {"bars": len(b.bars),
                                   "last_bar": b.bars[-1].ts.isoformat(timespec="minutes") if b.bars else None,
                                   "stale": b.stale_alerted, "feed_errors": b.errors} for s, b in books.items()}}
        (self.cfg.state_dir / f"heartbeat-{self.cfg.label}.json").write_text(json.dumps(payload))

    def _poll(self, book: Book, day: date, now: datetime, state: dict) -> None:
        t = self.cfg.times
        try:
            bars = self.feed.poll(book.symbol, day, now)
            book.errors = 0
        except Exception as exc:
            book.errors += 1
            self.log(f"{book.symbol}: feed error ({type(exc).__name__}: {exc})")
            bars = []
        last = book.bars[-1].ts if book.bars else None
        fresh = [b for b in bars if (last is None or b.ts > last) and t.open <= b.ts.time() < t.close]
        for bar in fresh:
            book.bars.append(bar)
            for sig in book.engine.on_bar(bar):
                key = signal_key(sig)
                if key in state["sent"]:
                    continue
                text = signal_message(sig)
                if now - sig.ts > timedelta(minutes=3):
                    text = f"<b>LATE ({now - sig.ts} after the signal, e.g. after a restart)</b>\n{text}"
                if self.notifier.send(text):
                    state["sent"].append(key)
                    self._save_state(day, state)
                self.log(f"signal {key}")
        if fresh:
            self._snapshot(book, day, state, live=True)
        self._check_stale(book, day, now, state)

    def snapshot_path(self, symbol: str, day: date) -> Path:
        return self.cfg.state_dir / f"snapshot-{self.cfg.label}-{day}-{symbol}.json"

    def _snapshot(self, book: Book, day: date, state: dict, live: bool) -> None:
        """Today's chart data in the console's session format, rewritten as bars arrive."""
        eng = book.engine
        if eng.state is None or not book.bars:
            return
        sent = set(state["sent"])
        signals = []
        for sig in eng.signals:
            d = to_jsonable(sig)
            d["key"] = signal_key(sig)
            d["journal"] = {"status": "open", "note": "Telegram sent" if d["key"] in sent else "not sent yet"}
            signals.append(d)
        payload = session_payload(symbol=book.symbol, day=day, live=live, bars=book.bars,
                                  today=live_today(eng, self.cfg.params.value_area_pct), plan=eng.plan,
                                  profile=histogram(eng.state.vp), signals=signals, skips=list(eng.state.skips))
        self.cfg.state_dir.mkdir(parents=True, exist_ok=True)
        path = self.snapshot_path(book.symbol, day)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload))
        tmp.replace(path)

    def _check_stale(self, book: Book, day: date, now: datetime, state: dict) -> None:
        t = self.cfg.times
        open_dt, close_dt = datetime.combine(day, t.open), datetime.combine(day, t.close)
        if not (open_dt + timedelta(minutes=self.cfg.stale_minutes) <= now < close_dt):
            return
        last_end = book.bars[-1].ts + timedelta(minutes=1) if book.bars else open_dt
        if now - last_end > timedelta(minutes=self.cfg.stale_minutes):
            if not book.stale_alerted and book.bars:
                self.notifier.send(f"<b>{esc(book.symbol)}: no new data since {last_end:%H:%M}</b> - "
                                   f"signals paused until the feed recovers.")
                book.stale_alerted = True
        elif book.stale_alerted:
            self.notifier.send(f"{esc(book.symbol)}: data resumed at {book.bars[-1].ts:%H:%M}.")
            book.stale_alerted = False

    def _finish(self, book: Book, day: date, state: dict) -> tuple[SessionReport | None, list[TradeOutcome]]:
        eng = book.engine
        self._snapshot(book, day, state, live=False)
        report = eng.end_session() if book.bars else None
        outcomes: list[TradeOutcome] = []
        if report:
            for sig in report.signals:
                out = (simulate_premium(sig, book.bars) if sig.option_plan.structure.is_short_premium
                       else simulate_directional(sig, book.bars))
                outcomes.append(out)
            self._journal(day, report, outcomes)
        self._once(day, state, f"eod:{book.symbol}", eod_message(book.symbol, day, report, outcomes))
        return report, outcomes

    def _journal(self, day: date, report: SessionReport, outcomes: list[TradeOutcome]) -> None:
        self.cfg.state_dir.mkdir(parents=True, exist_ok=True)
        path = self.cfg.state_dir / f"journal-{self.cfg.label}.jsonl"
        done = set()
        if path.exists():
            done = {json.loads(ln)["key"] for ln in path.read_text().splitlines() if ln.strip()}
        with open(path, "a") as f:
            for o in outcomes:
                key = signal_key(o.signal)
                if key in done:
                    continue
                s = o.signal
                f.write(json.dumps({
                    "key": key, "date": day.isoformat(), "symbol": s.symbol, "setup": s.setup_id,
                    "time": f"{s.ts:%H:%M}", "direction": s.direction.value, "entry": s.entry, "stop": s.stop,
                    "structure": s.option_plan.structure.value, "lots": s.lots, "r": o.r_multiple,
                    "contained": o.contained, "exit": o.exit_reason,
                    "legs": to_jsonable(s.option_plan.legs),
                }) + "\n")


def journal_summary(path: Path, since: date | None = None) -> str:
    if not path.exists():
        return f"no journal at {path}"
    rows = [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]
    rows = [r for r in rows if since is None or r["date"] >= since.isoformat()]
    if not rows:
        return "no signals recorded"
    lines = [f"{len(rows)} signals from {rows[0]['date']} to {rows[-1]['date']}"]
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(f"{r['symbol']} {r['setup']}", []).append(r)
    total = 0.0
    for k, rs in sorted(by.items()):
        scored = [r["r"] for r in rs if r["r"] is not None]
        prem = [r for r in rs if r["contained"] is not None]
        part = f"  {k}: {len(rs)} signals"
        if scored:
            part += f", {sum(x > 0 for x in scored)}/{len(scored)} wins, {sum(scored):+.2f}R"
            total += sum(scored)
        if prem:
            part += f", condors contained {sum(bool(r['contained']) for r in prem)}/{len(prem)}"
        lines.append(part)
    lines.append(f"total {total:+.2f}R (index replay, before costs)")
    return "\n".join(lines)


def log_stderr(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", file=sys.stderr, flush=True)
