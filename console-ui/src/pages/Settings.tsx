import { useEffect, useMemo, useState } from "react";
import type { PageProps } from "../App";
import { api } from "../api";
import { Badge, Card, ErrorBox } from "../components/ui";
import type { SchemaField, SchemaSection, SettingsResponse } from "../types";

type Draft = Record<string, string | boolean>;

const keyOf = (section: string, field: string) => (section ? `${section}.${field}` : field);
const ACRONYMS = new Set(["ib", "iv", "vix", "poc", "dpoc", "oi", "atm", "itm", "va", "csv", "hvn", "lvn", "tpos", "a3", "b2", "b3", "c2", "c3"]);
const human = (name: string) => {
  const words = name.split("_").map((w) => (ACRONYMS.has(w) ? w.toUpperCase() : w));
  return words.join(" ").replace(/^./, (c) => c.toUpperCase());
};

function toDraft(schema: SchemaSection[]): Draft {
  const d: Draft = {};
  for (const sec of schema) {
    for (const f of sec.fields) {
      const k = keyOf(sec.key, f.name);
      if (f.kind === "boolean") d[k] = Boolean(f.value);
      else if (f.kind === "pair") {
        const [a, b] = f.value as [unknown, unknown];
        d[`${k}#0`] = String(a);
        d[`${k}#1`] = String(b);
      } else if (f.kind === "list") d[k] = (f.value as string[]).join("\n");
      else d[k] = f.value === null || f.value === undefined ? "" : String(f.value);
    }
  }
  return d;
}

function parse(f: SchemaField, raw: string | boolean): unknown {
  if (f.kind === "boolean") return raw;
  const s = String(raw).trim();
  switch (f.kind) {
    case "number":
    case "integer":
      return s === "" ? s : Number(s);
    case "optional-number":
      return s === "" ? null : Number(s);
    case "list":
      return s.split(/[\n,]+/).map((x) => x.trim()).filter(Boolean);
    default:
      return s;
  }
}

function buildPayload(schema: SchemaSection[], draft: Draft): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const sec of schema) {
    const target: Record<string, unknown> = sec.key ? ((out[sec.key] = {}) as Record<string, unknown>) : out;
    for (const f of sec.fields) {
      const k = keyOf(sec.key, f.name);
      target[f.name] = f.kind === "pair"
        ? [Number(draft[`${k}#0`]), Number(draft[`${k}#1`])]
        : parse(f, draft[k]);
    }
  }
  return out;
}

function FieldInput({ f, k, draft, set }: { f: SchemaField; k: string; draft: Draft; set: (k: string, v: string | boolean) => void }) {
  const id = `f-${k}`;
  switch (f.kind) {
    case "boolean":
      return <input id={id} type="checkbox" checked={Boolean(draft[k])} onChange={(e) => set(k, e.target.checked)} />;
    case "select":
      return (
        <select id={id} value={String(draft[k])} onChange={(e) => set(k, e.target.value)}>
          {f.options?.map((o) => <option key={o}>{o}</option>)}
        </select>
      );
    case "time":
      return <input id={id} type="time" value={String(draft[k])} onChange={(e) => set(k, e.target.value)} />;
    case "pair":
      return (
        <span className="pair">
          <input aria-label={`${f.name} min`} type="number" value={String(draft[`${k}#0`])} onChange={(e) => set(`${k}#0`, e.target.value)} />
          <span>to</span>
          <input aria-label={`${f.name} max`} type="number" value={String(draft[`${k}#1`])} onChange={(e) => set(`${k}#1`, e.target.value)} />
        </span>
      );
    case "list":
      return <textarea id={id} rows={2} value={String(draft[k])} placeholder="one per line" onChange={(e) => set(k, e.target.value)} />;
    case "number":
    case "integer":
    case "optional-number":
      return <input id={id} type="number" step={f.kind === "integer" ? 1 : "any"} value={String(draft[k])} onChange={(e) => set(k, e.target.value)} />;
    default:
      return <input id={id} type="text" value={String(draft[k])} onChange={(e) => set(k, e.target.value)} />;
  }
}

function defaultText(f: SchemaField): string {
  if (Array.isArray(f.default)) return f.default.length ? f.default.join(", ") : "empty";
  return f.default === null || f.default === "" ? "empty" : String(f.default);
}

export function SettingsPage({ refreshStatus }: PageProps) {
  const [resp, setResp] = useState<SettingsResponse | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = (r: SettingsResponse) => {
    setResp(r);
    setDraft(toDraft(r.schema));
  };

  useEffect(() => {
    api.settings().then(load).catch((e) => setError(String(e)));
  }, []);

  const original = useMemo(() => (resp ? toDraft(resp.schema) : {}), [resp]);
  const dirtyKeys = Object.keys(draft).filter((k) => draft[k] !== original[k]);

  const run = async (fn: () => Promise<SettingsResponse | unknown>, msg: string) => {
    setBusy(true);
    setError(null);
    setSaved(null);
    try {
      const r = await fn();
      if (r && typeof r === "object" && "schema" in r) load(r as SettingsResponse);
      else load(await api.settings());
      setSaved(msg);
      refreshStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!resp) return <ErrorBox error={error} />;

  return (
    <div className="page settings">
      <div className="toolbar sticky">
        <button className="btn good" disabled={busy || !dirtyKeys.length}
          onClick={() => void run(() => api.saveSettings(buildPayload(resp.schema, draft)), "Settings saved.")}>
          Save{dirtyKeys.length ? ` (${dirtyKeys.length})` : ""}
        </button>
        <button className="btn ghost" disabled={busy || !dirtyKeys.length} onClick={() => setDraft(original)}>Discard</button>
        <button className="btn ghost" disabled={busy}
          onClick={() => window.confirm("Restore every setting to its default?") && void run(api.restoreDefaults, "Defaults restored.")}>
          Restore defaults
        </button>
        {resp.pending_restart && (
          <button className="btn warn" disabled={busy} onClick={() => void run(() => api.control("reset"), "Data reloaded with the new settings.")}>
            Reset to apply
          </button>
        )}
        <span className="muted small">{resp.settings_path ? `Saved to ${resp.settings_path}` : "Not persisted"}</span>
      </div>
      <ErrorBox error={error} />
      {saved && <div className="alert good">{saved}</div>}
      <p className="muted small">
        Fields marked <Badge tone="good">live</Badge> apply immediately; everything else applies on the next Reset or Start.
        Enable or disable individual setups on the Setups page.
      </p>
      {resp.schema.map((sec) => (
        <Card key={sec.key || "general"} title={sec.title}>
          <div className="form-grid">
            {sec.fields.map((f) => {
              const k = keyOf(sec.key, f.name);
              const dirty = dirtyKeys.some((d) => d === k || d.startsWith(`${k}#`));
              return (
                <div key={k} className={`field ${dirty ? "dirty" : ""}`}>
                  <label htmlFor={`f-${k}`}>
                    {human(f.name)} {f.live && <Badge tone="good">live</Badge>}
                  </label>
                  <FieldInput f={f} k={k} draft={draft} set={(key, v) => setDraft({ ...draft, [key]: v })} />
                  <div className="field-help">
                    {f.help && <span>{f.help} </span>}
                    <span className="muted">default: {defaultText(f)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      ))}
    </div>
  );
}
