"""Console settings: one JSON document covering data source, context, risk, playbook params and times."""

from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from ..playbook.config import INSTRUMENTS, PlaybookParams, RiskParams, SessionTimes
from ..playbook.state import DayContext
from .catalog import SETUP_IDS

LIVE_KEYS = {"replay_speed", "disabled_setups"}
DATA_SOURCES = ("synthetic", "upstox", "dhan", "csv")
_OPTIONAL_FLOATS = {"iv", "max_oi_strike"}
_SECTIONS = ("context", "risk", "params", "times")

HELP = {
    "symbol": "Index whose current-month futures bars are loaded.",
    "data_source": "upstox = real 1-minute NIFTY/BANKNIFTY index bars downloaded from Upstox (cached); "
                   "dhan = 1-minute front-month futures with volume and OI from DhanHQ (read-only, needs "
                   "DHAN_CLIENT_ID / DHAN_ACCESS_TOKEN in the environment; active contracts only); "
                   "csv = your own bars file; synthetic = generated demo sessions.",
    "upstox_from": "First date to download (YYYY-MM-DD, 2022-01-01 or later).",
    "upstox_to": "Last date to download (YYYY-MM-DD); empty = today.",
    "data_cache": "Folder where downloaded Upstox months are cached.",
    "dhan_from": "First date to download from Dhan (YYYY-MM-DD). Expired futures are not served, so data "
                 "starts where the oldest listed contract's history starts.",
    "dhan_to": "Last date to download from Dhan (YYYY-MM-DD); empty = today.",
    "dhan_cache": "Folder where Dhan contract months and the contract registry are cached.",
    "dhan_back_adjust": "Add each roll gap to earlier bars so profile levels line up across contract rolls.",
    "csv_path": "Path to a CSV with timestamp,open,high,low,close,volume[,buy_volume,sell_volume] (IST).",
    "warmup_sessions": "Sessions used only to build history (prior value, averages) before signals start.",
    "replay_speed": "Bars per second for the background replay; 0 = as fast as possible.",
    "iv": "Annualised implied volatility used to price option legs (e.g. 0.13). Empty = do not price.",
    "basis": "Futures minus spot in points; profile levels are converted to strikes with it.",
    "holidays": "Exchange holidays (YYYY-MM-DD); expiries on a holiday move to the previous trading day.",
    "events": "Scheduled events (YYYY-MM-DDTHH:MM); no entries within the event buffer before them.",
    "vix_rising": "Blocks all premium selling.",
    "max_oi_strike": "Highest open-interest strike for the expiry pin setup (D1).",
    "capital": "Trading capital in rupees.",
    "risk_per_trade": "Fraction of capital risked per trade (0.01 = 1%).",
    "max_trades_per_day": "Signals beyond this count are skipped.",
    "premium_stop_pct": "Option-buying premium stop (0.35 = 35%).",
    "value_area_pct": "Share of volume inside the value area.",
    "narrow_ib_ratio": "IB below this multiple of its 10-day average is narrow (breakout-prone).",
    "wide_ib_ratio": "IB above this multiple is wide (containment-prone).",
    "event_buffer_minutes": "Minutes before a scheduled event with no new entries.",
}


class SettingsError(ValueError):
    pass


@dataclass
class ContextSettings:
    iv: float | None = None
    basis: float = 0.0
    holidays: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    vix_rising: bool = False
    max_oi_strike: float | None = None

    def to_day_context(self) -> DayContext:
        return DayContext(
            holidays=frozenset(date.fromisoformat(d) for d in self.holidays),
            events=tuple(datetime.fromisoformat(e) for e in self.events),
            vix_rising=self.vix_rising, basis=self.basis, iv=self.iv, max_oi_strike=self.max_oi_strike,
        )


@dataclass
class ConsoleSettings:
    symbol: str = "NIFTY"
    data_source: str = "synthetic"
    csv_path: str = ""
    upstox_from: str = "2025-10-01"
    upstox_to: str = ""
    data_cache: str = "data/upstox"
    dhan_from: str = "2026-07-01"
    dhan_to: str = ""
    dhan_cache: str = "data/dhan"
    dhan_back_adjust: bool = True
    synthetic_days: int = 30
    synthetic_seed: int = 7
    synthetic_start: str = "2026-08-03"
    warmup_sessions: int = 3
    replay_speed: float = 25.0
    disabled_setups: list[str] = field(default_factory=list)
    context: ContextSettings = field(default_factory=ContextSettings)
    risk: RiskParams = field(default_factory=RiskParams)
    params: PlaybookParams = field(default_factory=PlaybookParams)
    times: SessionTimes = field(default_factory=SessionTimes)


def _encode(v: Any) -> Any:
    if isinstance(v, time):
        return v.strftime("%H:%M")
    if isinstance(v, (tuple, list)):
        return [_encode(x) for x in v]
    if dataclasses.is_dataclass(v):
        return {f.name: _encode(getattr(v, f.name)) for f in dataclasses.fields(v)}
    return v


def settings_to_dict(s: ConsoleSettings) -> dict[str, Any]:
    return _encode(s)


def _coerce(name: str, raw: Any, default: Any) -> Any:
    try:
        if name.rsplit(".", 1)[-1] in _OPTIONAL_FLOATS:
            return None if raw in (None, "") else float(raw)
        if isinstance(default, bool):
            if not isinstance(raw, bool):
                raise TypeError("expected true/false")
            return raw
        if isinstance(default, int):
            if isinstance(raw, bool) or float(raw) != int(float(raw)):
                raise TypeError("expected a whole number")
            return int(float(raw))
        if isinstance(default, float):
            if isinstance(raw, bool):
                raise TypeError("expected a number")
            return float(raw)
        if isinstance(default, time):
            return time.fromisoformat(str(raw))
        if isinstance(default, tuple):
            if not isinstance(raw, (list, tuple)) or len(raw) != len(default):
                raise TypeError(f"expected {len(default)} values")
            return tuple(_coerce(name, r, d) for r, d in zip(raw, default))
        if isinstance(default, list):
            if not isinstance(raw, list):
                raise TypeError("expected a list")
            return [str(x).strip() for x in raw if str(x).strip()]
        if isinstance(default, str):
            return str(raw).strip()
    except (TypeError, ValueError) as exc:
        raise SettingsError(f"{name}: {exc}") from None
    raise SettingsError(f"{name}: unsupported field")


def _merge(obj: Any, data: dict[str, Any], prefix: str) -> Any:
    if not isinstance(data, dict):
        raise SettingsError(f"{prefix or 'settings'}: expected an object")
    names = {f.name for f in dataclasses.fields(obj)}
    unknown = set(data) - names
    if unknown:
        raise SettingsError(f"unknown field(s): {', '.join(sorted(prefix + k for k in unknown))}")
    changes = {}
    for k, raw in data.items():
        current = getattr(obj, k)
        if k in _SECTIONS and not prefix:
            changes[k] = _merge(current, raw, k + ".")
        else:
            changes[k] = _coerce(prefix + k, raw, current)
    return dataclasses.replace(obj, **changes)


def settings_from_dict(data: dict[str, Any], base: ConsoleSettings | None = None) -> ConsoleSettings:
    """Apply a (possibly partial) settings document on top of base, validating every field."""
    s = _merge(base or ConsoleSettings(), data, "")
    validate(s)
    return s


def validate(s: ConsoleSettings) -> None:
    def check(ok: bool, msg: str) -> None:
        if not ok:
            raise SettingsError(msg)

    check(s.symbol in INSTRUMENTS, f"symbol: must be one of {', '.join(INSTRUMENTS)}")
    check(s.data_source in DATA_SOURCES, f"data_source: must be one of {', '.join(DATA_SOURCES)}")
    if s.data_source == "csv":
        p = Path(s.csv_path).expanduser()
        check(p.suffix.lower() == ".csv" and p.is_file(), f"csv_path: no CSV file at {s.csv_path!r}")
    check(2 <= s.synthetic_days <= 2000, "synthetic_days: must be between 2 and 2000")
    try:
        date.fromisoformat(s.synthetic_start)
        start = date.fromisoformat(s.upstox_from)
        end = date.fromisoformat(s.upstox_to) if s.upstox_to else date.today()
        dhan_start = date.fromisoformat(s.dhan_from)
        dhan_end = date.fromisoformat(s.dhan_to) if s.dhan_to else date.today()
        [date.fromisoformat(d) for d in s.context.holidays]
        [datetime.fromisoformat(e) for e in s.context.events]
    except ValueError as exc:
        raise SettingsError(f"invalid date: {exc}") from None
    if s.data_source == "upstox":
        check(start <= end, "upstox_from must be on or before upstox_to")
        check(end >= date(2022, 1, 1), "upstox: 1-minute history starts 2022-01-01")
    if s.data_source == "dhan":
        check(dhan_start <= dhan_end, "dhan_from must be on or before dhan_to")
    check(s.warmup_sessions >= 1, "warmup_sessions: need at least 1 session of history")
    check(s.replay_speed >= 0, "replay_speed: must be >= 0")
    check(set(s.disabled_setups) <= set(SETUP_IDS), "disabled_setups: unknown setup id")
    check(s.risk.capital > 0, "risk.capital: must be positive")
    check(0 < s.risk.risk_per_trade <= 0.05, "risk.risk_per_trade: must be in (0, 0.05]")
    check(0 < s.risk.premium_stop_pct < 1, "risk.premium_stop_pct: must be in (0, 1)")
    check(s.risk.max_trades_per_day >= 1, "risk.max_trades_per_day: must be >= 1")
    check(0.5 <= s.params.value_area_pct < 1, "params.value_area_pct: must be in [0.5, 1)")
    check(s.params.narrow_ib_ratio < s.params.wide_ib_ratio, "params: narrow_ib_ratio must be below wide_ib_ratio")
    check(s.times.open < s.times.close, "times: open must be before close")
    check(s.context.iv is None or 0 < s.context.iv < 3, "context.iv: annualised IV, e.g. 0.13")


def _kind(name: str, value: Any) -> str:
    if name in _OPTIONAL_FLOATS:
        return "optional-number"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, time):
        return "time"
    if isinstance(value, tuple):
        return "pair"
    if isinstance(value, list):
        return "list"
    return "text"


def schema(s: ConsoleSettings) -> list[dict[str, Any]]:
    """Form description for the UI: sections of typed fields with current and default values."""
    defaults = ConsoleSettings()

    def fields_of(obj: Any, dflt: Any, skip: set[str]) -> list[dict[str, Any]]:
        out = []
        for f in dataclasses.fields(obj):
            if f.name in skip:
                continue
            v = getattr(obj, f.name)
            item = {"name": f.name, "kind": _kind(f.name, v), "value": _encode(v),
                    "default": _encode(getattr(dflt, f.name)), "help": HELP.get(f.name, ""),
                    "live": f.name in LIVE_KEYS}
            if f.name == "symbol":
                item.update(kind="select", options=list(INSTRUMENTS))
            if f.name == "data_source":
                item.update(kind="select", options=list(DATA_SOURCES))
            out.append(item)
        return out

    return [
        {"key": "", "title": "Data & replay", "fields": fields_of(s, defaults, set(_SECTIONS) | {"disabled_setups"})},
        {"key": "context", "title": "Market context", "fields": fields_of(s.context, defaults.context, set())},
        {"key": "risk", "title": "Risk", "fields": fields_of(s.risk, defaults.risk, set())},
        {"key": "params", "title": "Playbook parameters", "fields": fields_of(s.params, defaults.params, set())},
        {"key": "times", "title": "Session times (IST)", "fields": fields_of(s.times, defaults.times, set())},
    ]


def load_settings(path: Path) -> ConsoleSettings:
    if not path.exists():
        return ConsoleSettings()
    return settings_from_dict(json.loads(path.read_text()))


def save_settings(path: Path, s: ConsoleSettings) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(settings_to_dict(s), indent=2))
    os.replace(tmp, path)
