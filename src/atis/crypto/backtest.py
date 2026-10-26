"""Hourly backtest of the trend bot: one account, all coins, the live bot's own signal code.

At the first hour of each UTC day the bot reads daily closes through yesterday, computes each
coin's target, and trades the difference at that hour's open. A trade costs the taker fee plus
slippage on its notional. Perpetual funding is charged every 8 hours (longs pay a positive rate).
Returns are before income tax.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime

from .config import BotConfig
from .signals import Candle, needs_rebalance, target_exposure


@dataclass
class Result:
    equity: list[tuple[datetime, float]]
    trades: int
    fees: float
    funding: float
    exposures: list[tuple[date, dict[str, float]]] = field(default_factory=list)


def run(hourly: dict[str, list[Candle]], funding: dict[str, dict[datetime, float]],
        cfg: BotConfig = BotConfig(), start: datetime | None = None) -> Result:
    syms = [s for s in cfg.markets if s in hourly]
    by_ts = [{c.ts: c for c in hourly[s]} for s in syms]
    stamps = sorted(set.intersection(*(set(m) for m in by_ts)))
    eq, fees_paid, funding_paid, trades = 1.0, 0.0, 0.0, 0
    qty = {s: 0.0 for s in syms}
    mark = {s: 0.0 for s in syms}
    closes: dict[str, list[float]] = {s: [] for s in syms}
    last_close = {s: 0.0 for s in syms}
    last_day: date | None = None
    curve, exposures = [], []
    for ts in stamps:
        bars = {s: m[ts] for s, m in zip(syms, by_ts)}
        for s in syms:  # value open positions at this hour's open
            if qty[s]:
                eq += qty[s] * (bars[s].open - mark[s])
                mark[s] = bars[s].open
        day = ts.date()
        if day != last_day:
            if last_day is not None:  # yesterday's last hourly close is its daily close
                for s in syms:
                    closes[s].append(last_close[s])
            if last_day is not None and (start is None or ts >= start):
                today = {}
                for s in syms:
                    t = target_exposure(closes[s], cfg.trend)
                    if t is None:
                        continue
                    px = bars[s].open
                    want = t.exposure * cfg.weights.get(s, 0.0)
                    have = qty[s] * px / eq if eq > 0 else 0.0
                    today[s] = want
                    if needs_rebalance(want, have, cfg.trend.band):
                        new = want * eq / px
                        cost = abs(new - qty[s]) * px * cfg.costs.per_side
                        eq -= cost
                        fees_paid += cost
                        trades += 1
                        qty[s], mark[s] = new, px
                exposures.append((day, today))
            last_day = day
        for s in syms:
            b = bars[s]
            if qty[s]:
                eq += qty[s] * (b.close - mark[s])
                mark[s] = b.close
                if ts.hour % 8 == 0:
                    rate = funding.get(s, {}).get(ts, cfg.costs.default_funding)
                    f = qty[s] * b.open * rate
                    eq -= f
                    funding_paid += f
        for s in syms:
            last_close[s] = bars[s].close
        if start is None or ts >= start:
            curve.append((ts, eq))
        if eq <= 0:
            break
    return Result(curve, trades, fees_paid, funding_paid, exposures)


def daily_equity(curve: list[tuple[datetime, float]]) -> list[tuple[date, float]]:
    out: dict[date, float] = {}
    for ts, e in curve:
        out[ts.date()] = e
    return sorted(out.items())


def stats(curve: list[tuple[datetime, float]], start: date | None = None, end: date | None = None) -> dict:
    d = [(k, v) for k, v in daily_equity(curve) if (start is None or k >= start) and (end is None or k <= end)]
    if len(d) < 30:
        return {}
    vals = [v for _, v in d]
    rets = [vals[i] / vals[i - 1] - 1 for i in range(1, len(vals))]
    years = (d[-1][0] - d[0][0]).days / 365.25
    mean = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))
    peak, mdd = vals[0], 0.0
    for v in vals:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    by_year: dict[int, tuple[float, float]] = {}
    for k, v in d:
        first, _ = by_year.get(k.year, (v, v))
        by_year[k.year] = (first, v)
    prev = None
    yearly = {}
    for y in sorted(by_year):
        first, last = by_year[y]
        base = prev if prev is not None else first
        yearly[y] = last / base - 1
        prev = last
    return {"cagr": (vals[-1] / vals[0]) ** (1 / years) - 1 if years > 0 else 0.0,
            "sharpe": mean / sd * math.sqrt(365) if sd > 0 else 0.0,
            "max_drawdown": mdd, "years": yearly, "start": d[0][0], "end": d[-1][0]}
