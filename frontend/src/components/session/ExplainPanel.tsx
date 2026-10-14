"use client";

import { motion } from "motion/react";
import { riskColor, TYPOLOGY_LABEL } from "@/config/policy";
import { spring } from "@/config/motion";
import { useDemo } from "@/context/DemoContext";
import { pct } from "@/utils/format";

/** Reason text from ml/engine/fusion.py REASON_TEXT → the signal row it explains. */
const REASON_KEY: Record<string, string> = {
  "session follows a known scam pattern": "workflow",
  "receiving account is linked to suspected mule activity": "payee",
  "touch behaviour differs from your usual pattern": "bio",
  "amount is much larger than your usual payments": "amount",
  "first payment to this account": "new",
  "you are on a call with an unknown number": "call",
  "the number calling you has been reported for fraud": "reported",
};

interface Signal {
  key: string;
  label: string;
  model: string;
  /** 0..1 strength for the bar; null = not measured yet. */
  level: number | null;
  value: string;
  detail?: string;
}

/**
 * Why this session is risky: every input the fusion model sees, with its live value and the model that produced
 * it. Rows the fusion model ranked as top contributors (positive SHAP, on the risky side) are marked; those are
 * exactly the reasons shown to the customer.
 */
export function ExplainPanel() {
  const { view, replay } = useDemo();
  const last = view.current;
  const pay = view.lastDecision?.decision ?? null;
  // the payee in focus: on the pay screen, else the one from the latest payment decision
  const payee = view.payee ?? view.lastDecision?.input ?? null;
  const top = new Set((pay?.reasons ?? []).map((r) => REASON_KEY[r]).filter(Boolean));

  const typ = last ? Object.entries(last.workflow.typology_top3).sort((a, b) => b[1] - a[1])[0] : null;
  const p = last?.workflow.p_scam_in_progress ?? null;
  const callKind = view.call?.kind;
  const unknownCall = !!view.call && callKind !== "contact";
  const payeeRisk = payee?.payee_mule_score ?? null;
  const ratio = pay ? Math.exp(pay.components.log_amt_vs_avg) : null;

  const signals: Signal[] = [
    {
      key: "workflow",
      label: "Scam workflow pattern",
      model: "Causal GRU",
      level: p,
      value: p == null ? "—" : pct(p),
      detail: typ && p != null && p >= 0.5 ? `${TYPOLOGY_LABEL[typ[0]] ?? typ[0]} ${pct(typ[1])}` : "event sequence so far",
    },
    {
      key: "call",
      label: "On a call with an unknown number",
      model: "Device context",
      level: pay ? pay.components.unknown_call_active : last ? (unknownCall ? 1 : 0) : null,
      value: !last ? "—" : (pay ? pay.components.unknown_call_active > 0 : unknownCall) ? "Yes" : "No",
      detail: unknownCall ? (callKind === "voip_intl" ? "internet (VoIP) caller" : "number not in contacts") : undefined,
    },
    {
      key: "reported",
      label: "Caller reported to 1930",
      model: "Telecom PSI",
      level: !view.call?.number ? null : view.call.reported ? 1 : 0,
      value: !view.call?.number ? "no call" : view.call.reported == null ? "no consent" : view.call.reported ? "Yes" : "No",
      detail: "private set intersection, consented",
    },
    {
      key: "bio",
      label: "Touch matches the customer",
      model: "BiLSTM+LDA",
      // the real model's deviation: < 0 owner-like, > 0 someone else's hands; shown on a 0..1 bar
      level: pay ? Math.max(0, Math.min(1, (pay.components.bio_dev + 1) / 2)) : view.touch ? Math.max(0, Math.min(1, (view.touch.behavioural_deviation + 1) / 2)) : null,
      value: pay ? pay.components.bio_dev.toFixed(2) : view.touch ? view.touch.behavioural_deviation.toFixed(2) : "at payment",
      detail: view.touch ? (view.touch.matches_profile ? "matches the enrolled owner" : "does not match the owner") : "real HMOG gestures vs. enrolled profile",
    },
    {
      key: "payee",
      label: "Payee mule risk",
      model: "Payee model",
      level: payeeRisk,
      value: payeeRisk == null ? "no payee yet" : payeeRisk.toFixed(2),
      detail: payee?.payee_vpa_age_days != null ? `account ${Math.round(payee.payee_vpa_age_days)} days old` : undefined,
    },
    {
      key: "amount",
      label: "Amount vs. usual",
      model: "Profile",
      level: ratio == null ? null : Math.min(1, Math.log(ratio) / Math.log(25)),
      value: ratio == null ? "at payment" : `${ratio.toFixed(1)}×`,
      detail: `usual payment ₹${Math.round(replay.user.avg_txn_amount).toLocaleString("en-IN")}`,
    },
    {
      key: "new",
      label: "First payment to this account",
      model: "Profile",
      level: payee ? (payee.payee_is_new ? 1 : 0) : null,
      value: payee ? (payee.payee_is_new ? "Yes" : "No") : "—",
    },
  ];

  return (
    <div className="flex h-full flex-col">
      <ul className="flex flex-col gap-2.5">
        {signals.map((s) => (
          <SignalRow key={s.key} s={s} top={top.has(s.key)} alerted={!!pay?.notify} />
        ))}
      </ul>
      <p className="mt-auto pt-4 text-caption-1 text-label-tertiary">
        <span className="font-semibold text-sys-red">Top reason</span> marks the fusion model&apos;s largest SHAP contributors
        at the payment; when the customer is alerted, these are the reasons they read. Without an alert they stay
        analyst-side as <span className="font-semibold text-label-secondary">top factors</span>.
      </p>
    </div>
  );
}

function SignalRow({ s, top, alerted }: { s: Signal; top: boolean; alerted: boolean }) {
  const color = s.level == null ? "var(--color-gray-3)" : riskColor(s.level);
  return (
    <motion.li layout="position" className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1">
      <div className="flex min-w-0 items-center gap-2">
        <span className="truncate text-subheadline">{s.label}</span>
        {top && (
          <motion.span
            initial={{ opacity: 0, scale: 0.6 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={spring.sheet}
            className={`shrink-0 rounded-full px-1.5 py-px text-caption-2 font-semibold ${
              alerted ? "bg-sys-red/15 text-sys-red" : "bg-fill-tertiary text-label-secondary"
            }`}
          >
            {alerted ? "Top reason" : "Top factor"}
          </motion.span>
        )}
      </div>
      <span className="text-subheadline font-semibold tabular-nums" style={{ color: s.level == null ? undefined : color }}>
        {s.value}
      </span>
      <div className="col-span-2 flex items-center gap-2">
        <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-fill-tertiary">
          <motion.div
            className="absolute inset-y-0 left-0 rounded-full"
            initial={false}
            animate={{ width: `${Math.max(0, Math.min(1, s.level ?? 0)) * 100}%`, backgroundColor: color }}
            transition={spring.default}
          />
        </div>
        <span className="max-w-[60%] shrink-0 truncate text-right text-caption-2 text-label-tertiary">
          {s.model}
          {s.detail ? ` · ${s.detail}` : ""}
        </span>
      </div>
    </motion.li>
  );
}
