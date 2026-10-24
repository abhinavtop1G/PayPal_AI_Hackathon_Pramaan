"use client";

import { useState } from "react";
import { useElementSize } from "@/hooks/useElementSize";
import { ChartTooltip } from "./ChartTooltip";

export interface ColumnDatum {
  key: string;
  /** x-axis tick text (shown for every `tickEvery`th column) */
  tick: string;
  /** tooltip title */
  title: string;
  /** one value per series, stacked bottom-up in series order */
  values: number[];
}

/** Rect with only the top corners rounded (data end), square at the baseline. */
export function topRounded(x: number, y: number, w: number, h: number, r: number) {
  if (h <= 0) return "";
  const rr = Math.min(r, h, w / 2);
  return `M${x},${y + h}V${y + rr}Q${x},${y} ${x + rr},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h}Z`;
}

function niceMax(v: number) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}

export const compact = (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(v >= 10000 ? 0 : 1).replace(/\.0$/, "")}K` : String(Math.round(v)));

/**
 * Columns over time, one or more series stacked. Thin columns (<= 24 px) with a rounded data end and a 2 px surface
 * gap between stacked segments; hairline grid; the whole column slot is the hover target. Columns past `upTo` are
 * drawn as a faint placeholder (a replay that has not reached them yet).
 */
export function Columns({
  data,
  series,
  height = 180,
  tickEvery = 4,
  upTo,
  format = (v: number) => v.toLocaleString("en-IN"),
  ariaLabel,
}: {
  data: ColumnDatum[];
  series: { name: string; color: string }[];
  height?: number;
  tickEvery?: number;
  upTo?: number;
  format?: (v: number) => string;
  ariaLabel: string;
}) {
  const [ref, { width }] = useElementSize<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const padL = 34, padB = 22, padT = 8;
  const plotW = Math.max(0, width - padL - 4), plotH = height - padB - padT;
  const totals = data.map((d) => d.values.reduce((s, v) => s + v, 0));
  const max = niceMax(Math.max(1, ...totals));
  const slot = data.length ? plotW / data.length : 0;
  const bw = Math.max(2, Math.min(24, slot * 0.62));
  const y = (v: number) => padT + plotH - (v / max) * plotH;
  const ticks = [0, max / 2, max];
  return (
    <div ref={ref} className="chart relative w-full" style={{ height }} onPointerLeave={() => setHover(null)}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label={ariaLabel}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={padL} x2={width - 4} y1={y(t)} y2={y(t)} stroke={t === 0 ? "var(--color-chart-axis)" : "var(--color-chart-grid)"} />
              <text x={padL - 6} y={y(t) + 3.5} textAnchor="end" fontSize={10.5} fill="var(--color-chart-muted)">{compact(t)}</text>
            </g>
          ))}
          {data.map((d, i) => {
            const x = padL + i * slot + (slot - bw) / 2;
            const pending = upTo !== undefined && i > upTo;
            let acc = 0;
            const top = d.values.reduce((last, v, k) => (v > 0 ? k : last), -1);
            return (
              <g key={d.key} opacity={pending ? 0.12 : hover === null || hover === i ? 1 : 0.55}>
                {d.values.map((v, k) => {
                  if (v <= 0) return null;
                  const y0 = y(acc), y1 = y(acc + v);
                  acc += v;
                  const h = Math.max(1, y0 - y1 - (k > 0 ? 2 : 0));
                  return k === top
                    ? <path key={k} d={topRounded(x, y1, bw, h, 4)} fill={series[k].color} />
                    : <rect key={k} x={x} y={y1} width={bw} height={h} fill={series[k].color} />;
                })}
                {i % tickEvery === 0 && (
                  <text x={x + bw / 2} y={height - 6} textAnchor="middle" fontSize={10.5} fill="var(--color-chart-muted)">{d.tick}</text>
                )}
                <rect x={padL + i * slot} y={padT} width={slot} height={plotH} fill="transparent"
                  onPointerEnter={() => setHover(i)} tabIndex={-1} />
              </g>
            );
          })}
        </svg>
      )}
      {hover !== null && data[hover] && (upTo === undefined || hover <= upTo) && (
        <ChartTooltip x={padL + hover * slot + slot / 2} y={padT} width={width} title={data[hover].title}
          rows={[...series.map((s, k) => ({ label: s.name, value: format(data[hover].values[k]), color: s.color })).reverse(),
            ...(series.length > 1 ? [{ label: "total", value: format(totals[hover]) }] : [])]} />
      )}
    </div>
  );
}
