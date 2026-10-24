"use client";

import { motion } from "motion/react";
import { DECISION_STYLE, inr } from "@/config/authSignals";
import { spring } from "@/config/motion";
import type { AuthResponse, Decision } from "@/types/auth";

const WHY: Record<Decision, string> = {
  allow: "risk × amount: fraud that would get through",
  challenge: "fraud the step-up would miss + the customer's friction",
  block: "a genuine payment refused (only when attack is more likely than not)",
};

/**
 * Why this action: the policy's expected cost (₹) of each one for this request; it takes the cheapest, unless a hard
 * rule applies. Bars are on a log scale because the three often differ by orders of magnitude.
 */
export function ExpectedCost({ response }: { response: AuthResponse }) {
  const ec = response.expected_cost ?? {};
  const keys = (["allow", "challenge", "block"] as Decision[]).filter((k) => k in ec);
  if (!keys.length) return null;
  const vals = keys.map((k) => ec[k]);
  const max = Math.log10(1 + Math.max(1, ...vals.filter((v): v is number => v != null)));
  const cheapest = keys.reduce((a, k) => ((ec[k] ?? Infinity) < (ec[a] ?? Infinity) ? k : a), keys[0]);
  return (
    <div>
      <ul className="space-y-2.5">
        {keys.map((k) => {
          const v = ec[k];
          const on = k === response.decision;
          return (
            <li key={k}>
              <div className="mb-1 flex items-baseline justify-between gap-3 text-footnote">
                <span className={on ? "font-semibold" : "text-label-secondary"}>
                  {DECISION_STYLE[k].label}{on ? " ← chosen" : ""}
                </span>
                <span className="font-mono tabular-nums">{v == null ? "not allowed" : inr(v)}</span>
              </div>
              <div className="relative h-2 rounded-r-[4px] bg-fill-quaternary">
                {v != null && (
                  <motion.span className="absolute inset-y-0 left-0 rounded-r-[4px]" initial={{ width: 0 }}
                    animate={{ width: `${Math.max(1.5, (100 * Math.log10(1 + v)) / max)}%` }} transition={spring.default}
                    style={{ background: on ? DECISION_STYLE[k].tint : "var(--color-gray-2)" }} />
                )}
              </div>
              <p className="mt-0.5 text-caption-2 text-label-tertiary">{WHY[k]}</p>
            </li>
          );
        })}
      </ul>
      {response.rule ? (
        <p className="mt-3 rounded-[0.6rem] bg-fill-quaternary px-2.5 py-1.5 text-caption-1 text-label-secondary">
          Hard rule <span className="font-mono text-label">{response.rule}</span> overrides the cheapest option ({cheapest}).
        </p>
      ) : (
        <p className="mt-3 text-caption-2 text-label-tertiary">Log scale. Efficacies and friction costs are policy assumptions (ml/auth/policy.py).</p>
      )}
    </div>
  );
}
