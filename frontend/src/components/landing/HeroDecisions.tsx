"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { recordedRuns } from "@/api/auth";
import { RiskGauge } from "@/components/charts/RiskGauge";
import { DecisionBadge } from "@/components/ui/DecisionBadge";
import { CHALLENGE_LABEL, FAMILY_TINT, inr } from "@/config/authSignals";
import { spring } from "@/config/motion";
import type { DemoRun } from "@/types/auth";

const ORDER = ["genuine_routine", "sim_swap", "genuine_new_phone", "remote_access", "genuine_big_purchase", "coerced", "bot", "genuine_travel", "ato_new_device"];

/** The hero card: the recorded scenarios (the API's own output) one after another, each as the request's key facts
 *  and the decision. */
export function HeroDecisions() {
  const [runs, setRuns] = useState<DemoRun[]>([]);
  const [i, setI] = useState(0);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    let on = true;
    recordedRuns().then(({ runs: rec }) => on && setRuns(ORDER.map((id) => rec[id]).filter((r): r is DemoRun => !!r)));
    return () => {
      on = false;
    };
  }, []);

  useEffect(() => {
    if (paused || runs.length < 2) return;
    const t = setInterval(() => setI((x) => (x + 1) % runs.length), 3600);
    return () => clearInterval(t);
  }, [paused, runs.length]);

  const run = runs[i];
  return (
    <div className="relative" onPointerEnter={() => setPaused(true)} onPointerLeave={() => setPaused(false)}>
      <div aria-hidden className="absolute -inset-8 rounded-[3rem] bg-gradient-to-br from-[#5e5ce6]/25 via-transparent to-[#64d2ff]/15 blur-2xl" />
      <div className="material-regular panel-sheen squircle relative overflow-hidden rounded-[2rem] p-5 sm:p-6">
        <div className="flex items-center justify-between gap-3">
          <p className="flex items-center gap-2 text-caption-1 text-label-secondary">
            <span className="pulse-ring size-2 rounded-full bg-sys-green text-sys-green" aria-hidden /> POST /v1/authenticate
          </p>
          <p className="font-mono text-caption-1 text-label-tertiary">{run ? `${run.response.latency_ms.toFixed(0)} ms` : "…"}</p>
        </div>
        <div className="relative mt-4 min-h-[20rem]">
          <AnimatePresence mode="wait">
            {run && (
              <motion.div key={run.scenario} initial={{ opacity: 0, y: 12, filter: "blur(8px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                exit={{ opacity: 0, y: -8, filter: "blur(8px)" }} transition={spring.default}>
                <p className="text-eyebrow" style={{ color: run.is_attack ? "var(--color-sys-red)" : "var(--color-sys-green)" }}>
                  {run.is_attack ? "Attack" : "Genuine customer"}
                </p>
                <p className="mt-1 text-title-2">{run.title.replace(/^(Genuine|Attack): /, "")}</p>
                <p className="mt-1 line-clamp-2 text-footnote text-label-secondary">{run.story}</p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {facts(run).map(([k, v, fam]) => (
                    <span key={k} className="flex items-center gap-1.5 rounded-full bg-fill-tertiary px-2.5 py-1 text-caption-1">
                      <span className="size-1.5 rounded-full" style={{ background: FAMILY_TINT[fam] }} aria-hidden />
                      <span className="text-label-tertiary">{k}</span> {v}
                    </span>
                  ))}
                </div>
                <div className="mt-4 grid grid-cols-[auto_1fr] items-center gap-4">
                  <RiskGauge risk={run.response.risk_score} decision={run.response.decision} size={170} />
                  <div className="min-w-0 space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <DecisionBadge decision={run.response.decision} size="md" />
                      {run.response.challenge_type && <span className="text-footnote text-label-secondary">{CHALLENGE_LABEL[run.response.challenge_type].title}</span>}
                    </div>
                    {run.response.reasons.length ? run.response.reasons.slice(0, 3).map((r) => (
                      <p key={r.signal} className="flex items-start gap-2 text-footnote">
                        <span className="mt-1.5 size-1.5 shrink-0 rounded-full" style={{ background: FAMILY_TINT[r.family] }} aria-hidden />{r.text_en}
                      </p>
                    )) : <p className="text-footnote text-label-secondary">Nothing unusual against her history: straight through, no OTP.</p>}
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
          {!run && <div className="skeleton absolute inset-0 rounded-2xl" />}
        </div>
        <div className="mt-2 flex gap-1" role="tablist" aria-label="Scenarios">
          {runs.map((r, k) => (
            <button key={r.scenario} role="tab" aria-selected={k === i} aria-label={r.title} onClick={() => setI(k)}
              className="group flex h-6 flex-1 items-center">
              <span className={`h-1 w-full rounded-full transition-colors ${k === i ? (r.is_attack ? "bg-sys-red" : "bg-sys-green") : "bg-fill-secondary group-hover:bg-fill"}`} />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function facts(run: DemoRun): [string, string, "behaviour" | "device" | "transaction"][] {
  const { device: d, network: n, transaction: t } = run.request;
  const f = run.response.features;
  const out: [string, string, "behaviour" | "device" | "transaction"][] = [];
  out.push(["device", (f.device_new ?? 0) >= 0.5 ? "never seen" : "her phone", "device"]);
  if (d.sim_change_hours != null) out.push(["SIM", `changed ${d.sim_change_hours} h ago`, "device"]);
  if (d.is_emulator) out.push(["", "emulator", "device"]);
  if (d.remote_access_app) out.push(["", "remote-control app", "device"]);
  if (n.city) out.push(["in", n.city, "device"]);
  if (f.bio_dev != null) out.push(["touch", f.bio_dev > 0.5 ? "not her hands" : "her hands", "behaviour"]);
  if (f.typing_dev != null) out.push(["typing", f.typing_dev > 0 ? "not her rhythm" : "her rhythm", "behaviour"]);
  if (run.request.behaviour.unknown_call_active) out.push(["", "on a call, unknown number", "behaviour"]);
  out.push(["pays", t.amount > 0 ? inr(t.amount) : "login", "transaction"]);
  if ((f.payee_new ?? 0) >= 0.5) out.push(["to", "a new payee", "transaction"]);
  return out.slice(0, 7);
}
