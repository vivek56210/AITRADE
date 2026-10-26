from datetime import date, datetime, timedelta

import pytest

from atis.console.runtime import Runtime
from atis.console.settings import ConsoleSettings
from atis.playbook.data import drop_short_sessions, infer_holidays, prepare_sessions, synthetic_sessions, time_weighted
from atis.playbook.models import Bar, Session
from atis.playbook.upstox import fetch_index_1m, month_ranges, parse_candles


def payload(day: date, n: int = 3) -> dict:
    t0 = datetime.combine(day, datetime.min.time()).replace(hour=9, minute=15)
    candles = [[(t0 + timedelta(minutes=i)).isoformat() + "+05:30", 100 + i, 101 + i, 99 + i, 100.5 + i, 0, 0]
               for i in range(n)]
    return {"status": "success", "data": {"candles": candles[::-1]}}


class FakeGet:
    def __init__(self):
        self.urls = []

    def __call__(self, url: str) -> dict:
        self.urls.append(url)
        start = date.fromisoformat(url.rsplit("/", 1)[1])
        return payload(start + timedelta(days=(7 - start.weekday()) % 7))  # first Monday of the range


def test_parse_candles_sorts_and_strips_timezone():
    bars = parse_candles(payload(date(2026, 9, 28)))
    assert [b.ts for b in bars] == sorted(b.ts for b in bars)
    assert bars[0].ts == datetime(2026, 9, 28, 9, 15) and bars[0].ts.tzinfo is None
    with pytest.raises(ValueError):
        parse_candles({"status": "error", "errors": ["bad"]})


def test_month_ranges_split_on_calendar_months():
    assert month_ranges(date(2026, 1, 20), date(2026, 3, 5)) == [
        (date(2026, 1, 20), date(2026, 1, 31)), (date(2026, 2, 1), date(2026, 2, 28)),
        (date(2026, 3, 1), date(2026, 3, 5))]


def test_fetch_caches_complete_months_and_refetches_current(tmp_path):
    get = FakeGet()
    today = date(2026, 10, 2)
    bars = fetch_index_1m("NIFTY", date(2026, 8, 1), today, tmp_path, get=get, today=today)
    assert len(get.urls) == 3 and "NSE_INDEX%7CNifty%2050/minutes/1/" in get.urls[0]
    assert sorted(p.name for p in (tmp_path / "NIFTY").iterdir()) == ["2026-08.csv", "2026-09.csv"]
    fetch_index_1m("NIFTY", date(2026, 8, 1), today, tmp_path, get=get, today=today)
    assert len(get.urls) == 4  # only the current (incomplete) month is downloaded again
    assert all(b.volume == 0 for b in bars)


def test_fetch_rejects_unknown_symbol_and_clamps_start(tmp_path):
    with pytest.raises(ValueError):
        fetch_index_1m("FINNIFTY", date(2026, 1, 1), date(2026, 1, 31), tmp_path, get=FakeGet())
    with pytest.raises(ValueError, match="2022-01-01"):
        fetch_index_1m("NIFTY", date(2020, 1, 1), date(2021, 6, 1), tmp_path, get=FakeGet())


def test_time_weighting_only_applies_when_volume_is_missing():
    t = datetime(2026, 9, 28, 9, 15)
    spot = [Bar(t, 1, 2, 0, 1, 0), Bar(t + timedelta(minutes=1), 1, 2, 0, 1, 0)]
    assert [b.volume for b in time_weighted(spot)] == [1.0, 1.0]
    fut = [Bar(t, 1, 2, 0, 1, 500)]
    assert time_weighted(fut) is fut


def test_holidays_and_short_sessions():
    full = synthetic_sessions(date(2026, 9, 21), 6)  # Mon 21 .. Mon 28
    sessions = [s for s in full if s.date != date(2026, 9, 23)]
    sessions.append(Session(date(2026, 9, 27), sessions[0].bars[:60]))  # a Sunday special session
    sessions.sort(key=lambda s: s.date)
    kept = drop_short_sessions(sessions)
    assert date(2026, 9, 27) not in {s.date for s in kept}
    assert infer_holidays(kept) == frozenset({date(2026, 9, 23)})


def test_prepare_sessions_returns_tpo_weighted_sessions():
    bars = [Bar(b.ts, b.open, b.high, b.low, b.close, 0) for s in synthetic_sessions(date(2026, 9, 21), 3)
            for b in s.bars]
    sessions, holidays = prepare_sessions(bars)
    assert len(sessions) == 3 and holidays == frozenset()
    assert all(b.volume == 1.0 for b in sessions[0].bars)


def test_console_upstox_source_loads_and_infers_holidays(tmp_path, monkeypatch):
    days = [s for s in synthetic_sessions(date(2026, 9, 1), 8) if s.date != date(2026, 9, 3)]
    bars = [Bar(b.ts, b.open, b.high, b.low, b.close, 0) for s in days for b in s.bars]
    calls = []

    def fake_fetch(symbol, start, end, cache_dir, on_month=None):
        calls.append((symbol, start, end, cache_dir))
        return bars

    monkeypatch.setattr("atis.console.runtime.fetch_index_1m", fake_fetch)
    rt = Runtime(None, None, ConsoleSettings(data_source="upstox", upstox_from="2026-09-01",
                                             upstox_to="2026-09-30", data_cache=str(tmp_path),
                                             warmup_sessions=2), start_worker=False)
    try:
        rt.step(10)
        assert calls[0][:3] == ("NIFTY", date(2026, 9, 1), date(2026, 9, 30))
        assert rt.data_holidays == frozenset({date(2026, 9, 3)})
        assert date(2026, 9, 3) in rt._context().holidays
        assert rt.status()["state"] == "paused" and rt.status()["bars_processed"] == 10
    finally:
        rt.shutdown()
