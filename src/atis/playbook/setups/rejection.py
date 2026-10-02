"""Group B - rejection / failed-breakout setups (return to value)."""

from __future__ import annotations

from ..models import Candidate, OpenLocation, Structure
from ..orderflow import delta_divergence
from ..state import BarEvent, SessionState
from ..structure import extension
from .common import direction_of, make_targets, thin_extreme


def b1_failed_gap(st: SessionState, ev: BarEvent) -> Candidate | None:
    c = ev.candle15_closed
    if st.prior is None or c is None or ev.now > st.at(st.times.ib_end):
        return None
    pr = st.prior
    loc = st.open_loc
    if loc == OpenLocation.ABOVE_VALUE:
        sgn, extreme = -1, st.high
    elif loc == OpenLocation.BELOW_VALUE:
        sgn, extreme = 1, st.low
    else:
        return None
    if abs(extreme - st.open) < st.retrace_tol:
        return None
    if sgn * (c.close - st.open) <= 0 or not (pr.low <= c.close <= pr.high):
        return None
    tail = thin_extreme(st, top=sgn < 0)
    div = (not st.flow_estimated) and delta_divergence(st.bars, st.deltas, up=sgn < 0)
    if not (tail or div):
        st.skip("B1", "no tail and no delta divergence at the rejected extreme")
        return None
    if st.migration == -sgn and sgn * (c.close - st.open) < st.retrace_tol:
        st.skip("B1", "gap aligns with multi-day value migration and the rejection is marginal")
        return None
    near_edge, far_edge = (pr.vah, pr.val) if sgn < 0 else (pr.val, pr.vah)
    entry = c.close
    return Candidate(
        "B1", "Open Rejection Reverse / failed gap", "B", direction_of(sgn), entry, extreme - sgn * st.row,
        "beyond the rejected early extreme",
        make_targets(sgn, entry, [(near_edge, "prior VA edge"), (pr.poc, "prior POC"),
                                  (far_edge, "opposite VA edge (only if 80% rule activates)")],
                     st.row, sizes=(50.0, 30.0, 20.0)),
        Structure.DEBIT_SPREAD, spread_target=pr.poc,
        confirmations={"low-volume tail at extreme": tail,
                       "delta divergence": None if st.flow_estimated else div},
        notes=["gap opens carry inflated IV - debit spread preferred over a naked buy"],
    )


def b2_eighty_percent_rule(st: SessionState, ev: BarEvent) -> Candidate | None:
    p = ev.period_closed
    if st.prior is None or p is None or len(st.periods) < 2:
        return None
    loc = st.open_loc
    if loc in (None, OpenLocation.INSIDE_VALUE):
        return None
    va = st.prior.value_area
    if not (va.contains(st.periods[-2].close) and va.contains(p.close)):
        return None
    if ev.now > st.at(st.times.b2_cutoff):
        st.skip("B2", "re-entry into value after 13:30 - not enough time to traverse")
        return None
    if st.avg_va_width and va.width > st.params.va_wide_ratio * st.avg_va_width:
        st.skip("B2", "prior value area unusually wide")
        return None

    def dist(x: float) -> float:
        return max(va.val - x, 0.0, x - va.vah)

    dpoc = st.dpoc()
    accepted = dist(dpoc) == 0 or dist(dpoc) < dist(st.dpoc_at_period[0])
    if st.params.require_dpoc_acceptance and not accepted:
        st.skip("B2", "DPOC not migrating into value - acceptance not visible")
        return None
    sgn = 1 if loc == OpenLocation.BELOW_VALUE else -1
    edge, far = (va.val, va.vah) if sgn > 0 else (va.vah, va.val)
    entry = p.close
    return Candidate(
        "B2", "80% rule (two periods back inside prior value)", "B", direction_of(sgn), entry,
        edge - sgn * max(2 * st.row, st.ref_tol),
        "30-min close back outside value beyond the re-entry edge",
        make_targets(sgn, entry, [(va.poc, "prior POC"), (far, "opposite VA edge")], st.row),
        Structure.DEBIT_SPREAD, spread_target=far,
        confirmations={"DPOC accepted into value": accepted, "period delta toward target": sgn * p.delta > 0},
        notes=["better fill: first pullback toward the re-entry edge that holds inside value"],
    )


def b3_failed_breakout(st: SessionState, ev: BarEvent) -> Candidate | None:
    p = ev.period_closed
    if p is None or not st.ib_complete or p.index < st.times.ib_periods:
        return None
    if ev.now > st.at(st.times.late_entry_cutoff) or not (st.ib_low < p.close < st.ib_high):
        return None
    up, down = extension(st.high, st.low, st.ib_high, st.ib_low, st.row)
    for brk, extended in ((1, up), (-1, down)):
        if not extended:
            continue
        outside = st.vp.volume_above(st.ib_high) if brk > 0 else st.vp.volume_below(st.ib_low)
        dpoc = st.dpoc()
        if outside / st.vp.total > st.params.b3_outside_volume_max or not (st.ib_low <= dpoc <= st.ib_high):
            st.skip("B3", "value was built outside the IB - not a failed auction")
            continue
        if st.migration == brk:
            st.skip("B3", "broader value is migrating in the breakout direction")
            continue
        sgn = -brk
        extreme = st.high if brk > 0 else st.low
        entry = p.close
        return Candidate(
            "B3", "Failed IB breakout (look above/below and fail)", "B", direction_of(sgn), entry,
            extreme + brk * st.row, "beyond the failed breakout extreme",
            make_targets(sgn, entry, [(st.ib_mid, "IB midpoint"),
                                      (st.ib_low if sgn < 0 else st.ib_high, "opposite IB extreme")], st.row),
            Structure.LONG_OPTION,
            confirmations={"low-volume tail at failed extreme": thin_extreme(st, top=brk > 0),
                           "delta divergence": None if st.flow_estimated
                           else delta_divergence(st.bars, st.deltas, up=brk > 0)},
            notes=["alternative: credit spread with short strike beyond the failed extreme"],
        )
    return None


def b4_poor_extreme_repair(st: SessionState, ev: BarEvent) -> Candidate | None:
    p, pr = ev.period_closed, st.prior
    if pr is None or p is None or not st.ib_complete or p.index < st.times.ib_periods:
        return None
    if ev.now > st.at(st.times.late_entry_cutoff):
        return None
    for sgn, poor, level in ((1, pr.poor_high, pr.high), (-1, pr.poor_low, pr.low)):
        if not poor:
            continue
        if (st.high >= level) if sgn > 0 else (st.low <= level):
            continue
        dist = sgn * (level - p.close)
        if not (2 * st.row < dist <= st.avg_ib):
            continue
        if sgn * (p.close - p.open) <= 0 or sgn * p.delta <= 0:
            continue
        entry = p.close
        return Candidate(
            "B4", "Poor high/low repair", "B", direction_of(sgn), entry,
            (p.low - st.row) if sgn > 0 else (p.high + st.row), "behind the initiating period",
            make_targets(sgn, entry, [(level + sgn * 2 * st.row, "just beyond the poor extreme")], st.row),
            Structure.LONG_OPTION, size_multiplier=0.5,
            confirmations={"initiative period delta": True},
            notes=["low priority - do not expect continuation after the repair"],
        )
    return None
