import time

import pytest
from fastapi.testclient import TestClient

from atis.console.api import create_app
from atis.console.runtime import Runtime
from atis.console.settings import ConsoleSettings, SettingsError, settings_from_dict, settings_to_dict


def wait_for(pred, timeout=15.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def rt(tmp_path):
    runtime = Runtime(tmp_path / "settings.json", tmp_path / "journal.json",
                      ConsoleSettings(synthetic_days=8, warmup_sessions=3), start_worker=False)
    yield runtime
    runtime.shutdown()


@pytest.fixture
def client(rt, tmp_path):
    return TestClient(create_app(rt, static_dir=tmp_path / "no-ui"))


def test_settings_round_trip():
    s = ConsoleSettings()
    assert settings_from_dict(settings_to_dict(s)) == s


def test_settings_validation_errors():
    with pytest.raises(SettingsError, match="risk_per_trade"):
        settings_from_dict({"risk": {"risk_per_trade": 0.5}})
    with pytest.raises(SettingsError, match="unknown field"):
        settings_from_dict({"params": {"nope": 1}})
    with pytest.raises(SettingsError, match="csv_path"):
        settings_from_dict({"data_source": "csv", "csv_path": "/does/not/exist.csv"})
    with pytest.raises(SettingsError, match="whole number"):
        settings_from_dict({"warmup_sessions": 2.5})


def test_step_builds_live_session_view(client):
    status = client.post("/api/control/step", json={"count": 100}).json()
    assert status["state"] == "paused" and status["bars_processed"] == 100
    view = client.get("/api/session").json()
    assert view["live"] is True and len(view["bars"]) == 100
    assert view["prior"]["vah"] > view["prior"]["val"]
    assert view["today"]["ib_high"] is not None and view["profile"]
    assert len(client.get("/api/setups").json()["setups"]) == 13


def test_full_replay_and_read_models(client):
    client.post("/api/control/step", json={"count": 5000})
    status = client.get("/api/status").json()
    assert status["state"] == "finished" and status["sessions_done"] == 5
    sessions = client.get("/api/sessions").json()
    assert len(sessions) == 5 and not any(s["live"] for s in sessions)
    past = client.get("/api/session", params={"date": sessions[0]["date"]}).json()
    assert past["live"] is False and len(past["bars"]) == 375
    dash = client.get("/api/dashboard").json()
    assert dash["status"]["signals_total"] == sum(s["signals"] for s in sessions)
    assert client.get("/api/session", params={"date": "1999-01-01"}).status_code == 404
    csv_text = client.get("/api/export/signals.csv").text
    assert csv_text.startswith("date,time,setup")


def test_journal_marks_signals_and_persists(client, rt, tmp_path):
    client.post("/api/control/step", json={"count": 5000})
    sigs = client.get("/api/signals").json()
    assert sigs, "synthetic replay should produce signals"
    key = sigs[0]["key"]
    r = client.post("/api/signals/journal", json={"key": key, "status": "taken", "note": "filled 1 lot"})
    assert r.json()["status"] == "taken"
    assert client.get("/api/signals").json()[0]["journal"]["status"] == "taken"
    assert key in (tmp_path / "journal.json").read_text()
    assert client.post("/api/signals/journal", json={"key": key, "status": "bogus"}).status_code == 422


def test_disable_setup_applies_live_and_persists(client, rt, tmp_path):
    client.post("/api/control/step", json={"count": 10})
    data = client.post("/api/setups/A3", json={"enabled": False}).json()
    assert next(s for s in data["setups"] if s["id"] == "A3")["enabled"] is False
    assert "A3" in rt.engine.disabled_setups
    assert '"A3"' in (tmp_path / "settings.json").read_text()
    assert client.post("/api/setups/ZZ", json={"enabled": False}).status_code == 404


def test_settings_update_flags_pending_restart(client):
    client.post("/api/control/step", json={"count": 1})
    r = client.put("/api/settings", json={"context": {"iv": 0.13}})
    assert r.status_code == 200 and r.json()["pending_restart"] is True
    assert client.put("/api/settings", json={"risk": {"capital": -1}}).status_code == 422
    client.post("/api/control/reset")
    assert client.get("/api/settings").json()["pending_restart"] is False


def test_control_conflicts(client):
    assert client.post("/api/control/pause").status_code == 409
    assert client.post("/api/control/jump").status_code == 404
    assert client.get("/api/nope").status_code == 404


def test_backtest_job_runs_in_background(client):
    job = client.post("/api/jobs/backtest").json()
    assert wait_for(lambda: client.get(f"/api/jobs/{job['id']}").json()["status"] == "done")
    res = client.get(f"/api/jobs/{job['id']}").json()["result"]
    assert res["sessions"] == 5 and isinstance(res["stats"], list)
    assert client.get("/api/dashboard").json()["backtest"]["id"] == job["id"]


def test_worker_thread_replays_and_pauses(tmp_path):
    rt = Runtime(None, None, ConsoleSettings(synthetic_days=6, warmup_sessions=3, replay_speed=0))
    try:
        client = TestClient(create_app(rt, static_dir=tmp_path))
        client.post("/api/control/start")
        assert wait_for(lambda: client.get("/api/status").json()["bars_processed"] > 0)
        assert wait_for(lambda: client.get("/api/status").json()["state"] == "finished")
        assert client.get("/api/health").json()["ok"] is True
        kinds = {e["kind"] for e in client.get("/api/events").json()}
        assert {"data", "session", "structure", "control"} <= kinds
        assert any(t["name"] == "replay-worker" for t in client.get("/api/system").json()["threads"])
    finally:
        rt.shutdown()
