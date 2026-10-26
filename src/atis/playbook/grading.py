"""Grade each signal by confluence, the way a discretionary profile/order-flow trader filters setups.

The rules were fixed before any backtest looked at grades, so the grade is a test of the idea
and not a fit to the data:

  +1  entry or stop sits at a pre-market map level (prior day, single prints, composite balance,
      prior week, naked POC)
  +1 / -1  the setup's structural confirmations all agree / any disagrees
  +1 / -1  real order-flow confirmations all agree / any disagrees (estimated flow scores 0)
  +1 / -1  trade direction with / against multi-day value migration (balance favours condors)
  +1 / -1  initiative (group A) trades on the right / wrong side of session VWAP
  +1 / -1  first target at least 1.5R away / less than 1R away
  -1  round-trip exchange fee above 0.2R (crypto)

A+ is a score of 2 or more, B is 0-1, C is below 0.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Candidate
from .state import SessionState

FLOW_WORDS = ("delta", "absorption", "cvd")
A_PLUS, B, C = "A+", "B", "C"
ORDER = {A_PLUS: 0, B: 1, C: 2}


@dataclass(frozen=True)
class Grade:
    grade: str
    score: int
    factors: tuple[str, ...]


def is_flow(key: str) -> bool:
    return any(w in key.lower() for w in FLOW_WORDS)


def at_least(grade: str, minimum: str) -> bool:
    return ORDER.get(grade, 9) <= ORDER.get(minimum, 9)


def nearest_reference(st: SessionState, prices: list[float]) -> tuple[str, float] | None:
    tol = max(st.ref_tol, 2 * st.row)
    best = None
    for name, level in st.references():
        dist = min(abs(p - level) for p in prices)
        if dist <= tol and (best is None or dist < best[0]):
            best = (dist, name, level)
    return (best[1], best[2]) if best else None


def grade_candidate(st: SessionState, cand: Candidate) -> Grade:
    score, why = 0, []

    def add(points: int, text: str) -> None:
        nonlocal score
        score += points
        why.append(f"{'+' if points > 0 else '-'} {text}")

    sgn = cand.direction.sign
    prices = [cand.entry] + [x for x in (cand.stop, cand.upper_level, cand.lower_level) if x is not None]
    ref = nearest_reference(st, prices)
    if ref:
        add(1, f"at {ref[0]} {ref[1]:g}")

    structure = {k: v for k, v in cand.confirmations.items() if v is not None and not is_flow(k)}
    if structure:
        if all(structure.values()):
            add(1, "structure confirms (" + ", ".join(structure) + ")")
        else:
            add(-1, "structure not confirmed (" + ", ".join(k for k, v in structure.items() if not v) + ")")

    flow = {k: v for k, v in cand.confirmations.items() if v is not None and is_flow(k)}
    if flow and not st.flow_estimated:
        if all(flow.values()):
            add(1, "order flow confirms (" + ", ".join(flow) + ")")
        else:
            add(-1, "order flow disagrees (" + ", ".join(k for k, v in flow.items() if not v) + ")")

    if sgn:
        if st.migration == sgn:
            add(1, "with multi-day value migration")
        elif st.migration == -sgn:
            add(-1, "against multi-day value migration")
    else:
        if st.migration:
            add(-1, "value migrating - balance trades are riskier")
        elif st.balance is not None:
            add(1, "market in multi-day balance")

    vwap = st.vwap
    if sgn and cand.group == "A" and vwap is not None:
        if sgn * (cand.entry - vwap) > 0:
            add(1, f"{'above' if sgn > 0 else 'below'} VWAP {vwap:.0f}")
        else:
            add(-1, f"wrong side of VWAP {vwap:.0f}")

    if sgn and cand.stop is not None and cand.targets:
        risk = abs(cand.entry - cand.stop)
        if risk > 0:
            rr = abs(cand.targets[0].price - cand.entry) / risk
            if rr >= 1.5:
                add(1, f"room to first target {rr:.1f}R")
            elif rr < 1.0:
                add(-1, f"first target only {rr:.1f}R away")
            fee = st.spec.fee_per_side
            if fee and 2 * fee * cand.entry / risk > 0.2:
                add(-1, f"fees {2 * fee * cand.entry / risk:.2f}R")

    grade = A_PLUS if score >= 2 else B if score >= 0 else C
    return Grade(grade, score, tuple(why))
