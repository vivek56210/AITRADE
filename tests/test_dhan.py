import os
from datetime import date, datetime, timedelta, timezone

import pytest

from atis.console.runtime import Runtime
from atis.console.settings import ConsoleSettings, SettingsError, settings_from_dict
from atis.playbook import dhan
from atis.playbook.cli import main
from atis.playbook.data import synthetic_sessions
from atis.playbook.dhan import (DhanError, fetch_futures_1m, front_contract, load_contracts,
                                parse_candles, parse_scrip_master)
from atis.playbook.models import Bar

IST = timezone(timedelta(hours=5, minutes=30))
HEADER = ("SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_INSTRUMENT_NAME,SEM_EXPIRY_CODE,SEM_TRADING_SYMBOL,"
          "SEM_LOT_UNITS,SEM_CUSTOM_SYMBOL,SEM_EXPIRY_DATE,SEM_STRIKE_PRICE,SEM_OPTION_TYPE,SEM_TICK_SIZE,"
          "SEM_EXPIRY_FLAG,SEM_EXCH_INSTRUMENT_TYPE,SEM_SERIES,SM_SYMBOL_NAME\n")
EXPIRIES = {"1": date(2026, 9, 29), "2": date(2026, 10, 27), "3": date(2026, 11, 24)}


def row(sec: str, tsym: str, expiry: date, exch: str = "NSE", instr: str = "FUTIDX") -> str:
    return f"{exch},D,{sec},{instr},0,{tsym},65.0,X,{expiry} 14:30:00,-0.01000,XX,10.0,M,FUT,,\n"


def master(*ids: str):
    names = {"1": "Sep2026", "2": "Oct2026", "3": "Nov2026"}
    lines = [HEADER] + [row(i, f"NIFTY-{names[i]}-FUT", EXPIRIES[i]) for i in ids]
    lines += [row("9", "BANKNIFTY-Oct2026-FUT", date(2026, 10, 27)),
              row("8", "NIFTYNXT50-Oct2026-FUT", date(2026, 10, 27)),
              row("7", "NIFTY-Oct2026-FUT", date(2026, 10, 29), exch="BSE"),
              row("6", "NIFTY-27Oct2026-25000-CE", date(2026, 10, 27), instr="OPTIDX")]
    return lambda: lines


class FakeDhan:
    """Each contract trades 90 days before expiry at 25000 + 50 * id, three bars a day from 09:15."""

    def __init__(self):
        self.calls = []

    def __call__(self, path: str, body: dict) -> dict:
        assert path == "/charts/intraday" and body["oi"] is True and body["instrument"] == "FUTIDX"
        self.calls.append(body)
        sec = body["securityId"]
        expiry = EXPIRIES[sec]
        d, last = date.fromisoformat(body["fromDate"][:10]), date.fromisoformat(body["toDate"][:10])
        out = {k: [] for k in ("open", "high", "low", "close", "volume", "timestamp", "open_interest")}
        while d <= min(last, expiry):
            if d.weekday() < 5 and d > expiry - timedelta(days=90):
                for i in range(3):
                    ts = datetime(d.year, d.month, d.day, 9, 15 + i, tzinfo=IST)
                    px = 25000 + 50 * int(sec) + i
                    for k, v in (("open", px), ("high", px + 1), ("low", px - 1), ("close", px), ("volume", 100),
                                 ("timestamp", int(ts.timestamp())), ("open_interest", 1000 + i)):
                        out[k].append(v)
            d += timedelta(days=1)
        return out


def test_scrip_master_keeps_only_nse_monthly_index_futures():
    cs = parse_scrip_master(master("2", "3")())
    assert [(c.symbol, c.security_id, c.expiry) for c in cs] == [
        ("BANKNIFTY", "9", date(2026, 10, 27)), ("NIFTY", "2", date(2026, 10, 27)), ("NIFTY", "3", date(2026, 11, 24))]


def test_registry_remembers_contracts_after_they_leave_the_master(tmp_path):
    load_contracts("NIFTY", tmp_path, date(2026, 9, 1), master("1", "2"))
    # same day: the registry is fresh, so the master is not read again
    assert [c.security_id for c in load_contracts("NIFTY", tmp_path, date(2026, 9, 1), master())] == ["1", "2"]
    stale = datetime(2026, 9, 1, 12).timestamp()
    os.utime(tmp_path / "contracts.csv", (stale, stale))
    cs = load_contracts("NIFTY", tmp_path, date(2026, 10, 2), master("2", "3"))
    assert [c.security_id for c in cs] == ["1", "2", "3"]


def test_front_contract_rolls_after_expiry_day():
    cs = parse_scrip_master(master("1", "2")())
    nifty = [c for c in cs if c.symbol == "NIFTY"]
    assert front_contract(date(2026, 9, 29), nifty).security_id == "1"
    assert front_contract(date(2026, 9, 30), nifty).security_id == "2"
    assert front_contract(date(2026, 10, 28), nifty) is None


def test_parse_candles_lands_bars_at_ist_and_keeps_oi():
    t = int(datetime(2026, 9, 28, 9, 15, tzinfo=IST).timestamp())
    p = {"open": [2, 1], "high": [3, 2], "low": [1, 0], "close": [2, 1], "volume": [5, 6],
         "timestamp": [t + 60, t], "open_interest": [11, 10]}
    bars = parse_candles(p)
    assert bars[0] == Bar(datetime(2026, 9, 28, 9, 15), 1, 2, 0, 1, 6, oi=10)
    # epochs that are really IST wall-clock seconds are detected by the 09:15 open
    shifted = parse_candles({**p, "timestamp": [x + 19800 for x in p["timestamp"]]})
    assert shifted[0].ts == datetime(2026, 9, 28, 9, 15)
    assert parse_candles({"open": [], "timestamp": []}) == []
    with pytest.raises(DhanError):
        parse_candles({"errorCode": "DH-905", "errorMessage": "bad"})


def test_futures_join_back_adjusts_at_rollover_and_caches(tmp_path):
    post, today = FakeDhan(), date(2026, 10, 2)
    rolls = []
    bars = fetch_futures_1m("NIFTY", date(2026, 9, 1), today, tmp_path, post=post, master=master("1", "2", "3"),
                            today=today, rolls_out=rolls)
    assert [(c["securityId"], c["fromDate"][:10]) for c in post.calls] == [
        ("1", "2026-09-01"), ("2", "2026-09-01"), ("2", "2026-10-01")]  # Nov is never front in range
    assert len(rolls) == 1 and rolls[0].gap == 50 and rolls[0].at == datetime(2026, 9, 29, 9, 17)
    by_day = {}
    for b in bars:
        by_day.setdefault(b.ts.date(), []).append(b)
    assert by_day[date(2026, 9, 29)][0].close == 25050 + 50  # Sep contract, shifted by the roll gap
    assert by_day[date(2026, 9, 30)][0].close == 25100  # Oct contract, unadjusted
    assert by_day[date(2026, 9, 30)][0].volume == 100 and by_day[date(2026, 9, 30)][0].oi == 1000
    assert len(by_day[date(2026, 9, 29)]) == 3  # no duplicate minutes on the roll day

    raw = fetch_futures_1m("NIFTY", date(2026, 9, 1), today, tmp_path, post=post, master=master("1", "2", "3"),
                           today=today, adjust=False)
    assert len(post.calls) == 4  # September (both contracts) came from the cache
    assert [b.ts for b in raw] == [b.ts for b in bars]
    assert next(b for b in raw if b.ts.date() == date(2026, 9, 29)).close == 25050


def test_expired_contract_without_data_is_replaced_by_the_next_one():
    post = FakeDhan()
    served = lambda path, body: {"timestamp": []} if body["securityId"] == "1" else post(path, body)  # noqa: E731
    bars = fetch_futures_1m("NIFTY", date(2026, 9, 21), date(2026, 9, 30), None, post=served,
                            master=master("1", "2"), today=date(2026, 10, 2))
    assert {b.close for b in bars} == {25100, 25101, 25102}
    assert len({b.ts.date() for b in bars}) == 8


def test_missing_expired_contract_falls_back_to_the_next_listed_one(tmp_path):
    post = FakeDhan()
    bars = fetch_futures_1m("NIFTY", date(2026, 9, 21), date(2026, 9, 25), None, post=post, master=master("2"),
                            today=date(2026, 10, 2))
    assert {c["securityId"] for c in post.calls} == {"2"} and bars[0].close == 25100


def test_only_read_only_endpoints_are_callable(monkeypatch):
    monkeypatch.setenv("DHAN_CLIENT_ID", "x")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "y")
    for path in ("/orders", "/super/orders", "/forever/orders", "/positions/convert"):
        with pytest.raises(DhanError, match="refusing"):
            dhan._request("POST", path, {})


def test_missing_credentials_fail_fast_without_downloading(monkeypatch, capsys):
    monkeypatch.delenv("DHAN_CLIENT_ID", raising=False)
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "secret-value")
    monkeypatch.setattr(dhan, "download_master", lambda: pytest.fail("downloaded the scrip master"))
    with pytest.raises(DhanError, match="DHAN_CLIENT_ID") as exc:
        fetch_futures_1m("NIFTY", date(2026, 9, 1), date(2026, 9, 30))
    assert "secret-value" not in str(exc.value)
    assert main(["run", "--dhan", "--from", "2026-09-01", "--backtest"]) == 1
    assert "DHAN_CLIENT_ID" in capsys.readouterr().err


def test_console_dhan_source(tmp_path, monkeypatch):
    with pytest.raises(SettingsError, match="dhan_from"):
        settings_from_dict({"data_source": "dhan", "dhan_from": "2026-10-01", "dhan_to": "2026-09-01"})
    bars = [b for s in synthetic_sessions(date(2026, 9, 1), 6) for b in s.bars]
    calls = []

    def fake_fetch(symbol, start, end, cache_dir, adjust=True, on_month=None, rolls_out=None):
        calls.append((symbol, start, end, cache_dir, adjust))
        return bars

    monkeypatch.setattr("atis.console.runtime.fetch_futures_1m", fake_fetch)
    rt = Runtime(None, None, ConsoleSettings(data_source="dhan", dhan_from="2026-09-01", dhan_to="2026-09-30",
                                             dhan_cache=str(tmp_path), dhan_back_adjust=False,
                                             warmup_sessions=2), start_worker=False)
    try:
        rt.step(5)
        assert calls == [("NIFTY", date(2026, 9, 1), date(2026, 9, 30), tmp_path, False)]
        assert rt.status()["bars_processed"] == 5
    finally:
        rt.shutdown()
