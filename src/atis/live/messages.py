"""Short, phone-friendly Telegram messages (HTML parse mode)."""

from __future__ import annotations

from datetime import date

from ..playbook.backtest import TradeOutcome
from ..playbook.engine import PremarketPlan, SessionReport
from ..playbook.models import SetupSignal
from .telegram import esc

NOTE = "CANDIDATE setup - paper trade only, no order placed."


def _n(x: float | None, digits: int = 0) -> str:
    return "-" if x is None else f"{x:,.{digits}f}"


def _rs(x: float | None) -> str:
    return "-" if x is None else f"Rs {x:,.0f}"


def signal_message(sig: SetupSignal) -> str:
    p = sig.option_plan
    legs = " / ".join(f"{l.side} {l.strike:g} {l.right}" + (f" @{l.premium:g}" if l.premium is not None else "")
                      for l in p.legs)
    lines = [
        f"<b>{esc(sig.symbol)} {esc(sig.setup_id)} {sig.direction.value.upper()}</b> - {esc(sig.name)}",
        f"Time {sig.ts:%H:%M} | index {_n(sig.entry, 1)}",
        f"<b>Trade:</b> {esc(legs)} | exp {p.expiry:%d-%b}",
        f"Lots {sig.lots} | risk {_rs(sig.risk_total)}"
        + (f" | exit by {sig.exit_by:%H:%M}" if sig.exit_by else f" | {esc(sig.horizon)}"),
    ]
    if sig.stop is not None:
        lines.append(f"Index stop {_n(sig.stop, 1)} ({esc(sig.stop_rule)})")
    else:
        lines.append(f"Exit rule: {esc(sig.stop_rule)}")
    if sig.targets:
        lines.append("Targets: " + ", ".join(f"{_n(t.price, 1)} ({esc(t.label)}, {t.size_pct:g}%)"
                                              for t in sig.targets))
    if sig.grade:
        lines.append(f"<b>Grade {esc(sig.grade)}</b> (score {sig.score:+d}): " + esc("; ".join(sig.grade_factors) or "no factors"))
    checks = [f"{k} {'yes' if v else 'no'}" for k, v in sig.confirmations.items() if v is not None]
    if checks:
        lines.append("Checks: " + esc(", ".join(checks)))
    if sig.lots == 0:
        lines.append("Size rounds to 0 lots at your risk budget - skip or reduce risk.")
    lines.append(f"<i>{NOTE}</i>")
    return "\n".join(lines)


def plan_message(plan: PremarketPlan, day: date) -> str:
    pr = plan.prior
    lines = [f"<b>{esc(plan.symbol)} plan - {day:%a %d %b}</b>"]
    if pr:
        lines.append(f"Prior {pr.date:%d %b}: VA {_n(pr.val)}-{_n(pr.vah)} | POC {_n(pr.poc)} | "
                     f"H {_n(pr.high)} L {_n(pr.low)} | {esc(pr.day_type.value)} day")
    if plan.balance:
        b = plan.balance
        lines.append(f"Balance {len(b.sessions)}d: {_n(b.val)}-{_n(b.vah)}" + (" (quiet)" if b.quiet else ""))
    if plan.htf and plan.htf.week_value:
        w = plan.htf.week_value
        lines.append(f"Prior week VA {_n(w.val)}-{_n(w.vah)} | POC {_n(w.poc)}")
    if plan.htf and plan.htf.naked_pocs:
        lines.append("Naked POCs: " + ", ".join(_n(x) for x in plan.htf.naked_pocs[-4:]))
    lines.append(f"Expiry {plan.nearest_expiry:%a %d %b}" + (" - TODAY" if plan.is_expiry else ""))
    lines += [f"- {esc(w)}" for w in plan.warnings if "CANDIDATE" not in w]
    return "\n".join(lines)


def outcome_text(o: TradeOutcome) -> str:
    if o.r_multiple is not None:
        return f"{o.r_multiple:+.2f}R ({esc(o.exit_reason)})"
    if o.contained is not None:
        return "contained" if o.contained else f"breached ({esc(o.exit_reason)})"
    return esc(o.exit_reason or "not scored")


def eod_message(symbol: str, day: date, report: SessionReport | None, outcomes: list[TradeOutcome]) -> str:
    lines = [f"<b>{esc(symbol)} day summary - {day:%a %d %b}</b>"]
    if report is None:
        lines.append("No bars were processed today.")
        return "\n".join(lines)
    p = report.profile
    ib = f"{_n(report.ib_low)}-{_n(report.ib_high)}" if report.ib_high is not None else "-"
    lines.append(f"{esc(p.day_type.value)} day | open {esc(report.open_type.value if report.open_type else '-')}"
                 f" | IB {ib} | VA {_n(p.val)}-{_n(p.vah)} POC {_n(p.poc)}")
    if not outcomes:
        lines.append("No signals - no trade today.")
    total = 0.0
    for o in outcomes:
        s = o.signal
        lines.append(f"{s.ts:%H:%M} {esc(s.setup_id)} {s.direction.value} -> {outcome_text(o)}")
        total += o.r_multiple or 0.0
    if any(o.r_multiple is not None for o in outcomes):
        lines.append(f"<b>Paper result: {total:+.2f}R</b> (index replay, before costs)")
    if report.skipped:
        lines.append(f"Skipped/blocked: {len(report.skipped)}")
    return "\n".join(lines)
