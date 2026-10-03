"""atis-live: Telegram alerts for the playbook during market hours (alerts only, never orders).

  atis-live run                    wait for the market, run today, send alerts, exit after the close
  atis-live replay --date D        replay a past day through the same code (sends to Telegram)
  atis-live telegram-chat-id       list chats that messaged your bot (to find TELEGRAM_CHAT_ID)
  atis-live telegram-test          send a test message
  atis-live summary [--since D]    paper results recorded so far
  atis-live record                 record NIFTY/BANKNIFTY futures order flow from Dhan's live feed
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

from ..playbook.config import RiskParams
from ..playbook.data import prepare_sessions
from ..playbook.upstox import fetch_index_1m
from .expiries import load_expiry_holidays
from .feed import ReplayFeed, SystemClock, UpstoxIntradayFeed, VirtualClock
from .runner import LiveConfig, LiveRunner, journal_summary, log_stderr
from .telegram import TelegramError, find_chat_ids, notifier_from_env


def _history_loader(cache: Path, days: int):
    def load(symbol: str, day: date):
        bars = fetch_index_1m(symbol, day - timedelta(days=days), day - timedelta(days=1), cache)
        return prepare_sessions(bars)
    return load


def _config(args, label: str) -> LiveConfig:
    risk = replace(RiskParams(), capital=args.capital, risk_per_trade=args.risk_pct / 100)
    return LiveConfig(symbols=tuple(s.strip().upper() for s in args.symbols.split(",") if s.strip()),
                      state_dir=Path(args.state_dir), risk=risk, label=label,
                      disabled_setups=tuple(x.strip().upper() for x in (args.disable or "").split(",") if x.strip()),
                      min_grade=args.min_grade)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="atis-live", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "replay"):
        p = sub.add_parser(name)
        p.add_argument("--symbols", default="NIFTY,BANKNIFTY")
        p.add_argument("--capital", type=float, default=RiskParams.capital)
        p.add_argument("--risk-pct", type=float, default=RiskParams.risk_per_trade * 100)
        p.add_argument("--disable", help="comma-separated setup ids to switch off, e.g. B1,B2,C2")
        p.add_argument("--min-grade", default="B", choices=("A+", "B", "C"),
                       help="lowest signal grade sent to Telegram (all signals are journaled)")
        p.add_argument("--dry-run", action="store_true", help="print messages instead of sending them")
        p.add_argument("--state-dir", default="data/live")
        p.add_argument("--cache", default="data/upstox")
        p.add_argument("--history-days", type=int, default=45)
        if name == "replay":
            p.add_argument("--date", required=True, type=date.fromisoformat)
    r = sub.add_parser("record", help="record front-month futures ticks with buy/sell aggressor volume (Dhan feed)")
    r.add_argument("--symbols", default="NIFTY,BANKNIFTY")
    r.add_argument("--out", default="data/flow", help="where 1-minute flow bars and raw ticks are written")
    r.add_argument("--cache", default="data/dhan", help="Dhan contract registry cache")
    r.add_argument("--dry-run", action="store_true", help="print notices instead of sending them to Telegram")
    sub.add_parser("telegram-test")
    sub.add_parser("telegram-chat-id")
    s = sub.add_parser("summary")
    s.add_argument("--since", type=date.fromisoformat)
    s.add_argument("--state-dir", default="data/live")
    s.add_argument("--label", default="live")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "telegram-chat-id":
            token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
            if not token:
                print("set TELEGRAM_BOT_TOKEN first", file=sys.stderr)
                return 2
            chats = find_chat_ids(token)
            if not chats:
                print("no chats yet: open your bot in Telegram, send it any message, then run this again")
            for cid, name in chats:
                print(f"TELEGRAM_CHAT_ID={cid}   ({name})")
            return 0
        if args.cmd == "telegram-test":
            ok = notifier_from_env().send("<b>ATIS test message</b> - Telegram alerts are working.")
            print("sent" if ok else "failed - see the error above")
            return 0 if ok else 1
        if args.cmd == "summary":
            print(journal_summary(Path(args.state_dir) / f"journal-{args.label}.jsonl", args.since))
            return 0

        if args.cmd == "record":
            from .recorder import record_day
            notifier = notifier_from_env(args.dry_run)
            clock = SystemClock()
            today = clock.now().date()
            if today.weekday() >= 5:
                log_stderr(f"{today} is a weekend - nothing to record")
                return 0
            res = record_day(today, tuple(x.strip().upper() for x in args.symbols.split(",") if x.strip()),
                             Path(args.out), Path(args.cache), notifier.send, log_stderr, clock.now)
            if res is None:
                return 1
            log_stderr(f"recorded {res.ticks} updates: {res.bars} ({res.stopped})")
            return 0
        notifier = notifier_from_env(args.dry_run)
        cache = Path(args.cache)
        history = _history_loader(cache, args.history_days)
        if args.cmd == "run":
            clock = SystemClock()
            today = clock.now().date()
            holidays, source = load_expiry_holidays(Path(args.state_dir), today)
            log_stderr(f"expiry calendar: {source}; holidays inferred from expiries: "
                       f"{', '.join(map(str, sorted(holidays))) or 'none'}")
            runner = LiveRunner(_config(args, "live"), UpstoxIntradayFeed(), notifier, clock, history,
                                holidays, log_stderr)
            if not runner.is_trading_day(today):
                log_stderr(f"{today} is not a trading day - nothing to do")
                return 0
            if clock.now() >= datetime.combine(today, runner.cfg.times.close):
                log_stderr("market already closed for today - nothing to do")
                return 0
            open_at = datetime.combine(today, runner.cfg.times.open) - timedelta(minutes=10)
            if clock.now() < open_at:
                log_stderr(f"waiting until {open_at:%H:%M} to start")
                clock.sleep((open_at - clock.now()).total_seconds())
            runner.run_day(today)
        else:
            day = args.date
            cfg = _config(args, "replay")
            bars = {s: fetch_index_1m(s, day, day, cache) for s in cfg.symbols}
            clock = VirtualClock(datetime.combine(day, cfg.times.open) - timedelta(minutes=5))
            cfg.poll_seconds = 60.0
            holidays, _ = load_expiry_holidays(Path(args.state_dir), day)
            runner = LiveRunner(cfg, ReplayFeed(bars), notifier, clock, history, holidays, log_stderr)
            runner.state_path(day).unlink(missing_ok=True)
            runner.run_day(day)
        return 0
    except TelegramError as exc:
        print(f"telegram: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
