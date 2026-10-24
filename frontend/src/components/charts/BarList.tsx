"use client";

import { motion } from "motion/react";
import { spring } from "@/config/motion";

export interface BarRow {
  key: string;
  label: React.ReactNode;
  value: number;
  /** text at the bar's tip (default: the value) */
  display?: string;
  color?: string;
  sub?: React.ReactNode;
  /** a second, lighter bar behind the first on the same scale (e.g. at risk vs stopped) */
  ghost?: number;
}

/**
 * Horizontal bars with the label above and the value at the tip. One colour unless rows carry their own (identity,
 * e.g. signal family); 4 px rounded data end, square at the baseline.
 */
export function BarList({ rows, max, thickness = 8, ariaLabel }: { rows: BarRow[]; max?: number; thickness?: number; ariaLabel: string }) {
  const m = max ?? Math.max(1e-9, ...rows.map((r) => Math.max(r.value, r.ghost ?? 0)));
  return (
    <ul className="space-y-2.5" aria-label={ariaLabel}>
      {rows.map((r) => (
        <li key={r.key}>
          <div className="mb-1 flex items-baseline justify-between gap-3">
            <span className="min-w-0 truncate text-footnote">{r.label}</span>
            <span className="shrink-0 text-footnote font-semibold tabular-nums">{r.display ?? r.value.toLocaleString("en-IN")}</span>
          </div>
          <div className="relative rounded-r-[4px]" style={{ height: thickness }}>
            <span className="absolute inset-0 rounded-r-[4px] bg-fill-quaternary" aria-hidden />
            {r.ghost !== undefined && (
              <span className="absolute inset-y-0 left-0 rounded-r-[4px] opacity-30"
                style={{ width: `${(100 * r.ghost) / m}%`, background: r.color ?? "var(--color-series-1)" }} aria-hidden />
            )}
            <motion.span className="absolute inset-y-0 left-0 rounded-r-[4px]" style={{ background: r.color ?? "var(--color-series-1)" }}
              initial={false} animate={{ width: `${Math.max(r.value > 0 ? 0.8 : 0, (100 * r.value) / m)}%` }} transition={spring.default} />
          </div>
          {r.sub && <p className="mt-0.5 text-caption-2 text-label-tertiary">{r.sub}</p>}
        </li>
      ))}
    </ul>
  );
}
