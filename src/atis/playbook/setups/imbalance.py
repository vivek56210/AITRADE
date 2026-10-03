"""Group A - imbalance / trend setups (buy ATM or one-strike-ITM options)."""

from __future__ import annotations

from ..models import Candidate, DayType, IBClass, OpenLocation, Structure
from ..orderflow import absorption
from ..state import BarEvent, SessionState
from ..structure import extension
from .common import direction_of, make_targets


def a1_open_drive(st: SessionState, ev: BarEvent) -> Candidate | None:
    if st.prior is None or not st.candles15 or ev.now > st.at(st.times.ib_end):
        return None
    if ev.candle15_closed is not None and ev.candle15_closed.index == 0:
        return None
    c0 = st.candles15[0]
    loc = st.open_loc
    for sgn in (1, -1):
        if loc != (OpenLocation.ABOVE_VALUE if sgn > 0 else OpenLocation.BELOW_VALUE):
            continue
        if sgn * (c0.close - st.open) < st.drive_min:
            continue
        if sgn * (c0.close - (c0.high + c0.low) / 2) < 0:
            continue
        held = st.low >= st.open - st.retrace_tol if sgn > 0 else st.high <= st.open + st.retrace_tol
        if not held:
            continue
        broke = ev.bar.high > c0.high if sgn > 0 else ev.bar.low < c0.low
        if not broke:
            continue
        entry = max(c0.high, ev.bar.open) if sgn > 0 else min(c0.low, ev.bar.open)
        t1 = entry + sgn * st.avg_ib
        t2 = entry + sgn * 2 * st.avg_ib
        nodes = list(st.prior.hvns) + (list(st.balance.hvns) if st.balance else [])
        hvn = sorted((n for n in nodes if sgn * (n - t1) > st.row and sgn * (n - t2) < 0),
                     key=lambda n: sgn * (n - t1))
        cands = [(t1, f"~1x IB extension (re-anchor to IB at {st.times.ib_end:%H:%M})"),
                 (hvn[0], "next HVN") if hvn else (t2, "~2x IB extension")]
        return Candidate(
            "A1", "Open Drive trend day", "A", direction_of(sgn), entry, st.open - sgn * st.row,
            "futures trade back through the opening price, or premium -30-35%",
            make_targets(sgn, entry, cands, st.row), Structure.LONG_OPTION,
            confirmations={"opening candle delta with drive": sgn * c0.delta > 0},
            notes=["trail under each new 30-min low/high while DPOC migrates"],
        )
    return None


def a2_open_test_drive(st: SessionState, ev: BarEvent) -> Candidate | None:
    if st.prior is None or ev.now > st.at(st.times.ib_end) or len(st.bars) < 3:
        return None
    loc = st.open_loc
    refs = st.prior.references()
    for sgn in (1, -1):
        if loc == (OpenLocation.BELOW_VALUE if sgn > 0 else OpenLocation.ABOVE_VALUE):
            continue  # moving away from value then reversing is B1 territory
        test = st.low if sgn > 0 else st.high
        if sgn * (st.open - test) < st.retrace_tol:
            continue
        if sgn * (ev.bar.close - st.open) <= st.row:
            continue
        i_test = st.first_bar_index(lambda b: (b.low if sgn > 0 else b.high) == test)
        if i_test is None or i_test >= len(st.bars) - 1:
            continue
        tested = [name for name, r in refs.items() if abs(test - r) <= st.ref_tol]
        if not tested:
            st.skip("A2", "early test was not at a reference level (mid-value test)")
            continue
        after = st.deltas[i_test:]
        entry = ev.bar.close
        cands = [(st.prior.high if sgn > 0 else st.prior.low, "prior day extreme"),
                 (test + sgn * st.avg_ib, "~opposite side of IB"),
                 (test + sgn * 2 * st.avg_ib, "~2x IB")]
        return Candidate(
            "A2", "Open Test Drive", "A", direction_of(sgn), entry, test - sgn * st.row,
            "futures beyond the test extreme, or premium -30%",
            make_targets(sgn, entry, cands, st.row), Structure.LONG_OPTION,
            confirmations={
                "delta flipped with drive": sgn * sum(after) > 0,
                "absorption at test": absorption(st.bars[:i_test + 4], test, st.ref_tol),
            },
            notes=[f"tested {', '.join(tested)} at {test:g}",
                   "invalid if price returns to the test extreme within 30 minutes"],
        )
    return None


def a3_ib_breakout(st: SessionState, ev: BarEvent) -> Candidate | None:
    p = ev.period_closed
    if p is None or not st.ib_complete or p.index < st.times.ib_periods:
        return None
    if ev.now > st.at(st.times.a3_cutoff):
        return None
    ib = st.ib_range
    for sgn in (1, -1):
        edge = st.ib_high if sgn > 0 else st.ib_low
        if sgn * (p.close - edge) <= 0:
            continue
        if st.ib_class == IBClass.WIDE:
            st.skip("A3", "wide IB - extensions often fail (see C2/B3)")
            return None
        dpoc = st.dpoc()
        if sgn * (dpoc - st.ib_mid) < 0:
            st.skip("A3", "DPOC has not shifted toward the breakout side")
            continue
        levels = list(st.prior.hvns) if st.prior else []
        if st.balance:
            levels += [st.balance.vah, st.balance.val]
        blockers = [x for x in levels if 0 < sgn * (x - p.close) <= st.params.obstacle_distance_ib * ib]
        if blockers:
            st.skip("A3", f"breakout runs into HVN/composite edge at {blockers[0]:g}")
            continue
        wide_ish = st.avg_ib > 0 and ib / st.avg_ib > st.params.debit_spread_ib_ratio
        t1, t2 = edge + sgn * 0.5 * ib, edge + sgn * ib
        cands = [(t1, "1.5x IB"), (t2, "2x IB (Normal Variation target)")]
        if st.prior:
            cands.append((st.prior.high if sgn > 0 else st.prior.low, "prior day extreme"))
        entry = p.close
        return Candidate(
            "A3", "IB breakout / Normal Variation extension", "A", direction_of(sgn), entry,
            edge - sgn * st.params.a3_stop_ib_fraction * ib,
            "back inside the IB by >25% of IB range, or premium -30%",
            make_targets(sgn, entry, cands, st.row),
            Structure.DEBIT_SPREAD if wide_ish else Structure.LONG_OPTION,
            spread_target=t2,
            confirmations={"period delta with breakout": sgn * p.delta > 0, "DPOC on breakout side": True},
            notes=["book half at 1.5x IB"] + (["IB above average - debit spread caps theta/IV"] if wide_ish else []),
        )
    return None


def a4_balance_breakout(st: SessionState, ev: BarEvent) -> Candidate | None:
    b, p = st.balance, ev.period_closed
    if b is None or p is None or ev.now > st.at(st.times.late_entry_cutoff):
        return None
    pending = st.flags.get("a4_break")
    if pending is None:
        for sgn in (1, -1):
            edge = b.vah if sgn > 0 else b.val
            if sgn * (p.close - edge) > 0:
                if not st.flow_estimated and sgn * p.delta < 0:
                    st.skip("A4", "breakout period delta disagrees with direction")
                    return None
                st.flags["a4_break"] = (sgn, p.index)
        return None
    sgn, idx = pending
    edge = b.vah if sgn > 0 else b.val
    if p.index <= idx:
        return None
    if sgn * (p.close - edge) < 0:
        st.flags.pop("a4_break")
        st.skip("A4", "breakout accepted back inside the balance (see B3)")
        return None
    retested = p.low <= edge + st.ref_tol if sgn > 0 else p.high >= edge - st.ref_tol
    if not retested:
        return None
    entry = p.close
    return Candidate(
        "A4", "Balance-area breakout (retest held)", "A", direction_of(sgn), entry,
        edge - sgn * max(st.ref_tol, 2 * st.row),
        "two 30-min periods accepted back inside the composite VA",
        make_targets(sgn, entry, [(edge + sgn * 0.5 * b.height, "half measured move"),
                                  (edge + sgn * b.height, "measured move (balance height)")], st.row),
        Structure.LONG_OPTION,
        confirmations={"retest period delta with breakout": sgn * p.delta > 0},
        notes=[f"composite {b.val:g}-{b.vah:g} over {len(b.sessions)} sessions",
               "positional variant: debit spread / ITM, next-week NIFTY or current-month BANKNIFTY"],
    )


def a5_single_print_continuation(st: SessionState, ev: BarEvent) -> Candidate | None:
    p = ev.period_closed
    if p is None or st.prior is None or ev.now > st.at(st.times.a3_cutoff):
        return None
    zones: list[tuple[int, float, float, str]] = []
    if st.prior.day_type in (DayType.TREND, DayType.DOUBLE_DISTRIBUTION):
        sgn = 1 if st.prior.close > st.prior.open else -1
        zones += [(sgn, lo, hi, "prior session") for lo, hi in st.prior.single_prints]
    if st.ib_complete and st.developing_day_type() in (DayType.TREND, DayType.DOUBLE_DISTRIBUTION):
        up, down = extension(st.high, st.low, st.ib_high, st.ib_low, st.row)
        if up != down:
            sgn = 1 if up else -1
            zones += [(sgn, lo, hi, "today") for lo, hi in st.tpo.single_prints(st.params.single_print_min_rows)]
    for sgn, lo, hi, source in zones:
        top, bottom = (hi, lo) if sgn > 0 else (lo, hi)
        came_from_beyond = sgn * (p.open - top) > 0
        probed = (lo <= p.low <= hi) if sgn > 0 else (lo <= p.high <= hi)
        rejected = sgn * (p.close - top) > 0
        if not (came_from_beyond and probed and rejected):
            continue
        if st.tpo.periods_touching(lo, hi) >= st.params.single_print_repair_periods:
            st.skip("A5", "value building inside the single prints (repair, not support)")
            continue
        entry = p.close
        cands = [(st.high if sgn > 0 else st.low, "retest of session extreme"),
                 (st.prior.high if sgn > 0 else st.prior.low, "prior extreme")]
        if st.ib_complete:
            cands.append(((st.ib_high + st.ib_range) if sgn > 0 else (st.ib_low - st.ib_range), "2x IB"))
        cands.append((entry + sgn * st.avg_ib, "~1x avg IB"))
        return Candidate(
            "A5", "Single-print continuation", "A", direction_of(sgn), entry, bottom - sgn * st.row,
            "single prints filled completely (trade into the lower distribution)",
            make_targets(sgn, entry, cands, st.row), Structure.LONG_OPTION,
            confirmations={"period delta with trend": sgn * p.delta > 0},
            notes=[f"single prints {lo:g}-{hi:g} ({source})"],
        )
    return None
