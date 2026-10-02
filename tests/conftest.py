from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest

from atis.playbook import NIFTY, PlaybookEngine, PlaybookParams, path_session

PRIOR_DAY = date(2026, 9, 30)
TODAY = date(2026, 10, 1)


def rotation(start: str, end: str, lo: float, hi: float, step: int = 15, start_high: bool = True):
    t = datetime.combine(PRIOR_DAY, time.fromisoformat(start))
    stop = datetime.combine(PRIOR_DAY, time.fromisoformat(end))
    out, up = [], start_high
    while t <= stop:
        out.append((t.strftime("%H:%M"), hi if up else lo))
        up = not up
        t += timedelta(minutes=step)
    return out


def balanced_prior(d: date = PRIOR_DAY):
    """VA 23970-24025, POC 24005, range 23900-24100, IB 200 points."""
    wps = [("09:15", 24000), ("09:30", 24100), ("10:00", 23900), ("10:15", 24000)]
    return path_session(d, wps + rotation("10:30", "15:30", 23960, 24040))


@pytest.fixture
def make_engine():
    def _make(prior_date: date = PRIOR_DAY, params: PlaybookParams = PlaybookParams(), **kw) -> PlaybookEngine:
        engine = PlaybookEngine(NIFTY, params, **kw)
        engine.run([balanced_prior(prior_date)], warmup=1)
        return engine
    return _make
