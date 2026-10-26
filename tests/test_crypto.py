from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from atis.playbook import crypto
from atis.playbook.backtest import fee_in_r
from atis.playbook.config import BTCUSD, NIFTY, SessionTimes, scaled_session_times
from atis.playbook.data import synthetic_sessions
from atis.playbook.delta import DeltaError, crypto_sessions, fetch_perp_1m, fetch_range, in_timezone, parse_candles
from atis.playbook.expiry import expiry_with_min_sessions, nearest_expiry, sessions_until
from atis.playbook.models import Bar, Direction, Target


def fake_api(start: datetime, minutes: int, cap: int = 4000):
    """A Delta-like endpoint: candles newest first, at most `cap` from the requested start."""
    calls = []

    def get(url):
        q = parse_qs(urlparse(url).query)
        s, e = int(q["start"][0]), int(q["end"][0])
        calls.append((s, e))
        t0 = int(start.replace(tzinfo=timezone.utc).timestamp())
        times = [t for t in range(max(s, t0), min(e, t0 + 60 * minutes) + 1, 60)][:cap]
        return {"success": True, "result": [{"time": t, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 3}
                                            for t in reversed(times)]}
    return get, calls


def test_parse_candles_orders_and_converts_to_utc():
    bars = parse_candles({"success": True, "result": [{"time": 1790996820, "open": 1, "high": 2, "low": 0, "close": 1,
                                                       "volume": 5}, {"time": 1790996760, "open": 1, "high": 2,
                                                                      "low": 0, "close": 1, "volume": 4}]})
    assert [b.ts for b in bars] == [datetime(2026, 10, 3, 3, 6), datetime(2026, 10, 3, 3, 7)]
    with pytest.raises(DeltaError):
        parse_candles({"success": False, "error": {"code": "bad"}})


def test_fetch_range_pages_without_gaps_or_duplicates():
    start = datetime(2025, 1, 1)
    get, calls = fake_api(start, 3 * 24 * 60)
    bars = fetch_range("BTCUSD", start, start + timedelta(days=3), get)
    assert len(bars) == 3 * 24 * 60 and len(calls) == 2
    assert all((b.ts - a.ts) == timedelta(minutes=1) for a, b in zip(bars, bars[1:]))


def test_fetch_perp_caches_complete_months_only(tmp_path):
    get, calls = fake_api(datetime(2025, 1, 1), 70 * 24 * 60)
    bars = fetch_perp_1m("BTCUSD", date(2025, 1, 30), date(2025, 2, 2), tmp_path, get, today=date(2025, 2, 10))
    assert bars[0].ts == datetime(2025, 1, 30) and bars[-1].ts.date() == date(2025, 2, 2)
    assert (tmp_path / "BTCUSD" / "2025-01.csv").exists() and not (tmp_path / "BTCUSD" / "2025-02.csv").exists()
    n = len(calls)
    again = fetch_perp_1m("BTCUSD", date(2025, 1, 30), date(2025, 2, 2), tmp_path, get, today=date(2025, 2, 10))
    assert again == bars and len(calls) - n == 4  # January from the cache; only February refetched
    with pytest.raises(ValueError, match="history starts"):
        fetch_perp_1m("BTCUSD", date(2023, 1, 1), date(2023, 2, 1), tmp_path, get)


def test_timezones_and_sessions():
    utc = [Bar(datetime(2025, 3, 10, 13, 29) + timedelta(minutes=i), 1, 1, 1, 1, 1) for i in range(3)]
    ny = in_timezone(utc, "America/New_York")
    assert ny[0].ts == datetime(2025, 3, 10, 9, 29)  # EDT (UTC-4) after the 9 Mar DST switch
    bars = [Bar(datetime(2025, 1, 6) + timedelta(minutes=i), 1, 1, 1, 1, 1) for i in range(3 * 1440)]
    sessions = crypto_sessions(bars, "Asia/Kolkata", time(9, 15), time(15, 30))
    assert [s.date for s in sessions] == [date(2025, 1, 6), date(2025, 1, 7), date(2025, 1, 8)]
    assert all(len(s.bars) == 375 for s in sessions)


def test_scaled_session_times():
    assert scaled_session_times(time(9, 15), 375) == SessionTimes()
    day = scaled_session_times(time(0, 0), 24 * 60)
    assert (day.ib_end, day.close) == (time(1, 0), time(23, 59, 59))
    assert day.ib_end < day.day_type_check < day.last_entry < day.flat_by < day.close
    assert day.session_minutes == 24 * 60
    ny = scaled_session_times(time(9, 30), 375)
    assert (ny.ib_end, ny.flat_by, ny.close) == (time(10, 30), time(15, 25), time(15, 45))
    with pytest.raises(ValueError):
        scaled_session_times(time(20, 0), 375)


def test_crypto_calendar_includes_weekends_and_daily_expiry():
    sat = date(2026, 10, 3)
    assert nearest_expiry(BTCUSD, sat) == sat
    assert sessions_until(sat, date(2026, 10, 9), weekends=True) == 6
    assert expiry_with_min_sessions(BTCUSD, sat, 3) == date(2026, 10, 6)
    assert nearest_expiry(NIFTY, sat) == date(2026, 10, 6)  # NSE unchanged


def test_fee_in_r():
    from atis.playbook.models import SetupSignal
    sig = SetupSignal.__new__(SetupSignal)
    sig.entry, sig.stop, sig.direction, sig.targets = 100_000.0, 99_800.0, Direction.LONG, [Target(100_400, "t", 100)]
    assert fee_in_r(sig, 0.00059) == pytest.approx(0.59)  # $118 round trip on a $200 stop
    assert fee_in_r(sig, 0.0) == 0.0


def test_crypto_run_on_synthetic_24h_sessions():
    bars = []
    for s in synthetic_sessions(date(2025, 1, 1), 20, base=90_000.0, daily_vol=0.02):
        for i in range(4):  # stretch each 375-minute session over a 24-hour UTC day
            base = datetime.combine(s.date, time(0, 0)) + timedelta(minutes=375 * i)
            bars += [Bar(base + (b.ts - s.bars[0].ts), b.open, b.high, b.low, b.close, b.volume) for b in s.bars]
    run = crypto.run("BTCUSD", crypto.SESSIONS["utc"], bars, date(2025, 1, 6), date(2025, 1, 31))
    sm = crypto.summarize(run)
    assert sm["sessions"] > 15 and sm["signals"] > 0
    t = sm["total"]
    assert t["net_r"] == pytest.approx(t["gross_r"] - t["cost_r"], abs=0.02) and t["cost_r"] > 0
    assert t["net_r"] <= t["net_r_maker_entry"] <= t["gross_r"]
    assert "NET" in crypto.format_summary(sm)
