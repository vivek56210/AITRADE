import gzip
import json
from datetime import date, datetime, timedelta

import pytest

from atis.live.messages import confidence, signal_message
from atis.live.optionquotes import OptionChain, OptionDesk, OptionPrices, option_pnl, quote_signal
from atis.playbook import NIFTY, PlaybookEngine, path_session
from atis.playbook.options import bs_price_delta, implied_vol

from conftest import TODAY, balanced_prior

A1_DAY = [("09:15", 24120), ("09:30", 24180), ("09:45", 24210), ("10:15", 24240), ("11:00", 24300)]
EXP = date(2026, 10, 6)


def master_rows():
    def row(strike, right, key):
        return {"segment": "NSE_FO", "instrument_type": right, "underlying_symbol": "NIFTY", "lot_size": 65,
                "instrument_key": key, "strike_price": strike,
                "expiry": int(datetime(2026, 10, 6, 23, 59, 59).timestamp() * 1000) - 19800 * 1000 + 0}
    rows = [row(k, r, f"NSE_FO|{int(k)}{r}") for k in range(23800, 24700, 50) for r in ("CE", "PE")]
    rows.append({"segment": "NSE_EQ", "instrument_type": "EQ", "underlying_symbol": "X"})
    return rows


def fake_prices(iv=0.12):
    """Option candles priced by Black-Scholes off the session's index bars."""
    session = path_session(TODAY, A1_DAY)

    def get(url):
        key = url.split("/")[-5] if "/intraday/" not in url else url.split("/")[-3]
        key = key.replace("%7C", "|")
        strike, right = float(key.split("|")[1][:-2]), key[-2:]
        candles = []
        for b in session.bars:
            yrs = (datetime.combine(EXP, datetime.min.time()).replace(hour=15, minute=30) - b.ts) / timedelta(days=365)
            px = round(bs_price_delta(b.close, strike, yrs, iv, 0.065, right)[0], 2)
            candles.append([b.ts.isoformat() + "+05:30", px, px, px, px, 100, 1000])
        return {"status": "success", "data": {"candles": candles}}
    return OptionPrices(get=get, historical=True), session


def a1_signal():
    eng = PlaybookEngine(NIFTY)
    eng.run([balanced_prior()], warmup=1)
    rep = eng.run_session(path_session(TODAY, A1_DAY))
    return next(s for s in rep.signals if s.setup_id == "A1"), rep


def test_chain_and_implied_vol():
    chain = OptionChain.from_rows(master_rows())
    assert chain.find("NIFTY", EXP, 24100, "CE") == ("NSE_FO|24100CE", 65)
    assert chain.find("NIFTY", EXP, 24125, "CE") is None
    px = bs_price_delta(24000, 24100, 5 / 365, 0.13, 0.065, "CE")[0]
    assert implied_vol(px, 24000, 24100, 5 / 365, 0.065, "CE") == pytest.approx(0.13, abs=1e-4)
    assert implied_vol(100.0, 24000, 26000, 5 / 365, 0.065, "PE") is None  # below intrinsic (~2000)


def test_chain_cache_and_offline_fallback(tmp_path):
    raw = gzip.compress(json.dumps(master_rows()).encode())
    c1 = OptionChain.load(tmp_path, date(2026, 10, 5), download=lambda: raw)

    def boom():
        raise OSError("offline")
    c2 = OptionChain.load(tmp_path, date(2026, 10, 6), download=boom)
    assert c1.keys == c2.keys and len(c1.keys) == 36


def test_quote_long_option_and_rupee_pnl():
    sig, rep = a1_signal()
    prices, session = fake_prices()
    q = quote_signal(sig, OptionChain.from_rows(master_rows()), prices, datetime(2026, 10, 1, 16, 0))
    leg = q.legs[0]
    assert leg.side == "BUY" and leg.right == "CE" and leg.iv == pytest.approx(0.12, abs=0.005)
    assert q.stop < q.entry < q.targets[0] < q.targets[-1]  # premium levels in the right order
    assert q.lot_size == 65 and q.lots == int(5000 // q.risk_per_lot)
    assert q.risk_per_lot == pytest.approx((q.entry - q.stop) * 65, abs=0.01)
    from atis.playbook.backtest import simulate_directional
    out = simulate_directional(sig, session.bars)
    pnl = option_pnl(q, out.exits, prices, TODAY, datetime(2026, 10, 1, 16, 0))
    assert out.r_multiple > 0 and pnl > 0


def test_quote_unavailable_returns_none_and_desk_never_raises():
    sig, _ = a1_signal()
    empty = OptionChain({})
    prices, _ = fake_prices()
    assert quote_signal(sig, empty, prices, datetime(2026, 10, 1, 16)) is None

    def bad_loader():
        raise OSError("no network")
    logs = []
    desk = OptionDesk(bad_loader, prices, log=logs.append)
    assert desk.quote(sig, datetime(2026, 10, 1, 16)) is None and "unavailable" in logs[0]
    assert desk.pnl(None, [], TODAY, datetime(2026, 10, 1, 16)) is None


def test_confidence_rule():
    sig, _ = a1_signal()
    good = {"NIFTY": {"A1": {"trades": 100, "wins": 55, "total_r": 8.0}}}
    bad = {"NIFTY": {"A1": {"trades": 100, "wins": 40, "total_r": -9.0}}}
    thin = {"NIFTY": {"A1": {"trades": 10, "wins": 6, "total_r": 3.0}}}
    sig.grade = "A+"
    assert confidence(sig, good)[0] == "HIGH" and confidence(sig, bad)[0] == "LOW"
    assert confidence(sig, thin) == ("MEDIUM", "only 10 past trades - too few to judge")
    sig.grade = "B"
    assert confidence(sig, good)[0] == "MEDIUM"
    sig.grade = "C"
    assert confidence(sig, good)[0] == "LOW"


def test_message_with_and_without_option_prices():
    sig, _ = a1_signal()
    prices, _ = fake_prices()
    q = quote_signal(sig, OptionChain.from_rows(master_rows()), prices, datetime(2026, 10, 1, 16, 0))
    text = signal_message(sig, q, {"NIFTY": {"A1": {"trades": 66, "wins": 32, "total_r": 5.5}}})
    for part in ("BUY 24", "OPTION - what you trade", "Buy at <b>₹", "Stop loss ₹", "Target 1 ₹",
                 "Risk:Reward T1 1:", "lots x 65", "INDEX - the levels behind it", "<b>Why:</b>",
                 "Confidence: <b>", "Track record (NIFTY A1, index backtest 2022-26): 66 trades"):
        assert part in text, part
    plain = signal_message(sig, None, {})
    assert "premium not available" in plain and "Risk:Reward T1 1:" in plain and "OPTION - what" not in plain
