"use client";

import { AnimatePresence, motion } from "motion/react";
import { CheckCircle2, Flag, PhoneOutgoing, Unlock } from "lucide-react";
import { Button } from "@/components/common/Button";
import { ACTION_COLOR, ACTION_LABEL, TYPOLOGY_LABEL } from "@/config/policy";
import { payeeDisplay } from "@/config/scenarios";
import { spring } from "@/config/motion";
import { useDemo, type AnalystAction } from "@/context/DemoContext";
import { toast } from "@/components/common/Toaster";
import { clock, pct, rupees } from "@/utils/format";

interface Entry {
  key: string;
  index: number;
  text: string;
  color: string;
  who: "system" | "analyst";
}

/**
 * The fraud-operations case for this session: what the system recorded as it happened, interleaved with the
 * analyst's own actions (buttons below). Analyst actions are local to the demo; nothing is sent anywhere.
 */
export function CaseLog() {
  const { view, replay, scenario, actions, act: record } = useDemo();
  const act = (k: AnalystAction["kind"], label: string) => {
    record(k, label);
    toast(label, k === "confirm" || k === "report" ? "alert" : "ok");
  };
  const entries: Entry[] = [];
  let suspected = false;
  view.seen.forEach((e, i) => {
    const x = e.input;
    const p = e.workflow.p_scam_in_progress;
    if (i === 0) entries.push({ key: "open", index: i, text: `Session opened · user ${replay.user.age_group} · usual payment ${rupees(replay.user.avg_txn_amount)}`, color: "var(--color-gray-1)", who: "system" });
    if (x.event === "CALL_START" && x.caller_kind !== "contact")
      entries.push({ key: `call${i}`, index: i, text: x.caller_kind === "voip_intl" ? "Internet (VoIP) caller on the line" : "Unknown caller on the line", color: "var(--color-sys-yellow)", who: "system" });
    if (x.event === "APP_INSTALL" && x.app_source === "sideload")
      entries.push({ key: `side${i}`, index: i, text: "App sideloaded from outside the store", color: "var(--color-sys-orange)", who: "system" });
    if (x.event === "ACCESSIBILITY_GRANT")
      entries.push({ key: `acc${i}`, index: i, text: "Screen-control permission granted to that app", color: "var(--color-sys-orange)", who: "system" });
    if (!suspected && p >= 0.5 && e.workflow.stage !== "none") {
      suspected = true;
      const top = Object.entries(e.workflow.typology_top3).sort((a, b) => b[1] - a[1])[0];
      entries.push({ key: `sus${i}`, index: i, text: `Scam workflow suspected: ${TYPOLOGY_LABEL[top[0]] ?? top[0]} (stage tracker ${pct(p)})`, color: "var(--color-sys-orange)", who: "system" });
    }
    if (x.event === "PAYEE_ADD" && (x.payee_mule_score ?? 0) >= 0.3)
      entries.push({ key: `payee${i}`, index: i, text: `New payee with elevated risk ${x.payee_mule_score?.toFixed(2)} (${payeeDisplay(scenario, x.payee_id).vpa})`, color: "var(--color-sys-orange)", who: "system" });
    const d = e.decision;
    if (d) {
      entries.push({ key: `dec${i}`, index: i, text: `Payment ${rupees(x.amount ?? 0)} → ${ACTION_LABEL[d.action]} (fused risk ${pct(d.fused_risk)})`, color: ACTION_COLOR[d.action], who: "system" });
      if (d.notify) entries.push({ key: `msg${i}`, index: i, text: "Customer alerted in English and Hindi", color: ACTION_COLOR[d.action], who: "system" });
      if (d.notify && d.action === "hold") entries.push({ key: `cb${i}`, index: i, text: "Funds held · bank callback queued to the registered number", color: "var(--color-sys-red)", who: "system" });
    }
  });
  actions.forEach((a) => entries.push({ key: `a${a.id}`, index: a.index, text: a.label, color: "var(--color-sys-blue)", who: "analyst" }));
  entries.sort((a, b) => a.index - b.index || (a.who === "analyst" ? 1 : 0) - (b.who === "analyst" ? 1 : 0));

  const decided = view.decisions.length > 0;
  const held = view.decisions.some((e) => e.decision?.action === "hold");
  const did = (k: AnalystAction["kind"]) => actions.some((a) => a.kind === k);
  const caseId = `CASE-${scenario.id.split("_").map((w) => w[0].toUpperCase()).join("")}-0417`;

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex items-center justify-between text-caption-1 text-label-secondary">
        <span className="font-mono">{caseId}</span>
        <span>{entries.length} entries</span>
      </div>
      <ol className="flex max-h-[17rem] min-h-[8rem] flex-col gap-1 overflow-y-auto pr-1">
        <AnimatePresence initial={false}>
          {entries.map((en) => (
            <motion.li
              key={en.key}
              layout="position"
              initial={{ opacity: 0, x: -8, filter: "blur(4px)" }}
              animate={{ opacity: 1, x: 0, filter: "blur(0px)" }}
              transition={spring.default}
              className="grid grid-cols-[3rem_0.5rem_1fr] items-baseline gap-2 text-footnote"
            >
              <span className="text-caption-1 text-label-tertiary tabular-nums">{clock(replay.start_time, replay.timeline[en.index]?.ts_min ?? 0)}</span>
              <span className="size-2 translate-y-[-1px] rounded-full" style={{ background: en.color }} aria-hidden />
              <span className={en.who === "analyst" ? "text-sys-blue" : "text-label"}>
                {en.who === "analyst" && <span className="mr-1 font-semibold">Analyst:</span>}
                {en.text}
              </span>
            </motion.li>
          ))}
        </AnimatePresence>
      </ol>
      <div className="mt-auto grid grid-cols-2 gap-2">
        <Button size="small" variant="tinted" tint="red" disabled={!decided || did("confirm")} onClick={() => act("confirm", "Confirmed as scam · payee flagged to the mule network team")}>
          <CheckCircle2 className="size-3.5" aria-hidden /> Confirm scam
        </Button>
        <Button size="small" variant="tinted" tint="blue" disabled={!decided || did("call")} onClick={() => act("call", "Called the customer on the registered number")}>
          <PhoneOutgoing className="size-3.5" aria-hidden /> Call customer
        </Button>
        <Button size="small" variant="tinted" tint="green" disabled={!held || did("release")} onClick={() => act("release", "Hold released after verification with the customer")}>
          <Unlock className="size-3.5" aria-hidden /> Release hold
        </Button>
        <Button size="small" variant="tinted" tint="gray" disabled={!decided || did("report")} onClick={() => act("report", "Reported to the national cyber-crime portal (1930)")}>
          <Flag className="size-3.5" aria-hidden /> Report 1930
        </Button>
      </div>
    </div>
  );
}
