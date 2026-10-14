"use client";

import { AnimatePresence, motion } from "motion/react";
import { KeyRound, Loader2, ShieldAlert, ShieldCheck, ShieldX } from "lucide-react";
import { Button } from "@/components/common/Button";
import { CHALLENGE_LABEL, DECISION_STYLE, inr } from "@/config/authSignals";
import { spring } from "@/config/motion";
import type { ChallengeOutcome, DemoRun } from "@/types/auth";

const ICON = { allow: ShieldCheck, challenge: ShieldAlert, block: ShieldX };

/** The verdict: allow / challenge (which one, and why) / block, risk, latency, the customer message, and the
 *  challenge loop (pass or fail it and see the final decision). */
export function DecisionCard({
  run,
  outcome,
  busy,
  onVerify,
}: {
  run: DemoRun | null;
  outcome: ChallengeOutcome | null;
  busy: boolean;
  onVerify: (passed: boolean) => void;
}) {
  if (!run) {
    return (
      <section className="material-regular panel-sheen squircle flex min-h-[18rem] items-center justify-center rounded-[var(--radius-panel)] p-6">
        {busy ? <Loader2 className="size-6 animate-spin text-label-tertiary" /> : <p className="text-callout text-label-secondary">Pick a scenario.</p>}
      </section>
    );
  }
  const r = run.response;
  const st = DECISION_STYLE[r.decision];
  const Icon = ICON[r.decision];
  const ch = r.challenge_type ? CHALLENGE_LABEL[r.challenge_type] : null;
  const risk = Math.min(1, Math.max(0, r.risk_score));
  return (
    <section className="material-regular panel-sheen squircle rounded-[var(--radius-panel)] p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-eyebrow text-label-tertiary">{run.is_attack === null ? "Custom request" : run.is_attack ? "Attack scenario" : "Genuine scenario"}</p>
          <h2 className="mt-0.5 text-title-3">{run.title}</h2>
          <p className="mt-1 max-w-[46rem] text-subheadline text-label-secondary">{run.story}</p>
        </div>
        <div className="flex items-center gap-2 text-caption-1 text-label-secondary">
          <span className="rounded-full bg-fill-tertiary px-2.5 py-1 font-mono">{r.latency_ms.toFixed(1)} ms</span>
          {r.amount > 0 && <span className="rounded-full bg-fill-tertiary px-2.5 py-1">{inr(r.amount)}</span>}
        </div>
      </div>

      <AnimatePresence initial={false}>
        <motion.div
          key={r.decision_id}
          initial={{ opacity: 0.4, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={spring.snappy}
          className="mt-5 grid gap-4 md:grid-cols-[auto_1fr]"
        >
          <div className={`squircle flex min-w-[12rem] flex-col items-center justify-center gap-2 rounded-[var(--radius-card)] px-6 py-5 ${st.bg}`}>
            <Icon className="size-10" style={{ color: st.tint }} aria-hidden />
            <p className="text-title-1" style={{ color: st.tint }}>{st.label}</p>
            <div className="w-full">
              <div className="flex justify-between text-caption-2 text-label-tertiary">
                <span>risk</span>
                <span className="font-mono">{risk < 0.0001 ? "<0.01%" : `${(100 * risk).toFixed(risk < 0.1 ? 2 : 1)}%`}</span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-fill-tertiary">
                <motion.div className="h-full rounded-full" style={{ background: st.tint }} initial={{ width: 0 }}
                  animate={{ width: `${Math.max(2, Math.sqrt(risk) * 100)}%` }} transition={spring.default} />
              </div>
            </div>
          </div>

          <div className="min-w-0 space-y-3">
            {ch && (
              <div className="squircle rounded-[var(--radius-card)] bg-fill-quaternary p-3.5">
                <p className="flex items-center gap-2 text-headline"><KeyRound className="size-4 text-sys-orange" aria-hidden />{ch.title}</p>
                <p className="mt-1 text-footnote text-label-secondary">{ch.why}</p>
              </div>
            )}
            {r.rule && <p className="text-footnote text-label-secondary">Rule applied: <span className="font-mono text-label">{r.rule}</span></p>}
            <div className="squircle rounded-[var(--radius-card)] bg-fill-quaternary p-3.5">
              <p className="text-eyebrow text-label-tertiary">What the customer sees</p>
              <p className="mt-1 text-callout">{r.message_en}</p>
              <p className="mt-1 text-callout text-label-secondary" lang="hi">{r.message_hi}</p>
            </div>
            {r.reasons.length > 0 && (
              <ul className="space-y-1">
                {r.reasons.map((x) => (
                  <li key={x.signal} className="flex items-start gap-2 text-subheadline">
                    <span className="mt-2 size-1.5 shrink-0 rounded-full bg-sys-red" aria-hidden />
                    <span>{x.text_en}</span>
                  </li>
                ))}
              </ul>
            )}
            {r.decision === "challenge" && !outcome && (
              <div className="flex flex-wrap gap-2 pt-1">
                <Button tint="green" size="small" onClick={() => onVerify(true)} disabled={busy}>Customer passes the challenge</Button>
                <Button tint="red" variant="tinted" size="small" onClick={() => onVerify(false)} disabled={busy}>Challenge fails</Button>
              </div>
            )}
            {outcome && (
              <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} transition={spring.snappy}
                className={`squircle rounded-[var(--radius-card)] p-3.5 ${DECISION_STYLE[outcome.decision].bg}`}>
                <p className="text-headline" style={{ color: DECISION_STYLE[outcome.decision].tint }}>
                  Final: {DECISION_STYLE[outcome.decision].label}
                  {outcome.device_trusted ? " · device is now trusted" : ""}
                </p>
                <p className="mt-1 text-footnote text-label-secondary">
                  {outcome.passed ? "Challenge passed: the payment goes through and joins the customer's history." :
                    "Challenge failed: blocked, and further attempts on this account are blocked for 30 minutes."}
                </p>
              </motion.div>
            )}
          </div>
        </motion.div>
      </AnimatePresence>
    </section>
  );
}
