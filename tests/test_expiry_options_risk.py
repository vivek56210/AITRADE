import math
from datetime import date, datetime

from atis.playbook import BANKNIFTY, NIFTY, PlaybookParams, RiskParams
from atis.playbook.expiry import expiry_with_min_sessions, is_expiry_day, monthly_expiry, weekly_expiry
from atis.playbook.models import Candidate, Direction, OptionLeg, OptionPlan, Structure
from atis.playbook.options import OptionPlanner, bs_price_delta, strike_above, strike_below
from atis.playbook.risk import lots_for_risk, size_trade


def test_nifty_weekly_tuesday_and_banknifty_last_tuesday():
    assert weekly_expiry(date(2026, 10, 2)) == date(2026, 10, 6)
    assert is_expiry_day(NIFTY, date(2026, 10, 13))
    assert monthly_expiry(date(2026, 10, 2)) == date(2026, 10, 27)
    assert monthly_expiry(date(2026, 10, 28)) == date(2026, 11, 24)
    assert not is_expiry_day(BANKNIFTY, date(2026, 10, 6))
    assert is_expiry_day(BANKNIFTY, date(2026, 10, 27))


def test_holiday_moves_expiry_to_previous_trading_day():
    assert monthly_expiry(date(2026, 10, 2), {date(2026, 10, 27)}) == date(2026, 10, 26)
    assert weekly_expiry(date(2026, 10, 2), {date(2026, 10, 6)}) == date(2026, 10, 5)


def test_option_buyers_skip_to_next_week_inside_three_sessions():
    assert expiry_with_min_sessions(NIFTY, date(2026, 10, 2), 3) == date(2026, 10, 13)
    assert expiry_with_min_sessions(NIFTY, date(2026, 10, 1), 3) == date(2026, 10, 6)


def test_strikes_are_strictly_beyond_levels():
    assert strike_above(24065, 50) == 24100
    assert strike_above(24100, 50) == 24150
    assert strike_below(23935, 50) == 23900
    assert strike_below(23900, 50) == 23850


def test_put_call_parity():
    c, dc = bs_price_delta(24000, 24000, 7 / 365, 0.13, 0.065, "CE")
    p, dp = bs_price_delta(24000, 24000, 7 / 365, 0.13, 0.065, "PE")
    assert abs((c - p) - (24000 - 24000 * math.exp(-0.065 * 7 / 365))) < 1e-6
    assert abs(dc - dp - 1) < 1e-9


def test_iron_condor_strikes_and_wings():
    cand = Candidate("C1", "x", "C", Direction.NEUTRAL, 24000, None, "", [], Structure.IRON_CONDOR,
                     upper_level=24100, lower_level=23900)
    plan = OptionPlanner(NIFTY, PlaybookParams()).build(cand, 24000, datetime(2026, 9, 29, 10, 15))
    assert [(l.side, l.right, l.strike) for l in plan.legs] == [
        ("SELL", "CE", 24150), ("BUY", "CE", 24300), ("SELL", "PE", 23850), ("BUY", "PE", 23700)]
    assert plan.expiry == date(2026, 9, 29)
    assert plan.max_loss_per_lot == 150 * 65


def test_doc_sizing_examples():
    budget = 500_000 * 0.01
    assert lots_for_risk(budget, 35 * 65) == 2
    assert lots_for_risk(budget, 80 * 30) == 2


def test_debit_spread_is_sized_on_the_debit_not_the_level_stop():
    cand = Candidate("B1", "x", "B", Direction.SHORT, 23465, 23525, "", [], Structure.DEBIT_SPREAD)
    legs = (OptionLeg("BUY", "PE", 23450, date(2026, 8, 25), -0.48, 185.71),
            OptionLeg("SELL", "PE", 23400, date(2026, 8, 25), -0.44, 162.46))
    plan = OptionPlan(Structure.DEBIT_SPREAD, legs, legs[0].expiry, 23.25, 23.25 * 65, 26.75 * 65)
    sizing = size_trade(cand, plan, 65, RiskParams())
    assert sizing.lots == 3


def test_long_option_stop_is_whichever_comes_first():
    cand = Candidate("A1", "x", "A", Direction.LONG, 24180, 24120, "", [], Structure.LONG_OPTION)
    leg = OptionLeg("BUY", "CE", 24200, date(2026, 10, 6), delta=0.5, premium=120)
    plan = OptionPlan(Structure.LONG_OPTION, (leg,), leg.expiry, 120, 120 * 65, None)
    sizing = size_trade(cand, plan, 65, RiskParams())
    assert sizing.risk_per_lot == 30 * 65
    assert sizing.lots == 2
