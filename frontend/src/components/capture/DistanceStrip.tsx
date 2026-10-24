"use client";

import { useState } from "react";
import { ChartTooltip } from "@/components/charts/ChartTooltip";
import { useElementSize } from "@/hooks/useElementSize";

export interface Group {
  key: string;
  label: string;
  values: number[];
  color: string;
}

/**
 * Distances from one typing profile, one row per group of reference attempts (a dot each), and the new attempt as a
 * vertical marker across all rows: where it lands says whose typing it resembles. Log scale.
 */
export function DistanceStrip({ groups, mine, height }: { groups: Group[]; mine: number | null; height?: number }) {
  const [ref, { width }] = useElementSize<HTMLDivElement>();
  const [hover, setHover] = useState<{ g: string; v: number; x: number; y: number } | null>(null);
  const all = [...groups.flatMap((g) => g.values), ...(mine != null ? [mine] : [])];
  const lo = Math.max(1, Math.min(...all) * 0.8), hi = Math.max(...all) * 1.15;
  const padL = 128, rowH = 26, h = height ?? groups.length * rowH + 24;
  const X = (v: number) => padL + ((Math.log(v) - Math.log(lo)) / (Math.log(hi) - Math.log(lo))) * Math.max(0, width - padL - 10);
  const ticks = [10, 20, 50, 100, 200, 500].filter((t) => t >= lo && t <= hi);
  return (
    <div ref={ref} className="chart relative w-full" style={{ height: h }} onPointerLeave={() => setHover(null)}>
      {width > 0 && (
        <svg width={width} height={h} role="img" aria-label="Distance of the attempt from the profile, compared with reference attempts">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={X(t)} x2={X(t)} y1={0} y2={h - 18} stroke="var(--color-chart-grid)" />
              <text x={X(t)} y={h - 4} textAnchor="middle" fontSize={10} fill="var(--color-chart-muted)">{t}</text>
            </g>
          ))}
          {groups.map((g, i) => (
            <g key={g.key}>
              <text x={0} y={i * rowH + rowH / 2 + 4} fontSize={11.5} fill="var(--color-label-secondary)">{g.label}</text>
              {g.values.map((v, k) => (
                <circle key={k} cx={X(v)} cy={i * rowH + rowH / 2} r={4} fill={g.color} stroke="var(--color-chart-surface)" strokeWidth={1.5}
                  opacity={0.85} onPointerEnter={() => setHover({ g: g.label, v, x: X(v), y: i * rowH })} />
              ))}
            </g>
          ))}
          {mine != null && (
            <g>
              <rect x={X(mine) - 1} y={0} width={2} height={h - 18} rx={1} fill="var(--color-label)" />
              <text x={X(mine)} y={10} dx={X(mine) > width - 90 ? -6 : 6} textAnchor={X(mine) > width - 90 ? "end" : "start"} fontSize={11} fontWeight={600} fill="var(--color-label)">
                you · {mine.toFixed(0)}
              </text>
            </g>
          )}
        </svg>
      )}
      {hover && <ChartTooltip x={hover.x} y={hover.y} width={width} rows={[{ label: hover.g, value: hover.v.toFixed(1) }]} />}
    </div>
  );
}
