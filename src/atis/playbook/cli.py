"""Command line: run the playbook over futures bars (CSV) or a synthetic demo."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import date, datetime

from .backtest import backtest
from .config import INSTRUMENTS, PlaybookParams, RiskParams
from .data import load_csv, synthetic_sessions, to_sessions
from .engine import PlaybookEngine
from .report import format_backtest, format_plan, format_report, to_json
from .state import DayContext


def _dates(raw: str | None) -> frozenset[date]:
    return frozenset(date.fromisoformat(x) for x in raw.split(",")) if raw else frozenset()


def _events(raw: str | None) -> tuple[datetime, ...]:
    return tuple(datetime.fromisoformat(x) for x in raw.split(",")) if raw else ()


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="atis-playbook",
                                 description="Market/volume-profile setups for NIFTY / BANKNIFTY index options")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "demo"):
        p = sub.add_parser(name)
        if name == "run":
            p.add_argument("--csv", required=True, help="current-month futures bars: timestamp,open,high,low,close,volume")
        else:
            p.add_argument("--days", type=int, default=30)
            p.add_argument("--seed", type=int, default=7)
        p.add_argument("--symbol", default="NIFTY", choices=sorted(INSTRUMENTS))
        p.add_argument("--capital", type=float, default=RiskParams.capital)
        p.add_argument("--risk-pct", type=float, default=RiskParams.risk_per_trade * 100)
        p.add_argument("--iv", type=float, help="annualised IV (e.g. 0.13) to price legs and Greeks")
        p.add_argument("--basis", type=float, default=0.0, help="futures minus spot, in points")
        p.add_argument("--holidays", help="comma-separated YYYY-MM-DD exchange holidays")
        p.add_argument("--events", help="comma-separated ISO datetimes of scheduled events")
        p.add_argument("--vix-rising", action="store_true")
        p.add_argument("--max-oi-strike", type=float, help="today's highest-OI strike (expiry pin, D1)")
        p.add_argument("--date", help="only report this session (YYYY-MM-DD); earlier sessions build history")
        p.add_argument("--warmup", type=int, default=3, help="sessions used only to build history")
        p.add_argument("--backtest", action="store_true", help="score signals on the futures replay")
        p.add_argument("--json", action="store_true")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    spec = INSTRUMENTS[args.symbol]
    sessions = (to_sessions(load_csv(args.csv)) if args.cmd == "run"
                else synthetic_sessions(date(2026, 8, 3), args.days, seed=args.seed,
                                        base=24000.0 if spec.symbol == "NIFTY" else 52000.0))
    if args.date:
        target = date.fromisoformat(args.date)
        sessions = [s for s in sessions if s.date <= target]
        warmup = len(sessions) - 1
    else:
        warmup = min(args.warmup, max(len(sessions) - 1, 0))
    if not sessions:
        print("no sessions found", file=sys.stderr)
        return 1
    ctx = DayContext(holidays=_dates(args.holidays), events=_events(args.events), vix_rising=args.vix_rising,
                     basis=args.basis, iv=args.iv, max_oi_strike=args.max_oi_strike)
    contexts = {s.date: ctx for s in sessions}
    risk = replace(RiskParams(), capital=args.capital, risk_per_trade=args.risk_pct / 100)
    engine = PlaybookEngine(spec, PlaybookParams(), risk=risk)
    if args.backtest:
        res = backtest(sessions, spec, engine, contexts, warmup=warmup)
        reports = res.reports
    else:
        res, reports = None, engine.run(sessions, contexts, warmup=warmup)
    if args.json:
        print(to_json({"reports": reports, "backtest": res.stats if res else None}))
        return 0
    for rep in reports:
        print(format_plan(rep.plan))
        print(format_report(rep))
        print()
    if res:
        print(format_backtest(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
