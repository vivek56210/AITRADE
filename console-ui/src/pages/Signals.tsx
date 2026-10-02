import { useMemo, useState } from "react";
import type { PageProps } from "../App";
import { api } from "../api";
import { SignalDetail, SignalSummary } from "../components/SignalCard";
import { Card, Empty, ErrorBox } from "../components/ui";
import { usePoll } from "../hooks";

export function SignalsPage({ status }: PageProps) {
  const { data, error, refresh } = usePoll(() => api.signals(), status?.state === "running" ? 2000 : 6000);
  const [setup, setSetup] = useState("");
  const [journal, setJournal] = useState("");
  const [dir, setDir] = useState("");
  const [open, setOpen] = useState<string | null>(null);

  const setups = useMemo(() => Array.from(new Set((data ?? []).map((s) => s.setup_id))).sort(), [data]);
  const rows = useMemo(
    () =>
      (data ?? [])
        .filter((s) => (!setup || s.setup_id === setup) && (!journal || s.journal.status === journal) && (!dir || s.direction === dir))
        .slice()
        .reverse(),
    [data, setup, journal, dir],
  );

  return (
    <div className="page">
      <div className="toolbar">
        <select value={setup} onChange={(e) => setSetup(e.target.value)} aria-label="Filter by setup">
          <option value="">All setups</option>
          {setups.map((s) => <option key={s}>{s}</option>)}
        </select>
        <select value={dir} onChange={(e) => setDir(e.target.value)} aria-label="Filter by direction">
          <option value="">All directions</option>
          <option value="long">Long</option>
          <option value="short">Short</option>
          <option value="neutral">Neutral (premium selling)</option>
        </select>
        <select value={journal} onChange={(e) => setJournal(e.target.value)} aria-label="Filter by journal status">
          <option value="">Any journal status</option>
          <option value="open">Open</option>
          <option value="taken">Taken</option>
          <option value="ignored">Ignored</option>
        </select>
        <span className="muted">{rows.length} of {data?.length ?? 0}</span>
        <a className="btn ghost" href="/api/export/signals.csv" download>Export CSV</a>
      </div>
      <ErrorBox error={error} />
      <Card>
        {rows.length ? (
          <ul className="list expandable">
            {rows.map((s) => (
              <li key={s.key}>
                <button className="row-btn" onClick={() => setOpen(open === s.key ? null : s.key)} aria-expanded={open === s.key}>
                  <SignalSummary s={s} />
                </button>
                {open === s.key && <SignalDetail s={s} onJournal={() => void refresh()} />}
              </li>
            ))}
          </ul>
        ) : (
          <Empty>No signals match. Signals appear here as the replay runs.</Empty>
        )}
      </Card>
    </div>
  );
}
