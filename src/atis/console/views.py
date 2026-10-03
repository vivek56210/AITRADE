"""JSON views of sessions shared by the console runtime and the live runner (pure functions)."""

from __future__ import annotations

from datetime import date
from typing import Any

from ..playbook.engine import PlaybookEngine, PremarketPlan, SessionReport
from ..playbook.models import Bar
from ..playbook.report import to_jsonable
from ..playbook.structure import SessionProfile


def histogram(profile) -> list[list[float]]:
    start, vols = profile.dense()
    return [[profile.price(start + i), round(v, 1)] for i, v in enumerate(vols) if v > 0]


def levels_view(p: SessionProfile | None) -> dict[str, Any] | None:
    if p is None:
        return None
    return {"date": p.date.isoformat(), "open": p.open, "high": p.high, "low": p.low, "close": p.close,
            "poc": p.poc, "vah": p.vah, "val": p.val, "ib_high": p.ib_high, "ib_low": p.ib_low,
            "hvns": list(p.hvns), "lvns": list(p.lvns), "single_prints": [list(z) for z in p.single_prints],
            "poor_high": p.poor_high, "poor_low": p.poor_low, "day_type": p.day_type.value,
            "shape": p.shape.value, "open_type": p.open_type.value if p.open_type else None}


def live_today(engine: PlaybookEngine, value_area_pct: float) -> dict[str, Any]:
    st = engine.state
    va = st.vp.value_area(value_area_pct)
    day_type = st.developing_day_type() or engine.day_type_check
    return {"open": st.open, "high": st.high, "low": st.low, "last": st.last,
            "ib_high": st.ib_high, "ib_low": st.ib_low, "ib_class": st.ib_class.value if st.ib_class else None,
            "dpoc": st.dpoc(), "vah": va.vah if va else None, "val": va.val if va else None,
            "open_type": engine.open_type.value if engine.open_type else None,
            "open_location": st.open_loc.value if st.open_loc else None,
            "day_type": day_type.value if day_type else None, "is_expiry": st.is_expiry}


def report_today(rep: SessionReport) -> dict[str, Any]:
    p = rep.profile
    return {"open": p.open, "high": p.high, "low": p.low, "last": p.close,
            "ib_high": rep.ib_high, "ib_low": rep.ib_low, "ib_class": rep.ib_class.value if rep.ib_class else None,
            "dpoc": p.poc, "vah": p.vah, "val": p.val,
            "open_type": rep.open_type.value if rep.open_type else None,
            "open_location": rep.open_location.value if rep.open_location else None,
            "day_type": p.day_type.value, "is_expiry": rep.plan.is_expiry}


def session_payload(*, symbol: str, day: date, live: bool, bars: list[Bar], today: dict[str, Any],
                    plan: PremarketPlan, profile: list[list[float]], signals: list[dict[str, Any]],
                    skips: list[tuple]) -> dict[str, Any]:
    prior = plan.prior
    return {
        "date": day.isoformat(), "live": live, "symbol": symbol,
        "bars": [[b.ts.isoformat(timespec="minutes"), b.open, b.high, b.low, b.close, b.volume] for b in bars],
        "today": today, "prior": levels_view(prior),
        "prior_profile": histogram(prior.profile) if prior else [],
        "profile": profile,
        "balance": to_jsonable(plan.balance) if plan.balance else None,
        "plan": {"scenarios": plan.scenarios, "warnings": plan.warnings, "avg_ib": round(plan.avg_ib, 1),
                 "nearest_expiry": plan.nearest_expiry.isoformat(), "is_expiry": plan.is_expiry},
        "signals": signals,
        "skips": [{"time": t.strftime("%H:%M") if t else None, "setup": sid, "reason": why} for t, sid, why in skips],
    }
