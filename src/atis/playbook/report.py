"""Human-readable and JSON rendering of plans, signals, session reports and backtests."""

from __future__ import annotations

import dataclasses
import json
from datetime import date, datetime
from enum import Enum
from typing import Any

from .backtest import BacktestResult
from .engine import PremarketPlan, SessionReport
from .models import SetupSignal
from .profile import VolumeProfile


def to_jsonable(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj):
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)
                if not isinstance(getattr(obj, f.name), VolumeProfile)}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    return obj


def to_json(obj: Any) -> str:
    return json.dumps(to_jsonable(obj), indent=2)


def format_plan(plan: PremarketPlan) -> str:
    lines = [f"=== {plan.symbol} {plan.date} pre-market plan ==="]
    pr = plan.prior
    if pr:
        lines.append(f"Prior {pr.date}: O {pr.open:g} H {pr.high:g} L {pr.low:g} C {pr.close:g} | "
                     f"VA {pr.val:g}-{pr.vah:g} POC {pr.poc:g} | IB {pr.ib_low:g}-{pr.ib_high:g} | "
                     f"{pr.day_type.value} day, {pr.shape.value}-shape, open {pr.open_type.value if pr.open_type else '-'}")
        if pr.hvns or pr.lvns:
            lines.append(f"  HVN {', '.join(f'{x:g}' for x in pr.hvns) or '-'} | "
                         f"LVN {', '.join(f'{x:g}' for x in pr.lvns) or '-'}")
    lines.append(f"Avg IB {plan.avg_ib:.1f} | nearest expiry {plan.nearest_expiry}"
                 + (" (TODAY)" if plan.is_expiry else ""))
    lines += [f"  - {s}" for s in plan.scenarios]
    lines += [f"  ! {w}" for w in plan.warnings]
    return "\n".join(lines)


def format_signal(sig: SetupSignal) -> str:
    plan = sig.option_plan
    legs = " / ".join(f"{l.side} {l.strike:g}{l.right}"
                      + (f" @{l.premium:g} (d {l.delta:+.2f})" if l.premium is not None else "")
                      for l in plan.legs)
    lines = [
        f"[{sig.ts:%H:%M}] {sig.setup_id} {sig.name} -> {sig.direction.value.upper()} "
        f"({sig.validation_status})",
        f"    futures entry {sig.entry:g}" + (f", stop {sig.stop:g}" if sig.stop is not None else "")
        + f" | stop rule: {sig.stop_rule}",
    ]
    if sig.targets:
        lines.append("    targets: " + ", ".join(f"{t.price:g} {t.label} ({t.size_pct:g}%)" for t in sig.targets))
    lines.append(f"    {plan.structure.value} exp {plan.expiry}: {legs}")
    risk = f"{sig.lots} lot(s)"
    if sig.risk_per_lot is not None:
        risk += f", risk/lot Rs {sig.risk_per_lot:,.0f}, total Rs {sig.risk_total:,.0f}"
    if sig.est_costs is not None:
        risk += f", est. round-trip costs Rs {sig.est_costs:,.0f}"
    lines.append(f"    size: {risk} [{sig.sizing_basis}]")
    if sig.exit_by:
        lines.append(f"    exit by {sig.exit_by:%H:%M}")
    conf = ", ".join(f"{k}={'n/a' if v is None else ('yes' if v else 'no')}" for k, v in sig.confirmations.items())
    if conf:
        lines.append(f"    confirmations: {conf}")
    lines += [f"    note: {n}" for n in list(sig.notes) + list(plan.notes)]
    return "\n".join(lines)


def format_report(rep: SessionReport) -> str:
    p = rep.profile
    lines = [
        f"--- {rep.symbol} {rep.date}: open {rep.open_type.value if rep.open_type else '-'} "
        f"({rep.open_location.value if rep.open_location else '-'}), "
        f"IB {rep.ib_low:g}-{rep.ib_high:g} {rep.ib_class.value if rep.ib_class else ''}, "
        f"day type at check {rep.day_type_at_check.value if rep.day_type_at_check else '-'}, "
        f"final {p.day_type.value} ({p.shape.value}-shape) VA {p.val:g}-{p.vah:g} POC {p.poc:g}"
        if rep.ib_high is not None else f"--- {rep.symbol} {rep.date}: session ended before the IB completed",
    ]
    lines += [format_signal(s) for s in rep.signals] or ["    no trade (default action)"]
    for ts, sid, reason in rep.skipped:
        lines.append(f"    skipped {sid}{f' @{ts:%H:%M}' if ts else ''}: {reason}")
    return "\n".join(lines)


def format_backtest(res: BacktestResult) -> str:
    sm = res.summary()
    lines = ["=== Backtest (underlying replay, R multiples before costs; not option P&L) ===",
             f"sessions {sm['sessions']}, signals {sm['signals']}"]
    if sm["directional_trades"]:
        pf = f"{sm['profit_factor']:.2f}" if sm["profit_factor"] is not None else "n/a"
        lines.append(f"directional {sm['directional_trades']}: total {sm['total_r']:+.2f}R, "
                     f"win {sm['win_rate']:.0%}, avg {sm['avg_r']:+.3f}R, PF {pf}, "
                     f"max drawdown {sm['max_drawdown_r']:.2f}R")
    if sm["premium_trades"]:
        lines.append(f"premium {sm['premium_trades']}: contained {sm['premium_contained']}")
    lines.append("by setup:")
    for sid, s in res.stats.items():
        if s.trades:
            lines.append(f"  {sid}: {s.trades} trades, win {s.win_rate:.0%}, avg {s.avg_r:+.2f}R, total {s.total_r:+.2f}R")
        if s.premium_trades:
            lines.append(f"  {sid}: {s.premium_trades} premium trades, contained {s.containment_rate:.0%}")
    if sm["monthly_r"]:
        lines.append("monthly R: " + ", ".join(f"{k} {v:+.1f}" for k, v in sm["monthly_r"].items()))
    return "\n".join(lines)
