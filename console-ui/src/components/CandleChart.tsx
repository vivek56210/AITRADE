import { useMemo, useRef, useState } from "react";
import type { MouseEvent } from "react";
import type { BarRow } from "../types";
import { fmt } from "../format";

export interface Level {
  price: number;
  label: string;
  color: string;
  dash?: boolean;
}

export interface Band {
  from: number;
  to: number;
  color: string;
}

export interface Marker {
  ts: string;
  price: number;
  label: string;
  direction: string;
}

interface Props {
  bars: BarRow[];
  slots?: number;
  levels?: Level[];
  bands?: Band[];
  profile?: [number, number][];
  priorProfile?: [number, number][];
  markers?: Marker[];
  height?: number;
}

const W = 1100;
const PAD_T = 14;
const PAD_B = 24;
const AXIS_W = 86;
const PROFILE_W = 130;
const GAP = 8;
const X0 = 4;
const X1 = W - AXIS_W - PROFILE_W - GAP;
const PX0 = X1 + GAP;
const AX0 = PX0 + PROFILE_W + 4;

function niceStep(range: number, ticks = 6): number {
  const raw = range / ticks;
  const mag = 10 ** Math.floor(Math.log10(raw || 1));
  return [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
}

function rowSize(profile: [number, number][]): number {
  let best = Infinity;
  for (let i = 1; i < profile.length; i++) best = Math.min(best, profile[i][0] - profile[i - 1][0]);
  return Number.isFinite(best) && best > 0 ? best : 1;
}

export function CandleChart({ bars, slots, levels = [], bands = [], profile = [], priorProfile = [], markers = [], height = 440 }: Props) {
  const H = height;
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<{ i: number; price: number } | null>(null);

  const { lo, hi } = useMemo(() => {
    const ps: number[] = [];
    for (const b of bars) ps.push(b[2], b[3]);
    for (const l of levels) ps.push(l.price);
    if (!ps.length) return { lo: 0, hi: 1 };
    const mn = Math.min(...ps);
    const mx = Math.max(...ps);
    const pad = Math.max((mx - mn) * 0.04, 1);
    return { lo: mn - pad, hi: mx + pad };
  }, [bars, levels]);

  const plotH = H - PAD_T - PAD_B;
  const y = (p: number) => PAD_T + ((hi - p) / (hi - lo)) * plotH;
  const n = Math.max(slots ?? 0, bars.length, 1);
  const cw = (X1 - X0) / n;
  const step = niceStep(hi - lo);
  const ticks: number[] = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) ticks.push(t);

  const onMove = (e: MouseEvent<SVGSVGElement>) => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect || !bars.length) return;
    const sx = ((e.clientX - rect.left) * W) / rect.width;
    const sy = ((e.clientY - rect.top) * H) / rect.height;
    if (sx < X0 || sx > X1 || sy < PAD_T || sy > H - PAD_B) return setHover(null);
    const i = Math.min(bars.length - 1, Math.max(0, Math.floor((sx - X0) / cw)));
    setHover({ i, price: hi - ((sy - PAD_T) / plotH) * (hi - lo) });
  };

  const drawProfile = (rows: [number, number][], cls: string) => {
    if (!rows.length) return null;
    const rs = rowSize(rows);
    const maxV = Math.max(...rows.map((r) => r[1])) || 1;
    return rows.map(([p, v]) => {
      const top = y(p + rs);
      return (
        <rect key={`${cls}${p}`} className={cls} x={PX0} y={top} width={(v / maxV) * PROFILE_W}
          height={Math.max(1, y(p) - top - 0.3)} />
      );
    });
  };

  const hb = hover ? bars[hover.i] : null;

  return (
    <svg ref={svgRef} className="candle-chart" viewBox={`0 0 ${W} ${H}`} role="img"
      aria-label="Futures price chart with volume profile" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
      {ticks.map((t) => (
        <g key={t}>
          <line className="grid" x1={X0} x2={X1} y1={y(t)} y2={y(t)} />
          <text className="axis-text" x={AX0} y={y(t) + 4}>{fmt(t, 0)}</text>
        </g>
      ))}
      {bars.map((b, i) =>
        b[0].slice(14, 16) === "15" && (i === 0 || bars[i - 1][0].slice(11, 13) !== b[0].slice(11, 13)) ? (
          <g key={`t${i}`}>
            <line className="grid" x1={X0 + i * cw} x2={X0 + i * cw} y1={PAD_T} y2={H - PAD_B} />
            <text className="axis-text" x={X0 + i * cw + 2} y={H - 7}>{b[0].slice(11, 16)}</text>
          </g>
        ) : null,
      )}
      {bands.map((b, i) => (
        <rect key={`b${i}`} x={X0} width={X1 - X0} y={y(Math.max(b.from, b.to))}
          height={Math.max(1, Math.abs(y(b.from) - y(b.to)))} style={{ fill: b.color }} />
      ))}
      {drawProfile(priorProfile, "prof-prior")}
      {drawProfile(profile, "prof-live")}
      {bars.map(([ts, o, h, l, c], i) => {
        const cx = X0 + (i + 0.5) * cw;
        const up = c >= o;
        return (
          <g key={ts} className={up ? "c-up" : "c-down"}>
            <line x1={cx} x2={cx} y1={y(h)} y2={y(l)} />
            {cw >= 2.5 && (
              <rect x={cx - cw * 0.35} width={cw * 0.7} y={y(Math.max(o, c))} height={Math.max(0.8, Math.abs(y(o) - y(c)))} />
            )}
          </g>
        );
      })}
      {levels.map((l) => (
        <g key={`${l.label}${l.price}`}>
          <line x1={X0} x2={PX0 + PROFILE_W} y1={y(l.price)} y2={y(l.price)} style={{ stroke: l.color }}
            strokeDasharray={l.dash ? "5 4" : undefined} className="level" />
          <rect x={AX0 - 2} y={y(l.price) - 8} width={AXIS_W - 2} height={16} rx={3} style={{ fill: l.color }} />
          <text className="level-text" x={AX0 + 2} y={y(l.price) + 4}>{l.label}</text>
        </g>
      ))}
      {markers.map((m) => {
        let i = -1;
        for (let k = 0; k < bars.length; k++) if (bars[k][0] < m.ts) i = k;
        if (i < 0) return null;
        const cx = X0 + (i + 0.5) * cw;
        const cy = y(m.price);
        const long = m.direction === "long";
        const short = m.direction === "short";
        const path = long
          ? `M${cx},${cy + 4} l-7,12 l14,0 z`
          : short
            ? `M${cx},${cy - 4} l-7,-12 l14,0 z`
            : `M${cx - 6},${cy} a6,6 0 1,0 12,0 a6,6 0 1,0 -12,0`;
        return (
          <g key={`${m.ts}${m.label}`} className={`marker ${m.direction}`}>
            <path d={path} />
            <text x={cx} y={long ? cy + 28 : cy - 20} textAnchor="middle">{m.label}</text>
          </g>
        );
      })}
      {hover && hb && (
        <g className="crosshair">
          <line x1={X0 + (hover.i + 0.5) * cw} x2={X0 + (hover.i + 0.5) * cw} y1={PAD_T} y2={H - PAD_B} />
          <line x1={X0} x2={X1} y1={y(hover.price)} y2={y(hover.price)} />
          <rect x={AX0 - 2} y={y(hover.price) - 8} width={AXIS_W - 2} height={16} rx={3} className="cross-tag" />
          <text className="level-text" x={AX0 + 2} y={y(hover.price) + 4}>{fmt(hover.price, 1)}</text>
          <g transform={`translate(${Math.min(X0 + (hover.i + 0.5) * cw + 10, X1 - 190)}, ${PAD_T + 4})`}>
            <rect width={180} height={58} rx={6} className="tooltip-bg" />
            <text className="tooltip-text" x={8} y={17}>{hb[0].replace("T", " ")}</text>
            <text className="tooltip-text" x={8} y={33}>O {fmt(hb[1])}  H {fmt(hb[2])}</text>
            <text className="tooltip-text" x={8} y={49}>L {fmt(hb[3])}  C {fmt(hb[4])}  V {fmt(hb[5], 0)}</text>
          </g>
        </g>
      )}
      <line className="axis" x1={X1} x2={X1} y1={PAD_T} y2={H - PAD_B} />
    </svg>
  );
}
