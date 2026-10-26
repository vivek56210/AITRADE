import { useState } from "react";
import { api } from "../api";
import { hhmm } from "../format";
import type { Status } from "../types";
import { Progress, StateBadge } from "./ui";

const SPEEDS: [number, string][] = [
  [1, "1 bar/s"],
  [5, "5 bars/s"],
  [25, "25 bars/s"],
  [100, "100 bars/s"],
  [500, "500 bars/s"],
  [0, "Max"],
];

export function ControlBar({ status, onChange }: { status: Status | null; onChange: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      onChange();
    }
  };

  if (!status) return <div className="controlbar">Connecting to the console API…</div>;
  const s = status;
  const running = s.state === "running";
  const loading = s.state === "loading";
  const paused = s.state === "paused";
  const canStep = !running && !loading;
  const sessionProgress = s.sessions_total ? (s.sessions_done + (s.bars_in_session ? s.bar_index / s.bars_in_session : 0)) / s.sessions_total : 0;

  return (
    <div className="controlbar">
      <div className="cb-status">
        <StateBadge state={s.state} />
        <div className="cb-meta">
          <strong>{s.symbol}</strong>
          <span className="muted">{s.data_source} replay</span>
          <span className="mono">
            {s.current_date ?? "—"} {s.last_bar_ts ? hhmm(s.last_bar_ts) : ""}
          </span>
          <span className="muted">
            session {Math.min(s.sessions_done + (s.current_date ? 1 : 0), s.sessions_total)}/{s.sessions_total}
          </span>
        </div>
        <div className="cb-progress" title={`${Math.round(sessionProgress * 100)}% of replay`}>
          <Progress value={sessionProgress} />
        </div>
      </div>
      <div className="cb-actions">
        {loading ? (
          <button className="btn" disabled>Loading data…</button>
        ) : running ? (
          <button className="btn warn" disabled={busy} onClick={() => act(() => api.control("pause"))}>❚❚ Pause</button>
        ) : paused ? (
          <button className="btn good" disabled={busy} onClick={() => act(() => api.control("resume"))}>▶ Resume</button>
        ) : (
          <button className="btn good" disabled={busy} onClick={() => act(() => api.control("start"))}>
            ▶ {s.state === "finished" || s.state === "stopped" ? "Restart" : "Start"}
          </button>
        )}
        <button className="btn" disabled={busy || !canStep} onClick={() => act(() => api.step(1))} title="Process one bar">Step 1</button>
        <button className="btn" disabled={busy || !canStep} onClick={() => act(() => api.step(30))} title="Process 30 bars">+30</button>
        <button className="btn" disabled={busy || loading || s.state === "idle" || s.state === "stopped"} onClick={() => act(() => api.control("stop"))}>■ Stop</button>
        <button className="btn ghost" disabled={busy || loading} onClick={() => act(() => api.control("reset"))}
          title="Reload data with the current settings">↺ Reset</button>
        <select aria-label="Replay speed" value={s.replay_speed} disabled={busy}
          onChange={(e) => act(() => api.speed(Number(e.target.value)))}>
          {SPEEDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>
      {error && <div className="cb-error">{error}</div>}
    </div>
  );
}
