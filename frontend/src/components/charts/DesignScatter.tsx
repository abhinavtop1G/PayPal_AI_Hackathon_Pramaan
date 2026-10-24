"use client";

import { useState } from "react";
import { useElementSize } from "@/hooks/useElementSize";
import { ChartTooltip } from "./ChartTooltip";

export interface DesignPoint {
  name: string;
  short: string;
  friction: number;
  stopped: number;
  highlight?: boolean;
}

/**
 * Friction vs protection, one point per design: genuine requests challenged (log scale) against attack requests
 * finally stopped. Top-left is better. Every point is named on the chart (six points), the one the story is about in
 * the accent colour.
 */
export function DesignScatter({ points, height = 300 }: { points: DesignPoint[]; height?: number }) {
  const [ref, { width }] = useElementSize<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const padL = 40, padR = 16, padT = 12, padB = 34;
  const xs = [0.5, 1, 2, 5, 10, 20, 50, 100];
  const lx = (v: number) => Math.log10(Math.max(0.3, v));
  const X = (v: number) => padL + ((lx(v) - lx(0.5)) / (lx(130) - lx(0.5))) * (width - padL - padR);
  const Y = (v: number) => padT + (1 - v / 100) * (height - padT - padB);
  return (
    <div ref={ref} className="chart relative w-full" style={{ height }} onPointerLeave={() => setHover(null)}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label="Genuine requests challenged versus attack requests stopped, per design">
          {[0, 25, 50, 75, 100].map((t) => (
            <g key={t}>
              <line x1={padL} x2={width - padR} y1={Y(t)} y2={Y(t)} stroke={t === 0 ? "var(--color-chart-axis)" : "var(--color-chart-grid)"} />
              <text x={padL - 6} y={Y(t) + 3.5} textAnchor="end" fontSize={10.5} fill="var(--color-chart-muted)">{t}%</text>
            </g>
          ))}
          {xs.map((t) => (
            <text key={t} x={X(t)} y={height - padB + 16} textAnchor="middle" fontSize={10.5} fill="var(--color-chart-muted)">{t}%</text>
          ))}
          <text x={width - padR} y={height - 4} textAnchor="end" fontSize={10.5} fill="var(--color-chart-muted)">genuine requests challenged →</text>
          <text x={padL} y={padT - 2} fontSize={10.5} fill="var(--color-chart-muted)" dx={4} dy={10}>↑ attack requests stopped</text>
          {points.map((p, i) => {
            const x = X(p.friction), y = Y(p.stopped);
            const right = x < width * 0.62;
            return (
              <g key={p.name} onPointerEnter={() => setHover(i)}>
                <circle cx={x} cy={y} r={14} fill="transparent" />
                <circle cx={x} cy={y} r={p.highlight ? 7 : 5} fill={p.highlight ? "var(--color-brand-2)" : "var(--color-gray-1)"}
                  stroke="var(--color-chart-surface)" strokeWidth={2} />
                <text x={x + (right ? 11 : -11)} y={y + 4} textAnchor={right ? "start" : "end"} fontSize={p.highlight ? 12 : 11}
                  fontWeight={p.highlight ? 600 : 400} fill={p.highlight ? "var(--color-label)" : "var(--color-label-secondary)"}>{p.short}</text>
              </g>
            );
          })}
        </svg>
      )}
      {hover !== null && (
        <ChartTooltip x={X(points[hover].friction)} y={Y(points[hover].stopped) - 70} width={width} title={points[hover].name}
          rows={[{ label: "attacks stopped", value: `${points[hover].stopped}%` }, { label: "genuine challenged", value: `${points[hover].friction}%` }]} />
      )}
    </div>
  );
}
