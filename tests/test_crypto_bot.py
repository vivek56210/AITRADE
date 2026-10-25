import hashlib
import hmac
import json
import math
from datetime import date, datetime, timedelta

import pytest

from atis.crypto import backtest as bt
from atis.crypto.broker import BrokerError, DeltaBroker, PaperBroker, sign
from atis.crypto.config import BotConfig, RiskLimits, TrendParams
from atis.crypto.risk import RiskManager, RiskState
from atis.crypto.runner import CryptoBot
from atis.crypto.signals import (Candle, needs_rebalance, realized_vol, target_exposure, trend_score,
                                 volume_profile)


def trend_closes(n=200, drift=0.004, wiggle=0.02):
    return [100 * math.exp(drift * i + wiggle * math.sin(i)) for i in range(n)]


def test_trend_score_and_target_sign():
    up, down = trend_closes(), trend_closes(drift=-0.004)
    assert trend_score(up, (20, 60, 120)) == 1.0
    assert trend_score(down, (20, 60, 120)) == -1.0
    t = target_exposure(up)
    assert t.exposure > 0 and t.score == 1.0
    assert target_exposure(down).exposure < 0
    assert target_exposure(down, TrendParams(long_only=True)).exposure == 0.0
    assert target_exposure(up[:100]) is None  # not enough history for the 120-day lookback


def test_vol_sizing_and_cap():
    t = target_exposure(trend_closes(wiggle=0.02))
    assert t.exposure == pytest.approx(min(0.20 / t.vol, 1.0))
    calm = target_exposure(trend_closes(wiggle=0.0001))  # tiny vol -> capped at max_exposure
    assert calm.exposure == 1.0
    assert realized_vol([100.0] * 40, 30) == 0.0


def test_rebalance_band():
    assert not needs_rebalance(0.22, 0.20, 0.25)
    assert needs_rebalance(0.30, 0.20, 0.25)
    assert needs_rebalance(-0.1, 0.2, 0.25) and needs_rebalance(0.0, 0.2, 0.25) and needs_rebalance(0.1, 0.0, 0.25)
    assert not needs_rebalance(0.0, 0.0, 0.25)


def test_volume_profile_finds_the_heavy_price():
    t0 = datetime(2026, 1, 1)
    cs = [Candle(t0 + timedelta(hours=i), 100, 101, 99, 100, 1000) for i in range(50)]
    cs += [Candle(t0 + timedelta(hours=50 + i), 110, 111, 109, 110, 10) for i in range(10)]
    p = volume_profile(cs)
    assert 99 <= p.poc <= 101 and p.val <= p.poc <= p.vah


def test_kill_switches_latch_until_resume():
    rm = RiskManager(RiskLimits(), RiskState())
    d = date(2026, 10, 1)
    assert rm.update(10_000, d) is None
    assert "daily loss" in rm.update(9_100, d)
    assert rm.state.halted and rm.update(9_500, d)  # still halted
    rm.resume(9_500)
    assert not rm.state.halted and rm.state.peak_equity == 9_500
    rm2 = RiskManager(RiskLimits(), RiskState())
    for i, e in enumerate([10_000, 9_400, 8_800, 8_200, 7_600, 6_950]):
        r = rm2.update(e, d + timedelta(days=i))
    assert "drawdown" in r


def test_order_checks_reject_stale_and_off_price_and_cap_gross():
    rm = RiskManager(RiskLimits(), RiskState())
    out = {c.symbol: c for c in rm.check_orders(
        10_000, {"BTCUSD": 9_000, "ETHUSD": 9_000, "X": 1_000},
        marks={"BTCUSD": 100.0, "ETHUSD": 103.0, "X": 50.0}, signal_prices={"BTCUSD": 100.5, "ETHUSD": 100.0, "X": 50.0},
        data_age_hours={"BTCUSD": 1, "ETHUSD": 1, "X": 40})}
    assert out["ETHUSD"].reason.startswith("mark")
    assert out["X"].reason.startswith("stale")
    assert out["BTCUSD"].reason is None and out["BTCUSD"].target_notional == pytest.approx(9_000)
    both = rm.check_orders(10_000, {"BTCUSD": 10_000, "ETHUSD": -10_000}, {"BTCUSD": 1.0, "ETHUSD": 1.0},
                           {"BTCUSD": 1.0, "ETHUSD": 1.0}, {"BTCUSD": 1, "ETHUSD": 1})
    assert sum(abs(c.target_notional) for c in both) == pytest.approx(15_000)  # scaled to 1.5x gross


def test_paper_broker_pnl_fees_and_reduce_only(tmp_path):
    px = {"BTCUSD": 100_000.0}
    b = PaperBroker(tmp_path / "p.json", 10_000, price=lambda s: px[s])
    f = b.market_order("BTCUSD", 10, False, "a")  # long 0.01 BTC
    assert f.price > 100_000 and b.positions() == {"BTCUSD": 10}
    b._marks["BTCUSD"] = 110_000
    assert b.equity() == pytest.approx(10_000 - f.fee + 10 * 0.001 * (110_000 - f.price))
    with pytest.raises(BrokerError):
        b.market_order("BTCUSD", 5, True, "bad")  # same side is not a reduction
    g = b.market_order("BTCUSD", -10, True, "close")
    assert b.positions() == {}
    assert b.st.cash == pytest.approx(10_000 - f.fee - g.fee + 10 * 0.001 * (g.price - f.price))
    again = PaperBroker(tmp_path / "p.json", 999, price=lambda s: px[s])  # state survives restart
    assert again.st.cash == pytest.approx(b.st.cash)


def test_delta_signature_and_request_shape():
    expected = hmac.new(b"s", b"POST1700000000/v2/orders{\"a\":1}", hashlib.sha256).hexdigest()
    assert sign("s", "POST", "1700000000", "/v2/orders", "", '{"a":1}') == expected
    seen = []

    def send(req):
        seen.append(req)
        if req.full_url.endswith("/v2/products/BTCUSD"):
            return {"success": True, "result": {"id": 27, "contract_value": "0.001"}}
        return {"success": True, "result": {"id": 9, "average_fill_price": "100000", "paid_commission": "0.6"}}
    d = DeltaBroker("k", "s", send=send)
    f = d.market_order("BTCUSD", -3, True, "x" * 40)
    body = json.loads(seen[-1].data)
    assert body == {"product_id": 27, "size": 3, "side": "sell", "order_type": "market_order",
                    "reduce_only": True, "client_order_id": "x" * 32}
    hdr = {k.lower(): v for k, v in seen[-1].header_items()}
    assert hdr["api-key"] == "k" and len(hdr["signature"]) == 64
    assert f.price == 100_000 and f.contracts == -3


class FakeCandles:
    def __init__(self, closes_by_sym, today):
        self.c, self.today = closes_by_sym, today

    def __call__(self, sym, res, start, end):
        closes = self.c[sym]
        if res == "1d":
            n = len(closes)
            return [Candle(self.today - timedelta(days=n - i), c, c * 1.01, c * 0.99, c, 100) for i, c in enumerate(closes)]
        return [Candle(end - timedelta(hours=h), closes[-1], closes[-1] * 1.005, closes[-1] * 0.995, closes[-1], 10)
                for h in range(1, 480)]


def make_bot(tmp_path, closes, now, sent):
    today = datetime(now.year, now.month, now.day)
    marks = {s: c[-1] for s, c in closes.items()}
    broker = PaperBroker(tmp_path / "paper.json", 10_000, price=lambda s: marks[s])
    return CryptoBot(broker, tmp_path, BotConfig(), notify=lambda m: sent.append(m) or True,
                     candles=FakeCandles(closes, today), now=lambda: now), broker


def test_rebalance_goes_long_btc_short_eth_once_per_day(tmp_path):
    now = datetime(2026, 10, 24, 0, 5)
    closes = {"BTCUSD": trend_closes(drift=0.004), "ETHUSD": trend_closes(drift=-0.004)}
    sent = []
    bot, broker = make_bot(tmp_path, closes, now, sent)
    plans = bot.rebalance()
    pos = broker.positions()
    assert pos["BTCUSD"] > 0 and pos["ETHUSD"] < 0
    for p in plans:  # each coin sized to ~half its vol-targeted exposure
        assert abs(p.target * {"BTCUSD": 0.001, "ETHUSD": 0.01}[p.symbol] * p.mark) == pytest.approx(
            abs(p.target_exposure) * 10_000, rel=0.15)
    assert "LONG" in sent[-1] and "SHORT" in sent[-1] and "volume profile" in sent[-1]
    bot.rebalance()
    assert "already rebalanced" in sent[-1] and broker.positions() == pos
    lines = (tmp_path / "crypto-journal-paper.jsonl").read_text().splitlines()
    assert json.loads(lines[-1])["kind"] == "rebalance"


def test_trend_flip_closes_reduce_only_then_opens(tmp_path):
    now = datetime(2026, 10, 24, 0, 5)
    sent = []
    bot, broker = make_bot(tmp_path, {"BTCUSD": trend_closes(), "ETHUSD": trend_closes()}, now, sent)
    bot.rebalance()
    assert broker.positions()["BTCUSD"] > 0
    later = now + timedelta(days=1)
    bot2, _ = make_bot(tmp_path, {"BTCUSD": trend_closes(drift=-0.004), "ETHUSD": trend_closes()}, later, sent)
    bot2.broker = broker
    broker._marks["BTCUSD"] = trend_closes(drift=-0.004)[-1]
    plans = {p.symbol: p for p in bot2.rebalance()}
    assert broker.positions()["BTCUSD"] < 0
    assert len(plans["BTCUSD"].fills) == 2  # close, then open the other way


def test_watch_flattens_and_halts_on_drawdown(tmp_path):
    now = datetime(2026, 10, 24, 0, 5)
    sent = []
    closes = {"BTCUSD": trend_closes(), "ETHUSD": trend_closes()}
    bot, broker = make_bot(tmp_path, closes, now, sent)
    bot.rebalance()
    broker.st.cash -= 4_000  # simulate a 40% loss
    assert "drawdown" in bot.watch() or "daily loss" in bot.risk.state.halt_reason
    assert broker.positions() == {} and bot.risk.state.halted and "HALTED" in sent[-1]
    bot.risk.state.last_rebalance_day = ""
    assert bot.rebalance() == [] and broker.positions() == {}  # stays flat until resume
    bot.resume()
    assert not bot.risk.state.halted


def test_stale_data_leaves_positions_unchanged(tmp_path):
    now = datetime(2026, 10, 26, 6, 0)  # candles end two days earlier
    sent = []
    closes = {"BTCUSD": trend_closes(), "ETHUSD": trend_closes()}
    bot, broker = make_bot(tmp_path, closes, now, sent)
    bot.candles = FakeCandles(closes, datetime(2026, 10, 24))
    plans = bot.rebalance()
    assert broker.positions() == {} and all("stale" in p.note for p in plans)


def test_backtest_engine_trades_trend_and_pays_costs():
    t0 = datetime(2025, 1, 1)
    hourly = {}
    for sym, drift in (("BTCUSD", 0.0002), ("ETHUSD", -0.0002)):
        hourly[sym] = [Candle(t0 + timedelta(hours=i), p := 100 * math.exp(drift * i + 0.01 * math.sin(i / 7)),
                              p * 1.001, p * 0.999, p, 1.0) for i in range(24 * 200)]
    res = bt.run(hourly, {}, BotConfig())
    assert res.trades > 0 and res.fees > 0
    assert res.equity[-1][1] > 1.0  # long the uptrend, short the downtrend
    s = bt.stats(res.equity)
    assert s["max_drawdown"] <= 0 and s["sharpe"] > 0
