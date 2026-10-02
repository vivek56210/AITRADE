import { useState } from "react";
import { api } from "../api";
import { fmt, fmtRs, hhmm } from "../format";
import type { JournalEntry, Signal } from "../types";
import { Badge, DirectionBadge } from "./ui";

const JOURNAL_TONE = { open: "muted", taken: "good", ignored: "warn" } as const;

export function SignalSummary({ s, compact = false }: { s: Signal; compact?: boolean }) {
  if (compact) {
    return (
      <div className="sig-summary compact" title={`${s.name} · ${s.option_plan.structure}`}>
        <span className="mono muted">{s.ts.slice(5, 10)} {hhmm(s.ts)}</span>
        <Badge tone="accent">{s.setup_id}</Badge>
        <DirectionBadge direction={s.direction} />
        <span className="mono">@ {fmt(s.entry)}</span>
        <span className="muted small">{s.lots}L</span>
        <Badge tone={JOURNAL_TONE[s.journal.status]}>{s.journal.status}</Badge>
      </div>
    );
  }
  return (
    <div className="sig-summary">
      <span className="mono">{s.ts.slice(0, 10)} {hhmm(s.ts)}</span>
      <Badge tone="accent">{s.setup_id}</Badge>
      <span className="sig-name">{s.name}</span>
      <DirectionBadge direction={s.direction} />
      <span className="mono">@ {fmt(s.entry)}</span>
      <span className="muted">{s.option_plan.structure}</span>
      <span>{s.lots} lot{s.lots === 1 ? "" : "s"}</span>
      <Badge tone={JOURNAL_TONE[s.journal.status]}>{s.journal.status}</Badge>
    </div>
  );
}

export function SignalDetail({ s, onJournal }: { s: Signal; onJournal?: (j: JournalEntry) => void }) {
  const [note, setNote] = useState(s.journal.note ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const plan = s.option_plan;

  const mark = async (status: JournalEntry["status"]) => {
    setBusy(true);
    setErr(null);
    try {
      onJournal?.(await api.journal(s.key, status, note));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="sig-detail">
      <div className="sig-grid">
        <div>
          <h4>Futures plan</h4>
          <table className="mini">
            <tbody>
              <tr><th>Entry</th><td className="mono">{fmt(s.entry)}</td></tr>
              <tr><th>Stop</th><td className="mono">{fmt(s.stop)}</td></tr>
              {s.targets.map((t) => (
                <tr key={t.label + t.price}>
                  <th>Target</th>
                  <td className="mono">{fmt(t.price)} <span className="muted">{t.label} · {t.size_pct}%</span></td>
                </tr>
              ))}
              <tr><th>Stop rule</th><td>{s.stop_rule}</td></tr>
              <tr><th>Exit by</th><td>{s.exit_by ? hhmm(s.exit_by) : s.horizon}</td></tr>
            </tbody>
          </table>
        </div>
        <div>
          <h4>Option structure · exp {plan.expiry}</h4>
          <table className="mini">
            <thead>
              <tr><th>Side</th><th>Strike</th><th>Δ</th><th>Premium</th></tr>
            </thead>
            <tbody>
              {plan.legs.map((l, i) => (
                <tr key={i}>
                  <td><Badge tone={l.side === "BUY" ? "good" : "bad"}>{l.side}</Badge></td>
                  <td className="mono">{fmt(l.strike, 0)} {l.right}</td>
                  <td className="mono">{l.delta === null ? "—" : l.delta.toFixed(2)}</td>
                  <td className="mono">{fmt(l.premium)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small">
            Lots {s.lots} · risk/lot {fmtRs(s.risk_per_lot)} · total {fmtRs(s.risk_total)}
            {s.est_costs !== null && <> · costs {fmtRs(s.est_costs)}</>}
            <br />
            {s.sizing_basis}
          </p>
        </div>
        <div>
          <h4>Confirmations & notes</h4>
          <ul className="checks">
            {Object.entries(s.confirmations).map(([k, v]) => (
              <li key={k} className={v === null ? "na" : v ? "yes" : "no"}>
                {v === null ? "n/a" : v ? "✓" : "✗"} {k}
              </li>
            ))}
          </ul>
          <ul className="notes">
            {[...s.notes, ...plan.notes].map((n, i) => <li key={i}>{n}</li>)}
          </ul>
        </div>
      </div>
      {onJournal && (
        <div className="journal-row">
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Journal note (fill price, reason…)" maxLength={500} aria-label="Journal note" />
          <button className="btn good" disabled={busy} onClick={() => mark("taken")}>Mark taken</button>
          <button className="btn warn" disabled={busy} onClick={() => mark("ignored")}>Mark ignored</button>
          <button className="btn ghost" disabled={busy} onClick={() => mark("open")}>Reopen</button>
          {err && <span className="error-text">{err}</span>}
        </div>
      )}
    </div>
  );
}
