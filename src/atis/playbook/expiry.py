"""Index-option expiry calendar.

NSE (Oct 2026 regime): NIFTY weekly Tuesday, BANKNIFTY monthly last Tuesday, trading Mon-Fri.
Crypto (Delta Exchange India): options expire every day and the market trades every calendar day
(`weekends=True`).
"""

from __future__ import annotations

import calendar as _cal
from collections.abc import Collection
from datetime import date, timedelta

from .config import InstrumentSpec


def is_trading_day(d: date, holidays: Collection[date] = (), weekends: bool = False) -> bool:
    return (weekends or d.weekday() < 5) and d not in holidays


def shift_for_holiday(d: date, holidays: Collection[date] = (), weekends: bool = False) -> date:
    while not is_trading_day(d, holidays, weekends):
        d -= timedelta(days=1)
    return d


def last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    last = date(year, month, _cal.monthrange(year, month)[1])
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def weekly_expiry(d: date, holidays: Collection[date] = (), weekday: int = 1, weekends: bool = False) -> date:
    t = d + timedelta(days=(weekday - d.weekday()) % 7)
    while True:
        e = shift_for_holiday(t, holidays, weekends)
        if e >= d:
            return e
        t += timedelta(days=7)


def monthly_expiry(d: date, holidays: Collection[date] = (), weekday: int = 1, weekends: bool = False) -> date:
    y, m = d.year, d.month
    while True:
        e = shift_for_holiday(last_weekday_of_month(y, m, weekday), holidays, weekends)
        if e >= d:
            return e
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def nearest_expiry(spec: InstrumentSpec, d: date, holidays: Collection[date] = ()) -> date:
    if spec.daily_expiry:
        while not is_trading_day(d, holidays, spec.trades_weekends):
            d += timedelta(days=1)
        return d
    if spec.weekly_expiry:
        return weekly_expiry(d, holidays, spec.expiry_weekday, spec.trades_weekends)
    return monthly_expiry(d, holidays, spec.expiry_weekday, spec.trades_weekends)


def is_expiry_day(spec: InstrumentSpec, d: date, holidays: Collection[date] = ()) -> bool:
    return nearest_expiry(spec, d, holidays) == d


def is_monthly_expiry_day(spec: InstrumentSpec, d: date, holidays: Collection[date] = ()) -> bool:
    return monthly_expiry(d, holidays, spec.expiry_weekday, spec.trades_weekends) == d


def sessions_until(d: date, expiry: date, holidays: Collection[date] = (), weekends: bool = False) -> int:
    """Trading sessions strictly after d up to and including expiry."""
    n, t = 0, d + timedelta(days=1)
    while t <= expiry:
        n += is_trading_day(t, holidays, weekends)
        t += timedelta(days=1)
    return n


def expiry_with_min_sessions(spec: InstrumentSpec, d: date, min_sessions: int,
                             holidays: Collection[date] = ()) -> date:
    e = nearest_expiry(spec, d, holidays)
    while sessions_until(d, e, holidays, spec.trades_weekends) < min_sessions:
        e = nearest_expiry(spec, e + timedelta(days=1), holidays)
    return e
