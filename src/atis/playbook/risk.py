"""Position sizing and transaction-cost estimates (playbook Part 4 risk rules)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .config import CostParams, RiskParams
from .models import Candidate, OptionPlan, Structure


def lots_for_risk(budget: float, risk_per_lot: float) -> int:
    """Lots = (capital x risk%) / (premium stop in points x lot size)."""
    if risk_per_lot <= 0:
        return 0
    return math.floor(budget / risk_per_lot + 1e-9)


@dataclass(frozen=True)
class Sizing:
    lots: int
    risk_per_lot: float | None
    basis: str


def size_trade(cand: Candidate, plan: OptionPlan, lot_size: int, risk: RiskParams) -> Sizing:
    budget = risk.capital * risk.risk_per_trade
    s = plan.structure
    if s == Structure.LONG_OPTION:
        leg = plan.legs[0]
        move = abs(cand.entry - cand.stop) if cand.stop is not None else None
        if leg.premium is not None:
            stops = [leg.premium * risk.premium_stop_pct]
            if move is not None and leg.delta is not None:
                stops.append(abs(leg.delta) * move)
            stop_pts = min(stops)
            basis = f"premium stop {stop_pts:.1f} pts (min of {risk.premium_stop_pct:.0%} premium and level stop)"
        elif move is not None:
            delta = risk.assumed_itm_delta if "one strike ITM" in plan.notes else risk.assumed_atm_delta
            stop_pts = delta * move
            basis = f"level stop x assumed delta {delta} = {stop_pts:.1f} premium pts (no IV supplied)"
        else:
            return Sizing(0, None, "no stop defined")
        per_lot = stop_pts * lot_size
    else:
        per_lot = plan.max_loss_per_lot or 0.0
        basis = "defined max loss per lot (debit paid, or wing width less credit)"
    lots = math.floor(lots_for_risk(budget, per_lot) * cand.size_multiplier)
    return Sizing(lots, round(per_lot, 2), basis)


def round_trip_costs(plan: OptionPlan, lots: int, lot_size: int, costs: CostParams = CostParams()) -> float | None:
    """Costs of opening and closing every leg at today's premium (an estimate; STT on sell side)."""
    if lots <= 0 or any(l.premium is None for l in plan.legs):
        return None
    total = 0.0
    for leg in plan.legs:
        turnover = leg.premium * lot_size * lots
        brokerage = 2 * costs.brokerage_per_order
        txn = 2 * turnover * costs.exchange_txn_pct
        sebi = 2 * turnover * costs.sebi_fee_pct
        total += (brokerage + txn + sebi + turnover * costs.stt_sell_premium_pct
                  + turnover * costs.stamp_buy_pct + (brokerage + txn + sebi) * costs.gst_pct)
    return round(total, 2)
