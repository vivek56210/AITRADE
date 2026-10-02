"""Map a setup to an option structure: strikes beyond profile levels, expiry choice, optional BS pricing."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from .config import InstrumentSpec, PlaybookParams
from .expiry import expiry_with_min_sessions, nearest_expiry, sessions_until
from .models import Candidate, Direction, OptionLeg, OptionPlan, Structure


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price_delta(spot: float, strike: float, years: float, iv: float, rate: float,
                   right: str) -> tuple[float, float]:
    if years <= 0 or iv <= 0:
        intrinsic = max(0.0, spot - strike) if right == "CE" else max(0.0, strike - spot)
        delta = (1.0 if spot > strike else 0.0) if right == "CE" else (-1.0 if spot < strike else 0.0)
        return intrinsic, delta
    sq = iv * math.sqrt(years)
    d1 = (math.log(spot / strike) + (rate + 0.5 * iv * iv) * years) / sq
    d2 = d1 - sq
    disc = math.exp(-rate * years)
    if right == "CE":
        return spot * _norm_cdf(d1) - strike * disc * _norm_cdf(d2), _norm_cdf(d1)
    return strike * disc * _norm_cdf(-d2) - spot * _norm_cdf(-d1), _norm_cdf(d1) - 1.0


def strike_above(level: float, step: float) -> float:
    """Nearest strike strictly above a level."""
    k = math.ceil(level / step) * step
    return k + step if k <= level else k


def strike_below(level: float, step: float) -> float:
    k = math.floor(level / step) * step
    return k - step if k >= level else k


def atm_strike(spot: float, step: float) -> float:
    return round(spot / step) * step


@dataclass
class OptionPlanner:
    spec: InstrumentSpec
    params: PlaybookParams
    basis: float = 0.0
    iv: float | None = None
    rate: float = 0.065
    holidays: frozenset[date] = frozenset()

    def spot(self, fut_price: float) -> float:
        return fut_price - self.basis

    def buying_expiry(self, d: date) -> date:
        return expiry_with_min_sessions(self.spec, d, self.params.buy_min_sessions_to_expiry, self.holidays)

    def intraday_expiry(self, d: date) -> date:
        return nearest_expiry(self.spec, d, self.holidays)

    def is_early_series(self, d: date) -> bool:
        return (not self.spec.weekly_expiry and
                sessions_until(d, nearest_expiry(self.spec, d, self.holidays), self.holidays)
                >= self.params.early_series_sessions)

    def _leg(self, side: str, right: str, strike: float, expiry: date, spot: float,
             now: datetime) -> OptionLeg:
        if self.iv is None:
            return OptionLeg(side, right, strike, expiry)
        expiry_dt = datetime.combine(expiry, time(15, 30))
        years = max((expiry_dt - now) / timedelta(days=365), 1e-6)
        premium, delta = bs_price_delta(spot, strike, years, self.iv, self.rate, right)
        return OptionLeg(side, right, strike, expiry, round(delta, 3), round(premium, 2))

    def build(self, cand: Candidate, fut_price: float, now: datetime) -> OptionPlan:
        step = self.spec.strike_step
        spot = self.spot(fut_price)
        d = now.date()
        lot = self.spec.lot_size
        notes: list[str] = []
        s = cand.structure

        if s in (Structure.LONG_OPTION, Structure.DEBIT_SPREAD):
            expiry = cand.expiry_hint or self.buying_expiry(d)
            right = "CE" if cand.direction == Direction.LONG else "PE"
            k = atm_strike(spot, step)
            itm = cand.itm or self.is_early_series(d)
            if itm:
                k = k - step if right == "CE" else k + step
                notes.append("one strike ITM")
            long_leg = self._leg("BUY", right, k, expiry, spot, now)
            if s == Structure.LONG_OPTION:
                prem = long_leg.premium
                return OptionPlan(s, (long_leg,), expiry, prem,
                                  None if prem is None else prem * lot, None, tuple(notes))
            target = self.spot(cand.spread_target) if cand.spread_target is not None else None
            if right == "CE":
                short_k = math.floor(target / step) * step if target else k + 2 * step
                short_k = max(short_k, k + step)
            else:
                short_k = math.ceil(target / step) * step if target else k - 2 * step
                short_k = min(short_k, k - step)
            short_leg = self._leg("SELL", right, short_k, expiry, spot, now)
            width = abs(short_k - k)
            if long_leg.premium is None:
                return OptionPlan(s, (long_leg, short_leg), expiry, None, width * lot, None,
                                  tuple(notes + ["max loss bounded by spread width (no IV supplied)"]))
            debit = long_leg.premium - short_leg.premium
            return OptionPlan(s, (long_leg, short_leg), expiry, round(debit, 2), debit * lot,
                              (width - debit) * lot, tuple(notes))

        expiry = cand.expiry_hint or self.intraday_expiry(d)
        wing = self.spec.credit_wing_width
        legs: list[OptionLeg] = []
        if s == Structure.IRON_FLY:
            k = cand.pin_strike if cand.pin_strike is not None else atm_strike(spot, step)
            legs = [self._leg("SELL", "CE", k, expiry, spot, now), self._leg("BUY", "CE", k + wing, expiry, spot, now),
                    self._leg("SELL", "PE", k, expiry, spot, now), self._leg("BUY", "PE", k - wing, expiry, spot, now)]
        else:
            if s == Structure.IRON_CONDOR or cand.direction == Direction.SHORT:
                kc = strike_above(self.spot(cand.upper_level), step)
                legs += [self._leg("SELL", "CE", kc, expiry, spot, now),
                         self._leg("BUY", "CE", kc + wing, expiry, spot, now)]
            if s == Structure.IRON_CONDOR or cand.direction == Direction.LONG:
                kp = strike_below(self.spot(cand.lower_level), step)
                legs += [self._leg("SELL", "PE", kp, expiry, spot, now),
                         self._leg("BUY", "PE", kp - wing, expiry, spot, now)]
        notes.append(f"short strikes beyond profile levels; verify short delta ~0.15-0.30, wings {wing:g} pts")
        if any(leg.premium is None for leg in legs):
            return OptionPlan(s, tuple(legs), expiry, None, wing * lot, None,
                              tuple(notes + ["max loss bounded by wing width (no IV supplied)"]))
        credit = sum(l.premium for l in legs if l.side == "SELL") - sum(l.premium for l in legs if l.side == "BUY")
        return OptionPlan(s, tuple(legs), expiry, round(-credit, 2), max(wing - credit, 0.0) * lot,
                          credit * lot, tuple(notes))
