import json
from datetime import date, datetime, timedelta

from atis.live.expiries import holidays_from_expiries, load_expiry_holidays, option_expiries
from atis.live.feed import ReplayFeed, VirtualClock, completed
from atis.live.runner import LiveConfig, LiveRunner, journal_summary
from atis.live.telegram import ConsoleNotifier, TelegramNotifier, find_chat_ids
from atis.playbook import path_session
from atis.playbook.models import Bar

from conftest import TODAY, balanced_prior

A1_DAY = [("09:15", 24120), ("09:30", 24180), ("09:45", 24210), ("10:15", 24240), ("11:00", 24300)]


def runner(tmp_path, bars, *, poll=60.0, notifier=None, holidays=frozenset()):
    cfg = LiveConfig(symbols=("NIFTY",), state_dir=tmp_path, poll_seconds=poll)
    clock = VirtualClock(datetime.combine(TODAY, cfg.times.open) - timedelta(minutes=5))
    feed = ReplayFeed({"NIFTY": bars})
    notifier = notifier or ConsoleNotifier(stream=open("/dev/null", "w"))
    return LiveRunner(cfg, feed, notifier, clock, lambda s, d: ([balanced_prior()], frozenset()), holidays,
                      log=lambda m: None), notifier


def test_holidays_inferred_from_shifted_expiries():
    exp = {"NIFTY": [date(2026, 10, 6), date(2026, 10, 19)], "BANKNIFTY": [date(2026, 11, 23)]}
    assert holidays_from_expiries(exp) == {date(2026, 10, 20), date(2026, 11, 24)}
    assert holidays_from_expiries({"X": [date(2026, 10, 2)]}) == {date(2026, 10, 5), date(2026, 10, 6)}


def test_option_expiries_from_scrip_master_rows():
    header = "SEM_EXM_EXCH_ID,SEM_INSTRUMENT_NAME,SEM_TRADING_SYMBOL,SEM_EXPIRY_DATE\n"
    rows = ["NSE,OPTIDX,NIFTY-Oct2026-24000-CE,2026-10-19 14:30:00\n",
            "NSE,OPTIDX,NIFTY-Oct2026-24000-PE,2026-10-19 14:30:00\n",
            "NSE,FUTIDX,NIFTY-Oct2026-FUT,2026-10-27 14:30:00\n",
            "NSE,OPTIDX,FINNIFTY-Oct2026-24000-CE,2026-10-27 14:30:00\n"]
    assert option_expiries([header] + rows) == {"NIFTY": [date(2026, 10, 19)], "BANKNIFTY": []}


def test_expiry_holidays_cache_and_fallback(tmp_path):
    header = "SEM_EXM_EXCH_ID,SEM_INSTRUMENT_NAME,SEM_TRADING_SYMBOL,SEM_EXPIRY_DATE\n"
    lines = [header, "NSE,OPTIDX,NIFTY-Oct2026-1-CE,2026-10-19 14:30:00\n"]
    hol, src = load_expiry_holidays(tmp_path, date(2026, 10, 3), download=lambda: lines)
    assert hol == {date(2026, 10, 20)} and src == "downloaded"

    def boom():
        raise OSError("offline")
    hol2, src2 = load_expiry_holidays(tmp_path, date(2026, 10, 4), download=boom)
    assert hol2 == hol and src2.startswith("stale cache")
    hol3, src3 = load_expiry_holidays(tmp_path / "empty", date(2026, 10, 4), download=boom)
    assert hol3 == frozenset() and src3.startswith("unavailable")


def test_completed_drops_forming_candle_and_weights_spot():
    t = datetime(2026, 10, 1, 9, 15)
    bars = [Bar(t, 1, 2, 0, 1, 0), Bar(t + timedelta(minutes=1), 1, 2, 0, 1, 0)]
    out = completed(bars, t + timedelta(minutes=1, seconds=30))
    assert len(out) == 1 and out[0].volume == 1.0


def test_telegram_send_and_errors(capsys):
    calls = []

    def post(url, payload):
        calls.append((url, payload))
        return {"ok": True}

    n = TelegramNotifier("123:SECRET", "42", post=post)
    assert n.send("<b>hi</b>" + "x" * 5000)
    url, payload = calls[0]
    assert url.endswith("/bot123:SECRET/sendMessage") and payload["chat_id"] == "42"
    assert payload["parse_mode"] == "HTML" and len(payload["text"]) <= 4000

    def fail(url, payload):
        raise OSError(f"boom at {url}")

    assert not TelegramNotifier("123:SECRET", "42", post=fail, retries=1).send("x")
    err = capsys.readouterr().err
    assert "send failed" in err and "SECRET" not in err


def test_find_chat_ids():
    res = {"ok": True, "result": [{"message": {"chat": {"id": 42, "first_name": "Vivek"}}},
                                  {"message": {"chat": {"id": 42, "first_name": "Vivek"}}}]}
    assert find_chat_ids("t", post=lambda u, p: res) == [("42", "Vivek")]


def test_live_day_sends_plan_signal_and_summary(tmp_path):
    r, n = runner(tmp_path, path_session(TODAY, A1_DAY).bars)
    result = r.run_day(TODAY)
    texts = n.sent
    assert texts[0].startswith("<b>NIFTY plan") and "started" in texts[1]
    signal = next(t for t in texts if "A1 Open Drive" in t)
    assert "BUY" in signal and "Entry 24" in signal and "Risk:Reward" in signal and "exit by 15:10" in signal
    assert "<b>Why:</b>" in signal and "Confidence: <b>" in signal and "Track record" in signal
    assert "paper trade only" in signal
    assert "day summary" in texts[-1] and "A1 long" in texts[-1]
    report, outcomes = result["NIFTY"]
    assert report is not None and outcomes[0].signal.setup_id == "A1"
    rows = (tmp_path / "journal-live.jsonl").read_text().splitlines()
    assert json.loads(rows[0])["setup"] == "A1"
    assert "2 signals" in journal_summary(tmp_path / "journal-live.jsonl")


def test_restart_does_not_resend(tmp_path):
    bars = path_session(TODAY, A1_DAY).bars
    r1, n1 = runner(tmp_path, bars)
    r1.run_day(TODAY)
    r2, n2 = runner(tmp_path, bars)
    r2.run_day(TODAY)
    assert sum("A1 Open Drive" in t for t in n1.sent) == 1
    assert n2.sent == []  # plan, signal and summary were all delivered before the restart
    keys = [json.loads(x)["key"] for x in (tmp_path / "journal-live.jsonl").read_text().splitlines()]
    assert len(keys) == len(set(keys)) == 2  # A1 and A3, each journaled once


def test_stale_feed_alert_and_recovery(tmp_path):
    bars = path_session(TODAY, A1_DAY).bars
    gap = [b for b in bars if not (datetime.combine(TODAY, datetime.min.time()).replace(hour=11) <= b.ts
                                   < datetime.combine(TODAY, datetime.min.time()).replace(hour=11, minute=20))]
    r, n = runner(tmp_path, gap)
    r.run_day(TODAY)
    stale = [t for t in n.sent if "no new data since" in t]
    assert len(stale) == 1 and "11:00" in stale[0]
    assert any("data resumed at 11:20" in t for t in n.sent)


def test_no_data_stops_early_and_weekend_skips(tmp_path):
    r, n = runner(tmp_path, [])
    assert r.run_day(TODAY)["NIFTY"] == (None, [])
    assert any("no market data by 09:45" in t for t in n.sent)
    assert r.clock.now() < datetime.combine(TODAY, datetime.min.time()).replace(hour=10)
    r2, n2 = runner(tmp_path, [])
    assert r2.run_day(date(2026, 10, 3)) == {} and n2.sent == []
    r3, n3 = runner(tmp_path, [], holidays=frozenset({TODAY}))
    assert r3.run_day(TODAY) == {} and n3.sent == []


def test_console_live_endpoints(tmp_path):
    from fastapi.testclient import TestClient

    from atis.console.api import create_app
    from atis.console.runtime import Runtime
    from atis.console.settings import ConsoleSettings

    live_dir = tmp_path / "live"
    r, _ = runner(live_dir, path_session(TODAY, A1_DAY).bars)
    r.run_day(TODAY)
    rt = Runtime(tmp_path / "s.json", tmp_path / "j.json", ConsoleSettings(synthetic_days=8, warmup_sessions=3),
                 start_worker=False)
    try:
        c = TestClient(create_app(rt, static_dir=tmp_path / "no-ui", live_dir=live_dir))
        ov = c.get("/api/live").json()
        assert ov["days"] == [TODAY.isoformat()] and ov["symbols"] == ["NIFTY"]
        assert ov["heartbeat"]["status"] == "finished" and ov["runner_alive"] is False
        assert ov["summary"]["signals"] == 2 and {s["key"] for s in ov["summary"]["by_setup"]} == {"NIFTY A1", "NIFTY A3"}
        snap = c.get("/api/live/snapshot", params={"symbol": "nifty"}).json()
        assert snap["symbol"] == "NIFTY" and snap["live"] is False and snap["bars"]
        assert snap["signals"][0]["setup_id"] == "A1" and snap["signals"][0]["journal"]["status"] == "open"
        assert c.get("/api/live/snapshot", params={"symbol": "NIFTY", "date": "2020-01-01"}).json() is None
        assert c.get("/api/live/snapshot", params={"symbol": "../x"}).status_code == 422
        assert c.get("/api/live/snapshot", params={"symbol": "NIFTY", "date": "bad"}).status_code == 422
        empty = TestClient(create_app(rt, static_dir=tmp_path / "no-ui", live_dir=tmp_path / "none"))
        assert empty.get("/api/live").json()["summary"]["signals"] == 0
    finally:
        rt.shutdown()


def test_run_after_close_exits_without_messages(tmp_path, monkeypatch, capsys):
    from atis.live import __main__ as cli

    monkeypatch.setattr(cli.SystemClock, "now", lambda self: datetime.combine(TODAY, datetime.min.time()).replace(hour=18))
    monkeypatch.setattr(cli, "load_expiry_holidays", lambda d, t: (frozenset(), "test"))
    assert cli.main(["run", "--dry-run", "--state-dir", str(tmp_path)]) == 0
    assert "already closed" in capsys.readouterr().err and not list(tmp_path.glob("state-*"))
    saturday = datetime(2026, 10, 3, 6, 0)
    monkeypatch.setattr(cli.SystemClock, "now", lambda self: saturday)
    monkeypatch.setattr(cli.SystemClock, "sleep", lambda self, s: (_ for _ in ()).throw(AssertionError("slept")))
    assert cli.main(["run", "--dry-run", "--state-dir", str(tmp_path)]) == 0
    assert "not a trading day" in capsys.readouterr().err


def test_find_chat_ids_wrong_token_is_a_clean_error():
    import urllib.error

    import pytest

    from atis.live.telegram import TelegramError

    def post(url, payload):
        raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)

    with pytest.raises(TelegramError, match="rejected") as exc:
        find_chat_ids("123:SECRET", post=post)
    assert "SECRET" not in str(exc.value)


def test_loss_limit_seeded_from_journal_and_announced_once(tmp_path):
    rows = [{"key": f"NIFTY|2026-09-28 10:0{i}|A3", "date": "2026-09-28", "symbol": "NIFTY", "setup": "A3",
             "r": -1.0, "contained": None} for i in range(6)]
    (tmp_path / "journal-live.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    r, n = runner(tmp_path, path_session(TODAY, A1_DAY).bars)
    r.run_day(TODAY)
    assert r.ledger.week(TODAY) == -6.0
    assert not any("A1 Open Drive" in t for t in n.sent)
    assert sum("weekly loss limit" in t for t in n.sent) == 1


def test_signal_message_shows_grade_and_low_grades_are_held(tmp_path):
    from atis.live.runner import signal_key
    r, n = runner(tmp_path, path_session(TODAY, A1_DAY).bars)
    r.cfg.min_grade = "A+"
    _, outcomes = r.run_day(TODAY)["NIFTY"]
    held = set(json.loads(r.state_path(TODAY).read_text())["held"])
    assert held == {signal_key(o.signal) for o in outcomes if o.signal.grade != "A+"}
    alerts = [t for t in n.sent if "Track record" in t]
    assert len(alerts) == sum(o.signal.grade == "A+" for o in outcomes)
    assert all("grade A+" in t for t in alerts)
    rows = [json.loads(x) for x in (tmp_path / "journal-live.jsonl").read_text().splitlines()]
    assert len(rows) == len(outcomes) and all(row["grade"] in ("A+", "B", "C") for row in rows)


def test_system_clock_waits_in_short_steps_against_the_wall_clock():
    from atis.live.feed import SystemClock
    t = [datetime(2026, 10, 8, 5, 0)]
    naps = []

    class Clock(SystemClock):
        def now(self):
            return t[0]

        def sleep(self, s):
            naps.append(s)
            t[0] += timedelta(seconds=s) if len(naps) != 2 else timedelta(hours=3)  # the laptop slept 3 h

    Clock().sleep_until(datetime(2026, 10, 8, 9, 5))
    assert max(naps) <= 30 and t[0] >= datetime(2026, 10, 8, 9, 5) and len(naps) < 1000
