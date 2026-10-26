from __future__ import annotations

from ..models import Direction, Target
from ..profile import to_row
from ..state import SessionState


def direction_of(sgn: int) -> Direction:
    return Direction.LONG if sgn > 0 else Direction.SHORT


def make_targets(sgn: int, entry: float, candidates: list[tuple[float, str]], min_dist: float,
                 sizes: tuple[float, ...] = (50.0, 50.0)) -> list[Target]:
    """Nearest distinct levels beyond entry in the trade direction, sized per `sizes`."""
    beyond = sorted((c for c in candidates if sgn * (c[0] - entry) >= min_dist),
                    key=lambda c: sgn * (c[0] - entry))
    picked: list[tuple[float, str]] = []
    for price, label in beyond:
        if all(abs(price - p) >= min_dist for p, _ in picked):
            picked.append((price, label))
        if len(picked) == len(sizes):
            break
    if not picked:
        return []
    used = sizes[:len(picked)]
    scale = 100.0 / sum(used)
    return [Target(round(p, 2), label, round(s * scale, 1)) for (p, label), s in zip(picked, used)]


def thin_extreme(st: SessionState, top: bool) -> bool:
    """Low-volume tail: the extreme rows traded well below the session's average row volume."""
    n = st.params.tail_min_rows
    mean = st.vp.mean_row_volume()
    if mean <= 0:
        return False
    edge = to_row(st.high if top else st.low, st.row)
    rows = [edge - i if top else edge + i for i in range(n)]
    vol = sum(st.vp.row_volume(r * st.row) for r in rows) / n
    return vol <= st.params.tail_volume_ratio * mean
