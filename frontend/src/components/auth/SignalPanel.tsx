"use client";

import { motion } from "motion/react";
import { Activity } from "lucide-react";
import { Panel } from "@/components/layout/Panel";
import { FAMILY_LABEL, FAMILY_TINT, SIGNAL_LABEL, showValue } from "@/config/authSignals";
import { spring } from "@/config/motion";
import type { AuthResponse, Family } from "@/types/auth";

/** Why the model decided: each family's share of the risk (log-odds) and the strongest individual signals, both from
 *  exact tree-SHAP contributions. Bars to the right raise risk, to the left lower it. */
export function SignalPanel({ response }: { response: AuthResponse | null }) {
  const fam = response?.family_contribution;
  const top = response ? [...response.signals].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution)).slice(0, 9) : [];
  const scale = Math.max(1, ...top.map((s) => Math.abs(s.contribution)), ...Object.values(fam ?? {}).map(Math.abs));
  return (
    <Panel eyebrow="Explainability · tree-SHAP" title="Signals behind the decision" icon={Activity} tint="var(--color-sys-purple)">
      {!response ? (
        <p className="text-footnote text-label-tertiary">Run a scenario to see its signals.</p>
      ) : (
        <div className="space-y-5">
          <div className="space-y-2">
            {(Object.keys(FAMILY_LABEL) as Family[]).map((f) => (
              <Bar key={f} label={FAMILY_LABEL[f]} value={fam?.[f] ?? 0} scale={scale} tint={FAMILY_TINT[f]} bold />
            ))}
          </div>
          <div>
            <p className="mb-2 text-eyebrow text-label-tertiary">Strongest signals</p>
            <div className="space-y-1.5">
              {top.map((s) => (
                <Bar key={s.name} label={SIGNAL_LABEL[s.name] ?? s.name} sub={showValue(s.name, s.value)} value={s.contribution}
                  scale={scale} tint={FAMILY_TINT[s.family]} />
              ))}
            </div>
          </div>
          <p className="text-caption-2 text-label-tertiary">
            Contributions in log-odds. Monotone model: a signal can only push risk up as it gets worse, so no signal can
            argue for an attacker.
          </p>
        </div>
      )}
    </Panel>
  );
}

function Bar({ label, sub, value, scale, tint, bold }: { label: string; sub?: string; value: number; scale: number; tint: string; bold?: boolean }) {
  const w = Math.min(50, (50 * Math.abs(value)) / scale);
  return (
    <div className="grid grid-cols-[minmax(0,11rem)_1fr_3rem] items-center gap-2">
      <div className="min-w-0">
        <p className={`truncate ${bold ? "text-subheadline font-semibold" : "text-footnote"}`} title={label}>{label}</p>
        {sub && <p className="truncate font-mono text-caption-2 text-label-tertiary">{sub}</p>}
      </div>
      <div className="relative h-2.5 rounded-full bg-fill-quaternary">
        <span className="absolute inset-y-0 left-1/2 w-px bg-separator" aria-hidden />
        <motion.span
          className="absolute inset-y-0 rounded-full"
          style={{ background: value >= 0 ? tint : "var(--color-gray-2)", [value >= 0 ? "left" : "right"]: "50%" }}
          initial={{ width: 0 }}
          animate={{ width: `${w}%` }}
          transition={spring.default}
        />
      </div>
      <span className={`text-right font-mono text-caption-1 ${value > 0.05 ? "text-label" : "text-label-tertiary"}`}>
        {value > 0 ? "+" : ""}{value.toFixed(2)}
      </span>
    </div>
  );
}
