"use client";

import { motion } from "motion/react";
import { Binary, BrainCircuit, Fingerprint, Keyboard, Landmark, Lock, Scale, Smartphone, type LucideIcon } from "lucide-react";
import { DECISION_STYLE } from "@/config/authSignals";
import type { DemoRun } from "@/types/auth";

interface Stage {
  key: string;
  label: string;
  detail: string;
  icon: LucideIcon;
  ms?: number;
  skipped?: boolean;
}

/**
 * The request's path through the service, lit stage by stage: what the SDK sent, the gateway, the three enrichment
 * models (each skipped when its input is missing), features, the model with exact SHAP, the policy. Stage times come
 * from the service's own timings_ms.
 */
export function PipelineTrace({ run }: { run: DemoRun }) {
  const r = run.response, b = run.request.behaviour, t = r.timings_ms ?? {};
  const stages: Stage[] = [
    { key: "sdk", label: "SDK", detail: `${run.request.channel} · ${run.request.device.platform ?? "web"}`, icon: Smartphone },
    { key: "gw", label: "Gateway", detail: "key · HMAC · replay · rate", icon: Lock },
    { key: "touch", label: "Touch BiLSTM", detail: b.gestures ? "10 gestures vs profile" : "no touch data", icon: Fingerprint, ms: t.touch, skipped: !b.gestures },
    { key: "typing", label: "Typing CNN", detail: b.keystrokes ? "31 timings vs profile" : "no typing data", icon: Keyboard, ms: t.typing, skipped: !b.keystrokes },
    { key: "payee", label: "Payee intel", detail: r.features.payee_risk != null ? `risk ${r.features.payee_risk.toFixed(2)}` : "account unknown", icon: Landmark, ms: t.payee },
    { key: "features", label: "27 features", detail: "live state, causal", icon: Binary, ms: t.features },
    { key: "model", label: "XGBoost + SHAP", detail: "monotone, exact", icon: BrainCircuit, ms: t.model },
    { key: "policy", label: "Policy", detail: r.challenge_type ? r.challenge_type.replace("_", " ") : r.decision, icon: Scale, ms: t.policy },
  ];
  const tint = DECISION_STYLE[r.decision].tint;
  return (
    <ol className="grid grid-cols-2 gap-1.5 sm:grid-cols-4" aria-label="Decision pipeline">
      {stages.map((s, i) => (
        <motion.li key={`${r.decision_id}-${s.key}`}
          initial={{ opacity: 0.25, y: 4 }} animate={{ opacity: s.skipped ? 0.45 : 1, y: 0 }} transition={{ delay: 0.07 * i, duration: 0.25 }}>
          <div className={`squircle h-full rounded-[0.9rem] px-3 py-2.5 ${i === stages.length - 1 ? "" : "bg-fill-quaternary"}`}
            style={i === stages.length - 1 ? { background: `color-mix(in srgb, ${tint} 14%, transparent)` } : undefined}>
            <div className="flex items-center justify-between gap-1">
              <span className="flex items-center gap-1.5">
                <span className="font-mono text-caption-2 text-label-tertiary">{i + 1}</span>
                <s.icon className="size-3.5" style={{ color: i === stages.length - 1 ? tint : "var(--color-label-secondary)" }} aria-hidden />
              </span>
              <span className="font-mono text-caption-2 tabular-nums text-label-tertiary">
                {s.skipped ? "skipped" : s.ms !== undefined ? `${s.ms < 0.1 ? "<0.1" : s.ms.toFixed(s.ms < 10 ? 1 : 0)} ms` : ""}
              </span>
            </div>
            <p className="mt-1.5 truncate text-footnote font-semibold">{s.label}</p>
            <p className="truncate text-caption-2 text-label-tertiary">{s.detail}</p>
          </div>
        </motion.li>
      ))}
    </ol>
  );
}
