"""Record real NSE futures order flow from Dhan's live market feed (read-only market data).

Historical tick data with the aggressor side is not available to retail traders, so this builds it
going forward. Each trading day it subscribes to the front-month NIFTY / BANKNIFTY futures in Dhan's
"full" mode (last trade, cumulative volume, 5-level depth), classifies every traded quantity as
buyer- or seller-initiated against the quotes in force just before it (Lee-Ready: at/above the ask =
buy, at/below the bid = sell, otherwise the tick rule), and writes:

  <out>/<SYMBOL>/<YYYY-MM-DD>.csv            1-minute bars with buy_volume / sell_volume / oi
  <out>/<SYMBOL>/<YYYY-MM-DD>-ticks.csv.gz   every update (for later research)

The bar files load with `atis-playbook run --csv` and give the engine true delta. Packet layouts
follow Dhan's official SDK (dhanhq 2.2, marketfeed.py). Needs DHAN_CLIENT_ID / DHAN_ACCESS_TOKEN and
an active Dhan Data API plan; it never calls an order endpoint.
"""

from __future__ import annotations

import asyncio
import csv
import gzip
import json
import struct
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path

FEED_URL = "wss://api-feed.dhan.co"
FULL = struct.Struct("<BHBIfHIfIIIIIIffff100s")  # response code 8, 162 bytes
DEPTH = struct.Struct("<IIHHff")  # bid qty, ask qty, bid orders, ask orders, bid price, ask price
DISCONNECT = struct.Struct("<BHBIH")  # response code 50
NSE_FNO = "NSE_FNO"
SUBSCRIBE_FULL = 21
DISCONNECT_REASONS = {
    805: "too many websocket connections",
    806: "Dhan Data API plan not active - renew it to record",
    807: "access token expired - generate a new one",
    808: "invalid client id",
    809: "authentication failed",
}


class FeedDisconnected(RuntimeError):
    def __init__(self, code: int):
        super().__init__(DISCONNECT_REASONS.get(code, f"server disconnected (code {code})"))
        self.code = code


@dataclass(frozen=True)
class Tick:
    security_id: int
    recv: datetime  # local IST receive time
    ltt: datetime  # exchange last-trade time (IST wall clock)
    ltp: float
    ltq: int
    volume: int  # cumulative day volume
    oi: int
    bid: float
    ask: float
    bid_qty: int
    ask_qty: int


def parse_packet(data: bytes, recv: datetime) -> Tick | None:
    """A full-mode packet -> Tick; other packet types -> None; a disconnect packet raises."""
    if not data:
        return None
    code = data[0]
    if code == 50 and len(data) >= DISCONNECT.size:
        raise FeedDisconnected(DISCONNECT.unpack(data[:DISCONNECT.size])[4])
    if code != 8 or len(data) < FULL.size:
        return None
    f = FULL.unpack(data[:FULL.size])
    bid_qty, ask_qty, _, _, bid, ask = DEPTH.unpack(f[18][:DEPTH.size])
    # Dhan sends LTT as an epoch already on the IST clock (the SDK formats it with utcfromtimestamp)
    ltt = datetime(1970, 1, 1) + timedelta(seconds=f[6])
    return Tick(f[3], recv, ltt, float(f[4]), f[5], f[8], f[11], float(bid), float(ask), bid_qty, ask_qty)


def build_full_packet(security_id: int, ltp: float, ltq: int, ltt: datetime, volume: int, oi: int,
                      bid: float, ask: float, bid_qty: int = 0, ask_qty: int = 0) -> bytes:
    """The inverse of parse_packet, for tests and replays."""
    depth = DEPTH.pack(bid_qty, ask_qty, 0, 0, bid, ask) + bytes(100 - DEPTH.size)
    epoch = int((ltt - datetime(1970, 1, 1)).total_seconds())
    return FULL.pack(8, FULL.size, 2, security_id, ltp, ltq, epoch, ltp, volume, 0, 0, oi, oi, oi,
                     ltp, ltp, ltp, ltp, depth)


@dataclass
class MinuteBar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0
    buy: int = 0
    sell: int = 0
    oi: int = 0


@dataclass
class FlowBook:
    """Turns one instrument's ticks into 1-minute bars with buyer/seller-initiated volume."""

    symbol: str
    prev_volume: int | None = None
    prev_bid: float = 0.0
    prev_ask: float = 0.0
    prev_ltp: float | None = None
    last_side: int = 0
    bar: MinuteBar | None = None
    done: list[MinuteBar] = field(default_factory=list)

    def side(self, ltp: float) -> int:
        if self.prev_ask > 0 and ltp >= self.prev_ask:
            return 1
        if self.prev_bid > 0 and ltp <= self.prev_bid:
            return -1
        if self.prev_ltp is not None and ltp != self.prev_ltp:
            return 1 if ltp > self.prev_ltp else -1
        return self.last_side

    def add(self, t: Tick, minute: datetime) -> None:
        qty = 0 if self.prev_volume is None else max(t.volume - self.prev_volume, 0)
        if qty:
            s = self.side(t.ltp)
            self.last_side = s or self.last_side
            if self.bar is None or self.bar.ts != minute:
                if self.bar is not None:
                    self.done.append(self.bar)
                self.bar = MinuteBar(minute, t.ltp, t.ltp, t.ltp, t.ltp)
            b = self.bar
            b.high, b.low, b.close = max(b.high, t.ltp), min(b.low, t.ltp), t.ltp
            b.volume += qty
            b.buy += qty if s > 0 else 0
            b.sell += qty if s < 0 else 0
            b.oi = t.oi
        self.prev_volume = t.volume if self.prev_volume is None else max(self.prev_volume, t.volume)
        self.prev_bid, self.prev_ask, self.prev_ltp = t.bid, t.ask, t.ltp

    def completed(self, now_minute: datetime) -> list[MinuteBar]:
        """Bars whose minute has passed (the current minute keeps forming)."""
        if self.bar is not None and self.bar.ts < now_minute:
            self.done.append(self.bar)
            self.bar = None
        out, self.done = self.done, []
        return out


class DayWriter:
    """Appends completed bars and raw ticks for one symbol and day."""

    def __init__(self, out: Path, symbol: str, day: date):
        self.dir = out / symbol
        self.dir.mkdir(parents=True, exist_ok=True)
        self.bars_path = self.dir / f"{day}.csv"
        new = not self.bars_path.exists()
        self._bars = open(self.bars_path, "a", newline="")
        self._bw = csv.writer(self._bars)
        if new:
            self._bw.writerow(["timestamp", "open", "high", "low", "close", "volume", "buy_volume", "sell_volume", "oi"])
        self._ticks = gzip.open(self.dir / f"{day}-ticks.csv.gz", "at", newline="")
        self._tw = csv.writer(self._ticks)
        self.bars = 0

    def tick(self, t: Tick) -> None:
        self._tw.writerow([t.recv.isoformat(timespec="milliseconds"), t.ltt.isoformat(), t.ltp, t.ltq, t.volume,
                           t.oi, t.bid, t.ask, t.bid_qty, t.ask_qty])

    def write(self, bars: list[MinuteBar]) -> None:
        for b in bars:
            self._bw.writerow([b.ts.isoformat(sep=" "), b.open, b.high, b.low, b.close, b.volume, b.buy, b.sell, b.oi])
            self.bars += 1
        if bars:
            self._bars.flush()

    def close(self) -> None:
        self._bars.close()
        self._ticks.close()


def subscribe_message(security_ids: list[int]) -> str:
    return json.dumps({"RequestCode": SUBSCRIBE_FULL, "InstrumentCount": len(security_ids),
                       "InstrumentList": [{"ExchangeSegment": NSE_FNO, "SecurityId": str(s)} for s in security_ids]})


@dataclass
class RecordResult:
    bars: dict[str, int]
    ticks: int
    stopped: str


async def record_session(ws, instruments: dict[int, str], out: Path, day: date, now: Callable[[], datetime],
                         end: time = time(15, 31), books: dict[int, FlowBook] | None = None,
                         writers: dict[str, DayWriter] | None = None) -> RecordResult:
    """Read one connection until `end`. `ws` needs async send() and recv() (websockets or a fake)."""
    books = books if books is not None else {sid: FlowBook(sym) for sid, sym in instruments.items()}
    writers = writers if writers is not None else {sym: DayWriter(out, sym, day) for sym in instruments.values()}
    await ws.send(subscribe_message(list(instruments)))
    ticks = 0
    stop_at = datetime.combine(day, end)
    while True:
        t_now = now()
        if t_now >= stop_at:
            reason = "session end"
            break
        try:
            data = await asyncio.wait_for(ws.recv(), timeout=30)
        except asyncio.TimeoutError:
            data = b""
        t_now = now()
        if isinstance(data, (bytes, bytearray)) and data:
            tick = parse_packet(bytes(data), t_now)
            if tick is not None and tick.security_id in books:
                ticks += 1
                sym = instruments[tick.security_id]
                writers[sym].tick(tick)
                ltt_ok = abs((tick.ltt - t_now).total_seconds()) < 3600
                minute = (tick.ltt if ltt_ok else t_now).replace(second=0, microsecond=0)
                books[tick.security_id].add(tick, minute)
        minute_now = t_now.replace(second=0, microsecond=0)
        for sid, book in books.items():
            writers[instruments[sid]].write(book.completed(minute_now))
    for sid, book in books.items():
        writers[instruments[sid]].write(book.completed(datetime.max))
    return RecordResult({sym: w.bars for sym, w in writers.items()}, ticks, reason)


def feed_url(client_id: str, token: str) -> str:
    return f"{FEED_URL}?version=2&token={token}&clientId={client_id}&authType=2"


def _mask(text: str, secret: str) -> str:
    return text.replace(secret, "***") if secret else text


def record_day(day: date, symbols: tuple[str, ...], out: Path, cache: Path, notify: Callable[[str], bool],
               log: Callable[[str], None], now: Callable[[], datetime], connect=None,
               credentials: Callable[[], tuple[str, str]] | None = None,
               contracts_for: Callable[[str, date], object] | None = None,
               end: time = time(15, 31), max_attempts: int = 30) -> RecordResult | None:
    """Record one trading day, reconnecting on drops; notify once on a fatal Dhan disconnect."""
    from ..playbook import dhan

    if connect is None:
        import websockets  # optional dependency: pip install 'atis[record]'
        connect = websockets.connect
    client_id, token = (credentials or dhan.credentials)()
    contracts_for = contracts_for or (lambda sym, d: dhan.front_contract(d, dhan.load_contracts(sym, cache, d)))
    instruments: dict[int, str] = {}
    for sym in symbols:
        c = contracts_for(sym, day)
        if c is None:
            log(f"{sym}: no live futures contract in the Dhan scrip master")
            continue
        instruments[int(c.security_id)] = sym
        log(f"{sym}: recording {getattr(c, 'trading_symbol', c.security_id)} (security id {c.security_id})")
    if not instruments:
        return None
    books = {sid: FlowBook(sym) for sid, sym in instruments.items()}
    writers = {sym: DayWriter(out, sym, day) for sym in instruments.values()}
    stop_at = datetime.combine(day, end)
    result, attempts, reason, total_ticks = None, 0, "session end", 0

    async def one_connection():
        async with connect(feed_url(client_id, token), ping_interval=20, ping_timeout=20) as ws:
            return await record_session(ws, instruments, out, day, now, end, books, writers)

    try:
        while now() < stop_at and attempts < max_attempts:
            try:
                result = asyncio.run(one_connection())
                total_ticks += result.ticks
                if result.stopped == "session end":
                    break
            except FeedDisconnected as exc:
                reason = str(exc)
                log(f"feed disconnected: {reason}")
                if exc.code in (806, 807, 808, 809):
                    notify(f"<b>ATIS recorder stopped:</b> {reason}.")
                    break
            except Exception as exc:  # network drops, handshake errors
                reason = _mask(f"{type(exc).__name__}: {exc}", token)
                log(f"feed error: {reason}")
                if "401" in reason or "403" in reason:
                    notify("<b>ATIS recorder stopped:</b> Dhan rejected the credentials (token expired?).")
                    break
            attempts += 1
            asyncio.run(asyncio.sleep(min(60, 2 ** min(attempts, 6))))
    finally:
        for sid, book in books.items():
            writers[instruments[sid]].write(book.completed(datetime.max))
        for w in writers.values():
            w.close()
    bars = {sym: w.bars for sym, w in writers.items()}
    notify(f"<b>ATIS recorder {day:%d %b}</b>: " + ", ".join(f"{s} {n} bars" for s, n in bars.items())
           + ("" if reason == "session end" else f" (stopped: {reason})"))
    return RecordResult(bars, total_ticks, reason)
