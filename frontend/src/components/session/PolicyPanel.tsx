"use client";

import { AnimatePresence, motion } from "motion/react";
import { Scale } from "lucide-react";
import { useReport } from "@/api/console";
import { AnimatedNumber } from "@/components/common/AnimatedNumber";
import { ACTION_COLOR, ACTION_LABEL, ev, TIERS } from "@/config/policy";
import { spring } from "@/config/motion";
import { useDemo } from "@/context/DemoContext";
import { pct, rupees } from "@/utils/format";

/**
 * The alert policy at the latest payment attempt: expected fraud cost against the friction cost of interrupting a
 * genuine user, the expected value of each tier, and the tier the engine chose. Below, what this does across the
 * whole test replay compared with a single threshold.
 */
export function PolicyPanel() {
  const { view } = useDemo();
  const { data: report } = useReport();
  const fleet = report?.scam_fleet;
  const pay = view.lastDecision;
  const d = pay?.decision ?? null;
  const amount = pay?.input.amount ?? 0;

  return (
    <div className="flex h-full flex-col">
      <AnimatePresence mode="popLayout" initial={false}>
        {!d ? (
          <motion.div
            key="idle"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, filter: "blur(6px)" }}
            className="flex flex-1 flex-col items-center justify-center gap-2 py-6 text-center"
          >
            <Scale className="size-8 text-label-tertiary" aria-hidden />
            <p className="text-subheadline text-label-secondary">Waiting for a payment attempt</p>
            <p className="max-w-[16rem] text-caption-1 text-label-tertiary">
              The engine only decides when money is about to move, so the call itself never triggers an alert.
            </p>
          </motion.div>
        ) : (
          <motion.div
            key={pay!.event_index}
            initial={{ opacity: 0, y: 8, filter: "blur(6px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            transition={{ ...spring.default, delay: 0.3 }}
            className="flex flex-col gap-4"
          >
            <div className="grid grid-cols-2 gap-3">
              <Metric
                label="Expected fraud cost"
                hint={`risk ${pct(d.fused_risk)} × ${rupees(amount)}`}
                value={d.fused_risk * amount}
                color="var(--color-sys-red)"
              />
              <Metric
                label="Friction cost of a hold"
                hint={`(1 − risk) × ${rupees(TIERS[3].friction)}`}
                value={(1 - d.fused_risk) * TIERS[3].friction}
                color="var(--color-sys-blue)"
              />
            </div>
            <TierBars p={d.fused_risk} amount={amount} chosen={d.ev_choice} final={d.action} />
            {d.suppressed_by && (
              <p className="text-caption-1 text-label-secondary">
                Anti-fatigue rule applied: <span className="text-label">{d.suppressed_by.replaceAll("_", " ")}</span>
              </p>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <div className="mt-auto pt-4">
        <p className="text-eyebrow text-label-tertiary">Fleet · 10k-session test replay</p>
        {fleet ? (
          <div className="mt-2 grid grid-cols-3 gap-2">
            <Fleet label="alerts / 1k genuine" engine={fleet.engine.notifications_per_1k} base={fleet.threshold.notifications_per_1k} fmt={(v) => v.toFixed(1)} better="lower" />
            <Fleet label="holds / 1k genuine" engine={fleet.engine.holds_per_1k} base={fleet.threshold.holds_per_1k} fmt={(v) => v.toFixed(1)} better="lower" />
            <Fleet label="scams stopped" engine={fleet.engine.scams_stopped_pct} base={fleet.threshold.scams_stopped_pct} fmt={(v) => `${v.toFixed(1)}%`} better="higher" />
          </div>
        ) : <div className="skeleton mt-2 h-16 rounded-xl" />}
        <p className="mt-2 text-caption-2 text-label-tertiary">Engine vs. one fixed hold threshold on the same fused score.</p>
      </div>
    </div>
  );
}

function Metric({ label, hint, value, color }: { label: string; hint: string; value: number; color: string }) {
  return (
    <div className="squircle rounded-[1rem] bg-fill-quaternary p-3">
      <p className="text-caption-1 text-label-secondary">{label}</p>
      <span className="mt-0.5 block text-title-2" style={{ color }}>
        <AnimatedNumber value={value} format={rupees} />
      </span>
      <p className="mt-0.5 text-caption-2 text-label-tertiary tabular-nums">{hint}</p>
    </div>
  );
}

/** EV of each tier as a diverging bar around zero; the engine picks the largest. */
function TierBars({ p, amount, chosen, final }: { p: number; amount: number; chosen: string; final: string }) {
  const vals = TIERS.map((t) => ({ t, v: ev(p, amount, t) }));
  const scale = Math.max(...vals.map((x) => Math.abs(x.v)), 1);
  return (
    <div>
      <p className="mb-1.5 text-caption-1 text-label-secondary">
        Expected value per tier · <span className="tabular-nums">p·A·efficacy − (1−p)·friction</span>
      </p>
      <ul className="flex flex-col gap-1.5">
        {vals.map(({ t, v }, i) => {
          const on = t.name === final || (final === "monitor" && t.name === "allow");
          const w = (Math.abs(v) / scale) * 50;
          return (
            <li key={t.name} className={`grid grid-cols-[4.5rem_1fr_5.5rem] items-center gap-2 rounded-[0.6rem] px-2 py-1 ${on ? "bg-fill-tertiary" : ""}`}>
              <span className="flex items-center gap-1.5 text-footnote" style={{ color: on ? t.color : undefined }}>
                <span className="size-1.5 rounded-full" style={{ background: t.color }} aria-hidden />
                {t.label}
              </span>
              <span className="relative h-2 rounded-full bg-fill-quaternary">
                <span className="absolute inset-y-[-3px] left-1/2 w-px bg-separator" aria-hidden />
                <motion.span
                  className="absolute inset-y-0 rounded-full"
                  style={{ background: v >= 0 ? t.color : "var(--color-gray-2)", [v >= 0 ? "left" : "right"]: "50%" }}
                  initial={{ width: 0 }}
                  animate={{ width: `${w}%` }}
                  transition={{ ...spring.default, delay: 0.35 + i * 0.05 }}
                />
              </span>
              <span className={`text-right text-footnote tabular-nums ${on ? "font-semibold" : "text-label-secondary"}`}>
                {v >= 0 ? "" : "−"}
                {rupees(Math.abs(v))}
              </span>
            </li>
          );
        })}
      </ul>
      <p className="mt-2 text-footnote">
        Decision:{" "}
        <span className="font-semibold" style={{ color: ACTION_COLOR[final as keyof typeof ACTION_COLOR] }}>
          {ACTION_LABEL[final as keyof typeof ACTION_LABEL]}
        </span>
        {chosen !== final && <span className="text-label-tertiary"> (EV choice: {ACTION_LABEL[chosen as keyof typeof ACTION_LABEL]})</span>}
      </p>
    </div>
  );
}

function Fleet({
  label,
  engine,
  base,
  fmt,
  better,
}: {
  label: string;
  engine: number;
  base: number;
  fmt: (v: number) => string;
  better: "lower" | "higher";
}) {
  const good = better === "lower" ? engine < base : engine >= base;
  return (
    <div className="squircle rounded-[0.9rem] bg-fill-quaternary px-2.5 py-2">
      <p className="text-headline tabular-nums" style={{ color: good ? "var(--color-sys-green)" : undefined }}>
        {fmt(engine)}
      </p>
      <p className="text-caption-2 text-label-tertiary tabular-nums">vs {fmt(base)}</p>
      <p className="mt-0.5 text-caption-2 text-label-secondary">{label}</p>
    </div>
  );
}
