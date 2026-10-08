"""Read what the live runner wrote (snapshots, journal, heartbeat) for the console."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def journal_rows(live_dir: Path, label: str = "live") -> list[dict[str, Any]]:
    path = live_dir / f"journal-{label}.jsonl"
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_setup: dict[str, dict[str, Any]] = {}
    by_day: dict[str, float] = {}
    for r in rows:
        k = f"{r['symbol']} {r['setup']}"
        s = by_setup.setdefault(k, {"key": k, "signals": 0, "scored": 0, "wins": 0, "total_r": 0.0,
                                    "condors": 0, "contained": 0})
        s["signals"] += 1
        if r.get("r") is not None:
            s["scored"] += 1
            s["wins"] += r["r"] > 0
            s["total_r"] = round(s["total_r"] + r["r"], 3)
            by_day[r["date"]] = round(by_day.get(r["date"], 0.0) + r["r"], 3)
        if r.get("contained") is not None:
            s["condors"] += 1
            s["contained"] += bool(r["contained"])
    scored = [r["r"] for r in rows if r.get("r") is not None]
    return {"signals": len(rows), "scored": len(scored), "wins": sum(x > 0 for x in scored),
            "total_r": round(sum(scored), 3), "by_setup": sorted(by_setup.values(), key=lambda x: x["key"]),
            "by_day": [{"date": d, "r": v} for d, v in sorted(by_day.items())]}


def snapshot_days(live_dir: Path, label: str = "live") -> list[str]:
    days = {p.name.split("-", 2)[2][:10] for p in live_dir.glob(f"snapshot-{label}-*.json")}
    return sorted(days, reverse=True)


def snapshot(live_dir: Path, symbol: str, day: str | None, label: str = "live") -> dict[str, Any] | None:
    days = snapshot_days(live_dir, label)
    day = day or (days[0] if days else None)
    return _read_json(live_dir / f"snapshot-{label}-{day}-{symbol}.json") if day else None


def overview(live_dir: Path, now: datetime, label: str = "live") -> dict[str, Any]:
    hb = _read_json(live_dir / f"heartbeat-{label}.json")
    alive = False
    if hb and hb.get("status") == "running":
        alive = now - datetime.fromisoformat(hb["time"]) < timedelta(minutes=3)
    rows = journal_rows(live_dir, label)
    symbols = sorted({p.name.rsplit("-", 1)[1][:-5] for p in live_dir.glob(f"snapshot-{label}-*.json")})
    return {"live_dir": str(live_dir), "heartbeat": hb, "runner_alive": alive, "days": snapshot_days(live_dir, label),
            "symbols": symbols or ["NIFTY", "BANKNIFTY"], "summary": summarize(rows), "journal": rows[-300:][::-1]}
