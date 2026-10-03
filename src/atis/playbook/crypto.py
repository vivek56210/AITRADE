"""Crypto backtest: the playbook on Delta Exchange India BTC/ETH perpetuals under several session definitions.

Crypto trades 24x7, so "the session" is a choice. Each definition is a clock (time zone), an open and a
length. The playbook's NSE timings are carried over by `scaled_session_times`. Results are in R on
the perpetual, gross and net of Delta's taker fees. Premium-selling setups are scored by containment,
as on NSE; neither is option P&L.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, time, timedelta

from .backtest import BacktestResult, TradeOutcome, backtest
from .config import CRYPTO_INSTRUMENTS, PlaybookParams, RiskParams, SessionTimes, scaled_session_times

# Fee scenario: entries as limit (maker 0.02%) orders, exits as stop/market (taker 0.05%), both + 18% GST.
MAKER_ENTRY_FEE_SHARE = (0.0002 + 0.0005) / (2 * 0.0005)
MAX_FEE_R = 0.20  # cost filter: skip trades whose round-trip fee would exceed 0.2R (stop too tight for the fee)
from .delta import crypto_sessions
from .engine import PlaybookEngine
from .models import Bar


@dataclass(frozen=True)
class SessionDef:
    key: str
    tz: str
    open: time
    minutes: int
    label: str

    @property
    def times(self) -> SessionTimes:
        return scaled_session_times(self.open, self.minutes)


SESSIONS = {
    "utc": SessionDef("utc", "UTC", time(0, 0), 24 * 60, "24-hour day from 00:00 UTC (05:30 IST)"),
    "ny": SessionDef("ny", "America/New_York", time(9, 30), 375,
                     "US cash hours 09:30-15:45 New York (19:00 or 20:00 IST)"),
    "ist": SessionDef("ist", "Asia/Kolkata", time(9, 15), 375, "Indian market hours 09:15-15:30 IST"),
}


@dataclass
class CryptoRun:
    symbol: str
    session: SessionDef
    start: date
    end: date
    result: BacktestResult


def run(symbol: str, session: SessionDef, bars_utc: list[Bar], start: date, end: date,
        warmup_days: int = 10, disabled: Iterable[str] = (), risk: RiskParams = RiskParams(),
        on_progress: Callable[[int, int], None] | None = None) -> CryptoRun:
    spec = CRYPTO_INSTRUMENTS[symbol]
    times = session.times
    sessions = [s for s in crypto_sessions(bars_utc, session.tz, times.open, times.close)
                if start - timedelta(days=warmup_days) <= s.date <= end]
    warmup = max(3, sum(s.date < start for s in sessions))
    engine = PlaybookEngine(spec, PlaybookParams(), times=times, risk=risk, disabled_setups=disabled)
    res = backtest(sessions, spec, engine, warmup=warmup, on_progress=on_progress)
    return CryptoRun(symbol, session, start, end, res)


def _split(start: date, end: date) -> list[tuple[str, date, date]]:
    """Consecutive 12-month windows (the last one may be shorter)."""
    out, s = [], start
    while s <= end:
        try:
            nxt = s.replace(year=s.year + 1)
        except ValueError:  # 29 Feb
            nxt = s.replace(year=s.year + 1, day=28)
        e = min(end, nxt - timedelta(days=1))
        out.append((f"{s:%b %Y}-{e:%b %Y}", s, e))
        s = nxt
    return out


def _agg(outs: list[TradeOutcome]) -> dict:
    d = [o for o in outs if o.r_multiple is not None]
    gross = sum(o.r_multiple for o in d)
    cost = sum(o.cost_r for o in d)
    net = [o.net_r for o in d]
    gains, losses = sum(r for r in net if r > 0), -sum(r for r in net if r < 0)
    cum = peak = dd = 0.0
    for r in net:
        cum += r
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    prem = [o for o in outs if o.contained is not None]
    return {"trades": len(d), "gross_r": round(gross, 2), "cost_r": round(cost, 2), "net_r": round(gross - cost, 2),
            "net_r_maker_entry": round(gross - cost * MAKER_ENTRY_FEE_SHARE, 2),
            "win_rate_net": sum(r > 0 for r in net) / len(net) if net else None,
            "avg_cost_r": cost / len(d) if d else None,
            "profit_factor_net": gains / losses if losses else None, "max_drawdown_net": round(dd, 2),
            "premium": len(prem), "contained": sum(bool(o.contained) for o in prem)}


def summarize(r: CryptoRun) -> dict:
    outs = r.result.outcomes
    years = [(label, _agg([o for o in outs if s <= o.signal.ts.date() <= e])) for label, s, e in _split(r.start, r.end)]
    setups = sorted({o.signal.setup_id for o in outs})
    by_setup = {sid: {"all": _agg([o for o in outs if o.signal.setup_id == sid]),
                      "years": [_agg([o for o in outs if o.signal.setup_id == sid and s <= o.signal.ts.date() <= e])
                                for _, s, e in _split(r.start, r.end)]} for sid in setups}
    return {"symbol": r.symbol, "session": r.session.key, "session_label": r.session.label,
            "start": r.start.isoformat(), "end": r.end.isoformat(), "sessions": len(r.result.reports),
            "signals": len(outs), "total": _agg(outs), "years": years, "by_setup": by_setup,
            "weekdays": _agg([o for o in outs if o.signal.ts.weekday() < 5]),
            "weekends": _agg([o for o in outs if o.signal.ts.weekday() >= 5]),
            # the fee in R is known at entry (it depends only on entry and stop), so this filter has no lookahead
            "fee_filtered": _agg([o for o in outs if o.r_multiple is None or o.cost_r <= MAX_FEE_R])}


def _pf(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.2f}"


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.0%}"


def format_summary(sm: dict) -> str:
    t = sm["total"]
    lines = [f"=== {sm['symbol']} | {sm['session']}: {sm['session_label']} | {sm['start']} -> {sm['end']} ===",
             f"sessions {sm['sessions']}, signals {sm['signals']}, directional {t['trades']}"
             f", premium {t['premium']} (contained {t['contained']})",
             f"gross {t['gross_r']:+.1f}R, fees {-t['cost_r']:.1f}R (avg {t['avg_cost_r'] or 0:.2f}R/trade) -> "
             f"NET {t['net_r']:+.1f}R | win {_pct(t['win_rate_net'])}, PF {_pf(t['profit_factor_net'])}, "
             f"max DD {t['max_drawdown_net']:.1f}R",
             f"with limit-order entries (maker fee in, taker out): NET {t['net_r_maker_entry']:+.1f}R"]
    lines.append("by year (net): " + " | ".join(f"{lbl}: {a['net_r']:+.1f}R ({a['trades']} tr, PF {_pf(a['profit_factor_net'])})"
                                                for lbl, a in sm["years"]))
    f = sm["fee_filtered"]
    lines.append(f"skipping trades whose fee > {MAX_FEE_R:.1f}R: {f['trades']} tr, gross {f['gross_r']:+.1f}R, "
                 f"NET {f['net_r']:+.1f}R, PF {_pf(f['profit_factor_net'])}, max DD {f['max_drawdown_net']:.1f}R")
    lines.append(f"weekdays net {sm['weekdays']['net_r']:+.1f}R ({sm['weekdays']['trades']} tr) | "
                 f"weekends net {sm['weekends']['net_r']:+.1f}R ({sm['weekends']['trades']} tr)")
    lines.append("by setup: trades, win(net), avg fee, net R per year, net total")
    for sid, d in sm["by_setup"].items():
        a = d["all"]
        if a["trades"]:
            yrs = " / ".join(f"{y['net_r']:+.1f}" for y in d["years"])
            lines.append(f"  {sid}: {a['trades']:4d} tr, win {_pct(a['win_rate_net']):>4}, fee {a['avg_cost_r']:.2f}R, "
                         f"years {yrs}, net {a['net_r']:+.1f}R")
        if a["premium"]:
            yrs = " / ".join(f"{y['contained']}/{y['premium']}" for y in d["years"])
            lines.append(f"  {sid}: {a['premium']:4d} premium, contained {a['contained'] / a['premium']:.0%} (years {yrs})")
    return "\n".join(lines)
