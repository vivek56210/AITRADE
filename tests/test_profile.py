from datetime import date

from atis.playbook import NIFTY, TPOProfile, VolumeProfile, analyze_session, path_session
from atis.playbook.models import DayType

from conftest import balanced_prior, rotation


def test_poc_and_value_area_expand_toward_heavier_side():
    vp = VolumeProfile(5)
    for price, vol in [(100, 10), (105, 20), (110, 50), (115, 15), (120, 5)]:
        vp.add(price, price, vol)
    va = vp.value_area(0.70)
    assert (va.poc, va.val, va.vah) == (110, 105, 110)


def test_bar_volume_is_spread_across_its_rows():
    vp = VolumeProfile(5)
    vp.add(100, 114, 300)
    assert [vp.row_volume(p) for p in (100, 105, 110)] == [100, 100, 100]
    assert vp.total == 300


def test_hvn_and_lvn_on_bimodal_profile():
    vp = VolumeProfile(1)
    shape = [1, 2, 5, 9, 5, 2, 1, 2, 5, 9, 5, 2, 1]
    for i, v in enumerate(shape):
        vp.add(100 + i, 100 + i, v)
    hvns, lvns = vp.nodes(smoothing=0, prominence=0.15)
    assert hvns == [103, 109]
    assert lvns == [106]


def test_tpo_poor_extremes_and_single_prints():
    tpo = TPOProfile(1)
    tpo.add(0, 100, 105)
    tpo.add(1, 100, 112)
    tpo.add(2, 104, 112)
    tpo.add(3, 112, 120)
    tpo.add(4, 125, 130)
    tpo.add(5, 125, 130)
    assert tpo.poor_extremes() == (True, True)
    assert tpo.tails(2) == (None, None)
    assert tpo.single_prints(3) == [(113, 124)]


def test_tpo_selling_tail():
    tpo = TPOProfile(1)
    tpo.add(0, 100, 110)
    tpo.add(1, 100, 110)
    tpo.add(2, 108, 116)
    buying, selling = tpo.tails(2)
    assert buying is None and selling == (111, 116)
    assert tpo.poor_extremes() == (True, False)


def test_balanced_prior_session_levels():
    p = analyze_session(balanced_prior(), NIFTY)
    assert (p.val, p.poc, p.vah) == (23970, 24005, 24025)
    assert (p.ib_low, p.ib_high) == (23900, 24100)
    assert p.day_type == DayType.NORMAL
    assert p.selling_tail is not None and p.buying_tail is not None


def test_trend_day_is_not_double_distribution():
    s = path_session(date(2026, 9, 29), [("09:15", 24000), ("15:30", 24400)])
    assert analyze_session(s, NIFTY).day_type == DayType.TREND


def test_double_distribution_day():
    wps = rotation("09:15", "12:15", 23980, 24020, step=5) + [("12:30", 24150)]
    wps += rotation("12:35", "15:30", 24130, 24170, step=5)
    s = path_session(date(2026, 9, 29), wps)
    assert analyze_session(s, NIFTY).day_type == DayType.DOUBLE_DISTRIBUTION


def test_neutral_day_extends_both_sides():
    wps = rotation("09:15", "10:15", 23980, 24020, step=10) + [("11:00", 24080), ("12:30", 23920), ("15:30", 24000)]
    s = path_session(date(2026, 9, 29), wps)
    assert analyze_session(s, NIFTY).day_type == DayType.NEUTRAL
