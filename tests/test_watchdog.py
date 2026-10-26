import json
from datetime import datetime, timezone

from atis.ops.watchdog import failed_units, run_once


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def hb(dir_, **kw):
    (dir_ / "heartbeat-live.json").write_text(json.dumps(kw))


def test_nse_runner_missing_alerts_once_then_resolves(tmp_path):
    sent, pings = [], []
    now = utc(2026, 10, 26, 4, 30)  # Monday 10:00 IST
    run = lambda t: run_once(tmp_path, sent.append, t, units=lambda: [], ping=pings.append, health_url="https://hc/x")
    assert run(now) == ["NSE alert runner has not started today (ignore if today is an NSE holiday)"]
    assert len(sent) == 1 and pings[-1] == "https://hc/x/fail"
    run(utc(2026, 10, 26, 4, 40))
    assert len(sent) == 1  # not repeated the same day
    hb(tmp_path, day="2026-10-26", status="running", time="2026-10-26T10:15:00")
    assert run(utc(2026, 10, 26, 4, 50)) == []
    assert "resolved" in sent[-1] and pings[-1] == "https://hc/x"


def test_nse_stale_heartbeat_and_quiet_outside_market_hours(tmp_path):
    sent = []
    hb(tmp_path, day="2026-10-26", status="running", time="2026-10-26T10:00:00")
    assert "stale" in run_once(tmp_path, sent.append, utc(2026, 10, 26, 5, 0), units=lambda: [])[0]
    assert run_once(tmp_path, sent.append, utc(2026, 10, 25, 5, 0), units=lambda: []) == []  # Sunday
    assert run_once(tmp_path, sent.append, utc(2026, 10, 26, 1, 0), units=lambda: []) == []  # 06:30 IST


def test_crypto_heartbeat_stale_and_halted(tmp_path):
    (tmp_path / "crypto-heartbeat-paper.json").write_text(
        json.dumps({"t": "2026-10-25T00:30:00", "equity": 1, "halted": True}))
    probs = run_once(tmp_path, lambda m: True, utc(2026, 10, 25, 4, 0), units=lambda: [])
    assert any("not checked in" in p for p in probs) and any("HALTED" in p for p in probs)


def test_failed_units_only_reports_atis():
    out = "atis-live.service loaded failed failed X\nsnapd.service loaded failed failed Y\n"
    assert failed_units(lambda cmd: out) == ["service atis-live.service has failed (journalctl -u atis-live.service -n 50)"]
