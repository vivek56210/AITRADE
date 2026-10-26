"""Group C - balance / rotational setups (defined-risk premium selling only)."""

from __future__ import annotations

from datetime import timedelta

from ..expiry import nearest_expiry, sessions_until
from ..models import Candidate, Direction, IBClass, OpenLocation, Structure
from ..state import BarEvent, SessionState

_HEDGED = "always hedged - never naked short options"


def c1_open_inside_value(st: SessionState, ev: BarEvent) -> Candidate | None:
    p, pr = ev.period_closed, st.prior
    if pr is None or p is None or p.index != st.times.ib_periods - 1 or not st.ib_complete:
        return None
    if st.open_loc != OpenLocation.INSIDE_VALUE or not (pr.low <= st.open <= pr.high):
        return None
    if st.ib_high > pr.vah + st.ref_tol or st.ib_low < pr.val - st.ref_tol:
        st.skip("C1", "IB did not form inside the prior value area")
        return None
    if not pr.value_area.contains(p.close):
        return None
    if st.ib_class == IBClass.NARROW:
        st.skip("C1", "narrow IB - breakouts likely (watch A3), not premium selling")
        return None
    return Candidate(
        "C1", "Open inside value - intraday iron condor", "C", Direction.NEUTRAL, p.close, None,
        "exit the threatened side on a 30-min close beyond the IB extreme or if its premium doubles; "
        "exit everything if the day turns into A3",
        [], Structure.IRON_CONDOR,
        upper_level=max(st.ib_high, pr.vah, pr.high), lower_level=min(st.ib_low, pr.val, pr.low),
        notes=["take 50-70% of the credit by 14:30-15:00", _HEDGED,
               "alternative: small ATM fade from VAH/VAL toward the prior POC"],
    )


def c2_wide_ib_normal_day(st: SessionState, ev: BarEvent) -> Candidate | None:
    p = ev.period_closed
    if p is None or not st.ib_complete or p.index != st.times.ib_periods or st.ib_class != IBClass.WIDE:
        return None
    if p.high > st.ib_high or p.low < st.ib_low:
        st.skip("C2", "C period extended the wide IB")
        return None
    pr = st.prior
    if pr is not None and not (pr.low <= st.open <= pr.high):
        drift = abs(st.dpoc() - st.dpoc_at_period[st.times.ib_periods - 1])
        if drift > st.params.c2_dpoc_drift_max * st.ib_range:
            st.skip("C2", "wide IB came from a gap still being repaired (DPOC drifting)")
            return None
    return Candidate(
        "C2", "Wide-IB normal day - iron condor outside IB", "C", Direction.NEUTRAL, p.close, None,
        "30-min close outside the IB on either side: close that side and consider A3",
        [], Structure.IRON_CONDOR, upper_level=st.ib_high, lower_level=st.ib_low,
        notes=["target 50-60% of credit or time exit by 15:00", _HEDGED],
    )


def c3_multi_day_balance(st: SessionState, ev: BarEvent) -> Candidate | None:
    p, b = ev.period_closed, st.balance
    if b is None or p is None or p.index != st.times.ib_periods - 1 or not st.ib_complete:
        return None
    if not b.quiet:
        st.skip("C3", "balance not quiet (POC drifting or range expanding)")
        return None
    if len(b.sessions) >= st.params.composite_max_sessions:
        st.skip("C3", "balance is old and compressed - expect a breakout (A4)")
        return None
    if abs(p.close - b.poc) > st.params.c3_poc_proximity * b.height:
        return None
    if st.ib_high > b.vah or st.ib_low < b.val:
        st.skip("C3", "IB traded outside composite value")
        return None
    lo, hi = st.params.c3_nifty_sessions if st.spec.weekly_expiry else st.params.c3_banknifty_sessions
    hol = st.ctx.holidays
    expiry = nearest_expiry(st.spec, st.date, hol)
    wk = st.spec.trades_weekends
    while sessions_until(st.date, expiry, hol, wk) < lo:
        expiry = nearest_expiry(st.spec, expiry + timedelta(days=1), hol)
    if sessions_until(st.date, expiry, hol, wk) > hi:
        st.skip("C3", f"no expiry {lo}-{hi} sessions out")
        return None
    if any(st.now <= e and e.date() <= expiry for e in st.ctx.events):
        st.skip("C3", "scheduled event inside the holding period")
        return None
    return Candidate(
        "C3", "Multi-day balance - positional iron condor", "C", Direction.NEUTRAL, p.close, None,
        "close the threatened side on a daily close outside the composite VA or short strike ~0.40 delta",
        [], Structure.IRON_CONDOR, upper_level=b.high, lower_level=b.low, horizon="positional",
        expiry_hint=expiry,
        notes=[f"composite {b.val:g}-{b.vah:g} (POC {b.poc:g}) over {len(b.sessions)} sessions",
               "target 50% of max credit or exit the day before expiry", _HEDGED],
    )
