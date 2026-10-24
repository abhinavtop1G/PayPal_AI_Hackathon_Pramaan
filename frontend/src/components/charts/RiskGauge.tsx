"use client";

import { motion } from "motion/react";
import { DECISION_STYLE, pct } from "@/config/authSignals";
import { spring } from "@/config/motion";
import type { Decision } from "@/types/auth";

// log-odds scale from 0.001% to 99.9%: everyday payments sit far left, attacks far right, and both stay visible
const LO = Math.log(1e-5 / (1 - 1e-5)), HI = -LO;
const pos = (p: number) => {
  const l = Math.log(Math.max(1e-6, p) / Math.max(1e-6, 1 - p));
  return Math.min(1, Math.max(0, (l - LO) / (HI - LO)));
};

/**
 * Risk on a half-dial (log-odds scale). The fill and number take the decision's status colour; the tick at 50% is the
 * block line (the policy blocks only when an attack is more likely than not; below it, cost decides allow vs challenge).
 */
export function RiskGauge({ risk, decision, size = 220 }: { risk: number; decision: Decision; size?: number }) {
  const r = size / 2 - 14, cx = size / 2, cy = size / 2 + 2;
  const arc = (t: number) => {
    const a = Math.PI * (1 - t);
    return [cx + r * Math.cos(a), cy - r * Math.sin(a)] as const;
  };
  const [x0, y0] = arc(0), [x1, y1] = arc(1);
  const track = `M${x0},${y0} A${r},${r} 0 0 1 ${x1},${y1}`;
  const len = Math.PI * r;
  const t = pos(risk);
  const [bx, by] = arc(0.5);
  const [nx, ny] = arc(t);
  const tint = DECISION_STYLE[decision].tint;
  const k = size / 220, stroke = Math.max(9, 12 * k);
  return (
    <svg width={size} height={size / 2 + 30 * k} viewBox={`0 0 ${size} ${size / 2 + 30 * k}`} role="img" aria-label={`Risk ${pct(risk)}`}>
      <path d={track} fill="none" stroke="var(--color-fill-tertiary)" strokeWidth={stroke} strokeLinecap="round" />
      <motion.path d={track} fill="none" stroke={tint} strokeWidth={stroke} strokeLinecap="round" strokeDasharray={len}
        initial={{ strokeDashoffset: len }} animate={{ strokeDashoffset: len * (1 - Math.max(0.012, t)) }} transition={spring.default} />
      <line x1={bx} y1={by - 10} x2={bx} y2={by + 10} stroke="var(--color-label-tertiary)" strokeWidth={1.5} />
      <text x={bx} y={by - 16} textAnchor="middle" fontSize={10} fill="var(--color-chart-muted)">50%</text>
      <motion.circle r={stroke / 2 + 1} fill={tint} stroke="var(--color-chart-surface)" strokeWidth={3}
        initial={false} animate={{ cx: nx, cy: ny }} transition={spring.default} />
      <text x={cx} y={cy - 14 * k} textAnchor="middle" fontSize={30 * k} fontWeight={700} fill="var(--color-label)" letterSpacing="-0.02em">{pct(risk)}</text>
      <text x={cx} y={cy + 4} textAnchor="middle" fontSize={Math.max(9.5, 11 * k)} fill="var(--color-chart-muted)">risk of account takeover</text>
      {size >= 200 && (
        <>
          <text x={x0 - 6} y={cy + 22} textAnchor="start" fontSize={10} fill="var(--color-chart-muted)">0.001%</text>
          <text x={x1 + 6} y={cy + 22} textAnchor="end" fontSize={10} fill="var(--color-chart-muted)">99.9%</text>
        </>
      )}
    </svg>
  );
}
