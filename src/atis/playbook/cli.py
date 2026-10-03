"""Command line: fetch index data, run the playbook over bars (CSV / Upstox / Dhan) or a synthetic demo."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

from .backtest import backtest
from .config import INSTRUMENTS, PlaybookParams, RiskParams
from .data import load_csv, prepare_sessions, synthetic_sessions, write_csv
from .dhan import DhanError, Roll, availability, fetch_futures_1m, profile
from .engine import PlaybookEngine
from .report import format_backtest, format_plan, format_report, to_json
from .state import DayContext
from .upstox import fetch_index_1m

DEFAULT_CACHE = Path("data/upstox")
DHAN_CACHE = Path("data/dhan")


def _dates(raw: str | None) -> frozenset[date]:
    return frozenset(date.fromisoformat(x) for x in raw.split(",")) if raw else frozenset()


def _events(raw: str | None) -> tuple[datetime, ...]:
    return tuple(datetime.fromisoformat(x) for x in raw.split(",")) if raw else ()


def _progress(symbol: str):
    return lambda month, n: print(f"  {symbol} {month:%Y-%m}: {n} bars", file=sys.stderr)


def _load(source: str, symbol: str, start: date, end: date, cache: str | None, adjust: bool = True):
    if source == "dhan":
        rolls: list[Roll] = []
        bars = fetch_futures_1m(symbol, start, end, Path(cache or DHAN_CACHE), adjust=adjust,
                                on_month=_progress(symbol), rolls_out=rolls)
        for r in rolls:
            at = f"{r.at:%Y-%m-%d %H:%M}" if r.at else "no overlap"
            print(f"  roll {r.old.trading_symbol} -> {r.new.trading_symbol} ({at}): gap {r.gap:+.2f}"
                  f"{'' if adjust else ' (not adjusted)'}", file=sys.stderr)
        if bars:
            print(f"  {symbol} futures {bars[0].ts:%Y-%m-%d} -> {bars[-1].ts:%Y-%m-%d}", file=sys.stderr)
        return bars
    return fetch_index_1m(symbol, start, end, Path(cache or DEFAULT_CACHE), on_month=_progress(symbol))


def dhan_check(symbol: str, cache: str) -> int:
    """Read-only: token check via GET /v2/profile, then how far back each known contract's 1-minute data goes."""
    p = profile()
    print("profile OK: " + ", ".join(f"{k}={p[k]}" for k in ("tokenValidity", "activeSegment", "dataPlan",
                                                           "dataValidity") if k in p))
    for c, first, last in availability(symbol, Path(cache)):
        span = f"{first} -> {last}" if first else "no intraday data"
        print(f"  {c.trading_symbol:24} id {c.security_id:>7}  expiry {c.expiry}  {span}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="atis-playbook",
                                 description="Market/volume-profile setups for NIFTY / BANKNIFTY index options")
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="download 1-minute bars (Upstox index or Dhan futures) into a CSV")
    f.add_argument("--source", default="upstox", choices=("upstox", "dhan"))
    f.add_argument("--symbol", default="NIFTY", choices=sorted(INSTRUMENTS))
    f.add_argument("--from", dest="start", required=True, type=date.fromisoformat)
    f.add_argument("--to", dest="end", default=date.today(), type=date.fromisoformat)
    f.add_argument("--out", required=True)
    f.add_argument("--cache", help=f"cache folder (default {DEFAULT_CACHE} / {DHAN_CACHE})")
    f.add_argument("--raw-roll", action="store_true", help="dhan: do not back-adjust roll gaps")

    d = sub.add_parser("dhan-check", help="read-only: check the Dhan token and how far back futures data goes")
    d.add_argument("--symbol", default="NIFTY", choices=sorted(INSTRUMENTS))
    d.add_argument("--cache", default=str(DHAN_CACHE))

    for name in ("run", "demo"):
        p = sub.add_parser(name)
        if name == "run":
            src = p.add_mutually_exclusive_group(required=True)
            src.add_argument("--csv", help="bars CSV: timestamp,open,high,low,close,volume (volume 0 = spot)")
            src.add_argument("--upstox", action="store_true", help="download 1-minute index bars from Upstox")
            src.add_argument("--dhan", action="store_true",
                             help="download 1-minute futures bars (volume + OI) from Dhan; needs DHAN_* env vars")
            p.add_argument("--from", dest="start", type=date.fromisoformat, help="with --upstox/--dhan: first date")
            p.add_argument("--to", dest="end", type=date.fromisoformat, default=date.today())
            p.add_argument("--cache", help=f"cache folder (default {DEFAULT_CACHE} / {DHAN_CACHE})")
            p.add_argument("--raw-roll", action="store_true", help="with --dhan: do not back-adjust roll gaps")
        else:
            p.add_argument("--days", type=int, default=30)
            p.add_argument("--seed", type=int, default=7)
        p.add_argument("--symbol", default="NIFTY", choices=sorted(INSTRUMENTS))
        p.add_argument("--capital", type=float, default=RiskParams.capital)
        p.add_argument("--risk-pct", type=float, default=RiskParams.risk_per_trade * 100)
        p.add_argument("--iv", type=float, help="annualised IV (e.g. 0.13) to price legs and Greeks")
        p.add_argument("--basis", type=float, default=0.0, help="futures minus spot, in points")
        p.add_argument("--holidays", help="extra comma-separated YYYY-MM-DD holidays (gaps in data are added)")
        p.add_argument("--events", help="comma-separated ISO datetimes of scheduled events")
        p.add_argument("--vix-rising", action="store_true")
        p.add_argument("--max-oi-strike", type=float, help="today's highest-OI strike (expiry pin, D1)")
        p.add_argument("--date", help="only report this session (YYYY-MM-DD); earlier sessions build history")
        p.add_argument("--warmup", type=int, default=3, help="sessions used only to build history")
        p.add_argument("--backtest", action="store_true", help="score signals on the replay")
        p.add_argument("--details", action="store_true", help="with --backtest: also print every session")
        p.add_argument("--json", action="store_true")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _main(args)
    except DhanError as exc:
        print(f"dhan: {exc}", file=sys.stderr)
        return 1


def _main(args: argparse.Namespace) -> int:
    spec = INSTRUMENTS[args.symbol]

    if args.cmd == "dhan-check":
        return dhan_check(spec.symbol, args.cache)
    if args.cmd == "fetch":
        bars = _load(args.source, spec.symbol, args.start, args.end, args.cache, not args.raw_roll)
        write_csv(args.out, bars)
        print(f"wrote {len(bars)} bars to {args.out}")
        return 0

    holidays: frozenset[date] = frozenset()
    if args.cmd == "demo":
        sessions = synthetic_sessions(date(2026, 8, 3), args.days, seed=args.seed,
                                      base=24000.0 if spec.symbol == "NIFTY" else 52000.0)
    else:
        if args.upstox or args.dhan:
            if not args.start:
                print(f"--{'dhan' if args.dhan else 'upstox'} needs --from YYYY-MM-DD", file=sys.stderr)
                return 2
            bars = _load("dhan" if args.dhan else "upstox", spec.symbol, args.start, args.end, args.cache,
                         not args.raw_roll)
        else:
            bars = load_csv(args.csv)
        sessions, holidays = prepare_sessions(bars)
    if args.date:
        target = date.fromisoformat(args.date)
        sessions = [s for s in sessions if s.date <= target]
        warmup = len(sessions) - 1
    else:
        warmup = min(args.warmup, max(len(sessions) - 1, 0))
    if not sessions:
        print("no sessions found", file=sys.stderr)
        return 1
    ctx = DayContext(holidays=holidays | _dates(args.holidays), events=_events(args.events),
                     vix_rising=args.vix_rising, basis=args.basis, iv=args.iv, max_oi_strike=args.max_oi_strike)
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
    if not res or args.details:
        for rep in reports:
            print(format_plan(rep.plan))
            print(format_report(rep))
            print()
    if res:
        print(f"{spec.symbol} {reports[0].date} -> {reports[-1].date}" if reports else spec.symbol)
        print(format_backtest(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
