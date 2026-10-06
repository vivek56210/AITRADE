"""Real option premiums for alerts: what to buy/sell, at what premium, and premium stop / targets.

The engine works on index levels. At each signal this module looks up the actual option contracts
(Upstox's public instrument master), reads each leg's premium at the signal minute (Upstox's public
1-minute candles: intraday on the live day, historical in replays), backs out each leg's implied
volatility, and reprices the position at the index stop and targets with that volatility. So the
alert can say "BUY 22550 PE at 129.4, SL 100.5, T1 151, T2 206" in option terms, and the day summary
can show option P&L in rupees from the premiums actually traded at each exit minute.
"""

from __future__ import annotations

import gzip
import json
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from ..playbook.config import RiskParams
from ..playbook.models import Bar, SetupSignal
from ..playbook.options import bs_price_delta, implied_vol
from ..playbook.upstox import _get, parse_candles

MASTER_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
CANDLES = "https://api.upstox.com/v3/historical-candle"
IST = timezone(timedelta(hours=5, minutes=30))
EXPIRY_CLOSE = time(15, 30)


def _download_master() -> bytes:
    import urllib.request
    from ..playbook.upstox import USER_AGENT
    req = urllib.request.Request(MASTER_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


@dataclass
class OptionChain:
    """(underlying, expiry, strike, CE/PE) -> (instrument key, lot size) for index options."""

    keys: dict[tuple[str, date, float, str], tuple[str, int]]

    @classmethod
    def from_rows(cls, rows: list[dict], underlyings=("NIFTY", "BANKNIFTY")) -> OptionChain:
        keys = {}
        for x in rows:
            if x.get("segment") != "NSE_FO" or x.get("instrument_type") not in ("CE", "PE"):
                continue
            if x.get("underlying_symbol") not in underlyings:
                continue
            exp = datetime.fromtimestamp(x["expiry"] / 1000, IST).date()
            keys[(x["underlying_symbol"], exp, float(x["strike_price"]), x["instrument_type"])] = \
                (x["instrument_key"], int(x.get("lot_size") or 0))
        return cls(keys)

    @classmethod
    def load(cls, cache_dir: Path, today: date, download: Callable[[], bytes] = _download_master) -> OptionChain:
        """The filtered chain, cached once per day; falls back to an older cache when offline."""
        path = cache_dir / "option_chain.json"
        if path.exists():
            data = json.loads(path.read_text())
            if data.get("day") == today.isoformat():
                return cls._from_cache(data)
        try:
            chain = cls.from_rows(json.loads(gzip.decompress(download())))
        except Exception:
            if path.exists():
                return cls._from_cache(json.loads(path.read_text()))
            raise
        cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"day": today.isoformat(), "rows": [
            [u, e.isoformat(), k, r, key, lot] for (u, e, k, r), (key, lot) in chain.keys.items()]}))
        return chain

    @classmethod
    def _from_cache(cls, data: dict) -> OptionChain:
        return cls({(u, date.fromisoformat(e), float(k), r): (key, int(lot)) for u, e, k, r, key, lot in data["rows"]})

    def find(self, symbol: str, expiry: date, strike: float, right: str) -> tuple[str, int] | None:
        return self.keys.get((symbol, expiry, float(strike), right))


class OptionPrices:
    """1-minute option candles from Upstox's public API, cached per instrument and day."""

    def __init__(self, get: Callable[[str], dict] = _get, historical: bool = False):
        self.get = get
        self.historical = historical  # replays: always use the historical endpoint
        self._cache: dict[tuple[str, date], tuple[datetime, list[Bar]]] = {}

    def candles(self, key: str, day: date, now: datetime) -> list[Bar]:
        hit = self._cache.get((key, day))
        live = not self.historical and now.date() == day
        if hit and (not live or now - hit[0] < timedelta(seconds=20)):
            return hit[1]
        q = urllib.parse.quote(key, safe="")
        url = f"{CANDLES}/intraday/{q}/minutes/1" if live else f"{CANDLES}/{q}/minutes/1/{day}/{day}"
        bars = parse_candles(self.get(url))
        self._cache[(key, day)] = (now, bars)
        return bars

    def price_at(self, key: str, day: date, at: datetime, now: datetime | None = None) -> float | None:
        """Close of the last minute that ended at or before `at`."""
        bars = self.candles(key, day, now or at)
        done = [b for b in bars if b.ts + timedelta(minutes=1) <= at]
        return done[-1].close if done else None


@dataclass
class LegQuote:
    side: str
    right: str
    strike: float
    expiry: date
    key: str
    premium: float
    iv: float | None


@dataclass
class TradeQuote:
    """A signal in option terms (premiums per unit; rupees use lots x lot size)."""

    legs: list[LegQuote]
    credit: bool  # True: the position is opened for a net credit (premium selling)
    entry: float  # net premium paid (debit) or received (credit)
    stop: float | None  # net premium at which to exit for a loss
    targets: list[float] = field(default_factory=list)
    lot_size: int = 0
    lots: int = 0
    risk_per_lot: float | None = None
    years: float = 0.0

    def value(self, index_level: float, years: float | None = None) -> float | None:
        """Net premium of the position if the index were at `index_level` (same IVs)."""
        total = 0.0
        t = self.years if years is None else years
        for leg in self.legs:
            if leg.iv is None:
                return None
            px = bs_price_delta(index_level, leg.strike, t, leg.iv, 0.065, leg.right)[0]
            total += px if (leg.side == "BUY") != self.credit else -px
        return total


def _years_to_expiry(expiry: date, now: datetime) -> float:
    return max((datetime.combine(expiry, EXPIRY_CLOSE) - now) / timedelta(days=365), 1e-6)


def quote_signal(sig: SetupSignal, chain: OptionChain, prices: OptionPrices, now: datetime,
                 risk: RiskParams = RiskParams(), rate: float = 0.065) -> TradeQuote | None:
    """Price the signal's option legs at the signal minute; None when any leg cannot be priced."""
    legs: list[LegQuote] = []
    lot_size = 0
    for leg in sig.option_plan.legs:
        found = chain.find(sig.symbol, leg.expiry, leg.strike, leg.right)
        if found is None:
            return None
        key, lot_size = found
        px = prices.price_at(key, sig.ts.date(), sig.ts, now)
        if px is None or px <= 0:
            return None
        yrs = _years_to_expiry(leg.expiry, sig.ts)
        legs.append(LegQuote(leg.side, leg.right, leg.strike, leg.expiry, key, px,
                             implied_vol(px, sig.entry, leg.strike, yrs, rate, leg.right)))
    if not legs:
        return None
    credit = sig.option_plan.structure.is_short_premium
    net = sum(l.premium if (l.side == "BUY") != credit else -l.premium for l in legs)
    q = TradeQuote(legs, credit, round(net, 2), None, [], lot_size, years=_years_to_expiry(legs[0].expiry, sig.ts))
    budget = risk.capital * risk.risk_per_trade * sig.size_multiplier
    if credit:
        # playbook: exit the threatened side if its premium doubles; book 50%, then 70% of the credit
        q.stop = round(2 * net, 2)
        q.targets = [round(0.5 * net, 2), round(0.3 * net, 2)]
        q.risk_per_lot = round(net * lot_size, 2)
    else:
        at_stop = q.value(sig.stop) if sig.stop is not None else None
        floor = net * (1 - risk.premium_stop_pct)
        q.stop = round(max(at_stop, floor) if at_stop is not None else floor, 2)
        q.targets = [round(v, 2) for v in (q.value(t.price) for t in sig.targets) if v is not None]
        # a spread's premium barely moves before its stop, so size it by what it can really lose: the debit
        q.risk_per_lot = round((net if len(legs) > 1 else net - q.stop) * lot_size, 2)
    q.lots = int(budget // q.risk_per_lot) if q.risk_per_lot and q.risk_per_lot > 0 else 0
    return q


def option_pnl(q: TradeQuote, exits: list[tuple[datetime, float]], prices: OptionPrices, symbol_day: date,
               now: datetime) -> float | None:
    """Rupee P&L of the quoted position from the premiums actually traded at each exit minute (per the
    lots in the quote, or one lot when the size rounded to zero)."""
    if not exits:
        return None
    lots = q.lots or 1
    pnl = 0.0
    for ts, frac in exits:
        net = 0.0
        for leg in q.legs:
            px = prices.price_at(leg.key, symbol_day, ts, now)
            if px is None:
                return None
            net += px if (leg.side == "BUY") != q.credit else -px
        pnl += frac * ((q.entry - net) if q.credit else (net - q.entry))
    return round(pnl * lots * q.lot_size, 0)


class OptionDesk:
    """What the live runner uses: quotes and P&L that never raise (a failure only drops the option part)."""

    def __init__(self, chain_loader: Callable[[], OptionChain], prices: OptionPrices,
                 risk: RiskParams = RiskParams(), log: Callable[[str], None] = print):
        self._load, self.prices, self.risk, self.log = chain_loader, prices, risk, log
        self._chain: OptionChain | None = None
        self._failed = False

    def chain(self) -> OptionChain | None:
        if self._chain is None and not self._failed:
            try:
                self._chain = self._load()
            except Exception as exc:
                self._failed = True
                self.log(f"option chain unavailable ({type(exc).__name__}: {exc}) - alerts carry index levels only")
        return self._chain

    def quote(self, sig: SetupSignal, now: datetime) -> TradeQuote | None:
        chain = self.chain()
        if chain is None:
            return None
        try:
            return quote_signal(sig, chain, self.prices, now, self.risk)
        except Exception as exc:
            self.log(f"{sig.symbol} {sig.setup_id}: option quote failed ({type(exc).__name__}: {exc})")
            return None

    def pnl(self, q: TradeQuote | None, exits: list, day: date, now: datetime) -> float | None:
        if q is None:
            return None
        try:
            return option_pnl(q, exits, self.prices, day, now)
        except Exception as exc:
            self.log(f"option P&L failed ({type(exc).__name__}: {exc})")
            return None


def quote_json(q: TradeQuote | None) -> dict | None:
    if q is None:
        return None
    return {"legs": [{"side": l.side, "strike": l.strike, "right": l.right, "expiry": l.expiry.isoformat(),
                      "premium": l.premium, "iv": None if l.iv is None else round(l.iv, 4)} for l in q.legs],
            "credit": q.credit, "entry": q.entry, "stop": q.stop, "targets": q.targets,
            "lots": q.lots, "lot_size": q.lot_size, "risk_per_lot": q.risk_per_lot}
