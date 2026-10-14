"use client";

import { motion, useReducedMotion } from "motion/react";
import { Activity, Brain, Fingerprint, GitMerge, Landmark, MessageSquareWarning, PhoneCall, Radio, Smartphone } from "lucide-react";
import { ACTION_COLOR, ACTION_LABEL, riskColor, STAGE_LABEL, TYPOLOGY_LABEL } from "@/config/policy";
import { spring } from "@/config/motion";
import { useDemo } from "@/context/DemoContext";
import { describe } from "@/utils/events";
import { pct, since } from "@/utils/format";

interface Node {
  key: string;
  title: string;
  model: string;
  icon: typeof Activity;
  on: boolean;
  value: string;
  sub: string;
  color?: string;
}

const STAGGER = 0.16;

/**
 * Inside the decision, one event at a time. The nodes that actually run for this event light up in pipeline order:
 * every event goes through context tracking and the stage tracker; payee intelligence, biometrics, fusion and the
 * alert policy only run when money is about to move.
 */
export function PipelinePanel() {
  const { view, index, replay } = useDemo();
  const reduce = useReducedMotion();
  const e = view.current;
  const x = e?.input;
  const d = e?.decision ?? null;
  const pay = x?.event === "PAYMENT_ATTEMPT";
  const hasPayee = !!x?.payee_id && (x.event === "PAYEE_ADD" || pay || x.event === "PAYMENT_SUCCESS" || x.event === "CREDIT_RECEIVED");
  const typ = e ? Object.entries(e.workflow.typology_top3).sort((a, b) => b[1] - a[1])[0] : null;

  const touch = view.touch;
  const ctx: string[] = [];
  if (view.call) ctx.push(view.call.kind === "voip_intl" ? "on VoIP call" : view.call.kind === "unknown" ? "on unknown call" : "on call");
  if (view.sideloaded) ctx.push("sideloaded app");
  if (view.accessibility) ctx.push("screen control");
  if (!ctx.length && view.appInstalled) ctx.push("new app");

  const nodes: Node[] = [
    {
      key: "event", title: "Event in", model: "device event", icon: Smartphone, on: !!e,
      value: x ? describe(x).label : "—", sub: e ? `${since(e.ts_min)}${e.latency_ms ? ` · ${e.latency_ms.toFixed(0)} ms round trip` : ""}` : "waiting",
    },
    {
      key: "ctx", title: "Device context", model: "server tracker", icon: Radio, on: !!e,
      value: ctx.length ? ctx.join(" · ") : "nothing unusual", sub: "call, screen share, installs, permissions",
      color: ctx.length ? "var(--color-sys-orange)" : undefined,
    },
    {
      key: "telecom", title: "Caller reputation", model: "telecom PSI · consented", icon: PhoneCall,
      on: x?.event === "CALL_START" && !!x.caller_number,
      value: !view.call || !view.call.number ? "no call" : view.call.reported == null ? "not checked" : view.call.reported ? "reported to 1930" : "not reported",
      sub: view.call?.number ? `${view.call.number} · bank learns 1 bit` : "private set intersection on call",
      color: view.call?.reported ? "var(--color-sys-red)" : view.call?.reported === false ? "var(--color-sys-green)" : undefined,
    },
    {
      key: "gru", title: "Stage tracker", model: "causal GRU", icon: Brain, on: !!e,
      value: e ? pct(e.workflow.p_scam_in_progress) : "—",
      sub: e ? `${STAGE_LABEL[e.workflow.stage]}${typ && e.workflow.p_scam_in_progress >= 0.5 ? ` · ${TYPOLOGY_LABEL[typ[0]] ?? typ[0]}` : ""}` : "P(scam in progress)",
      color: e ? riskColor(e.workflow.p_scam_in_progress) : undefined,
    },
    {
      key: "payee", title: "Payee intel", model: "payee model", icon: Landmark, on: hasPayee,
      value: hasPayee && x?.payee_mule_score != null ? `risk ${x.payee_mule_score.toFixed(2)}` : "—",
      sub: hasPayee ? `${x?.payee_is_new ? "new payee" : "known payee"}${x?.payee_vpa_age_days != null ? ` · ${Math.round(x.payee_vpa_age_days)} d old` : ""}` : "runs when a payee appears",
      color: hasPayee && x?.payee_mule_score != null ? riskColor(x.payee_mule_score) : undefined,
    },
    {
      key: "bio", title: "Biometrics", model: "BiLSTM + LDA · real HMOG", icon: Fingerprint, on: pay || x?.event === "BIO_WINDOW",
      value: touch ? (touch.matches_profile ? "owner's touch" : "someone else's touch?") : d ? `deviation ${d.components.bio_dev.toFixed(2)}` : "—",
      sub: touch ? `deviation ${touch.behavioural_deviation.toFixed(2)} vs enrolled profile` : "10 real gestures per window",
      color: touch ? (touch.matches_profile ? "var(--color-sys-green)" : "var(--color-sys-red)") : undefined,
    },
    {
      key: "fusion", title: "Fusion", model: "monotone XGBoost", icon: GitMerge, on: !!d,
      value: d ? pct(d.fused_risk) : "—", sub: d ? `prior-corrected · ${d.reasons.length} reasons` : "runs at a payment attempt",
      color: d ? riskColor(d.fused_risk) : undefined,
    },
    {
      key: "policy", title: "Alert policy", model: "EV tiers + anti-fatigue", icon: Activity, on: !!d,
      value: d ? ACTION_LABEL[d.action] : "—",
      sub: d ? (d.suppressed_by ? `rule: ${d.suppressed_by.replaceAll("_", " ")}` : `best expected value: ${ACTION_LABEL[d.ev_choice]}`) : "allow · nudge · cool-off · hold",
      color: d ? ACTION_COLOR[d.action] : undefined,
    },
    {
      key: "user", title: "Customer", model: "EN / HI message", icon: MessageSquareWarning, on: !!d,
      value: d ? (d.notify ? "alert shown" : d.action === "hold" ? "stays held" : "no message") : "—",
      sub: d ? (d.notify ? "bilingual sheet + 1930" : "no interruption") : "only if the policy interrupts",
      color: d ? (d.notify ? ACTION_COLOR[d.action] : "var(--color-sys-green)") : undefined,
    },
  ];
  const active = nodes.filter((n) => n.on).length;

  return (
    <div className="flex flex-col gap-3">
      {/* progress rail: fills to the last node that runs for this event */}
      <div className="relative h-1 overflow-hidden rounded-full bg-fill-quaternary">
        <motion.div
          key={`${replay.typology}-${index}`}
          className="absolute inset-y-0 left-0 rounded-full bg-sys-blue"
          initial={{ width: "0%" }}
          animate={{ width: `${(active / nodes.length) * 100}%` }}
          transition={{ duration: reduce ? 0 : active * STAGGER, ease: "linear" }}
        />
      </div>
      <ol className="grid grid-cols-2 gap-2 md:grid-cols-3">
        {nodes.map((n, i) => (
          <motion.li
            key={`${n.key}-${replay.typology}-${index}`}
            initial={n.on ? { opacity: 0.35, scale: 0.97 } : false}
            animate={{ opacity: n.on ? 1 : 0.38, scale: 1 }}
            transition={{ ...spring.snappy, delay: reduce ? 0 : i * STAGGER }}
            className="squircle relative flex min-h-[6.25rem] flex-col rounded-[1rem] bg-fill-quaternary p-3"
          >
            {n.on && (
              <motion.span
                aria-hidden
                className="pointer-events-none absolute inset-0 rounded-[1rem]"
                initial={{ boxShadow: `inset 0 0 0 1.5px ${n.color ?? "var(--color-sys-blue)"}` }}
                animate={{ boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${n.color ?? "var(--color-sys-blue)"} 35%, transparent)` }}
                transition={{ delay: (reduce ? 0 : i * STAGGER) + 0.35, duration: 0.6 }}
              />
            )}
            <div className="flex items-center gap-1.5">
              <span className="flex size-5 items-center justify-center rounded-full bg-fill-tertiary text-caption-2 font-semibold tabular-nums text-label-secondary">
                {i + 1}
              </span>
              <n.icon className="size-3.5 text-label-secondary" aria-hidden />
              <span className="truncate text-footnote font-semibold">{n.title}</span>
            </div>
            <span className="mt-0.5 text-caption-2 text-label-tertiary">{n.model}</span>
            <span className="mt-auto truncate pt-1.5 text-subheadline font-semibold tabular-nums" style={{ color: n.on ? n.color : undefined }}>
              {n.value}
            </span>
            <span className="truncate text-caption-2 text-label-tertiary">{n.sub}</span>
          </motion.li>
        ))}
      </ol>
    </div>
  );
}
