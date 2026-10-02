import { useEffect, useRef, useState } from "react";
import type { PageProps } from "../App";
import { api } from "../api";
import { Badge, Card, Empty, KV, Progress, StateBadge } from "../components/ui";
import { fmtDuration, hhmm } from "../format";
import { usePoll } from "../hooks";
import type { LogEvent } from "../types";
import { JOB_TONE } from "./Backtest";

const LEVELS = ["all", "info", "signal", "skip", "warn", "error"] as const;
const MAX_EVENTS = 1000;

export function MonitorPage({ status }: PageProps) {
  const { data: system } = usePoll(api.system, 3000);
  const { data: jobs, refresh: refreshJobs } = usePoll(api.jobs, (status?.jobs_running ?? 0) > 0 ? 1000 : 4000);
  const [events, setEvents] = useState<LogEvent[]>([]);
  const [level, setLevel] = useState<(typeof LEVELS)[number]>("all");
  const [follow, setFollow] = useState(true);
  const [paused, setPaused] = useState(false);
  const lastId = useRef(0);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      if (paused) return;
      try {
        const fresh = await api.events(lastId.current);
        if (!alive || !fresh.length) return;
        lastId.current = fresh[fresh.length - 1].id;
        setEvents((prev) => [...prev, ...fresh].slice(-MAX_EVENTS));
      } catch {
        /* status bar already reports API errors */
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), 1000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [paused]);

  useEffect(() => {
    if (follow && logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [events, follow]);

  const shown = level === "all" ? events : events.filter((e) => e.level === level);
  const s = status;

  return (
    <div className="page">
      <div className="grid-3">
        <Card title="Replay worker">
          {s ? (
            <KV items={[
              ["State", <StateBadge state={s.state} />],
              ["Thread", s.worker_alive ? <Badge tone="good">alive</Badge> : <Badge tone="bad">down</Badge>],
              ["Heartbeat", `${s.heartbeat_age_s.toFixed(1)}s ago`],
              ["Throughput", `${s.bars_per_second} bars/s (target ${s.replay_speed || "max"})`],
              ["Bars processed", s.bars_processed.toLocaleString()],
              ["Session", s.current_date ? `${s.current_date} · bar ${s.bar_index}/${s.bars_in_session}` : "between sessions"],
              ["Last bar", s.last_bar_ts ? s.last_bar_ts.replace("T", " ") : "—"],
              ["Sessions", `${s.sessions_done}/${s.sessions_total} done (+${s.warmup_sessions} history)`],
              ["Last error", s.last_error ?? "none"],
            ]} />
          ) : <Empty>—</Empty>}
        </Card>
        <Card title="Background jobs">
          {jobs?.length ? (
            <table className="table">
              <thead><tr><th>Job</th><th>Status</th><th>Progress</th><th>Time</th><th /></tr></thead>
              <tbody>
                {jobs.map((j) => (
                  <tr key={j.id}>
                    <td className="mono">{j.kind} {j.id}</td>
                    <td><Badge tone={JOB_TONE[j.status]}>{j.status}</Badge></td>
                    <td style={{ minWidth: 90 }}><Progress value={j.status === "done" ? 1 : j.progress} /></td>
                    <td className="muted small">{j.duration_s !== null ? `${j.duration_s}s` : "—"}</td>
                    <td>
                      {(j.status === "running" || j.status === "queued") && (
                        <button className="btn small warn" onClick={() => void api.cancelJob(j.id).then(() => refreshJobs())}>Cancel</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <Empty>No jobs have run. Start one from the Backtest page.</Empty>}
        </Card>
        <Card title="System">
          {system ? (
            <>
              <KV items={[
                ["Process", `pid ${system.pid} · Python ${system.python}`],
                ["Uptime", s ? fmtDuration(s.uptime_s) : "—"],
                ["Peak memory", system.peak_rss_mb !== null ? `${system.peak_rss_mb} MB` : "n/a"],
                ["CPU time", `${system.cpu_s}s`],
                ["Settings file", system.settings_path ?? "not persisted"],
                ["Journal file", system.journal_path ?? "not persisted"],
                ["Events buffered", system.events_buffered.toLocaleString()],
              ]} />
              <h4>Threads</h4>
              <ul className="threads">
                {system.threads.map((t, i) => (
                  <li key={`${t.name}${i}`}><span className={`dot ${t.alive ? "ok" : "bad"}`} /> {t.name} {t.daemon && <span className="muted small">daemon</span>}</li>
                ))}
              </ul>
            </>
          ) : <Empty>—</Empty>}
        </Card>
      </div>

      <Card title={`Event log (${shown.length})`} actions={
        <>
          <select value={level} onChange={(e) => setLevel(e.target.value as (typeof LEVELS)[number])} aria-label="Filter events by level">
            {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
          <label className="check"><input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> follow</label>
          <button className="btn small ghost" onClick={() => setPaused(!paused)}>{paused ? "Resume log" : "Pause log"}</button>
          <button className="btn small ghost" onClick={() => setEvents([])}>Clear view</button>
        </>
      }>
        <div className="log" ref={logRef}>
          {shown.length ? shown.map((e) => (
            <div key={e.id} className={`ev ${e.level}`}>
              <span className="mono muted">{e.wall.slice(11)}</span>
              <span className="mono">{e.market ? `${e.market.slice(0, 10)} ${hhmm(e.market)}` : "—"}</span>
              <Badge tone={e.level === "error" ? "bad" : e.level === "warn" || e.level === "skip" ? "warn" : e.level === "signal" ? "good" : "muted"}>{e.level}</Badge>
              <span className="muted">{e.kind}</span>
              <span>{e.message}</span>
            </div>
          )) : <Empty>No events.</Empty>}
        </div>
      </Card>
    </div>
  );
}
