"""Setup detectors. Each takes (SessionState, BarEvent) and returns a Candidate or None."""

from .balance import c1_open_inside_value, c2_wide_ib_normal_day, c3_multi_day_balance
from .expiry_day import d1_expiry_pin
from .imbalance import (a1_open_drive, a2_open_test_drive, a3_ib_breakout, a4_balance_breakout,
                        a5_single_print_continuation)
from .rejection import b1_failed_gap, b2_eighty_percent_rule, b3_failed_breakout, b4_poor_extreme_repair

DETECTORS = (
    ("B1", b1_failed_gap),
    ("A1", a1_open_drive),
    ("A2", a2_open_test_drive),
    ("B2", b2_eighty_percent_rule),
    ("C1", c1_open_inside_value),
    ("C2", c2_wide_ib_normal_day),
    ("C3", c3_multi_day_balance),
    ("A3", a3_ib_breakout),
    ("A4", a4_balance_breakout),
    ("A5", a5_single_print_continuation),
    ("B3", b3_failed_breakout),
    ("B4", b4_poor_extreme_repair),
    ("D1", d1_expiry_pin),
)

__all__ = ["DETECTORS"]
