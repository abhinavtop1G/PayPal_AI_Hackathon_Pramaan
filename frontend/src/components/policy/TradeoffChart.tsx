"use client";

import { useState } from "react";
import { ChartTooltip } from "@/components/charts/ChartTooltip";
import { useElementSize } from "@/hooks/useElementSize";

interface Pt {
  friction: number;
  stopped: number;
}

/**
 * The trade-off one policy knob traces: genuine requests challenged (log scale) against attack requests stopped, as
 * the friction cost moves from cheap to dear. Points: the service's setting, the tuned one, and an SMS OTP on every
 * payment for reference. One axis each; points named on the chart.
 */
export function TradeoffChart({ curve, current, service, otp, height = 300 }: {
  curve: (Pt & { frictionX: number })[];
  current: Pt;
  service: Pt;
  otp: Pt;
  height?: number;
}) {
  const [ref, { width }] = useElementSize<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const padL = 40, padR = 16, padT = 14, padB = 34;
  const lo = 0.1, hi = 130;
  const lx = (v: number) => Math.log10(Math.min(hi, Math.max(lo, v)));
  const X = (v: number) => padL + ((lx(v) - lx(lo)) / (lx(hi) - lx(lo))) * (width - padL - padR);
  const Y = (v: number) => padT + (1 - v / 100) * (height - padT - padB);
  const path = curve.map((p, i) => `${i ? "L" : "M"}${X(p.friction).toFixed(1)},${Y(p.stopped).toFixed(1)}`).join("");
  const dot = (p: Pt, label: string, color: string, r: number, right = true, dy = 4) => (
    <g>
      <circle cx={X(p.friction)} cy={Y(p.stopped)} r={r} fill={color} stroke="var(--color-chart-surface)" strokeWidth={2} />
      {label && (
        <text x={X(p.friction) + (right ? r + 6 : -(r + 6))} y={Y(p.stopped) + dy} textAnchor={right ? "start" : "end"} fontSize={11.5}
          fontWeight={600} fill="var(--color-label)">{label}</text>
      )}
    </g>
  );
  // the tuned and service points often coincide or sit close: one label then, otherwise one above and one below
  const same = width > 0 && Math.abs(X(current.friction) - X(service.friction)) < 40 && Math.abs(Y(current.stopped) - Y(service.stopped)) < 16;
  const exact = Math.abs(current.friction - service.friction) < 1e-9 && Math.abs(current.stopped - service.stopped) < 1e-9;
  return (
    <div ref={ref} className="chart relative w-full" style={{ height }} onPointerLeave={() => setHover(null)}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label="Genuine requests challenged versus attack requests stopped as the friction cost changes">
          {[0, 25, 50, 75, 100].map((t) => (
            <g key={t}>
              <line x1={padL} x2={width - padR} y1={Y(t)} y2={Y(t)} stroke={t === 0 ? "var(--color-chart-axis)" : "var(--color-chart-grid)"} />
              <text x={padL - 6} y={Y(t) + 3.5} textAnchor="end" fontSize={10.5} fill="var(--color-chart-muted)">{t}%</text>
            </g>
          ))}
          {[0.1, 0.5, 1, 2, 5, 10, 20, 50, 100].map((t) => (
            <text key={t} x={X(t)} y={height - padB + 16} textAnchor="middle" fontSize={10.5} fill="var(--color-chart-muted)">{t}%</text>
          ))}
          <text x={width - padR} y={height - 4} textAnchor="end" fontSize={10.5} fill="var(--color-chart-muted)">genuine requests challenged →</text>
          <text x={padL + 4} y={padT + 10} fontSize={10.5} fill="var(--color-chart-muted)">↑ attack requests stopped (expected)</text>
          <path d={path} fill="none" stroke="var(--color-series-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          {curve.map((p, i) => (
            <circle key={i} cx={X(p.friction)} cy={Y(p.stopped)} r={10} fill="transparent" onPointerEnter={() => setHover(i)} />
          ))}
          {hover !== null && <circle cx={X(curve[hover].friction)} cy={Y(curve[hover].stopped)} r={4} fill="var(--color-series-1)" stroke="var(--color-chart-surface)" strokeWidth={2} />}
          {dot(otp, "SMS OTP on every payment", "var(--color-series-2)", 5, false)}
          {dot(service, same ? "" : "service setting", "var(--color-gray-1)", 5, service.friction < 20, 18)}
          {dot(current, same ? (exact ? "your setting = the service's" : "your setting (near the service's)") : "your setting",
            "var(--color-brand-2)", 7, current.friction < 20, same ? 4 : -10)}
        </svg>
      )}
      {hover !== null && (
        <ChartTooltip x={X(curve[hover].friction)} y={Y(curve[hover].stopped) - 70} width={width} title={`friction × ${curve[hover].frictionX.toFixed(2)}`}
          rows={[{ label: "attacks stopped", value: `${curve[hover].stopped.toFixed(1)}%`, color: "var(--color-series-1)" },
            { label: "genuine challenged", value: `${curve[hover].friction.toFixed(2)}%` }]} />
      )}
    </div>
  );
}
