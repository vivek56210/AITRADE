import type { PageProps } from "../App";
import { api } from "../api";
import { CandleChart } from "../components/CandleChart";
import { EquityChart } from "../components/EquityChart";
import { buildOverlays } from "../components/overlays";
import { SignalSummary } from "../components/SignalCard";
import { Badge, Card, Empty, ErrorBox, KV, Stat, StateBadge } from "../components/ui";
import { fmt, fmtDuration, fmtPct, fmtR, hhmm, label } from "../format";
import { usePoll } from "../hooks";

export function DashboardPage({ status }: PageProps) {
  const fast = status?.state === "running" ? 1500 : 4000;
  const { data, error } = usePoll(api.dashboard, fast);
  const { data: view } = usePoll(() => api.session(), fast);

  if (!data) return <ErrorBox error={error} />;
  const s = data.status;
  const sess = data.session;
  const t = sess?.today;
  const overlays = view ? buildOverlays(view) : null;
  const bySetup = Object.entries(data.signals_by_setup).sort((a, b) => b[1] - a[1]);
  const maxCount = Math.max(1, ...bySetup.map(([, c]) => c));

  return (
    <div className="page">
      <div className="stats-row">
        <Stat label="Engine" value={<StateBadge state={s.state} />} sub={`${s.bars_per_second || 0} bars/s · up ${fmtDuration(s.uptime_s)}`} />
        <Stat label="Replay progress" value={`${s.sessions_done}/${s.sessions_total}`} sub={`${s.bars_processed.toLocaleString()} bars processed`} />
        <Stat label="Signals" value={s.signals_total} sub={sess ? `${sess.signals} in ${sess.date}` : "—"} />
        <Stat label="Journal" value={`${data.journal.taken ?? 0} taken`} sub={`${data.journal.ignored ?? 0} ignored · ${data.journal.open ?? 0} open`} />
        <Stat label="Last backtest" value={data.backtest ? fmtR(data.backtest.total_r) : "—"}
          tone={data.backtest ? (data.backtest.total_r >= 0 ? "good" : "bad") : "muted"}
          sub={data.backtest ? `${data.backtest.signals} signals · win ${fmtPct(data.backtest.win_rate)}` : "not run yet"} />
        <Stat label="Background jobs" value={s.jobs_running} sub={s.worker_alive ? "replay worker alive" : "worker down"} tone={s.worker_alive ? undefined : "bad"} />
      </div>

      <div className="grid-2-1">
        <Card title={view ? `${view.symbol} futures · ${view.date}${view.live ? " (live)" : ""}` : "Market"}
          actions={<a className="btn ghost small" href="#/market">Open market view →</a>}>
          {view && overlays ? (
            <CandleChart bars={view.bars} slots={view.live ? s.bars_in_session : undefined} levels={overlays.levels}
              bands={overlays.bands} profile={view.profile} markers={overlays.markers} height={320} />
          ) : (
            <Empty>Press <strong>Start</strong> or <strong>Step</strong> to replay sessions through the playbook.</Empty>
          )}
        </Card>
        <Card title="Today's structure">
          {t ? (
            <KV items={[
              ["Session", <>{sess!.date} {t.is_expiry && <Badge tone="warn">expiry</Badge>}</>],
              ["Open type", <>{label(t.open_type)} <span className="muted">({label(t.open_location)})</span></>],
              ["Initial balance", t.ib_high !== null ? <>{fmt(t.ib_low)} – {fmt(t.ib_high)} <Badge>{t.ib_class}</Badge></> : "forming…"],
              ["Day type", label(t.day_type)],
              ["Last / dPOC", <span className="mono">{fmt(t.last)} / {fmt(t.dpoc)}</span>],
              ["Developing VA", <span className="mono">{fmt(t.val)} – {fmt(t.vah)}</span>],
              ["Prior VA / POC", sess!.prior ? <span className="mono">{fmt(sess!.prior.val)} – {fmt(sess!.prior.vah)} / {fmt(sess!.prior.poc)}</span> : "—"],
              ["Avg IB / expiry", <>{fmt(sess!.plan.avg_ib, 1)} · {sess!.plan.nearest_expiry}</>],
            ]} />
          ) : (
            <Empty>No session yet.</Empty>
          )}
        </Card>
      </div>

      <div className="grid-3">
        <Card title="Recent signals" actions={<a className="btn ghost small" href="#/signals">All signals →</a>}>
          {data.recent_signals.length ? (
            <ul className="list">
              {data.recent_signals.map((sig) => <li key={sig.key} className="pad-y"><SignalSummary s={sig} compact /></li>)}
            </ul>
          ) : <Empty>No signals yet - the default action is no trade.</Empty>}
        </Card>
        <Card title="Signals by setup">
          {bySetup.length ? (
            <ul className="bars">
              {bySetup.map(([id, c]) => (
                <li key={id}>
                  <span className="bar-label">{id}</span>
                  <span className="bar-track"><span className="bar-fill" style={{ width: `${(c / maxCount) * 100}%` }} /></span>
                  <span className="bar-value">{c}</span>
                </li>
              ))}
            </ul>
          ) : <Empty>Nothing fired yet.</Empty>}
        </Card>
        <Card title="Activity" actions={<a className="btn ghost small" href="#/monitor">Monitor →</a>}>
          <ul className="events compact">
            {data.recent_events.map((e) => (
              <li key={e.id} className={`ev ${e.level}`}>
                <span className="mono muted">{e.market ? hhmm(e.market) : e.wall.slice(11, 16)}</span>
                <span>{e.message}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <div className="grid-2">
        <Card title="Plan warnings">
          {sess?.plan.warnings.length ? (
            <ul className="notes">{sess.plan.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
          ) : <Empty>None.</Empty>}
        </Card>
        <Card title="Backtest equity (cumulative R)" actions={<a className="btn ghost small" href="#/backtest">Backtest →</a>}>
          {data.backtest ? <EquityChart points={data.backtest.equity} height={180} /> : <Empty>Run a backtest from the Backtest page.</Empty>}
        </Card>
      </div>
    </div>
  );
}
