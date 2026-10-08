"""Actual index-option expiry dates from Dhan's public scrip master, and the holidays they imply.

Expiries move to the previous trading day when the scheduled Tuesday is a holiday (e.g. NIFTY's
2026-10-20 expiry is listed on Monday 2026-10-19), so the listed dates reveal those holidays.
"""

from __future__ import annotations

import csv
import io
import json
import urllib.request
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta
from pathlib import Path

SCRIP_MASTER = "https://images.dhan.co/api-data/api-scrip-master.csv"
SYMBOLS = ("NIFTY", "BANKNIFTY")
SCHEDULED_WEEKDAY = 1  # Tuesday


def option_expiries(lines: Iterable[str], symbols: Iterable[str] = SYMBOLS) -> dict[str, list[date]]:
    want = set(symbols)
    out: dict[str, set[date]] = {s: set() for s in want}
    for r in csv.DictReader(lines):
        if r.get("SEM_EXM_EXCH_ID") != "NSE" or r.get("SEM_INSTRUMENT_NAME") != "OPTIDX":
            continue
        underlying = (r.get("SEM_TRADING_SYMBOL") or "").split("-", 1)[0]
        if underlying in want and r.get("SEM_EXPIRY_DATE"):
            out[underlying].add(datetime.fromisoformat(r["SEM_EXPIRY_DATE"].strip()).date())
    return {s: sorted(v) for s, v in out.items()}


def holidays_from_expiries(expiries: dict[str, list[date]]) -> frozenset[date]:
    """Weekdays between a shifted expiry and the Tuesday it replaced are exchange holidays."""
    out: set[date] = set()
    for dates in expiries.values():
        for e in dates:
            scheduled = e + timedelta(days=(SCHEDULED_WEEKDAY - e.weekday()) % 7)
            d = e + timedelta(days=1)
            while d <= scheduled:
                if d.weekday() < 5:
                    out.add(d)
                d += timedelta(days=1)
    return frozenset(out)


def download_option_lines() -> list[str]:
    req = urllib.request.Request(SCRIP_MASTER, headers={"User-Agent": "atis-live"})
    with urllib.request.urlopen(req, timeout=120) as r:
        stream = io.TextIOWrapper(r, encoding="utf-8", newline="")
        header = next(stream)
        return [header] + [ln for ln in stream if ",OPTIDX," in ln]


def load_expiry_holidays(cache_dir: Path, today: date,
                         download: Callable[[], list[str]] = download_option_lines) -> tuple[frozenset[date], str]:
    """Holidays implied by listed expiries, refreshed once a day; falls back to the last cached copy."""
    path = cache_dir / "option_expiries.json"
    cached = json.loads(path.read_text()) if path.exists() else None
    if cached and cached.get("fetched") == today.isoformat():
        expiries = {s: [date.fromisoformat(d) for d in v] for s, v in cached["expiries"].items()}
        return holidays_from_expiries(expiries), "cached today"
    try:
        expiries = option_expiries(download())
        cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"fetched": today.isoformat(),
                                    "expiries": {s: [d.isoformat() for d in v] for s, v in expiries.items()}}))
        return holidays_from_expiries(expiries), "downloaded"
    except Exception as exc:
        if cached:
            expiries = {s: [date.fromisoformat(d) for d in v] for s, v in cached["expiries"].items()}
            return holidays_from_expiries(expiries), f"stale cache from {cached['fetched']} ({exc})"
        return frozenset(), f"unavailable ({exc}); expiries assume no holidays"
