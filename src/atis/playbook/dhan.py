"""Download 1-minute NIFTY / BANKNIFTY futures candles (with volume and OI) from DhanHQ v2, cached per month.

Read-only: only the profile and intraday-chart endpoints are ever called (see READ_ONLY_PATHS); this module
cannot place, modify or cancel orders. Credentials come from DHAN_CLIENT_ID / DHAN_ACCESS_TOKEN in the
environment and are never logged.

Futures are contract-wise. Security IDs come from Dhan's public scrip master, which lists only live contracts,
so every contract seen is remembered in <cache>/contracts.csv. Monthly contracts are joined at rollover: a
contract is the front month up to and including its expiry day. With back-adjustment (default) each roll gap,
measured at the last minute both contracts traded on the expiry day, is added to all earlier bars so profile
levels stay comparable across the roll; R multiples are unchanged, absolute prices before a roll are not.

Dhan serves intraday history only for *active* contracts (expired futures return nothing), so the joined
series starts where the oldest still-listed contract's data starts; `availability()` measures that. On days
whose real front month is unknown or no longer served, the next contract with data stands in. Months fetched
while a contract was active stay in the cache, so history accumulates from the first download onward.
"""

from __future__ import annotations

import csv
import io
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .models import Bar
from .upstox import month_ranges

API = "https://api.dhan.co/v2"
SCRIP_MASTER = "https://images.dhan.co/api-data/api-scrip-master.csv"
READ_ONLY_PATHS = frozenset({"/profile", "/charts/intraday"})
SYMBOLS = ("NIFTY", "BANKNIFTY")
IST = timezone(timedelta(hours=5, minutes=30))
CONTRACT_FIELDS = ["security_id", "symbol", "expiry", "lot", "trading_symbol"]
BAR_FIELDS = ["timestamp", "open", "high", "low", "close", "volume", "oi"]

Post = Callable[[str, dict], dict]


class DhanError(RuntimeError):
    pass


@dataclass(frozen=True)
class Contract:
    security_id: str
    symbol: str
    expiry: date
    lot: int
    trading_symbol: str


# ---- credentials / HTTP ----------------------------------------------------------------------

def credentials() -> tuple[str, str]:
    client_id = os.environ.get("DHAN_CLIENT_ID", "").strip()
    token = os.environ.get("DHAN_ACCESS_TOKEN", "").strip()
    missing = [n for n, v in (("DHAN_CLIENT_ID", client_id), ("DHAN_ACCESS_TOKEN", token)) if not v]
    if missing:
        raise DhanError(f"{' and '.join(missing)} not set in the environment (Dhan Web -> DhanHQ Trading APIs)")
    return client_id, token


def _request(method: str, path: str, body: dict | None = None, retries: int = 4) -> dict:
    if path not in READ_ONLY_PATHS:
        raise DhanError(f"refusing to call {path}: only {sorted(READ_ONLY_PATHS)} are allowed")
    client_id, token = credentials()
    headers = {"access-token": token, "client-id": client_id, "Accept": "application/json"}
    data = None
    if body is not None:
        data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
    for attempt in range(retries):
        req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 502, 503) and attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            if e.code in (401, 403):
                raise DhanError(f"Dhan rejected the token (HTTP {e.code}); tokens last 24 h: {detail}") from None
            raise DhanError(f"Dhan HTTP {e.code} on {path}: {detail}") from None
        except urllib.error.URLError as e:
            if attempt == retries - 1:
                raise DhanError(f"could not reach Dhan: {e.reason}") from None
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def profile() -> dict:
    """GET /v2/profile: token validity, active segments, data plan."""
    return _request("GET", "/profile")


def _post(path: str, body: dict) -> dict:
    return _request("POST", path, body)


# ---- scrip master / contract registry --------------------------------------------------------

def parse_scrip_master(lines: Iterable[str], symbols: Iterable[str] = SYMBOLS) -> list[Contract]:
    """NSE monthly index futures (FUTIDX) for the given underlyings."""
    want = set(symbols)
    out = []
    for r in csv.DictReader(lines):
        tsym = (r.get("SEM_TRADING_SYMBOL") or "").strip()
        if (r.get("SEM_EXM_EXCH_ID") != "NSE" or r.get("SEM_INSTRUMENT_NAME") != "FUTIDX"
                or not tsym.endswith("-FUT") or tsym.split("-", 1)[0] not in want):
            continue
        out.append(Contract(r["SEM_SMST_SECURITY_ID"].strip(), tsym.split("-", 1)[0],
                            datetime.fromisoformat(r["SEM_EXPIRY_DATE"].strip()).date(),
                            int(float(r["SEM_LOT_UNITS"])), tsym))
    return sorted(out, key=lambda c: (c.symbol, c.expiry))


def download_master() -> list[str]:
    """Header plus FUTIDX rows of the ~25 MB scrip master, streamed (rows are filtered before parsing)."""
    req = urllib.request.Request(SCRIP_MASTER, headers={"User-Agent": "atis-playbook"})
    with urllib.request.urlopen(req, timeout=120) as r:
        stream = io.TextIOWrapper(r, encoding="utf-8", newline="")
        header = next(stream)
        return [header] + [ln for ln in stream if ",FUTIDX," in ln]


def _read_registry(path: Path) -> list[Contract]:
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return [Contract(r["security_id"], r["symbol"], date.fromisoformat(r["expiry"]), int(r["lot"]),
                         r["trading_symbol"]) for r in csv.DictReader(f)]


def _write_registry(path: Path, contracts: list[Contract]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(CONTRACT_FIELDS)
        for c in contracts:
            w.writerow([c.security_id, c.symbol, c.expiry.isoformat(), c.lot, c.trading_symbol])
    tmp.replace(path)


def load_contracts(symbol: str, cache_dir: Path | None, today: date,
                   master: Callable[[], list[str]] = download_master) -> list[Contract]:
    """Known futures contracts for symbol, oldest expiry first. The scrip master is read at most once a day
    and merged into the registry, so contracts stay known after they drop off the master at expiry."""
    path = cache_dir / "contracts.csv" if cache_dir else None
    known = _read_registry(path) if path else []
    fresh = path is not None and path.exists() and date.fromtimestamp(path.stat().st_mtime) >= today
    if not fresh:
        merged = {c.security_id: c for c in known}
        merged.update((c.security_id, c) for c in parse_scrip_master(master()))
        known = sorted(merged.values(), key=lambda c: (c.symbol, c.expiry))
        if path:
            _write_registry(path, known)
    return [c for c in known if c.symbol == symbol]


def front_contract(day: date, contracts: list[Contract]) -> Contract | None:
    """The nearest contract not yet expired on day (expiring contracts stay front through expiry day)."""
    return next((c for c in contracts if c.expiry >= day), None)


# ---- candles ---------------------------------------------------------------------------------

def _epoch_shift(stamps: list[int]) -> int:
    """Seconds to add so bars land at IST: whichever reading puts the most sessions' first bar at 09:15."""
    def score(shift: int) -> int:
        first: dict[date, datetime] = {}
        for t in stamps:
            d = datetime.fromtimestamp(t + shift, IST)
            if d.date() not in first or d < first[d.date()]:
                first[d.date()] = d
        return sum(1 for d in first.values() if (d.hour, d.minute) == (9, 15))
    return max((0, -19800), key=score)


def parse_candles(payload: dict) -> list[Bar]:
    if isinstance(payload, dict) and "timestamp" not in payload and isinstance(payload.get("data"), dict):
        payload = payload["data"]
    if payload.get("errorCode") or payload.get("status") == "failure":
        raise DhanError(f"Dhan error: {payload}")
    ts = payload.get("timestamp") or []
    if not ts:
        return []
    shift = _epoch_shift([int(t) for t in ts])
    oi = payload.get("open_interest") or [None] * len(ts)
    vol = payload.get("volume") or [0] * len(ts)
    bars = [Bar(datetime.fromtimestamp(int(t) + shift, IST).replace(tzinfo=None), float(payload["open"][i]),
                float(payload["high"][i]), float(payload["low"][i]), float(payload["close"][i]), float(vol[i]),
                oi=None if oi[i] is None else float(oi[i]))
            for i, t in enumerate(ts)]
    return sorted(bars, key=lambda b: b.ts)


def fetch_contract(contract: Contract, start: date, end: date, post: Post = _post) -> list[Bar]:
    """1-minute bars of one contract for [start, end] (at most 90 days per request)."""
    if (end - start).days > 89:
        raise ValueError("Dhan serves at most 90 days of intraday data per request")
    return parse_candles(post("/charts/intraday", {
        "securityId": contract.security_id, "exchangeSegment": "NSE_FNO", "instrument": "FUTIDX",
        "interval": "1", "oi": True, "fromDate": f"{start} 09:00:00", "toDate": f"{end} 15:30:00"}))


def _write(path: Path, bars: list[Bar]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(BAR_FIELDS)
        for b in bars:
            w.writerow([b.ts.isoformat(sep=" "), b.open, b.high, b.low, b.close, b.volume,
                        "" if b.oi is None else b.oi])
    tmp.replace(path)


def _read(path: Path) -> list[Bar]:
    with open(path, newline="") as f:
        return [Bar(datetime.fromisoformat(r["timestamp"]), float(r["open"]), float(r["high"]), float(r["low"]),
                    float(r["close"]), float(r["volume"]), oi=float(r["oi"]) if r["oi"] else None)
                for r in csv.DictReader(f)]


def _month_end(d: date) -> date:
    return (d.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)


def _contract_month(contract: Contract, month_start: date, today: date, cache_dir: Path | None,
                    post: Post) -> list[Bar]:
    """One contract's bars for one calendar month; completed months are cached, the current one refetched."""
    month_end = _month_end(month_start)
    complete = month_end < today or contract.expiry < today and contract.expiry <= month_end
    path = (cache_dir / contract.symbol / f"{month_start:%Y-%m}" / f"{contract.trading_symbol}.csv"
            if cache_dir else None)
    if path and complete and path.exists():
        return _read(path)
    bars = fetch_contract(contract, month_start, min(month_end, today), post)
    if path and complete and bars:
        _write(path, bars)
    if post is _post:
        time.sleep(0.25)
    return bars


@dataclass(frozen=True)
class Roll:
    old: Contract
    new: Contract
    at: datetime | None
    gap: float  # new minus old at `at`; 0.0 when the contracts never overlapped in the data


def join_contracts(by_contract: dict[str, list[Bar]], contracts: list[Contract],
                   start: date, end: date, adjust: bool = True) -> tuple[list[Bar], list[Roll]]:
    """Stitch contracts into one front-month series for [start, end], optionally back-adjusting each roll.

    Each day uses the nearest-expiry contract that has bars that day, so a contract Dhan no longer serves is
    replaced by the next one instead of leaving a hole."""
    days: dict[date, dict[str, list[Bar]]] = {}
    for sec, bars in by_contract.items():
        for b in bars:
            if start <= b.ts.date() <= end:
                days.setdefault(b.ts.date(), {}).setdefault(sec, []).append(b)
    series: list[tuple[Contract, list[Bar]]] = []
    for d in sorted(days):
        c = next((c for c in contracts if c.expiry >= d and c.security_id in days[d]), None)
        if c is None:
            continue
        if not series or series[-1][0] != c:
            series.append((c, []))
        series[-1][1].extend(days[d][c.security_id])
    rolls = []
    for (old, old_bars), (new, _) in zip(series, series[1:]):
        last_day = old_bars[-1].ts.date()
        o = {b.ts: b.close for b in old_bars if b.ts.date() == last_day}
        n = {b.ts: b.close for b in by_contract[new.security_id] if b.ts.date() == last_day}
        common = sorted(o.keys() & n.keys())
        rolls.append(Roll(old, new, common[-1], n[common[-1]] - o[common[-1]]) if common
                     else Roll(old, new, None, 0.0))
    out: list[Bar] = []
    for i, (_, bars) in enumerate(series):
        offset = sum(r.gap for r in rolls[i:]) if adjust else 0.0
        out += [_shift(b, offset) for b in bars] if offset else bars
    return out, rolls


def _shift(b: Bar, offset: float) -> Bar:
    return replace(b, open=round(b.open + offset, 2), high=round(b.high + offset, 2),
                   low=round(b.low + offset, 2), close=round(b.close + offset, 2))


def fetch_futures_1m(symbol: str, start: date, end: date, cache_dir: Path | None = None,
                     post: Post = _post, master: Callable[[], list[str]] = download_master,
                     today: date | None = None, adjust: bool = True,
                     on_month: Callable[[date, int], None] | None = None,
                     rolls_out: list[Roll] | None = None) -> list[Bar]:
    """Continuous front-month 1-minute futures bars (volume + OI) for [start, end]."""
    if symbol not in SYMBOLS:
        raise ValueError(f"unknown symbol {symbol}; expected one of {', '.join(SYMBOLS)}")
    if post is _post:
        credentials()  # fail before downloading the scrip master
    today = today or date.today()
    end = min(end, today)
    if start > end:
        raise ValueError("empty date range")
    contracts = load_contracts(symbol, cache_dir, today, master)
    if not contracts:
        raise DhanError(f"no {symbol} futures contracts in the Dhan scrip master")
    by_contract: dict[str, list[Bar]] = {}
    for s, e in month_ranges(start, end):
        month_start = s.replace(day=1)
        needed = {front_contract(d, contracts) for d in _days(s, e)} - {None}
        # The next contract is also fetched in a month where one expires, to measure the roll gap.
        rolling = [c for c in needed if month_start <= c.expiry <= _month_end(month_start) and c.expiry < end]
        needed |= {nxt for c in rolling if (nxt := front_contract(c.expiry + timedelta(days=1), contracts))}
        queue, done = sorted(needed, key=lambda c: c.expiry), set()
        while queue:
            c = queue.pop(0)
            if c.security_id in done:
                continue
            done.add(c.security_id)
            bars = _contract_month(c, month_start, today, cache_dir, post)
            by_contract.setdefault(c.security_id, []).extend(bars)
            # An empty front contract (expired, no longer served): its successor stands in.
            if not bars and (nxt := front_contract(c.expiry + timedelta(days=1), contracts)):
                queue.append(nxt)
        if on_month:
            on_month(month_start, len({b.ts for sec in done for b in by_contract[sec] if s <= b.ts.date() <= e}))
    bars, rolls = join_contracts(by_contract, contracts, start, end, adjust)
    if rolls_out is not None:
        rolls_out.extend(rolls)
    return bars


def _days(s: date, e: date) -> Iterable[date]:
    while s <= e:
        yield s
        s += timedelta(days=1)


def availability(symbol: str, cache_dir: Path | None = None, post: Post = _post,
                 master: Callable[[], list[str]] = download_master,
                 today: date | None = None) -> list[tuple[Contract, date | None, date | None]]:
    """(contract, first bar date, last bar date) for every known contract, probing back up to 360 days.

    Expired contracts kept in the registry are probed too, which shows whether Dhan still serves them."""
    today = today or date.today()
    out = []
    for c in load_contracts(symbol, cache_dir, today, master):
        first = last = None
        hi = min(c.expiry, today)
        for _ in range(4):
            lo = hi - timedelta(days=89)
            bars = fetch_contract(c, lo, hi, post)
            if post is _post:
                time.sleep(0.25)
            if not bars:
                break
            first, last = bars[0].ts.date(), last or bars[-1].ts.date()
            if bars[0].ts.date() > lo + timedelta(days=5):
                break
            hi = lo - timedelta(days=1)
        out.append((c, first, last))
    return out
