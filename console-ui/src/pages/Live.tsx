import { useState } from "react";
import { api } from "../api";
import { CandleChart } from "../components/CandleChart";
import { buildOverlays } from "../components/overlays";
import { SignalDetail, SignalSummary } from "../components/SignalCard";
import { Badge, Card, Empty, ErrorBox, KV, Stat } from "../components/ui";
import { fmt, fmtR, hhmm, label } from "../format";
import { usePoll } from "../hooks";
import type { LiveOverview } from "../types";

/** Minutes from 09:15 to 15:30 - the chart's x-axis for a full 1-minute session. */
const SESSION_SLOTS = 375;

function RunnerStatus({ ov }: { ov: LiveOverview }) {
  const hb = ov.heartbeat;
  if (!hb) {
    return <Empty>The live runner has not written anything to {ov.live_dir} yet. It starts at 08:55 IST on trading days.</Empty>;
  }
  const tone = ov.runner_alive ? "good" : hb.status === "finished" ? "accent" : "bad";
  const text = ov.runner_alive ? "running" : hb.status === "finished" ? "finished" : "not responding";
  return (
    <>
      <p>
        <Badge tone={tone}><span className={`dot ${ov.runner_alive ? "pulse" : ""}`} />{text}</Badge>{" "}
        <span className="muted">session {hb.day} · last heartbeat {hb.time.replace("T", " ")} IST</span>
      </p>
      {!ov.runner_alive && hb.status === "running" && (
        <div className="alert warn">No heartbeat for over 3 minutes during a session. Check the service: <code>systemctl status atis-live</code></div>
      )}
      <table className="table">
        <thead><tr><th>Symbol</th><th>Bars</th><th>Last bar</th><th>Feed</th></tr></thead>
        <tbody>
          {Object.entries(hb.symbols).map(([sym, s]) => (
            <tr key={sym}>
              <td>{sym}</td>
              <td className="mono">{s.bars}</td>
              <td className="mono">{hhmm(s.last_bar)}</td>
              <td>
                {s.stale ? <Badge tone="bad">stale</Badge> : <Badge tone="good">ok</Badge>}
                {s.feed_errors > 0 && <> <Badge tone="warn">{s.feed_errors} errors</Badge></>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

export function LivePage() {
  const [symbol, setSymbol] = useState<string>("");
  const [day, setDay] = useState<string>("");
  const [open, setOpen] = useState<string | null>(null);
  const { data: ov, error } = usePoll(api.live, 15000);
  const sym = symbol || ov?.symbols[0] || "NIFTY";
  const { data: view, error: snapError } = usePoll(() => api.liveSnapshot(sym, day || undefined), 15000, [sym, day]);

  if (!ov) {
    return <div className="page"><ErrorBox error={error} />{!error && <Card><Empty>Loading…</Empty></Card>}</div>;
  }
  const s = ov.summary;
  const winRate = s.scored ? Math.round((100 * s.wins) / s.scored) : null;

  return (
    <div className="page">
      <ErrorBox error={error ?? snapError} />
      <div className="alert info">
        Alert-only mode: signals go to Telegram as paper-trade candidates. No orders are placed.
        Results below are simulated on the index (directional setups in R, short-premium setups as contained or not).
      </div>

      <div className="grid-2">
        <Card title="Live runner">
          <RunnerStatus ov={ov} />
        </Card>
        <Card title="Paper results so far">
          <div className="stats-row">
            <Stat label="Signals" value={s.signals} sub={`${ov.days.length} session${ov.days.length === 1 ? "" : "s"}`} />
            <Stat label="Win rate" value={winRate === null ? "—" : `${winRate}%`} sub={`${s.wins}/${s.scored} scored`} />
            <Stat label="Total" value={fmtR(s.total_r)} tone={s.total_r > 0 ? "good" : s.total_r < 0 ? "bad" : "muted"} />
          </div>
        </Card>
      </div>

      <div className="toolbar">
        <div className="chips" role="tablist" aria-label="Symbol">
          {ov.symbols.map((x) => (
            <button key={x} role="tab" aria-selected={x === sym} className={`chip ${x === sym ? "on" : ""}`} onClick={() => setSymbol(x)}>
              {x}
            </button>
          ))}
        </div>
        <label>
          Session{" "}
          <select value={day} onChange={(e) => setDay(e.target.value)} aria-label="Live session">
            <option value="">Latest</option>
            {ov.days.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </label>
      </div>

      {!view ? (
        <Card><Empty>No live chart for {sym} yet. It appears once the first candles of a session arrive.</Empty></Card>
      ) : (
        <>
          <Card title={<>{view.symbol} index · {view.date} {view.live ? <Badge tone="good">live</Badge> : <Badge>closed</Badge>} {view.today.is_expiry && <Badge tone="warn">expiry day</Badge>}</>}>
            {(() => {
              const o = buildOverlays(view);
              return (
                <CandleChart bars={view.bars} slots={SESSION_SLOTS} levels={o.levels} bands={o.bands}
                  profile={view.profile} priorProfile={view.prior_profile} markers={o.markers} height={460} />
              );
            })()}
          </Card>
          <div className="grid-3">
            <Card title="Session structure">
              <KV items={[
                ["Open", <>{fmt(view.today.open)} · {label(view.today.open_type)} <span className="muted">({label(view.today.open_location)})</span></>],
                ["High / Low", <span className="mono">{fmt(view.today.high)} / {fmt(view.today.low)}</span>],
                ["IB", view.today.ib_high !== null ? <>{fmt(view.today.ib_low)} – {fmt(view.today.ib_high)} ({view.today.ib_class})</> : "forming…"],
                ["Day type", label(view.today.day_type)],
                ["dPOC / dVA", <span className="mono">{fmt(view.today.dpoc)} / {fmt(view.today.val)}–{fmt(view.today.vah)}</span>],
              ]} />
            </Card>
            <Card title="Pre-market plan">
              <ul className="notes">{view.plan.scenarios.map((x, i) => <li key={i}>{x}</li>)}</ul>
              <ul className="notes warn">{view.plan.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
            </Card>
            <Card title={`Skipped (${view.skips.length})`}>
              {view.skips.length ? (
                <ul className="notes">
                  {view.skips.slice(-12).map((k, i) => <li key={i}><span className="mono">{k.time ?? "—"}</span> {k.setup}: {k.reason}</li>)}
                </ul>
              ) : <Empty>Nothing skipped.</Empty>}
            </Card>
          </div>
          <Card title={`Signals today (${view.signals.length})`}>
            {view.signals.length ? (
              <ul className="list expandable">
                {view.signals.map((x) => (
                  <li key={x.key}>
                    <button className="row-btn" onClick={() => setOpen(open === x.key ? null : x.key)} aria-expanded={open === x.key}>
                      <SignalSummary s={x} />
                      <span className="muted small">{x.journal.note}</span>
                    </button>
                    {open === x.key && <SignalDetail s={x} />}
                  </li>
                ))}
              </ul>
            ) : <Empty>No signals yet this session.</Empty>}
          </Card>
        </>
      )}

      <div className="grid-2">
        <Card title="By setup">
          {s.by_setup.length ? (
            <table className="table">
              <thead><tr><th>Setup</th><th>Signals</th><th>Wins</th><th>Total R</th><th>Condors held</th></tr></thead>
              <tbody>
                {s.by_setup.map((b) => (
                  <tr key={b.key}>
                    <td>{b.key}</td>
                    <td className="mono">{b.signals}</td>
                    <td className="mono">{b.scored ? `${b.wins}/${b.scored}` : "—"}</td>
                    <td className={`mono ${b.total_r > 0 ? "good-text" : b.total_r < 0 ? "bad-text" : ""}`}>{b.scored ? fmtR(b.total_r) : "—"}</td>
                    <td className="mono">{b.condors ? `${b.contained}/${b.condors}` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <Empty>No completed sessions yet.</Empty>}
        </Card>
        <Card title="By day">
          {s.by_day.length ? (
            <table className="table">
              <thead><tr><th>Date</th><th>R</th></tr></thead>
              <tbody>
                {s.by_day.slice().reverse().map((d) => (
                  <tr key={d.date}><td className="mono">{d.date}</td><td className={`mono ${d.r > 0 ? "good-text" : d.r < 0 ? "bad-text" : ""}`}>{fmtR(d.r)}</td></tr>
                ))}
              </tbody>
            </table>
          ) : <Empty>No completed sessions yet.</Empty>}
        </Card>
      </div>

      <Card title={`Paper journal (${ov.journal.length})`}>
        {ov.journal.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Date</th><th>Time</th><th>Symbol</th><th>Setup</th><th>Dir</th><th>Entry</th><th>Stop</th><th>Structure</th><th>Lots</th><th>Result</th><th>Exit</th></tr></thead>
              <tbody>
                {ov.journal.map((r) => (
                  <tr key={r.key}>
                    <td className="mono">{r.date}</td>
                    <td className="mono">{r.time}</td>
                    <td>{r.symbol}</td>
                    <td><Badge tone="accent">{r.setup}</Badge></td>
                    <td>{r.direction}</td>
                    <td className="mono">{fmt(r.entry)}</td>
                    <td className="mono">{fmt(r.stop)}</td>
                    <td>{r.structure}</td>
                    <td className="mono">{r.lots}</td>
                    <td className={`mono ${(r.r ?? 0) > 0 || r.contained ? "good-text" : (r.r ?? 0) < 0 || r.contained === false ? "bad-text" : ""}`}>
                      {r.r !== null ? fmtR(r.r) : r.contained === null ? "—" : r.contained ? "held" : "breached"}
                    </td>
                    <td className="muted small">{r.exit ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <Empty>The journal fills in at 15:31 each trading day.</Empty>}
      </Card>
    </div>
  );
}
