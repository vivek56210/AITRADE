"""Instrument specs and tunable parameters.

Every number here is a proposed default (P) from the volume-profile playbook
(src/docs/10-VOLUME-PROFILE-PLAYBOOK.md) and must be overridable, never hardcoded at call sites.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from datetime import datetime, time, timedelta


@dataclass(frozen=True)
class InstrumentSpec:
    symbol: str
    lot_size: float  # underlying units per lot / contract (NIFTY 65; Delta BTCUSD 0.001 BTC)
    strike_step: float
    row_size: float
    weekly_expiry: bool
    credit_wing_width: float
    expiry_weekday: int = 1  # Tuesday
    trades_weekends: bool = False  # crypto: every calendar day is a session
    daily_expiry: bool = False  # crypto options expire every day
    expiry_day_rules: bool = True  # NSE expiry-day restrictions (gamma, closing auction); off for crypto
    fee_per_side: float = 0.0  # exchange fee incl. tax as a fraction of notional, charged on entry and exit


NIFTY = InstrumentSpec("NIFTY", lot_size=65, strike_step=50.0, row_size=5.0,
                       weekly_expiry=True, credit_wing_width=150.0)
BANKNIFTY = InstrumentSpec("BANKNIFTY", lot_size=30, strike_step=100.0, row_size=10.0,
                           weekly_expiry=False, credit_wing_width=400.0)
INSTRUMENTS = {s.symbol: s for s in (NIFTY, BANKNIFTY)}

# Delta Exchange India perpetuals (USD-quoted). Fee: 0.05% taker + 18% GST, assumed on both entry and exit.
# Option strikes: dailies step 200 (BTC) / 20 (ETH); expiries daily, weekly and monthly on Friday.
DELTA_TAKER_FEE = 0.0005 * 1.18
BTCUSD = InstrumentSpec("BTCUSD", lot_size=0.001, strike_step=200.0, row_size=25.0, weekly_expiry=True,
                        credit_wing_width=1000.0, expiry_weekday=4, trades_weekends=True, daily_expiry=True,
                        expiry_day_rules=False, fee_per_side=DELTA_TAKER_FEE)
ETHUSD = InstrumentSpec("ETHUSD", lot_size=0.01, strike_step=20.0, row_size=1.0, weekly_expiry=True,
                        credit_wing_width=100.0, expiry_weekday=4, trades_weekends=True, daily_expiry=True,
                        expiry_day_rules=False, fee_per_side=DELTA_TAKER_FEE)
CRYPTO_INSTRUMENTS = {s.symbol: s for s in (BTCUSD, ETHUSD)}


@dataclass(frozen=True)
class SessionTimes:
    open: time = time(9, 15)
    close: time = time(15, 30)
    period_minutes: int = 30
    ib_periods: int = 2
    ib_end: time = time(10, 15)
    day_type_check: time = time(11, 30)
    a3_cutoff: time = time(14, 30)
    b2_cutoff: time = time(13, 30)
    late_entry_cutoff: time = time(14, 30)
    last_entry: time = time(14, 45)
    premium_exit: time = time(15, 0)
    flat_by: time = time(15, 10)
    expiry_no_new_shorts_after: time = time(13, 30)
    expiry_buy_only_breakout_after: time = time(14, 0)
    expiry_short_exit: time = time(14, 30)
    expiry_flat_by: time = time(15, 5)
    pin_window_start: time = time(12, 0)
    pin_window_end: time = time(14, 0)

    @property
    def session_minutes(self) -> int:
        return _minutes(self.close) - _minutes(self.open) + (1 if self.close.second else 0)


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def scaled_session_times(open_: time, minutes: int, base: SessionTimes = SessionTimes()) -> SessionTimes:
    """The NSE session clock moved to another open and stretched to another length.

    The opening periods through the end of the IB keep their real durations (a 60-minute IB stays 60
    minutes). Every later checkpoint keeps its relative position between the IB end and the close.
    A session reaching midnight closes at 23:59:59, so it never spans two calendar dates.
    """
    b_open, b_ib = _minutes(base.open), _minutes(base.ib_end) - _minutes(base.open)
    b_len = _minutes(base.close) - b_open
    if not b_ib < minutes <= 24 * 60 - _minutes(open_):
        raise ValueError(f"session of {minutes} min from {open_} must outlast the IB and end by midnight")
    day0 = datetime.combine(datetime.min.date(), open_)

    def move(t: time) -> time:
        off = _minutes(t) - b_open
        new = off if off <= b_ib else b_ib + (off - b_ib) * (minutes - b_ib) / (b_len - b_ib)
        if new >= 24 * 60 - _minutes(open_):
            return time(23, 59, 59)
        return (day0 + timedelta(minutes=round(new))).time()

    return replace(base, **{f.name: move(getattr(base, f.name)) for f in fields(base) if f.type in ("time", time)})


@dataclass(frozen=True)
class PlaybookParams:
    value_area_pct: float = 0.70
    ib_lookback: int = 10
    narrow_ib_ratio: float = 0.60
    wide_ib_ratio: float = 1.30
    debit_spread_ib_ratio: float = 1.00
    retrace_tolerance: float = 0.10
    drive_min_fraction: float = 0.25
    reference_tolerance: float = 0.10
    tail_min_rows: int = 2
    tail_volume_ratio: float = 0.50
    single_print_min_rows: int = 3
    single_print_repair_periods: int = 3
    node_smoothing_rows: int = 2
    node_prominence: float = 0.15
    trend_range_multiple: float = 2.0
    extreme_close_fraction: float = 0.20
    trend_open_fraction: float = 0.25
    double_distribution_min_share: float = 0.25
    double_distribution_min_tpos: int = 3
    non_trend_range_ratio: float = 0.50
    shape_upper: float = 0.60
    shape_lower: float = 0.40
    composite_min_sessions: int = 3
    composite_max_sessions: int = 7
    balance_overlap_min: float = 0.50
    balance_poc_spread_max: float = 0.50
    migration_sessions: int = 3
    va_wide_ratio: float = 1.50
    a3_stop_ib_fraction: float = 0.25
    obstacle_distance_ib: float = 0.50
    b3_outside_volume_max: float = 0.20
    c2_dpoc_drift_max: float = 0.25
    c3_poc_proximity: float = 0.25
    c3_nifty_sessions: tuple[int, int] = (3, 5)
    c3_banknifty_sessions: tuple[int, int] = (8, 16)
    buy_min_sessions_to_expiry: int = 3
    early_series_sessions: int = 10
    event_buffer_minutes: int = 60
    require_dpoc_acceptance: bool = True
    # R1 level + reaction (fixed before testing); off until a backtest supports it
    reaction_setups: bool = False
    reaction_start_minutes: int = 15
    reaction_window_bars: int = 15
    reaction_margin_ib: float = 0.15
    reaction_max_risk_ib: float = 0.60
    absorption_volume_ratio: float = 1.3
    divergence_lookback_bars: int = 60
    # trade management: after the first target, trail the stop under the low (long) / above the high
    # (short) of the last N bars; 0 = off (breakeven only)
    trail_bars: int = 0


@dataclass(frozen=True)
class RiskParams:
    capital: float = 500_000.0
    risk_per_trade: float = 0.01
    daily_loss_limit: float = 0.03
    weekly_loss_limit: float = 0.06
    max_trades_per_day: int = 3
    premium_stop_pct: float = 0.35
    assumed_atm_delta: float = 0.55
    assumed_itm_delta: float = 0.62


@dataclass(frozen=True)
class CostParams:
    brokerage_per_order: float = 20.0
    stt_sell_premium_pct: float = 0.0015
    exchange_txn_pct: float = 0.0003503
    sebi_fee_pct: float = 0.000001
    stamp_buy_pct: float = 0.00003
    gst_pct: float = 0.18
