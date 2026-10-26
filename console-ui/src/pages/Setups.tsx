import { useState } from "react";
import type { PageProps } from "../App";
import { api } from "../api";
import { Badge, Card, ErrorBox, Toggle } from "../components/ui";
import type { Tone } from "../components/ui";
import { fmtPct, fmtR } from "../format";
import { usePoll } from "../hooks";
import type { SetupInfo } from "../types";

const TODAY_TONE: Record<SetupInfo["today"], Tone> = {
  fired: "good",
  skipped: "warn",
  watching: "info",
  disabled: "bad",
  idle: "muted",
};

export function SetupsPage({ status, refreshStatus }: PageProps) {
  const { data, error, refresh, setData } = usePoll(api.setups, status?.state === "running" ? 2000 : 5000);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const toggle = async (id: string, enabled: boolean) => {
    setBusy(id);
    setActionError(null);
    try {
      setData(await api.toggleSetup(id, enabled));
      refreshStatus();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
      void refresh();
    } finally {
      setBusy(null);
    }
  };

  if (!data) return <ErrorBox error={error} />;
  const groups = Object.entries(data.groups);

  return (
    <div className="page">
      <ErrorBox error={actionError} />
      <p className="muted">
        All setups are <Badge tone="warn">CANDIDATE</Badge> - unvalidated hypotheses until backtests and live
        paper results earn them a VALIDATED status. Disabling a setup takes effect on the next bar.
      </p>
      {data.global_skips.length > 0 && (
        <div className="alert info">
          Engine-wide blocks: {data.global_skips.map((g) => `${g.reason} (${g.count})`).join("; ")}
        </div>
      )}
      {groups.map(([g, name]) => (
        <Card key={g} title={<>Group {g} · {name}</>}>
          <div className="setup-grid">
            {data.setups.filter((s) => s.group === g).map((s) => (
              <article key={s.id} className={`setup ${s.enabled ? "" : "off"}`}>
                <header>
                  <Badge tone="accent">{s.id}</Badge>
                  <h3>{s.name}</h3>
                  <Toggle checked={s.enabled} disabled={busy === s.id} label={`${s.enabled ? "Disable" : "Enable"} ${s.id}`}
                    onChange={(v) => void toggle(s.id, v)} />
                </header>
                <div className="setup-status">
                  <Badge tone={TODAY_TONE[s.today]} title={s.today_reason ?? undefined}>today: {s.today}</Badge>
                  <span className="muted small">fired {s.fired} · skipped {s.skipped}</span>
                </div>
                {s.today_reason && <p className="small warn-text">{s.today_reason}</p>}
                <p className="small">{s.context}</p>
                {s.backtest && (
                  <div className="setup-bt">
                    {s.backtest.trades > 0 && (
                      <>
                        <span>{s.backtest.trades} trades</span>
                        <span>win {fmtPct(s.backtest.win_rate)}</span>
                        <span className={(s.backtest.avg_r ?? 0) >= 0 ? "good-text" : "bad-text"}>avg {fmtR(s.backtest.avg_r)}</span>
                      </>
                    )}
                    {s.backtest.premium_trades > 0 && (
                      <span>{s.backtest.premium_trades} condors · contained {fmtPct(s.backtest.containment_rate)}</span>
                    )}
                  </div>
                )}
                <button className="link-btn" onClick={() => setExpanded({ ...expanded, [s.id]: !expanded[s.id] })}
                  aria-expanded={!!expanded[s.id]}>
                  {expanded[s.id] ? "Hide rules" : "Show rules"}
                </button>
                {expanded[s.id] && (
                  <dl className="rules">
                    <dt>Trigger</dt><dd>{s.trigger}</dd>
                    <dt>Option strategy</dt><dd>{s.strategy}</dd>
                    <dt>Stop</dt><dd>{s.stop}</dd>
                    <dt>Targets</dt><dd>{s.targets}</dd>
                    {s.top_skip_reasons.length > 0 && (
                      <>
                        <dt>Most common skip reasons</dt>
                        <dd>
                          <ul>{s.top_skip_reasons.map((r) => <li key={r.reason}>{r.reason} ({r.count})</li>)}</ul>
                        </dd>
                      </>
                    )}
                  </dl>
                )}
              </article>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}
