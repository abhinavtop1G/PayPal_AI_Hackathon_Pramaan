"use client";

import { useEffect, useState } from "react";
import { recordedRuns } from "@/api/auth";
import { DecisionBadge } from "@/components/ui/DecisionBadge";
import { CHALLENGE_SHORT, FAMILY_TINT, inr, pct } from "@/config/authSignals";
import type { DemoRun } from "@/types/auth";

const ORDER = ["genuine_routine", "genuine_travel", "genuine_new_phone", "genuine_big_purchase", "ato_new_device", "sim_swap", "bot",
  "remote_access", "coerced"];

/** Every scenario's recorded decision side by side: look-alikes next to the attacks they resemble. */
export function ScenarioMatrix({ selected, onPick }: { selected: string | null; onPick: (id: string) => void }) {
  const [runs, setRuns] = useState<DemoRun[]>([]);
  useEffect(() => {
    recordedRuns().then(({ runs: r }) => setRuns(ORDER.map((id) => r[id]).filter(Boolean)));
  }, []);
  return (
    <div className="relative overflow-x-auto">
      <table className="w-full min-w-[52rem] text-footnote">
        <caption className="sr-only">Recorded decision for every scenario</caption>
        <thead>
          <tr className="text-left text-caption-1 text-label-tertiary">
            {["scenario", "amount", "risk", "decision", "strongest reason", "latency"].map((h) => <th key={h} scope="col" className="pb-2 pr-3 font-medium">{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => {
            const top = r.response.reasons[0];
            return (
              <tr key={r.scenario} onClick={() => onPick(r.scenario)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && onPick(r.scenario)}
                className={`cursor-pointer border-t border-separator/40 transition-colors hover:bg-fill-quaternary ${selected === r.scenario ? "bg-fill-tertiary" : ""}`}>
                <td className="py-2 pr-3">
                  <span className="flex items-center gap-2">
                    <span className={`size-1.5 rounded-full ${r.is_attack ? "bg-sys-red" : "bg-sys-green"}`} aria-hidden />
                    {r.title.replace(/^(Genuine|Attack): /, "")}
                  </span>
                </td>
                <td className="py-2 pr-3 tabular-nums">{r.response.amount > 0 ? inr(r.response.amount) : "login"}</td>
                <td className="py-2 pr-3 font-mono text-caption-1 tabular-nums">{pct(r.response.risk_score)}</td>
                <td className="py-2 pr-3">
                  <span className="flex items-center gap-1.5">
                    <DecisionBadge decision={r.response.decision} size="xs" />
                    {r.response.challenge_type && <span className="text-caption-1 text-label-secondary">{CHALLENGE_SHORT[r.response.challenge_type]}</span>}
                  </span>
                </td>
                <td className="py-2 pr-3 text-caption-1 text-label-secondary">
                  {top ? (
                    <span className="flex items-center gap-1.5"><span className="size-1.5 shrink-0 rounded-full" style={{ background: FAMILY_TINT[top.family] }} aria-hidden />{top.text_en}</span>
                  ) : r.response.rule ? <span className="font-mono">rule: {r.response.rule}</span> : "nothing unusual"}
                </td>
                <td className="py-2 font-mono text-caption-1 tabular-nums text-label-tertiary">{r.response.latency_ms.toFixed(0)} ms</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
