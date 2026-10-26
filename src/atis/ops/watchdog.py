"""Watchdog: notice when a job has stopped, and tell someone outside the VM that the VM is alive.

Runs every 10 minutes from a systemd timer. It checks:
  - the NSE alert runner, during market hours on weekdays: today's heartbeat exists and is fresh
  - each crypto bot: its hourly watch heartbeat is under 2.5 hours old, and it is not halted
  - systemd: no atis-* unit is in the failed state
Each problem is sent to Telegram once per day, with a note when it clears. If HEALTHCHECK_URL is
set (for example a free healthchecks.io check), the URL is pinged on every run, with /fail appended
when there is a problem. When the whole VM is down nothing here can run, so that external check is
what alerts you.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
MARKET_CHECK = (time(9, 25), time(15, 25))
NSE_STALE = timedelta(minutes=10)
CRYPTO_STALE = timedelta(hours=2, minutes=30)


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def nse_problem(live_dir: Path, now_ist: datetime) -> str | None:
    if now_ist.weekday() >= 5 or not (MARKET_CHECK[0] <= now_ist.time() <= MARKET_CHECK[1]):
        return None
    hb = _read(live_dir / "heartbeat-live.json")
    today = now_ist.date().isoformat()
    if not hb or hb.get("day") != today:
        return "NSE alert runner has not started today (ignore if today is an NSE holiday)"
    if hb.get("status") == "running":
        seen = datetime.fromisoformat(hb["time"])
        if now_ist.replace(tzinfo=None) - seen > NSE_STALE:
            return f"NSE alert runner heartbeat is stale (last {seen:%H:%M} IST)"
    return None


def crypto_problems(live_dir: Path, now_utc: datetime) -> list[str]:
    out = []
    for hb_path in sorted(live_dir.glob("crypto-heartbeat-*.json")):
        name = hb_path.stem.removeprefix("crypto-heartbeat-")
        hb = _read(hb_path)
        if not hb:
            out.append(f"crypto bot ({name}) heartbeat unreadable")
            continue
        seen = datetime.fromisoformat(hb["t"])
        if now_utc.replace(tzinfo=None) - seen > CRYPTO_STALE:
            out.append(f"crypto bot ({name}) has not checked in since {seen:%Y-%m-%d %H:%M} UTC")
        if hb.get("halted"):
            out.append(f"crypto bot ({name}) is HALTED - review, then run: atis-crypto resume --broker {name.split('-')[-1]}")
    return out


def failed_units(run: Callable[[list[str]], str] | None = None) -> list[str]:
    run = run or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout)
    try:
        text = run(["systemctl", "--failed", "--no-legend", "--plain"])
    except (OSError, subprocess.SubprocessError):
        return []
    units = [line.split()[0] for line in text.splitlines() if line.strip()]
    return [f"service {u} has failed (journalctl -u {u} -n 50)" for u in units if u.startswith("atis-")]


def run_once(live_dir: Path, notify: Callable[[str], bool], now_utc: datetime | None = None,
             units: Callable[[], list[str]] = failed_units, ping: Callable[[str], None] | None = None,
             health_url: str | None = None) -> list[str]:
    now_utc = now_utc or datetime.now(timezone.utc)
    now_ist = now_utc.astimezone(IST)
    problems = [p for p in [nse_problem(live_dir, now_ist)] if p] + crypto_problems(live_dir, now_utc) + units()
    state_path = live_dir / "watchdog-state.json"
    state = _read(state_path) or {}
    day = now_ist.date().isoformat()
    sent = set(state.get("sent", [])) if state.get("day") == day else set()
    active = set(state.get("active", []))
    new = [p for p in problems if p not in sent]
    if new:
        notify("<b>ATIS watchdog</b>\n" + "\n".join(f"- {p}" for p in new))
    cleared = [p for p in active if p not in problems]
    if cleared:
        notify("<b>ATIS watchdog: resolved</b>\n" + "\n".join(f"- {p}" for p in cleared))
    live_dir.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"day": day, "sent": sorted(sent | set(problems)), "active": problems,
                                      "checked": now_utc.isoformat(timespec="seconds")}))
    if health_url:
        (ping or _ping)(health_url.rstrip("/") + ("/fail" if problems else ""))
    return problems


def _ping(url: str) -> None:
    try:
        urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "atis-watchdog"}), timeout=10)
    except OSError as exc:
        print(f"watchdog: health ping failed ({type(exc).__name__})", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="atis-watchdog", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live-dir", default="data/live")
    ap.add_argument("--dry-run", action="store_true", help="print alerts instead of sending them")
    args = ap.parse_args(argv)
    from ..live.telegram import notifier_from_env
    try:
        notify = notifier_from_env(args.dry_run).send
    except Exception as exc:
        print(f"telegram unavailable ({exc}); printing", file=sys.stderr)
        notify = notifier_from_env(True).send
    problems = run_once(Path(args.live_dir), notify, health_url=os.environ.get("HEALTHCHECK_URL") or None)
    print("ok" if not problems else "\n".join(problems))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
