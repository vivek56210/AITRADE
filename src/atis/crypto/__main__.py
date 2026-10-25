"""atis-crypto: backtest and run the BTC/ETH trend bot.

  atis-crypto backtest [--sync]          8+ years on Binance history with Delta India costs
  atis-crypto rebalance                  daily job (00:05 UTC); paper trading by default
  atis-crypto watch                      hourly kill-switch check
  atis-crypto status | resume | flatten

Brokers: --broker paper (default, simulated fills), testnet (Delta India demo, no real money), or
live. Live needs DELTA_API_KEY, DELTA_API_SECRET and ATIS_CRYPTO_LIVE=I_ACCEPT_THE_RISK in the
environment. Testnet needs the first two, from a testnet account.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from ..live.telegram import notifier_from_env
from . import backtest as bt
from .broker import DELTA_LIVE, DELTA_TESTNET, DeltaBroker, PaperBroker
from .config import MARKETS, BotConfig
from .data import load_binance_funding, load_binance_hourly, sync_binance
from .runner import CryptoBot

LIVE_CONFIRM = "I_ACCEPT_THE_RISK"


def make_broker(args):
    if args.broker == "paper":
        return PaperBroker(Path(args.state_dir) / "crypto-paper.json", args.paper_capital)
    key, secret = os.environ.get("DELTA_API_KEY"), os.environ.get("DELTA_API_SECRET")
    if not key or not secret:
        sys.exit("DELTA_API_KEY and DELTA_API_SECRET must be set in the environment (never on the command line)")
    if args.broker == "live" and os.environ.get("ATIS_CRYPTO_LIVE") != LIVE_CONFIRM:
        sys.exit(f"live trading is off: set ATIS_CRYPTO_LIVE={LIVE_CONFIRM} to place real orders")
    return DeltaBroker(key, secret, DELTA_LIVE if args.broker == "live" else DELTA_TESTNET, args.settle_asset)


def cmd_backtest(args) -> int:
    cache = Path(args.cache)
    cfg = BotConfig()
    hourly, funding = {}, {}
    for sym in cfg.markets:
        b = MARKETS[sym].binance
        if args.sync:
            sync_binance(b, cache, log=lambda m: print("  " + m, file=sys.stderr))
        hourly[sym] = load_binance_hourly(b, cache)
        funding[sym] = load_binance_funding(b, cache)
        if not hourly[sym]:
            sys.exit(f"no history for {b} in {cache}; run with --sync first")
    res = bt.run(hourly, funding, cfg)
    print(f"trades {res.trades}, fees {res.fees:.1%} of starting equity, funding {res.funding:+.1%}")
    for label, a, b in (("2018-01 .. 2022-12 (selection window)", date(2018, 1, 1), date(2022, 12, 31)),
                        ("2023-01 .. now (out of sample)", date(2023, 1, 1), None),
                        ("2018-01 .. now", date(2018, 1, 1), None)):
        s = bt.stats(res.equity, a, b)
        if s:
            print(f"{label:<40} CAGR {s['cagr']:+.1%}  Sharpe {s['sharpe']:.2f}  max DD {s['max_drawdown']:.1%}")
    s = bt.stats(res.equity, date(2018, 1, 1))
    print("by year: " + "  ".join(f"{y}: {r:+.0%}" for y, r in s["years"].items()))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="atis-crypto", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backtest")
    b.add_argument("--cache", default="data/crypto")
    b.add_argument("--sync", action="store_true", help="download/refresh Binance archives first")
    for name in ("rebalance", "watch", "status", "resume", "flatten"):
        p = sub.add_parser(name)
        p.add_argument("--broker", choices=("paper", "testnet", "live"), default="paper")
        p.add_argument("--state-dir", default="data/live")
        p.add_argument("--paper-capital", type=float, default=10_000.0, help="starting USD for paper trading")
        p.add_argument("--settle-asset", default="USD", help="wallet asset Delta reports balances in")
        p.add_argument("--dry-run", action="store_true", help="print messages instead of sending to Telegram")
        if name == "rebalance":
            p.add_argument("--force", action="store_true", help="rebalance again even if done today")
    args = ap.parse_args(argv)
    if args.cmd == "backtest":
        return cmd_backtest(args)
    broker = make_broker(args)
    try:
        notify = notifier_from_env(args.dry_run).send
    except Exception as exc:
        print(f"telegram unavailable ({exc}); printing messages", file=sys.stderr)
        notify = notifier_from_env(True).send
    bot = CryptoBot(broker, Path(args.state_dir), notify=notify)
    if args.cmd == "rebalance":
        bot.rebalance(force=args.force)
    elif args.cmd == "watch":
        bot.watch()
    elif args.cmd == "resume":
        bot.resume()
    elif args.cmd == "flatten":
        bot.flatten("manual flatten")
        bot.notify(f"<b>Crypto bot</b> ({broker.name}): all positions closed by hand.")
    else:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        print(json.dumps({"broker": broker.name, "equity": broker.equity(), "positions": broker.positions(),
                          "risk": bot.risk.state.__dict__, "at": now}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
