import asyncio
import csv
import gzip
import json
import threading
from datetime import date, datetime, time, timedelta

import pytest

from atis.live.recorder import (DISCONNECT, FeedDisconnected, FlowBook, build_full_packet, parse_packet,
                                record_day, record_session)
from atis.playbook.data import load_csv

DAY = date(2026, 10, 5)
T0 = datetime(2026, 10, 5, 9, 15, 0)


def test_full_packet_round_trip_and_disconnect():
    raw = build_full_packet(53001, 24510.5, 75, T0 + timedelta(seconds=12), 150_000, 9_000_000, 24510.0, 24511.0, 300, 450)
    t = parse_packet(raw, T0)
    assert (t.security_id, t.ltp, t.ltq, t.volume, t.oi) == (53001, 24510.5, 75, 150_000, 9_000_000)
    assert (t.bid, t.ask, t.bid_qty, t.ask_qty) == (24510.0, 24511.0, 300, 450)
    assert t.ltt == T0 + timedelta(seconds=12)
    assert parse_packet(b"\x02" + bytes(20), T0) is None  # ticker packets are ignored
    with pytest.raises(FeedDisconnected, match="token expired"):
        parse_packet(DISCONNECT.pack(50, 10, 2, 0, 807), T0)


def tick(ltp, vol, bid, ask, sec=0, minute=0):
    return parse_packet(build_full_packet(1, ltp, 1, T0, vol, 10, bid, ask), T0 + timedelta(minutes=minute, seconds=sec))


def test_flow_book_classifies_against_prior_quotes():
    book = FlowBook("NIFTY")
    m0, m1 = T0, T0 + timedelta(minutes=1)
    book.add(tick(100.0, 1000, 99.5, 100.5), m0)  # first update only sets the baseline
    book.add(tick(100.5, 1075, 100.0, 101.0), m0)  # at the prior ask -> 75 bought
    book.add(tick(100.0, 1100, 99.5, 100.5), m0)  # at the prior bid -> 25 sold
    book.add(tick(100.25, 1150, 99.5, 100.5), m0)  # inside the spread, up-tick -> 50 bought
    book.add(tick(100.25, 1150, 99.75, 100.75), m0)  # quote change, no trade
    assert book.completed(m0) == []  # minute still forming
    book.add(tick(99.5, 1200, 99.0, 100.0), m1)  # below the prior bid (99.75) -> 50 sold, new minute
    (bar,) = book.completed(m1)
    assert (bar.volume, bar.buy, bar.sell) == (150, 125, 25)
    assert (bar.open, bar.high, bar.low, bar.close) == (100.5, 100.5, 100.0, 100.25)
    (bar2,) = book.completed(datetime.max)
    assert (bar2.volume, bar2.sell) == (50, 50)


class FakeWS:
    def __init__(self, packets, clock):
        self.packets, self.clock, self.sent = list(packets), clock, []

    async def send(self, msg):
        self.sent.append(json.loads(msg))

    async def recv(self):
        if not self.packets:
            self.clock["t"] = datetime.combine(DAY, time(15, 31))
            return b""
        t, raw = self.packets.pop(0)
        self.clock["t"] = t
        return raw


def minute_packets(sec_id, start_vol=1000):
    out, vol = [], start_vol
    for m in range(3):
        for s, (px, bid, ask, q) in enumerate([(100.0, 99.5, 100.5, 0), (100.5, 100.0, 101.0, 10), (100.0, 99.5, 100.5, 4)]):
            t = T0 + timedelta(minutes=m, seconds=10 * s)
            vol += q
            out.append((t, build_full_packet(sec_id, px + m, q, t, vol, 50, bid + m, ask + m)))
    return out


def test_record_session_writes_bars_with_real_flow(tmp_path):
    clock = {"t": T0}
    ws = FakeWS(minute_packets(7), clock)
    res = asyncio.run(record_session(ws, {7: "NIFTY"}, tmp_path, DAY, lambda: clock["t"]))
    assert ws.sent[0]["RequestCode"] == 21 and ws.sent[0]["InstrumentList"] == [{"ExchangeSegment": "NSE_FNO", "SecurityId": "7"}]
    assert res.ticks == 9 and res.stopped == "session end"
    bars = load_csv(tmp_path / "NIFTY" / f"{DAY}.csv")
    assert len(bars) == 3 and all(b.buy_volume is not None for b in bars)
    assert sum(b.volume for b in bars) == 3 * 14 - 0
    with gzip.open(tmp_path / "NIFTY" / f"{DAY}-ticks.csv.gz", "rt") as f:
        assert len(list(csv.reader(f))) == 9


def test_record_day_over_a_real_websocket(tmp_path):
    websockets = pytest.importorskip("websockets")
    from websockets.asyncio.server import serve

    packets = [raw for _, raw in minute_packets(53001)]
    got = {}

    async def handler(ws):
        got["sub"] = json.loads(await ws.recv())
        got["path"] = ws.request.path
        for raw in packets:
            await ws.send(raw)
        await ws.send(DISCONNECT.pack(50, 10, 2, 0, 807))  # then the token "expires"
        await asyncio.sleep(0.5)

    ready, stop = threading.Event(), threading.Event()

    def server():
        async def main():
            async with serve(handler, "127.0.0.1", 0) as srv:
                got["port"] = srv.sockets[0].getsockname()[1]
                ready.set()
                while not stop.is_set():
                    await asyncio.sleep(0.05)
        asyncio.run(main())

    th = threading.Thread(target=server, daemon=True)
    th.start()
    ready.wait(5)

    class C:
        security_id, trading_symbol = "53001", "NIFTY-Oct2026-FUT"

    sent = []
    clock = iter([T0 + timedelta(seconds=i) for i in range(10_000)])
    url_seen = {}

    def connect(url, **kw):
        url_seen["url"] = url
        return websockets.connect(f"ws://127.0.0.1:{got['port']}/?" + url.split("?", 1)[1], **kw)

    try:
        res = record_day(DAY, ("NIFTY",), tmp_path, tmp_path, lambda m: sent.append(m) or True, lambda m: None,
                         now=lambda: next(clock), connect=connect, credentials=lambda: ("1100", "SECRET-TOKEN"),
                         contracts_for=lambda s, d: C())
    finally:
        stop.set()
        th.join(5)
    assert "token=SECRET-TOKEN" in url_seen["url"] and "authType=2" in got["path"]
    assert got["sub"]["InstrumentList"][0]["SecurityId"] == "53001"
    assert res.stopped.startswith("access token expired") and res.bars["NIFTY"] == 3
    assert any("token expired" in m for m in sent) and not any("SECRET" in m for m in sent)
    assert len(load_csv(tmp_path / "NIFTY" / f"{DAY}.csv")) == 3
