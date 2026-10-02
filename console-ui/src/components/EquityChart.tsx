import { useRef, useState } from "react";
import { fmtR } from "../format";

interface Point {
  n: number;
  date: string;
  cum_r: number;
}

const W = 900;

export function EquityChart({ points, height = 220 }: { points: Point[]; height?: number }) {
  const H = height;
  const ref = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  if (!points.length) return <div className="empty">No directional trades yet.</div>;
  const pad = { l: 46, r: 12, t: 12, b: 22 };
  const vals = points.map((p) => p.cum_r);
  const lo = Math.min(0, ...vals);
  const hi = Math.max(0, ...vals);
  const span = hi - lo || 1;
  const x = (i: number) => pad.l + (points.length === 1 ? 0.5 : i / (points.length - 1)) * (W - pad.l - pad.r);
  const y = (v: number) => pad.t + ((hi - v) / span) * (H - pad.t - pad.b);
  const line = points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.cum_r)}`).join(" ");
  const area = `${line} L${x(points.length - 1)},${y(0)} L${x(0)},${y(0)} Z`;
  const last = points[points.length - 1].cum_r;
  const hp = hover !== null ? points[hover] : null;

  return (
    <svg ref={ref} className={`equity-chart ${last >= 0 ? "pos" : "neg"}`} viewBox={`0 0 ${W} ${H}`} role="img"
      aria-label="Cumulative R equity curve"
      onMouseMove={(e) => {
        const rect = ref.current?.getBoundingClientRect();
        if (!rect) return;
        const sx = ((e.clientX - rect.left) * W) / rect.width;
        const t = (sx - pad.l) / (W - pad.l - pad.r);
        setHover(Math.min(points.length - 1, Math.max(0, Math.round(t * (points.length - 1)))));
      }}
      onMouseLeave={() => setHover(null)}>
      {[hi, (hi + lo) / 2, lo].map((v) => (
        <g key={v}>
          <line className="grid" x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} />
          <text className="axis-text" x={4} y={y(v) + 4}>{fmtR(v)}</text>
        </g>
      ))}
      <line className="zero" x1={pad.l} x2={W - pad.r} y1={y(0)} y2={y(0)} />
      <path className="eq-area" d={area} />
      <path className="eq-line" d={line} />
      {hp && hover !== null && (
        <g>
          <circle className="eq-dot" cx={x(hover)} cy={y(hp.cum_r)} r={4} />
          <text className="tooltip-text strong" x={Math.min(x(hover) + 8, W - 150)} y={pad.t + 14}>
            #{hp.n} {hp.date} {fmtR(hp.cum_r)}
          </text>
        </g>
      )}
    </svg>
  );
}
