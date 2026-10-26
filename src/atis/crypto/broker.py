"""Brokers: a paper broker (default) and Delta Exchange India (signed REST, live or testnet).

Positions are signed contract counts. The bot only sends market orders, and every reduction is
`reduce_only`, so a retried or duplicated close can never open a position the other way.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

from .config import MARKETS, Costs

USER_AGENT = "atis-crypto/0.1"
DELTA_LIVE = "https://api.india.delta.exchange"
DELTA_TESTNET = "https://cdn-ind.testnet.deltaex.org"


class BrokerError(RuntimeError):
    pass


@dataclass(frozen=True)
class Fill:
    symbol: str
    contracts: int  # signed
    price: float
    fee: float
    order_id: str


class Broker(Protocol):
    name: str

    def equity(self) -> float: ...
    def positions(self) -> dict[str, int]: ...
    def mark_price(self, symbol: str) -> float: ...
    def market_order(self, symbol: str, contracts: int, reduce_only: bool, client_id: str) -> Fill: ...
    def prepare(self, symbol: str, leverage: int) -> None: ...


def public_mark_price(symbol: str, base: str = DELTA_LIVE) -> float:
    req = urllib.request.Request(f"{base}/v2/tickers/{symbol}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as r:
        res = json.load(r)
    if not res.get("success"):
        raise BrokerError(f"ticker {symbol}: {res.get('error')}")
    return float(res["result"]["mark_price"])


# ---- paper ----------------------------------------------------------------------------------------

@dataclass
class PaperState:
    cash: float
    positions: dict[str, int] = field(default_factory=dict)
    entry: dict[str, float] = field(default_factory=dict)
    fees: float = 0.0
    n: int = 0


class PaperBroker:
    """Fills at the mark price plus slippage, pays the taker fee; state persists in a JSON file.

    Funding is not simulated, so paper P&L is slightly optimistic for longs in bull markets.
    """

    name = "paper"

    def __init__(self, path: Path, capital: float, costs: Costs = Costs(),
                 price: Callable[[str], float] = public_mark_price):
        self.path, self.costs, self._price = path, costs, price
        self._marks: dict[str, float] = {}
        if path.exists():
            self.st = PaperState(**json.loads(path.read_text()))
        else:
            self.st = PaperState(cash=capital)
            self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self.st), indent=1))
        tmp.replace(self.path)

    def mark_price(self, symbol: str) -> float:
        if symbol not in self._marks:
            self._marks[symbol] = self._price(symbol)
        return self._marks[symbol]

    def positions(self) -> dict[str, int]:
        return {k: v for k, v in self.st.positions.items() if v}

    def equity(self) -> float:
        eq = self.st.cash
        for sym, n in self.positions().items():
            cv = MARKETS[sym].contract_value
            eq += n * cv * (self.mark_price(sym) - self.st.entry[sym])
        return eq

    def prepare(self, symbol: str, leverage: int) -> None:
        return None

    def market_order(self, symbol: str, contracts: int, reduce_only: bool, client_id: str) -> Fill:
        cur = self.st.positions.get(symbol, 0)
        if reduce_only and (cur == 0 or (cur > 0) == (contracts > 0) or abs(contracts) > abs(cur)):
            raise BrokerError(f"reduce-only order {contracts:+d} would not reduce position {cur:+d}")
        cv = MARKETS[symbol].contract_value
        mark = self.mark_price(symbol)
        px = mark * (1 + self.costs.slippage) if contracts > 0 else mark * (1 - self.costs.slippage)
        fee = abs(contracts) * cv * px * self.costs.taker
        new = cur + contracts
        if cur and (new == 0 or (new > 0) != (cur > 0) or abs(new) < abs(cur)):
            closed = min(abs(contracts), abs(cur)) * (1 if cur > 0 else -1)
            self.st.cash += closed * cv * (px - self.st.entry[symbol])
        if new and (cur == 0 or (new > 0) != (cur > 0)):
            self.st.entry[symbol] = px
        elif new and abs(new) > abs(cur):
            self.st.entry[symbol] = (self.st.entry[symbol] * abs(cur) + px * abs(contracts)) / abs(new)
        self.st.positions[symbol] = new
        self.st.cash -= fee
        self.st.fees += fee
        self.st.n += 1
        self._save()
        return Fill(symbol, contracts, px, fee, f"paper-{self.st.n}")


# ---- Delta Exchange India ---------------------------------------------------------------------------

def sign(secret: str, method: str, timestamp: str, path: str, query: str, body: str) -> str:
    """Delta's signature: hex HMAC-SHA256 of method + timestamp + path + query + body."""
    msg = method + timestamp + path + query + body
    return hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()


class DeltaBroker:
    """Delta Exchange India REST. `base` is the live or the testnet URL."""

    def __init__(self, api_key: str, api_secret: str, base: str = DELTA_LIVE, settle_asset: str = "USD",
                 send: Callable[[urllib.request.Request], dict] | None = None):
        self.name = "delta-testnet" if base == DELTA_TESTNET else "delta-live"
        self._key, self._secret, self.base, self.settle = api_key, api_secret, base, settle_asset
        self._send = send or self._urlopen
        self._products: dict[str, dict] = {}

    @staticmethod
    def _urlopen(req: urllib.request.Request) -> dict:
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as exc:
            try:
                body = json.load(exc)
            except Exception:
                body = {"error": str(exc)}
            raise BrokerError(f"HTTP {exc.code}: {body.get('error', body)}") from None

    def _request(self, method: str, path: str, params: dict | None = None, body: dict | None = None,
                 auth: bool = True) -> dict:
        path = "/v2" + path
        query = ("?" + urllib.parse.urlencode(params)) if params else ""
        payload = json.dumps(body, separators=(",", ":")) if body is not None else ""
        headers = {"User-Agent": USER_AGENT, "Content-Type": "application/json", "Accept": "application/json"}
        if auth:
            ts = str(int(time.time()))
            headers.update({"api-key": self._key, "timestamp": ts,
                            "signature": sign(self._secret, method, ts, path, query, payload)})
        req = urllib.request.Request(self.base + path + query, data=payload.encode() if payload else None,
                                     method=method, headers=headers)
        res = self._send(req)
        if not res.get("success", False):
            raise BrokerError(f"{method} {path}: {res.get('error') or res}")
        return res["result"]

    def product(self, symbol: str) -> dict:
        if symbol not in self._products:
            p = self._request("GET", f"/products/{symbol}", auth=False)
            if abs(float(p["contract_value"]) - MARKETS[symbol].contract_value) > 1e-12:
                raise BrokerError(f"{symbol} contract value is {p['contract_value']}, "
                                  f"expected {MARKETS[symbol].contract_value}")
            self._products[symbol] = p
        return self._products[symbol]

    def mark_price(self, symbol: str) -> float:
        return float(self._request("GET", f"/tickers/{symbol}", auth=False)["mark_price"])

    def positions(self) -> dict[str, int]:
        out = {}
        for p in self._request("GET", "/positions/margined"):
            sym, size = p.get("product_symbol"), int(p.get("size") or 0)
            if sym in MARKETS and size:
                out[sym] = size
        return out

    def equity(self) -> float:
        bal = next((b for b in self._request("GET", "/wallet/balances") if b.get("asset_symbol") == self.settle), None)
        if bal is None:
            raise BrokerError(f"no {self.settle} wallet balance")
        upnl = sum(float(p.get("unrealized_pnl") or 0) for p in self._request("GET", "/positions/margined")
                   if p.get("product_symbol") in MARKETS)
        return float(bal["balance"]) + upnl

    def prepare(self, symbol: str, leverage: int) -> None:
        pid = self.product(symbol)["id"]
        self._request("POST", f"/products/{pid}/orders/leverage", body={"leverage": str(leverage)})

    def market_order(self, symbol: str, contracts: int, reduce_only: bool, client_id: str) -> Fill:
        body = {"product_id": self.product(symbol)["id"], "size": abs(contracts),
                "side": "buy" if contracts > 0 else "sell", "order_type": "market_order",
                "reduce_only": reduce_only, "client_order_id": client_id[:32]}
        r = self._request("POST", "/orders", body=body)
        px = float(r.get("average_fill_price") or r.get("limit_price") or 0)
        fee = float(r.get("paid_commission") or 0)
        return Fill(symbol, contracts, px, fee, str(r.get("id")))
