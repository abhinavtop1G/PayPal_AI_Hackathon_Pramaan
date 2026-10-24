"use client";

import { useElementSize } from "@/hooks/useElementSize";

/** Key presses (ms from the first key) recovered from an attempt's timings: down_i+1 = down_i + DD_i, up = down + H. */
export function keysFromTimings(t: number[]): { down: number; up: number }[] {
  const n = (t.length + 2) / 3;
  const keys: { down: number; up: number }[] = [];
  let down = 0;
  for (let i = 0; i < n; i++) {
    const hold = i < n - 1 ? t[3 * i] : t[t.length - 1];
    keys.push({ down: 1000 * down, up: 1000 * (down + hold) });
    if (i < n - 1) down += t[3 * i + 1];
  }
  return keys;
}

/**
 * A piano roll of one password attempt: a bar per key from press to release, on one time axis, with the reference
 * rhythm (the profile's mean timings) as a ghost bar behind each key.
 */
export function KeyRoll({ attempt, reference, labels, color = "var(--color-series-1)" }: {
  attempt: number[];
  reference?: number[];
  labels: string[];
  color?: string;
}) {
  const [ref, { width }] = useElementSize<HTMLDivElement>();
  const a = keysFromTimings(attempt), r = reference ? keysFromTimings(reference) : null;
  const end = Math.max(...a.map((k) => k.up), ...(r ?? []).map((k) => k.up), 1);
  const padL = 30, rowH = 15, height = a.length * rowH + 22;
  const X = (ms: number) => padL + (ms / end) * Math.max(0, width - padL - 8);
  const step = end > 3000 ? 1000 : end > 1200 ? 500 : 250;
  return (
    <div ref={ref} className="chart w-full" style={{ height }}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label="Key presses of the attempt over time">
          {Array.from({ length: Math.floor(end / step) + 1 }, (_, i) => i * step).map((ms) => (
            <g key={ms}>
              <line x1={X(ms)} x2={X(ms)} y1={0} y2={height - 18} stroke="var(--color-chart-grid)" />
              <text x={X(ms)} y={height - 5} textAnchor="middle" fontSize={10} fill="var(--color-chart-muted)">{ms === 0 ? "0" : `${ms / 1000}s`}</text>
            </g>
          ))}
          {a.map((k, i) => (
            <g key={i}>
              <text x={0} y={i * rowH + 11} fontSize={10.5} fontFamily="var(--font-mono)" fill="var(--color-label-secondary)">{labels[i] ?? ""}</text>
              {r && <rect x={X(r[i].down)} y={i * rowH + 2} width={Math.max(2, X(r[i].up) - X(r[i].down))} height={rowH - 5} rx={3}
                fill="none" stroke="var(--color-label-tertiary)" strokeWidth={1} strokeDasharray="0" opacity={0.7} />}
              <rect x={X(k.down)} y={i * rowH + 3.5} width={Math.max(2, X(k.up) - X(k.down))} height={rowH - 8} rx={3} fill={color} />
            </g>
          ))}
        </svg>
      )}
    </div>
  );
}
