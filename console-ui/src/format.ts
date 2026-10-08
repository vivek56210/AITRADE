export const fmt = (v: number | null | undefined, digits = 2): string =>
  v === null || v === undefined || Number.isNaN(v)
    ? "—"
    : v.toLocaleString("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: 0 });

export const fmtPct = (v: number | null | undefined): string =>
  v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`;

export const fmtR = (v: number | null | undefined): string =>
  v === null || v === undefined ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}R`;

export const fmtRs = (v: number | null | undefined): string =>
  v === null || v === undefined ? "—" : `₹${Math.round(v).toLocaleString("en-IN")}`;

export const hhmm = (iso: string | null | undefined): string => (iso ? iso.slice(11, 16) : "—");

export const fmtDuration = (s: number): string => {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${m}m` : m ? `${m}m ${s % 60}s` : `${s}s`;
};

export const label = (v: string | null | undefined): string => (v ? v.replace(/-/g, " ") : "—");
