import { useState } from "react";
import type { PageProps } from "../App";
import { api } from "../api";
import { EquityChart } from "../components/EquityChart";
import { Badge, Card, Empty, ErrorBox, Progress, Stat } from "../components/ui";
import type { Tone } from "../components/ui";
import { fmt, fmtPct, fmtR } from "../format";
import { usePoll } from "../hooks";
import type { JobSummary } from "../types";

export const JOB_TONE: Record<JobSummary["status"], Tone> = {
  queued: "info",
  running: "good",
  done: "accent",
  failed: "bad",
  cancelled: "muted",
};

export function BacktestPage({ status, refreshStatus }: PageProps) {
  const anyRunning = (status?.jobs_running ?? 0) > 0;
  const { data: jobs, refresh: refreshJobs } = usePoll(api.jobs, anyRunning ? 1000 : 5000);
  const [selected, setSelected] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const backtests = (jobs ?? []).filter((j) => j.kind === "backtest");
  const current = selected ?? backtests.find((j) => j.status === "done")?.id ?? backtests[0]?.id ?? null;
  const { data: job } = usePoll(() => (current ? api.job(current) : Promise.resolve(null)), anyRunning ? 1000 : 0, [current]);

  const run = async () => {
    setActionError(null);
    try {
      const j = await api.runBacktest();
      setSelected(j.id);
      refreshStatus();
      void refreshJobs();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    }
  };

  const res = job?.result;

  return (
    <div className="page">
      <div className="toolbar">
        <button className="btn good" onClick={() => void run()} disabled={anyRunning}>
          {anyRunning ? "Backtest running…" : "Run backtest"}
        </button>
        <span className="muted small">
          Runs in the background on the configured data and settings. Scores R multiples on the underlying (before costs) and condor containment - not option P&amp;L.
        </span>
      </div>
      <ErrorBox error={actionError} />
      <div className="grid-1-2">
        <Card title="Backtest jobs">
          {backtests.length ? (
            <ul className="list">
              {backtests.map((j) => (
                <li key={j.id}>
                  <button className={`row-btn ${j.id === current ? "selected" : ""}`} onClick={() => setSelected(j.id)}>
                    <div className="job-row">
                      <span className="mono">{j.id}</span>
                      <Badge tone={JOB_TONE[j.status]}>{j.status}</Badge>
                      <span className="muted small">{j.created.slice(11)}</span>
                      <span className="muted small">{j.duration_s !== null ? `${j.duration_s}s` : ""}</span>
                    </div>
                    {(j.status === "running" || j.status === "queued") && <Progress value={j.progress} />}
                  </button>
                </li>
              ))}
            </ul>
          ) : <Empty>No backtests yet.</Empty>}
        </Card>
        <div className="stack">
          {job && (job.status === "running" || job.status === "queued") && (
            <Card title={`Backtest ${job.id} running`}>
              <Progress value={job.progress} />
              <p className="muted small">{job.done}/{job.total} sessions</p>
              <button className="btn warn" onClick={() => void api.cancelJob(job.id).then(() => refreshJobs())}>Cancel</button>
            </Card>
          )}
          {job?.status === "failed" && <div className="alert bad">Backtest failed: {job.error}</div>}
          {res ? (
            <>
              <p className="muted small">
                {res.symbol} · {res.data_source} data · {res.first} → {res.last}. {res.note}.
              </p>
              <div className="stats-row">
                <Stat label="Sessions" value={res.sessions} sub={`${res.signals} signals`} />
                <Stat label="Total R (directional)" value={fmtR(res.total_r)} tone={res.total_r >= 0 ? "good" : "bad"}
                  sub={`avg ${fmtR(res.avg_r)} per trade`} />
                <Stat label="Win rate" value={fmtPct(res.win_rate)} />
                <Stat label="Profit factor" value={res.profit_factor === null ? "—" : res.profit_factor.toFixed(2)}
                  tone={(res.profit_factor ?? 0) >= 1 ? "good" : "bad"} />
                <Stat label="Max drawdown" value={fmtR(res.max_drawdown_r)} tone="bad" />
                <Stat label="Condors contained" value={res.premium_trades ? `${res.premium_contained}/${res.premium_trades}` : "—"} />
              </div>
              <Card title="Equity curve (cumulative R)"><EquityChart points={res.equity} /></Card>
              <Card title="Monthly R">
                {(() => {
                  const months = Object.entries(res.monthly_r);
                  const max = Math.max(1, ...months.map(([, v]) => Math.abs(v)));
                  return months.length ? (
                    <ul className="months">
                      {months.map(([m, v]) => (
                        <li key={m}>
                          <span className="mono muted">{m}</span>
                          <span className="month-track">
                            <span className={`month-bar ${v >= 0 ? "pos" : "neg"}`}
                              style={{ width: `${(Math.abs(v) / max) * 50}%`, [v >= 0 ? "left" : "right"]: "50%" }} />
                          </span>
                          <span className={`mono ${v >= 0 ? "good-text" : "bad-text"}`}>{fmtR(v)}</span>
                        </li>
                      ))}
                    </ul>
                  ) : <Empty>No directional trades.</Empty>;
                })()}
              </Card>
              <Card title="By setup">
                <table className="table">
                  <thead>
                    <tr><th>Setup</th><th>Trades</th><th>Win</th><th>Avg R</th><th>Total R</th><th>Condors</th><th>Contained</th></tr>
                  </thead>
                  <tbody>
                    {res.stats.map((s) => (
                      <tr key={s.setup}>
                        <td><Badge tone="accent">{s.setup}</Badge></td>
                        <td>{s.trades || "—"}</td>
                        <td>{fmtPct(s.win_rate)}</td>
                        <td className={(s.avg_r ?? 0) >= 0 ? "good-text" : "bad-text"}>{fmtR(s.avg_r)}</td>
                        <td>{s.trades ? fmtR(s.total_r) : "—"}</td>
                        <td>{s.premium_trades || "—"}</td>
                        <td>{fmtPct(s.containment_rate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
              <Card title={`Trades (${res.trades.length})`}>
                <div className="scroll">
                  <table className="table">
                    <thead>
                      <tr><th>Date</th><th>Time</th><th>Setup</th><th>Dir</th><th>Structure</th><th>Entry</th><th>Stop</th><th>Result</th><th>Exit</th></tr>
                    </thead>
                    <tbody>
                      {res.trades.slice().reverse().map((t, i) => (
                        <tr key={i}>
                          <td className="mono">{t.date}</td>
                          <td className="mono">{t.time}</td>
                          <td>{t.setup}</td>
                          <td>{t.direction}</td>
                          <td className="muted">{t.structure}</td>
                          <td className="mono">{fmt(t.entry)}</td>
                          <td className="mono">{fmt(t.stop)}</td>
                          <td className={t.r !== null ? (t.r >= 0 ? "good-text" : "bad-text") : t.contained === null ? "muted" : t.contained ? "good-text" : "bad-text"}>
                            {t.r !== null ? fmtR(t.r) : t.contained === null ? "—" : t.contained ? "contained" : "breached"}
                          </td>
                          <td className="muted">{t.exit}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </>
          ) : (!job && <Card><Empty>Run a backtest to see per-setup results and the equity curve.</Empty></Card>)}
        </div>
      </div>
    </div>
  );
}
