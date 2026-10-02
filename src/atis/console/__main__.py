"""Run the operator console: python -m atis.console [--host 127.0.0.1] [--port 8765]."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from .api import create_app
from .runtime import Runtime


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="atis-console", description="ATIS playbook operator console")
    ap.add_argument("--host", default="127.0.0.1", help="bind address (keep it local; there is no login)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--settings", default="atis_console.json", help="settings file (created on first save)")
    ap.add_argument("--journal", default="atis_journal.json", help="signal journal file")
    ap.add_argument("--autostart", action="store_true", help="start the replay immediately")
    args = ap.parse_args(argv)
    rt = Runtime(Path(args.settings), Path(args.journal))
    if args.autostart:
        rt.start()
    print(f"ATIS console on http://{args.host}:{args.port}")
    uvicorn.run(create_app(rt), host=args.host, port=args.port, log_level="warning")
    rt.shutdown()


if __name__ == "__main__":
    main()
