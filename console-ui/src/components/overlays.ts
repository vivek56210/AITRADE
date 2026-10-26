import type { SessionView } from "../types";
import type { Band, Level, Marker } from "./CandleChart";

export interface OverlayToggles {
  prior: boolean;
  ib: boolean;
  developing: boolean;
  nodes: boolean;
  singles: boolean;
  balance: boolean;
}

export const DEFAULT_TOGGLES: OverlayToggles = {
  prior: true,
  ib: true,
  developing: true,
  nodes: false,
  singles: true,
  balance: false,
};

export function buildOverlays(view: SessionView, t: OverlayToggles = DEFAULT_TOGGLES) {
  const levels: Level[] = [];
  const bands: Band[] = [];
  const p = view.prior;
  const d = view.today;
  if (t.prior && p) {
    bands.push({ from: p.val, to: p.vah, color: "var(--va-band)" });
    levels.push(
      { price: p.vah, label: `pVAH ${Math.round(p.vah)}`, color: "var(--lv-va)" },
      { price: p.val, label: `pVAL ${Math.round(p.val)}`, color: "var(--lv-va)" },
      { price: p.poc, label: `pPOC ${Math.round(p.poc)}`, color: "var(--lv-poc)" },
      { price: p.high, label: `pH ${Math.round(p.high)}`, color: "var(--lv-hl)", dash: true },
      { price: p.low, label: `pL ${Math.round(p.low)}`, color: "var(--lv-hl)", dash: true },
    );
  }
  if (t.ib && d.ib_high !== null && d.ib_low !== null) {
    levels.push(
      { price: d.ib_high, label: `IBH ${Math.round(d.ib_high)}`, color: "var(--lv-ib)", dash: true },
      { price: d.ib_low, label: `IBL ${Math.round(d.ib_low)}`, color: "var(--lv-ib)", dash: true },
    );
  }
  if (t.developing && d.dpoc !== null) {
    levels.push({ price: d.dpoc, label: `${view.live ? "dPOC" : "POC"} ${Math.round(d.dpoc)}`, color: "var(--lv-dpoc)" });
  }
  if (t.nodes && p) {
    p.hvns.forEach((h) => levels.push({ price: h, label: `HVN ${Math.round(h)}`, color: "var(--lv-hvn)", dash: true }));
    p.lvns.forEach((l) => levels.push({ price: l, label: `LVN ${Math.round(l)}`, color: "var(--lv-lvn)", dash: true }));
  }
  if (t.singles && p) {
    p.single_prints.forEach(([lo, hi]) => bands.push({ from: lo, to: hi, color: "var(--sp-band)" }));
  }
  if (t.balance && view.balance) {
    const b = view.balance;
    levels.push(
      { price: b.vah, label: `cVAH ${Math.round(b.vah)}`, color: "var(--lv-bal)", dash: true },
      { price: b.val, label: `cVAL ${Math.round(b.val)}`, color: "var(--lv-bal)", dash: true },
    );
  }
  const markers: Marker[] = view.signals.map((s) => ({
    ts: s.ts.slice(0, 16),
    price: s.entry,
    label: s.setup_id,
    direction: s.direction,
  }));
  return { levels, bands, markers };
}
