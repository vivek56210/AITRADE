"""Short, phone-friendly Telegram messages (HTML parse mode)."""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from ..playbook.backtest import TradeOutcome
from ..playbook.engine import PremarketPlan, SessionReport
from ..playbook.models import SetupSignal
from .telegram import esc

NOTE = "CANDIDATE setup - paper trade only, no order placed."


def _n(x: float | None, digits: int = 0) -> str:
    return "-" if x is None else f"{x:,.{digits}f}"


CONFIDENCE_RULE = ("confidence = signal grade + this setup's 2022-26 track record on this index; "
                   "it is not a win probability")
VIEW = {"long": ("\U0001F7E2", "bullish"), "short": ("\U0001F534", "bearish"), "neutral": ("\U0001F7E1", "range-bound")}


def _rs(x: float | None) -> str:
    return "-" if x is None else f"\u20b9{x:,.0f}"


def _signed(x: float, digits: int = 2) -> str:
    return f"{'+' if x >= 0 else '-'}\u20b9{abs(x):,.{digits}f}"


def _p(x: float | None) -> str:
    return "-" if x is None else f"\u20b9{x:,.2f}"


@lru_cache(maxsize=1)
def setup_history() -> dict:
    path = Path(__file__).with_name("setup_history.json")
    return json.loads(path.read_text()) if path.exists() else {}


def track_record(symbol: str, setup_id: str, history: dict | None = None) -> dict | None:
    return (history if history is not None else setup_history()).get(symbol, {}).get(setup_id)


def confidence(sig: SetupSignal, history: dict | None = None) -> tuple[str, str]:
    """(HIGH / MEDIUM / LOW, one-line track record)."""
    rec = track_record(sig.symbol, sig.setup_id, history)
    good = bad = False
    note = "no track record yet"
    if rec and rec.get("trades", 0) >= 30:
        avg = rec["total_r"] / rec["trades"]
        good, bad = avg >= 0.03, avg <= -0.03
        note = f"{rec['trades']} trades, {rec['wins'] / rec['trades']:.0%} wins, {avg:+.2f}R per trade"
    elif rec and rec.get("premium", 0) >= 20:
        rate = rec["contained"] / rec["premium"]
        good, bad = rate >= 0.70, rate < 0.50
        note = f"{rec['premium']} trades, range held {rate:.0%} of the time"
    elif rec:
        note = f"only {rec.get('trades', 0) or rec.get('premium', 0)} past trades - too few to judge"
    if sig.grade == "C" or bad:
        level = "LOW"
    elif sig.grade == "A+" and good:
        level = "HIGH"
    else:
        level = "MEDIUM"
    return level, note


def reasoning(sig: SetupSignal) -> str:
    from ..console.catalog import SETUPS
    info = next((x for x in SETUPS if x["id"] == sig.setup_id), None)
    if info is None:
        return sig.name
    return f"{info['context']} Trigger: {info['trigger']}"


def _rr(entry: float, stop: float | None, target: float, credit: bool = False) -> str:
    if stop is None:
        return "-"
    risk = abs(stop - entry)
    reward = abs(entry - target)
    return f"1:{reward / risk:.1f}" if risk > 0 else "-"


def signal_message(sig: SetupSignal, quote=None, history: dict | None = None) -> str:
    """The Telegram alert: what to trade in option terms, the index levels behind it, R:R, confidence, why."""
    emoji, view = VIEW[sig.direction.value]
    plan = sig.option_plan
    level, record = confidence(sig, history)
    exit_txt = f"exit by {sig.exit_by:%H:%M}" if sig.exit_by else esc(sig.horizon)
    if quote is not None and quote.credit:
        title = f"SELL {esc(plan.structure.value.replace('-', ' '))}"
    elif plan.legs:
        main = plan.legs[0]
        title = f"{main.side} {main.strike:g} {main.right}" + (
            f" / {plan.legs[1].side} {plan.legs[1].strike:g} {plan.legs[1].right}" if len(plan.legs) > 1 else "")
    else:
        title = sig.direction.value.upper()
    lines = [f"{emoji} <b>{esc(sig.symbol)} - {esc(title)}</b> ({plan.expiry:%d %b} expiry) - {view} view",
             f"{esc(sig.setup_id)} {esc(sig.name)} | {sig.ts:%H:%M} | Confidence: <b>{level}</b>", ""]

    if quote is not None:
        q = quote
        lines.append("<b>OPTION - what you trade</b>")
        if len(q.legs) > 1:
            lines.append("Legs: " + " | ".join(f"{l.side} {l.strike:g} {l.right} @ {_p(l.premium)}" for l in q.legs))
        if q.credit:
            lines.append(f"Sell for a net credit of <b>{_p(q.entry)}</b>")
            lines.append(f"Stop loss: buy back at {_p(q.stop)} (credit doubles)")
            for i, t in enumerate(q.targets, 1):
                lines.append(f"Target {i}: buy back at {_p(t)} (keep {_p(q.entry - t)})")
            rr = " | ".join(f"T{i} {_rr(q.entry, q.stop, t)}" for i, t in enumerate(q.targets, 1))
        else:
            verb = "Pay" if len(q.legs) > 1 else "Buy at"
            lines.append(f"{verb} <b>{_p(q.entry)}</b>" + (" net debit" if len(q.legs) > 1 else ""))
            lines.append(f"Stop loss {_p(q.stop)} ({_signed(q.stop - q.entry)})")
            for i, (t, tg) in enumerate(zip(q.targets, sig.targets), 1):
                lines.append(f"Target {i} {_p(t)} ({_signed(t - q.entry)}) - book {tg.size_pct:g}%")
            rr = " | ".join(f"T{i} {_rr(q.entry, q.stop, t)}" for i, t in enumerate(q.targets, 1))
        lines.append(f"Risk:Reward {rr}")
        if q.lots:
            lines.append(f"Size {q.lots} lot{'s' if q.lots > 1 else ''} x {q.lot_size} = {q.lots * q.lot_size} qty | "
                         f"max risk {_rs(q.lots * q.risk_per_lot)} | {exit_txt}")
        else:
            lines.append(f"Size 0 lots: 1 lot risks {_rs(q.risk_per_lot)}, more than your per-trade budget - skip | {exit_txt}")
        lines.append("")

    lines.append(f"<b>{esc(sig.symbol)} INDEX - the levels behind it</b>")
    if sig.stop is not None and sig.targets:
        lines.append(f"Entry {_n(sig.entry, 1)} | SL {_n(sig.stop, 1)} | "
                     + " | ".join(f"T{i} {_n(t.price, 1)}" for i, t in enumerate(sig.targets, 1)))
        if quote is None:
            lines.append("Risk:Reward " + " | ".join(f"T{i} {_rr(sig.entry, sig.stop, t.price)}"
                                                    for i, t in enumerate(sig.targets, 1)))
            legs = " / ".join(f"{l.side} {l.strike:g} {l.right}" for l in plan.legs)
            lines.append(f"Option: {esc(legs)} - premium not available, check the live price | {exit_txt}")
    else:
        shorts = [l for l in plan.legs if l.side == "SELL"]
        if shorts:
            lines.append("Profit zone: index stays between " + " and ".join(f"{l.strike:g}" for l in sorted(shorts, key=lambda l: l.strike))
                         + f" until {exit_txt.replace('exit by ', '')}")
        lines.append(f"Exit rule: {esc(sig.stop_rule)}")
    lines.append("")
    lines.append(f"<b>Why:</b> {esc(reasoning(sig))}")
    lines.append(f"<b>Confidence {level}:</b> grade {esc(sig.grade or '-')} ({sig.score:+d}) - "
                 + esc("; ".join(sig.grade_factors) or "no extra factors"))
    lines.append(f"Track record ({esc(sig.symbol)} {esc(sig.setup_id)}, index backtest 2022-26): {esc(record)}")
    lines.append(f"<i>{NOTE} Index levels are NSE spot; option prices are live premiums at the signal minute.</i>")
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


def eod_message(symbol: str, day: date, report: SessionReport | None, outcomes: list[TradeOutcome],
                pnls: dict[int, float | None] | None = None, one_lot: set[int] | frozenset = frozenset()) -> str:
    """Day summary; `pnls` maps an outcome's index to its option P&L in rupees (when priced); indices in
    `one_lot` sized to zero lots, so their P&L is shown for one lot."""
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
    total, rupees, priced = 0.0, 0.0, 0
    for i, o in enumerate(outcomes):
        s = o.signal
        pnl = (pnls or {}).get(i)
        extra = (f" | option {_signed(pnl, 0)}" + (" (1 lot; size was 0)" if i in one_lot else "")) if pnl is not None else ""
        lines.append(f"{s.ts:%H:%M} {esc(s.setup_id)} {s.direction.value} -> {outcome_text(o)}{extra}")
        total += o.r_multiple or 0.0
        if pnl is not None and i not in one_lot:
            rupees += pnl
            priced += 1
    if any(o.r_multiple is not None for o in outcomes):
        lines.append(f"<b>Paper result: {total:+.2f}R</b> (index levels, before costs)")
    if priced:
        lines.append(f"<b>Option P&amp;L: {_signed(rupees, 0)}</b> ({priced} trade{'s' if priced > 1 else ''}, "
                     f"real premiums at each exit, before brokerage and taxes)")
    if report.skipped:
        lines.append(f"Skipped/blocked: {len(report.skipped)}")
    return "\n".join(lines)
