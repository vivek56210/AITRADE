from datetime import date

from atis.playbook import NIFTY, PlaybookEngine, path_session
from atis.playbook.backtest import backtest
from atis.playbook.data import synthetic_sessions
from atis.playbook.trade import RiskLedger

from conftest import TODAY

A1_DAY = [("09:15", 24120), ("09:30", 24180), ("09:45", 24210), ("10:15", 24240), ("11:00", 24300)]


def test_ledger_day_and_week():
    led = RiskLedger()
    led.record(date(2026, 9, 28), -2.0)  # Monday
    led.record(date(2026, 10, 1), -1.5)  # Thursday
    led.record(date(2026, 10, 1), 0.5)
    led.record(date(2026, 10, 5), -1.0)  # next Monday
    assert led.day(date(2026, 10, 1)) == -1.0
    assert led.week(date(2026, 10, 2)) == -3.0
    assert led.week(date(2026, 10, 5)) == -1.0


def test_engine_ledger_matches_backtest_scoring():
    sessions = synthetic_sessions(date(2026, 6, 1), 60, seed=11)
    engine = PlaybookEngine(NIFTY)
    res = backtest(sessions, NIFTY, engine, warmup=3)
    scored = [o for o in res.outcomes if o.r_multiple is not None]
    assert scored
    expected = sum(o.r_multiple * o.signal.size_multiplier for o in scored)
    assert round(sum(engine.ledger.days.values()), 6) == round(expected, 6)


def test_daily_loss_limit_blocks_new_trades(make_engine):
    led = RiskLedger()
    led.record(TODAY, -3.0)
    eng = make_engine(ledger=led)
    rep = eng.run_session(path_session(TODAY, A1_DAY))
    assert not [s for s in rep.signals if s.direction.sign]
    assert any("daily loss limit" in why for _, _, why in rep.skipped)


def test_weekly_loss_limit_blocks_until_next_week(make_engine):
    led = RiskLedger()
    led.record(date(2026, 9, 28), -6.0)  # Monday of TODAY's week
    eng = make_engine(ledger=led)
    rep = eng.run_session(path_session(TODAY, A1_DAY))
    assert not rep.signals and any("weekly loss limit" in why for _, _, why in rep.skipped)
    nxt = date(2026, 10, 5)
    eng2 = make_engine(prior_date=date(2026, 10, 2), ledger=led)
    rep2 = eng2.run_session(path_session(nxt, A1_DAY))
    assert any(s.setup_id == "A1" for s in rep2.signals)


def test_shared_ledger_is_account_wide(make_engine):
    led = RiskLedger()
    led.record(TODAY, -2.5)
    a, b = make_engine(ledger=led), make_engine(ledger=led)
    assert a.ledger is b.ledger
    a.ledger.record(TODAY, -0.5)
    b.start_session(TODAY)
    assert b.loss_limit_hit().startswith("daily loss limit")
