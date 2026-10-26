"""Group D - expiry-day pin trade. The rest of D1 (cut-offs, sizing, CAS exit) is enforced by the engine."""

from __future__ import annotations

from ..models import Candidate, Direction, Structure
from ..state import BarEvent, SessionState


def d1_expiry_pin(st: SessionState, ev: BarEvent) -> Candidate | None:
    p, k = ev.period_closed, st.ctx.max_oi_strike
    if not st.is_expiry or p is None or k is None:
        return None
    if not (st.at(st.times.pin_window_start) < ev.now <= st.at(st.times.pin_window_end)):
        return None
    step = st.spec.strike_step
    spot = p.close - st.ctx.basis
    dpoc_spot = st.dpoc() - st.ctx.basis
    if abs(spot - k) > 0.5 * step or abs(dpoc_spot - k) > step:
        return None
    return Candidate(
        "D1", "Expiry pin at high-OI strike - iron fly", "D", Direction.NEUTRAL, p.close, None,
        "exit if price leaves the pin strike by more than one strike, and by 14:30 regardless",
        [], Structure.IRON_FLY, pin_strike=k, size_multiplier=0.5,
        notes=["small size; +2% ELM applies to short index options on expiry day"],
    )
