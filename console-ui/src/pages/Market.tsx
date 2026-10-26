import { useState } from "react";
import type { PageProps } from "../App";
import { api } from "../api";
import { CandleChart } from "../components/CandleChart";
import { DEFAULT_TOGGLES, buildOverlays } from "../components/overlays";
import type { OverlayToggles } from "../components/overlays";
import { SignalDetail, SignalSummary } from "../components/SignalCard";
import { Badge, Card, Empty, ErrorBox, KV } from "../components/ui";
import { fmt, label } from "../format";
import { usePoll } from "../hooks";

const TOGGLE_LABELS: Record<keyof OverlayToggles, string> = {
  prior: "Prior value",
  ib: "Initial balance",
  developing: "Developing POC",
  nodes: "HVN / LVN",
  singles: "Single prints",
  balance: "Composite balance",
};

export function MarketPage({ status }: PageProps) {
  const [date, setDate] = useState<string>("");
  const [toggles, setToggles] = useState<OverlayToggles>(DEFAULT_TOGGLES);
  const [open, setOpen] = useState<string | null>(null);
  const running = status?.state === "running";
  const { data: sessions } = usePoll(api.sessions, running ? 3000 : 6000);
  const { data: view, error, refresh } = usePoll(() => api.session(date || undefined), running && !date ? 1200 : 5000, [date]);

  return (
    <div className="page">
      <div className="toolbar">
        <label>
          Session{" "}
          <select value={date} onChange={(e) => setDate(e.target.value)} aria-label="Session">
            <option value="">Latest / live</option>
            {(sessions ?? []).slice().reverse().map((s) => (
              <option key={s.date} value={s.live ? "" : s.date} disabled={s.live}>
                {s.date} {s.live ? "(live)" : `· ${label(s.day_type)} · ${s.signals} sig`}
              </option>
            ))}
          </select>
        </label>
        <div className="chips">
          {(Object.keys(TOGGLE_LABELS) as (keyof OverlayToggles)[]).map((k) => (
            <label key={k} className={`chip ${toggles[k] ? "on" : ""}`}>
              <input type="checkbox" checked={toggles[k]} onChange={(e) => setToggles({ ...toggles, [k]: e.target.checked })} />
              {TOGGLE_LABELS[k]}
            </label>
          ))}
        </div>
      </div>
      <ErrorBox error={error} />
      {!view ? (
        <Card><Empty>No session to show yet. Start or step the replay.</Empty></Card>
      ) : (
        <>
          <Card title={<>{view.symbol} current-month futures · {view.date} {view.live && <Badge tone="good">live</Badge>} {view.today.is_expiry && <Badge tone="warn">expiry day</Badge>}</>}>
            {(() => {
              const o = buildOverlays(view, toggles);
              return (
                <CandleChart bars={view.bars} slots={view.live ? status?.bars_in_session : undefined}
                  levels={o.levels} bands={o.bands} profile={view.profile}
                  priorProfile={toggles.prior ? view.prior_profile : []} markers={o.markers} height={480} />
              );
            })()}
            <p className="legend muted small">
              Right panel: today's volume profile (solid) over the prior session's (faint). Blue band: prior value area;
              amber band: prior single prints. Triangles mark signals at their futures entry.
            </p>
          </Card>

          <div className="grid-3">
            <Card title="Session structure">
              <KV items={[
                ["Open", <>{fmt(view.today.open)} · {label(view.today.open_type)} <span className="muted">({label(view.today.open_location)})</span></>],
                ["High / Low", <span className="mono">{fmt(view.today.high)} / {fmt(view.today.low)}</span>],
                ["IB", view.today.ib_high !== null ? <>{fmt(view.today.ib_low)} – {fmt(view.today.ib_high)} ({view.today.ib_class})</> : "forming…"],
                ["Day type", label(view.today.day_type)],
                [view.live ? "dPOC / dVA" : "POC / VA", <span className="mono">{fmt(view.today.dpoc)} / {fmt(view.today.val)}–{fmt(view.today.vah)}</span>],
              ]} />
            </Card>
            <Card title={`Prior session ${view.prior?.date ?? ""}`}>
              {view.prior ? (
                <KV items={[
                  ["VA / POC", <span className="mono">{fmt(view.prior.val)}–{fmt(view.prior.vah)} / {fmt(view.prior.poc)}</span>],
                  ["High / Low", <span className="mono">{fmt(view.prior.high)} / {fmt(view.prior.low)}</span>],
                  ["Day / shape", <>{label(view.prior.day_type)} · {view.prior.shape}-shape</>],
                  ["Poor extremes", [view.prior.poor_high && "poor high", view.prior.poor_low && "poor low"].filter(Boolean).join(", ") || "none"],
                  ["Single prints", view.prior.single_prints.map(([a, b]) => `${fmt(a)}–${fmt(b)}`).join(", ") || "none"],
                  ["Composite", view.balance ? `${fmt(view.balance.val)}–${fmt(view.balance.vah)} (${view.balance.sessions.length}d${view.balance.quiet ? ", quiet" : ""})` : "no balance"],
                ]} />
              ) : <Empty>No prior session.</Empty>}
            </Card>
            <Card title="Pre-market plan">
              <ul className="notes">{view.plan.scenarios.map((s, i) => <li key={i}>{s}</li>)}</ul>
              <ul className="notes warn">{view.plan.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
            </Card>
          </div>

          <div className="grid-2">
            <Card title={`Signals (${view.signals.length})`}>
              {view.signals.length ? (
                <ul className="list expandable">
                  {view.signals.map((s) => (
                    <li key={s.key}>
                      <button className="row-btn" onClick={() => setOpen(open === s.key ? null : s.key)} aria-expanded={open === s.key}>
                        <SignalSummary s={s} />
                      </button>
                      {open === s.key && <SignalDetail s={s} onJournal={() => void refresh()} />}
                    </li>
                  ))}
                </ul>
              ) : <Empty>No signals this session.</Empty>}
            </Card>
            <Card title={`Skipped / no-trade reasons (${view.skips.length})`}>
              {view.skips.length ? (
                <table className="table">
                  <thead><tr><th>Time</th><th>Setup</th><th>Reason</th></tr></thead>
                  <tbody>
                    {view.skips.map((k, i) => (
                      <tr key={i}><td className="mono">{k.time ?? "—"}</td><td><Badge>{k.setup}</Badge></td><td>{k.reason}</td></tr>
                    ))}
                  </tbody>
                </table>
              ) : <Empty>Nothing skipped.</Empty>}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
