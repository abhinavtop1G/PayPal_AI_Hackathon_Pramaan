"use client";

import { useState } from "react";
import { useElementSize } from "@/hooks/useElementSize";
import { ChartTooltip } from "./ChartTooltip";
import { topRounded } from "./Columns";

const BINS = 24, LO = -6, HI = 0; // log10(risk) from one in a million to certain

/** Downward bar from the baseline at y: square at the baseline, rounded at the data end. */
function bottomRounded(x: number, y: number, w: number, h: number, r: number) {
  const rr = Math.min(r, h, w / 2);
  return `M${x},${y}H${x + w}V${y + h - rr}Q${x + w},${y + h} ${x + w - rr},${y + h}H${x + rr}Q${x},${y + h} ${x},${y + h - rr}Z`;
}

/**
 * How the model separates customers from attackers: share of genuine requests (up) and of attack requests (down) in
 * each risk bin, on one percentage axis (each group sums to 100%, so a small attack count stays readable).
 */
export function RiskHistogram({ genuine, attacks, height = 200 }: { genuine: number[]; attacks: number[]; height?: number }) {
  const [ref, { width }] = useElementSize<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const bin = (p: number) => Math.min(BINS - 1, Math.max(0, Math.floor(((Math.log10(Math.max(p, 1e-6)) - LO) / (HI - LO)) * BINS)));
  const share = (xs: number[]) => {
    const c = new Array(BINS).fill(0);
    xs.forEach((p) => c[bin(p)]++);
    return c.map((v) => (xs.length ? v / xs.length : 0));
  };
  const g = share(genuine), a = share(attacks);
  const max = Math.max(0.05, ...g, ...a);
  const padL = 34, padB = 20, mid = (height - padB) / 2;
  const plotW = Math.max(0, width - padL - 4), slot = plotW / BINS, bw = Math.min(18, slot * 0.7);
  const h = (v: number) => (v / max) * (mid - 6);
  const label = (i: number) => {
    const v = 10 ** (LO + (i * (HI - LO)) / BINS) * 100;
    return `${v >= 1 ? Math.round(v) : Number(v.toPrecision(1))}%`;
  };
  return (
    <div ref={ref} className="chart relative w-full" style={{ height }} onPointerLeave={() => setHover(null)}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label="Risk score distribution of genuine and attack requests">
          <line x1={padL} x2={width - 4} y1={mid} y2={mid} stroke="var(--color-chart-axis)" />
          {[max, max / 2].map((t) => (
            <g key={t}>
              <line x1={padL} x2={width - 4} y1={mid - h(t)} y2={mid - h(t)} stroke="var(--color-chart-grid)" />
              <line x1={padL} x2={width - 4} y1={mid + h(t)} y2={mid + h(t)} stroke="var(--color-chart-grid)" />
              <text x={padL - 6} y={mid - h(t) + 3.5} textAnchor="end" fontSize={10.5} fill="var(--color-chart-muted)">{Math.round(100 * t)}%</text>
              <text x={padL - 6} y={mid + h(t) + 3.5} textAnchor="end" fontSize={10.5} fill="var(--color-chart-muted)">{Math.round(100 * t)}%</text>
            </g>
          ))}
          {g.map((v, i) => {
            const x = padL + i * slot + (slot - bw) / 2;
            const dim = hover !== null && hover !== i ? 0.5 : 1;
            return (
              <g key={i} opacity={dim}>
                {v > 0 && <path d={topRounded(x, mid - h(v) - 1, bw, h(v), 4)} fill="var(--color-series-1)" />}
                {a[i] > 0 && <path d={bottomRounded(x, mid + 1, bw, h(a[i]), 4)} fill="var(--color-series-2)" />}
                <rect x={padL + i * slot} y={0} width={slot} height={height - padB} fill="transparent" onPointerEnter={() => setHover(i)} />
              </g>
            );
          })}
          {[0, 4, 8, 12, 16, 20, 24].map((i) => (
            <text key={i} x={padL + i * slot} y={height - 5} textAnchor={i === 24 ? "end" : "middle"} fontSize={10.5} fill="var(--color-chart-muted)">
              {i === 24 ? "100%" : label(i)}
            </text>
          ))}
        </svg>
      )}
      {hover !== null && (
        <ChartTooltip x={padL + hover * slot + slot / 2} y={8} width={width} title={`risk ${label(hover)} – ${hover === BINS - 1 ? "100%" : label(hover + 1)}`}
          rows={[{ label: "of genuine requests", value: `${(100 * g[hover]).toFixed(1)}%`, color: "var(--color-series-1)" },
            { label: "of attack requests", value: `${(100 * a[hover]).toFixed(1)}%`, color: "var(--color-series-2)" }]} />
      )}
    </div>
  );
}
