"""Group R - responsive trades at pre-market map levels, entered on the reaction, not the clock.

R1: price comes into a map level (prior day VAH/VAL/POC/high/low, single-print edges, composite
balance, prior week, naked POCs) from one side, probes it, and closes back away from it within
`reaction_window_bars`. With real order flow (bars carrying buy/sell volume) the probe must also
show absorption (heavy aggressive volume into the level that made no progress) or a delta
divergence (a new extreme that cumulative delta did not confirm). The stop sits beyond the probe's
extreme; targets are the next map levels at least 1R away. Without real flow (index spot data) the
reaction is structural only and the order-flow checks are reported as n/a.
"""

from __future__ import annotations

from itertools import accumulate

from ..models import Candidate, Structure
from ..state import BarEvent, SessionState
from .common import direction_of, make_targets


def _probe_flow(st: SessionState, i0: int, sgn: int) -> tuple[bool, bool]:
    """(absorption, divergence) for a probe from bar i0 to now; sgn is the trade direction."""
    bars, deltas = st.bars, st.deltas
    probe = bars[i0:]
    session_mean = sum(b.volume for b in bars) / len(bars)
    probe_mean = sum(b.volume for b in probe) / len(probe)
    probe_delta = sum(deltas[i0:])
    # resistance (short, sgn -1): aggressive buying (delta > 0) into the level that got absorbed
    absorption = -sgn * probe_delta > 0 and probe_mean >= st.params.absorption_volume_ratio * session_mean
    cvd = list(accumulate(deltas))
    lookback = range(max(0, i0 - st.params.divergence_lookback_bars), i0)
    if not lookback:
        return absorption, False
    if sgn < 0:
        k = max(range(i0, len(bars)), key=lambda j: bars[j].high)
        prior = max(lookback, key=lambda j: bars[j].high)
        divergence = bars[k].high > bars[prior].high and cvd[k] < cvd[prior]
    else:
        k = min(range(i0, len(bars)), key=lambda j: bars[j].low)
        prior = min(lookback, key=lambda j: bars[j].low)
        divergence = bars[k].low < bars[prior].low and cvd[k] > cvd[prior]
    return absorption, divergence


def r1_level_reaction(st: SessionState, ev: BarEvent) -> Candidate | None:
    p = st.params
    if not p.reaction_setups or st.avg_ib <= 0 or len(st.bars) < 2:
        return None
    if (st.now - st.at(st.times.open)).total_seconds() < p.reaction_start_minutes * 60:
        return None
    mem = st.flags.setdefault("r1", {"armed": {}, "used": set()})
    tol = max(st.ref_tol, 2 * st.row)
    margin = p.reaction_margin_ib * st.avg_ib
    bar, prev = st.bars[-1], st.bars[-2]
    i = len(st.bars) - 1
    for name, level in st.references():
        key = (name, round(level, 2))
        if key in mem["used"]:
            continue
        armed = mem["armed"].get(key)
        if armed is None:
            touched = bar.low <= level + tol and bar.high >= level - tol
            if touched and prev.close < level - tol:
                mem["armed"][key] = (i, -1)  # came up into resistance: fade short
            elif touched and prev.close > level + tol:
                mem["armed"][key] = (i, 1)  # came down into support: fade long
            continue
        i0, sgn = armed
        if i - i0 > p.reaction_window_bars:
            mem["used"].add(key)
            continue
        if sgn * (bar.close - level) < margin:
            continue
        mem["used"].add(key)
        probe = st.bars[i0:]
        extreme = min(b.low for b in probe) if sgn > 0 else max(b.high for b in probe)
        buffer = max(2 * st.row, 0.05 * st.avg_ib)
        stop = extreme - sgn * buffer
        entry = bar.close
        risk = abs(entry - stop)
        if risk <= 0 or risk > p.reaction_max_risk_ib * st.avg_ib:
            st.skip("R1", f"stop beyond the {name} probe is too wide ({risk:.0f} > {p.reaction_max_risk_ib} x avg IB)")
            continue
        confirmations: dict[str, bool | None] = {"rejection close back beyond the level": True}
        if st.flow_estimated:
            confirmations.update({"absorption at level": None, "delta divergence at probe": None})
        else:
            absorption, divergence = _probe_flow(st, i0, sgn)
            confirmations.update({"absorption at level": absorption, "delta divergence at probe": divergence})
            if not (absorption or divergence):
                st.skip("R1", f"{name} {level:g} rejected but order flow showed neither absorption nor divergence")
                continue
        levels = [(lv, nm) for nm, lv in st.references()]
        if st.dpoc() is not None:
            levels.append((st.dpoc(), "developing POC"))
        targets = make_targets(sgn, entry, levels, risk)
        if not targets:
            st.skip("R1", f"{name} {level:g} rejected but no map level at least 1R away")
            continue
        return Candidate(
            "R1", f"Rejection at {name}", "R", direction_of(sgn), entry, stop,
            f"beyond the probe extreme {extreme:g}", targets, Structure.LONG_OPTION,
            confirmations=confirmations,
            notes=[f"{'support' if sgn > 0 else 'resistance'} at {name} {level:g}; probe extreme {extreme:g}",
                   "responsive fade: take the first target quickly if order flow turns"],
        )
    return None
