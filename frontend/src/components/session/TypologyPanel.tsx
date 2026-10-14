"use client";

import { motion } from "motion/react";
import { riskColor, STAGE_COLOR, STAGE_LABEL, TYPOLOGY_LABEL } from "@/config/policy";
import { spring } from "@/config/motion";
import { useDemo } from "@/context/DemoContext";
import { pct, since } from "@/utils/format";

const ALL = ["digital_arrest", "voice_clone_relative", "fake_kyc_apk", "investment_task"];

/**
 * Which scam this looks like. The stage tracker's typology head gives a distribution over the four scam workflows
 * after every event; the sparkline follows P(scam in progress). Below: the stage it infers against the simulator's
 * ground truth for the same event.
 */
export function TypologyPanel() {
  const { view, custom } = useDemo();
  const noTruth = custom?.from === "builder"; // a hand-built session has no ground truth
  const e = view.current;
  const probs = Object.fromEntries(ALL.map((t) => [t, e?.workflow.typology_top3[t] ?? 0]));
  const top = ALL.reduce((a, b) => (probs[b] > probs[a] ? b : a), ALL[0]);
  const scamOn = !!e && e.workflow.p_scam_in_progress >= 0.5;
  const firstId = view.seen.find((s) => s.workflow.p_scam_in_progress >= 0.5 && s.workflow.stage !== "none");

  // sparkline of P(scam in progress) over events seen so far
  const pts = view.seen.map((s, i, a) => [a.length > 1 ? (i / (a.length - 1)) * 100 : 0, (1 - s.workflow.p_scam_in_progress) * 32 + 2]);
  const path = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join("");

  return (
    <div className="flex h-full flex-col gap-4">
      <ul className="flex flex-col gap-2.5">
        {ALL.map((t) => {
          const p = probs[t];
          const lead = scamOn && t === top;
          return (
            <li key={t}>
              <div className="flex items-baseline justify-between text-subheadline">
                <span className={lead ? "font-semibold" : "text-label-secondary"}>{TYPOLOGY_LABEL[t]}</span>
                <span className="tabular-nums" style={{ color: lead ? riskColor(p) : undefined }}>
                  {e && t in e.workflow.typology_top3 ? pct(p) : "<1%"}
                </span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-fill-tertiary">
                <motion.div
                  className="h-full rounded-full"
                  initial={false}
                  animate={{ width: `${p * 100}%`, backgroundColor: lead ? "var(--color-sys-red)" : "var(--color-gray-2)" }}
                  transition={spring.default}
                />
              </div>
            </li>
          );
        })}
      </ul>
      <p className="text-caption-1 text-label-tertiary">
        Typology head of the stage tracker; it only matters once P(scam in progress) passes 50%.
        {firstId && <> First flagged at <span className="text-label-secondary">{since(firstId.ts_min)}</span>.</>}
      </p>

      <div>
        <p className="mb-1 text-caption-1 text-label-secondary">P(scam in progress), event by event</p>
        <svg viewBox="0 0 100 36" preserveAspectRatio="none" className="h-12 w-full overflow-visible" aria-hidden>
          <line x1="0" x2="100" y1="18" y2="18" stroke="var(--color-separator)" strokeDasharray="2 2" vectorEffect="non-scaling-stroke" />
          {pts.length > 1 && <path d={path} fill="none" stroke="var(--color-sys-orange)" strokeWidth={2} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />}
        </svg>
      </div>

      <div className="mt-auto grid grid-cols-2 gap-2">
        {[
          { label: "Model stage", s: e?.workflow.stage },
          { label: noTruth ? "Ground truth (n/a)" : "Ground truth", s: noTruth ? undefined : e?.true_stage },
        ].map(({ label, s }) => (
          <div key={label} className="squircle rounded-[0.9rem] bg-fill-quaternary px-3 py-2">
            <p className="text-caption-2 text-label-tertiary">{label}</p>
            <p className="flex items-center gap-1.5 text-subheadline font-semibold">
              <span className="size-2 rounded-full" style={{ background: s ? STAGE_COLOR[s] : "var(--color-gray-3)" }} aria-hidden />
              {s ? STAGE_LABEL[s] : "—"}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
