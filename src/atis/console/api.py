"""HTTP API for the operator console. The built React UI is served from ./static when present."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .catalog import SETUP_IDS
from .runtime import ConflictError, Runtime
from .settings import SettingsError

STATIC_DIR = Path(__file__).parent / "static"


def create_app(runtime: Runtime, static_dir: Path = STATIC_DIR) -> FastAPI:
    app = FastAPI(title="ATIS console", version="0.1.0")
    rt = runtime

    def guard(fn, *args):
        try:
            return fn(*args)
        except ConflictError as exc:
            raise HTTPException(409, str(exc)) from None
        except (SettingsError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from None
        except KeyError as exc:
            raise HTTPException(404, f"not found: {exc}") from None

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        s = rt.status()
        return {"ok": s["worker_alive"] and s["state"] != "error", "state": s["state"]}

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        return rt.status()

    @app.get("/api/dashboard")
    def dashboard() -> dict[str, Any]:
        return rt.dashboard()

    @app.get("/api/session")
    def session(date: str | None = None) -> dict[str, Any] | None:
        view = rt.session_view(date)
        if view is None and date is not None:
            raise HTTPException(404, f"no session {date}")
        return view

    @app.get("/api/sessions")
    def sessions() -> list[dict[str, Any]]:
        return rt.sessions_list()

    @app.get("/api/setups")
    def setups() -> dict[str, Any]:
        return rt.setups()

    @app.post("/api/setups/{setup_id}")
    def toggle_setup(setup_id: str, enabled: bool = Body(..., embed=True)) -> dict[str, Any]:
        if setup_id not in SETUP_IDS:
            raise HTTPException(404, f"unknown setup {setup_id}")
        guard(rt.set_setup_enabled, setup_id, enabled)
        return rt.setups()

    @app.get("/api/signals")
    def signals(date: str | None = None) -> list[dict[str, Any]]:
        return rt.signals(date)

    @app.post("/api/signals/journal")
    def journal(key: str = Body(...), status: str = Body(...), note: str = Body("")) -> dict[str, Any]:
        return guard(rt.set_journal, key, status, note)

    @app.get("/api/events")
    def events(since: int = 0, limit: int = 200, level: str | None = None) -> list[dict[str, Any]]:
        return rt.events(since, min(limit, 1000), level)

    @app.post("/api/control/speed")
    def speed(bars_per_second: float = Body(..., embed=True)) -> dict[str, Any]:
        guard(rt.set_speed, bars_per_second)
        return rt.status()

    @app.post("/api/control/{action}")
    def control(action: str, count: int = Body(1, embed=True)) -> dict[str, Any]:
        actions = {"start": rt.start, "pause": rt.pause, "resume": rt.start, "stop": rt.stop, "reset": rt.reset}
        if action == "step":
            guard(rt.step, count)
        elif action in actions:
            guard(actions[action])
        else:
            raise HTTPException(404, f"unknown action {action}")
        return rt.status()

    @app.get("/api/jobs")
    def jobs() -> list[dict[str, Any]]:
        return rt.jobs_view()

    @app.post("/api/jobs/backtest")
    def run_backtest() -> dict[str, Any]:
        return guard(rt.start_backtest).summary()

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str) -> dict[str, Any]:
        return guard(rt.job_view, job_id)

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel(job_id: str) -> dict[str, Any]:
        return guard(rt.cancel_job, job_id).summary()

    @app.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        return rt.settings_view()

    @app.put("/api/settings")
    def put_settings(data: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return guard(rt.update_settings, data)

    @app.post("/api/settings/defaults")
    def defaults() -> dict[str, Any]:
        return guard(rt.restore_defaults)

    @app.get("/api/system")
    def system() -> dict[str, Any]:
        return rt.system()

    @app.get("/api/export/signals.csv", response_class=PlainTextResponse)
    def export_signals() -> PlainTextResponse:
        return PlainTextResponse(rt.export_signals_csv(), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=atis-signals.csv"})

    if (static_dir / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            if path.startswith("api/"):
                raise HTTPException(404, f"no endpoint /{path}")
            return FileResponse(static_dir / "index.html")
    else:
        @app.get("/", include_in_schema=False, response_class=PlainTextResponse)
        def no_ui() -> str:
            return ("ATIS console API is running, but the UI is not built.\n"
                    "Build it with: cd console-ui && npm install && npm run build\n"
                    "API docs: /docs")

    return app
