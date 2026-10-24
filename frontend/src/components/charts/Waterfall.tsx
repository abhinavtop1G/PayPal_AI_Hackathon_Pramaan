"use client";

import { motion } from "motion/react";
import { FAMILY_TINT, SIGNAL_LABEL, pct, showValue } from "@/config/authSignals";
import { spring } from "@/config/motion";
import type { AuthResponse } from "@/types/auth";

const sigmoid = (x: number) => 1 / (1 + Math.exp(-x));
const logit = (p: number) => Math.log(Math.max(1e-9, p) / Math.max(1e-9, 1 - p));
const TICKS = [0.0001, 0.001, 0.01, 0.1, 0.5, 0.9, 0.99];

function Row({ label, sub, children, value, grid }: {
  label: React.ReactNode; sub?: string; children: React.ReactNode; value: string; grid: string[];
}) {
  return (
    <div className="grid grid-cols-[minmax(0,10.5rem)_1fr_3.25rem] items-center gap-3 py-[5px]">
      <div className="min-w-0">
        <p className="truncate text-footnote">{label}</p>
        {sub ? <p className="truncate font-mono text-caption-2 text-label-tertiary">{sub}</p> : null}
      </div>
      <div className="relative h-3.5">
        {grid.map((left) => <span key={left} className="absolute inset-y-[-6px] w-px bg-[var(--color-chart-grid)]" style={{ left }} aria-hidden />)}
        {children}
      </div>
      <span className="text-right font-mono text-caption-1 tabular-nums text-label-secondary">{value}</span>
    </div>
  );
}

/**
 * The decision as a SHAP waterfall on one log-odds axis (ticks labelled as risk): from the base rate, each signal
 * pushes the score right (more risk, family colour) or left (less, gray), the rest are summed, and the bar ends at the
 * risk the policy saw. Exact tree-SHAP: the contributions add up to the score.
 */
export function Waterfall({ response, top = 7 }: { response: AuthResponse; top?: number }) {
  const sigs = [...response.signals].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution));
  const shown = sigs.slice(0, top).filter((s) => Math.abs(s.contribution) >= 0.01);
  const restSum = sigs.slice(shown.length).reduce((s, x) => s + x.contribution, 0);
  const final = logit(response.risk_score);
  const base = response.base_logit ?? final - sigs.reduce((s, x) => s + x.contribution, 0);

  const steps: { key: string; label: string; sub: string; from: number; to: number; v: number; color: string }[] = [];
  let acc = base;
  for (const s of shown) {
    steps.push({ key: s.name, label: SIGNAL_LABEL[s.name] ?? s.name, sub: showValue(s.name, s.value), from: acc, to: acc + s.contribution,
      v: s.contribution, color: s.contribution >= 0 ? FAMILY_TINT[s.family] : "var(--color-gray-2)" });
    acc += s.contribution;
  }
  if (Math.abs(restSum) >= 0.005) {
    steps.push({ key: "rest", label: `${sigs.length - shown.length} other signals`, sub: "", from: acc, to: acc + restSum, v: restSum,
      color: restSum >= 0 ? "var(--color-gray-1)" : "var(--color-gray-2)" });
  }
  const pts = [base, final, ...steps.flatMap((s) => [s.from, s.to])];
  const lo = Math.min(...pts) - 0.6, hi = Math.max(...pts) + 0.6;
  const X = (v: number) => `${(100 * (v - lo)) / (hi - lo)}%`;
  const W = (a: number, b: number) => `${Math.max(0.6, (100 * Math.abs(b - a)) / (hi - lo))}%`;
  const ticks = TICKS.filter((p) => logit(p) > lo && logit(p) < hi);
  const grid = ticks.map((p) => X(logit(p)));

  return (
    <div className="chart" role="img" aria-label={`Risk from ${pct(sigmoid(base))} base to ${pct(response.risk_score)}`}>
      <Row grid={grid} label={<span className="text-label-secondary">Base rate (no signals)</span>} value={pct(sigmoid(base))}>
        <span className="absolute inset-y-0 w-[3px] -translate-x-1/2 rounded-full bg-label-tertiary" style={{ left: X(base) }} />
      </Row>
      {steps.map((s, i) => (
        <Row grid={grid} key={s.key} label={s.label} sub={s.sub} value={`${s.v > 0 ? "+" : ""}${s.v.toFixed(2)}`}>
          <motion.span className="absolute inset-y-0 rounded-[4px]" style={{ background: s.color, left: X(Math.min(s.from, s.to)) }}
            initial={{ width: 0 }} animate={{ width: W(s.from, s.to) }} transition={{ ...spring.default, delay: 0.04 * i }} />
        </Row>
      ))}
      <div className="mt-1 border-t border-separator/60 pt-1">
        <Row grid={grid} label={<span className="font-semibold">Risk the policy saw</span>} value={pct(response.risk_score)}>
          <span className="absolute inset-y-0 left-0 rounded-[4px] bg-fill-tertiary" style={{ width: X(final) }} />
          <span className="absolute inset-y-[-3px] w-[3px] -translate-x-1/2 rounded-full bg-label" style={{ left: X(final) }} />
        </Row>
      </div>
      <div className="relative ml-[calc(10.5rem+0.75rem)] mr-[calc(3.25rem+0.75rem)] mt-1 h-4">
        {ticks.map((p) => (
          <span key={p} className="absolute -translate-x-1/2 text-[10.5px] text-[var(--color-chart-muted)] tabular-nums" style={{ left: X(logit(p)) }}>
            {p < 0.01 ? `${100 * p}%` : `${Math.round(100 * p)}%`}
          </span>
        ))}
      </div>
    </div>
  );
}
