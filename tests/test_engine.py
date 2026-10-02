from datetime import date, datetime, timedelta

from atis.playbook import DayContext, PlaybookParams, path_session
from atis.playbook.backtest import simulate_directional
from atis.playbook.models import Bar, Direction, OpenType, Structure, Target

from conftest import TODAY, rotation


def signals(report, setup_id):
    return [s for s in report.signals if s.setup_id == setup_id]


def test_a1_open_drive_long(make_engine):
    s = path_session(TODAY, [("09:15", 24120), ("09:30", 24180), ("09:45", 24210), ("10:15", 24240),
                             ("11:00", 24300)])
    rep = make_engine().run_session(s)
    (sig,) = signals(rep, "A1")
    assert sig.direction == Direction.LONG
    assert sig.ts == datetime(2026, 10, 1, 9, 31)
    assert (sig.entry, sig.stop) == (24180, 24115)
    assert sig.option_plan.legs[0].right == "CE"
    assert sig.validation_status == "CANDIDATE"
    assert rep.open_type == OpenType.OPEN_DRIVE


def test_b2_eighty_percent_rule_long(make_engine):
    wps = [("09:15", 23880), ("09:22", 23985)] + rotation("09:32", "11:00", 23975, 23995, step=10)
    rep = make_engine().run_session(path_session(TODAY, wps))
    (sig,) = signals(rep, "B2")
    assert sig.direction == Direction.LONG
    assert sig.ts == datetime(2026, 10, 1, 10, 15)
    assert [t.label for t in sig.targets] == ["prior POC", "opposite VA edge"]
    assert sig.targets[-1].price == 24025
    assert sig.stop == 23950
    assert sig.option_plan.structure == Structure.DEBIT_SPREAD


def test_c1_open_inside_value_iron_condor(make_engine):
    wps = rotation("09:15", "15:30", 23985, 24020, step=10)
    rep = make_engine(params=PlaybookParams(narrow_ib_ratio=0.1)).run_session(path_session(TODAY, wps))
    (sig,) = signals(rep, "C1")
    assert sig.ts == datetime(2026, 10, 1, 10, 15)
    strikes = [(l.side, l.right, l.strike) for l in sig.option_plan.legs]
    assert strikes == [("SELL", "CE", 24150), ("BUY", "CE", 24300), ("SELL", "PE", 23850), ("BUY", "PE", 23700)]
    assert sig.exit_by == datetime(2026, 10, 1, 15, 0)
    assert sig.lots == 0  # 150-pt wings x 65 exceed a 1% risk budget on 5 lakh


def test_c1_skipped_when_ib_is_narrow(make_engine):
    wps = rotation("09:15", "15:30", 23985, 24020, step=10)
    rep = make_engine().run_session(path_session(TODAY, wps))
    assert not signals(rep, "C1")
    assert any(sid == "C1" and "narrow IB" in why for _, sid, why in rep.skipped)


def a3_path(breakout_period_start: str = "10:15"):
    """IB 24000-24060 with value in its upper half; the given 30-min period closes at 24090."""
    t0 = datetime.strptime(breakout_period_start, "%H:%M")
    up, close = ((t0 + timedelta(minutes=m)).strftime("%H:%M") for m in (25, 30))
    return [("09:15", 24000), ("09:20", 24060)] \
        + rotation("09:25", breakout_period_start, 24040, 24060, step=5, start_high=False) \
        + [(up, 24095), (close, 24090)]


def test_a3_ib_breakout_long(make_engine):
    rep = make_engine().run_session(path_session(TODAY, a3_path()))
    (sig,) = signals(rep, "A3")
    assert sig.ts == datetime(2026, 10, 1, 10, 45)
    assert sig.direction == Direction.LONG
    assert sig.stop == 24045
    assert [t.label for t in sig.targets] == ["prior day extreme", "2x IB (Normal Variation target)"]


def test_breakout_beyond_all_targets_gets_a_1r_target(make_engine):
    wps = [("09:15", 24000), ("09:20", 24060)] + rotation("09:25", "10:15", 24040, 24060, step=5, start_high=False) \
        + [("10:40", 24210), ("10:45", 24200)]
    rep = make_engine().run_session(path_session(TODAY, wps))
    (sig,) = signals(rep, "A3")
    assert len(sig.targets) == 1 and sig.targets[0].label.startswith("1R")
    assert sig.targets[0].price == sig.entry + (sig.entry - sig.stop)


def test_b1_failed_gap_short(make_engine):
    wps = [("09:15", 24150), ("09:17", 24190), ("09:19", 24150)] \
        + rotation("09:21", "09:29", 24140, 24150, step=2) + [("09:44", 24080), ("10:30", 24040)]
    rep = make_engine().run_session(path_session(TODAY, wps))
    (sig,) = signals(rep, "B1")
    assert sig.direction == Direction.SHORT
    assert sig.ts == datetime(2026, 10, 1, 9, 45)
    assert sig.stop == 24195
    assert [t.price for t in sig.targets] == [24025, 24005, 23970]
    assert sig.confirmations["low-volume tail at extreme"] is True


def test_a2_open_test_drive_off_prior_vah(make_engine):
    rep = make_engine().run_session(path_session(TODAY, [("09:15", 24050), ("09:20", 24028), ("09:30", 24070),
                                                         ("10:00", 24100)]))
    (sig,) = signals(rep, "A2")
    assert sig.direction == Direction.LONG
    assert sig.stop == 24023
    assert any("prior VAH" in n for n in sig.notes)


def test_b3_failed_ib_extension_fades_back(make_engine):
    wps = rotation("09:15", "10:15", 23985, 24020, step=10, start_high=False) \
        + [("10:20", 24045), ("10:25", 24010)] + rotation("10:30", "11:30", 24008, 24020, step=5)
    rep = make_engine().run_session(path_session(TODAY, wps))
    (sig,) = signals(rep, "B3")
    assert sig.direction == Direction.SHORT
    assert sig.ts == datetime(2026, 10, 1, 10, 45)
    assert sig.stop == 24050
    assert sig.targets[-1].label == "opposite IB extreme"


def test_c2_wide_ib_condor_outside_ib(make_engine):
    wps = [("09:15", 24000), ("09:30", 24150), ("10:00", 23870), ("10:15", 24000)] \
        + rotation("10:20", "15:30", 23950, 24050, step=10)
    rep = make_engine().run_session(path_session(TODAY, wps))
    (sig,) = signals(rep, "C2")
    assert sig.ts == datetime(2026, 10, 1, 10, 45)
    shorts = [(l.right, l.strike) for l in sig.option_plan.legs if l.side == "SELL"]
    assert shorts == [("CE", 24200), ("PE", 23850)]


def test_d1_expiry_pin_iron_fly(make_engine):
    expiry = date(2026, 10, 6)
    engine = make_engine(prior_date=date(2026, 10, 5))
    wps = rotation("09:15", "15:30", 23985, 24015, step=10)
    rep = engine.run_session(path_session(expiry, wps), DayContext(max_oi_strike=24000))
    (sig,) = signals(rep, "D1")
    assert sig.ts == datetime(2026, 10, 6, 12, 15)
    assert sig.option_plan.structure == Structure.IRON_FLY
    assert {l.strike for l in sig.option_plan.legs} == {24000, 24150, 23850}
    assert sig.exit_by == datetime(2026, 10, 6, 14, 30)


def test_event_within_the_hour_blocks_entry(make_engine):
    s = path_session(TODAY, [("09:15", 24120), ("09:30", 24180), ("10:15", 24240)])
    rep = make_engine().run_session(s, DayContext(events=(datetime(2026, 10, 1, 10, 0),)))
    assert not signals(rep, "A1")
    assert any(sid == "A1" and "event" in why for _, sid, why in rep.skipped)


def test_vix_rising_blocks_premium_selling(make_engine):
    wps = rotation("09:15", "15:30", 23985, 24020, step=10)
    engine = make_engine(params=PlaybookParams(narrow_ib_ratio=0.1))
    rep = engine.run_session(path_session(TODAY, wps), DayContext(vix_rising=True))
    assert not signals(rep, "C1")


def test_expiry_afternoon_allows_only_small_a3_and_exits_before_auction(make_engine):
    expiry = date(2026, 10, 6)
    engine = make_engine(prior_date=date(2026, 10, 5))
    rep = engine.run_session(path_session(expiry, a3_path("13:45")))
    assert rep.plan.is_expiry
    (sig,) = signals(rep, "A3")
    assert sig.size_multiplier == 0.5
    assert sig.exit_by == datetime(2026, 10, 6, 15, 5)


def test_iv_prices_legs_and_sizes_from_premium(make_engine):
    s = path_session(TODAY, [("09:15", 24120), ("09:30", 24180), ("10:15", 24240)])
    rep = make_engine().run_session(s, DayContext(iv=0.13))
    (sig,) = signals(rep, "A1")
    leg = sig.option_plan.legs[0]
    assert leg.premium and 0.4 < leg.delta < 0.7
    assert sig.lots >= 1 and sig.est_costs > 0


def test_no_history_means_no_value_setups():
    from atis.playbook import NIFTY, PlaybookEngine
    s = path_session(TODAY, [("09:15", 24120), ("09:30", 24180), ("10:15", 24240)])
    rep = PlaybookEngine(NIFTY).run_session(s)
    assert not rep.signals
    assert any("no prior session" in w for w in rep.plan.warnings)


def test_history_grows_after_each_session(make_engine):
    engine = make_engine()
    engine.run_session(path_session(TODAY, rotation("09:15", "15:30", 23985, 24020, step=10)))
    assert [p.date for p in engine.history] == [date(2026, 9, 30), TODAY]


def _signal(entry, stop, targets):
    from atis.playbook.models import OptionPlan, SetupSignal
    plan = OptionPlan(Structure.LONG_OPTION, (), TODAY, None, None, None)
    return SetupSignal("A3", "x", "A", "NIFTY", datetime(2026, 10, 1, 10, 0), Direction.LONG, entry, stop, "",
                       targets, plan, 1, None, None, "", datetime(2026, 10, 1, 15, 10), "intraday", 1.0, None, {}, [])


def _bars(prices):
    t0 = datetime(2026, 10, 1, 10, 0)
    return [Bar(t0 + timedelta(minutes=i), p, h, l, p, 1) for i, (p, h, l) in enumerate(prices)]


def test_backtest_partial_target_then_breakeven():
    sig = _signal(100, 90, [Target(110, "t1", 50), Target(120, "t2", 50)])
    out = simulate_directional(sig, _bars([(105, 111, 101), (100, 104, 99)]))
    assert out.r_multiple == 0.5 and out.exit_reason == "breakeven"


def test_backtest_stop_first_when_bar_spans_both():
    sig = _signal(100, 90, [Target(110, "t1", 100)])
    out = simulate_directional(sig, _bars([(100, 112, 89)]))
    assert out.r_multiple == -1.0
