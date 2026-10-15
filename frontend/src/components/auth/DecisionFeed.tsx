import { History } from "lucide-react";
import { Panel } from "@/components/layout/Panel";
import { DECISION_STYLE, inr } from "@/config/authSignals";
import type { AuthStats, Decision, FeedRow } from "@/types/auth";

/** Analyst feed: the service's latest decisions and challenge results (from the audit log), with live counters. */
export function DecisionFeed({ rows, stats, live }: { rows: FeedRow[]; stats: AuthStats | null; live: boolean }) {
  return (
    <Panel eyebrow="Audit log" title="Decision feed" icon={History} tint="var(--color-sys-teal)">
      {!live ? (
        <p className="text-footnote text-label-tertiary">Connect the console to the API (NEXT_PUBLIC_PRAMAAN_API) to see the live audit feed.</p>
      ) : (
        <>
          {stats && (
            <div className="mb-3 grid grid-cols-3 gap-2 text-center">
              <Stat label="decisions" value={String(stats.decisions)} />
              <Stat label="p50 latency" value={stats.latency_ms.p50 != null ? `${stats.latency_ms.p50} ms` : "—"} />
              <Stat label="p95 latency" value={stats.latency_ms.p95 != null ? `${stats.latency_ms.p95} ms` : "—"} />
            </div>
          )}
          <ul className="max-h-[22rem] space-y-1 overflow-y-auto pr-1">
            {rows.map((r) => {
              const d = (r.decision in DECISION_STYLE ? r.decision : "allow") as Decision;
              return (
                <li key={`${r.kind}-${r.decision_id}`} className="flex items-center gap-2.5 rounded-[0.6rem] px-2 py-1.5 text-footnote hover:bg-fill-quaternary">
                  <span className="size-2 shrink-0 rounded-full" style={{ background: DECISION_STYLE[d].tint }} aria-hidden />
                  <span className="w-[4.5rem] shrink-0 font-mono text-caption-1 text-label-tertiary">
                    {new Date(r.ts * 1000).toLocaleTimeString("en-IN", { hour12: false })}
                  </span>
                  <span className="min-w-0 flex-1 truncate">
                    {r.kind === "challenge" ? `${r.challenge_type} ${r.passed ? "passed" : "failed"} → ${r.decision}` :
                      `${r.decision}${r.challenge_type ? ` · ${r.challenge_type}` : ""}${r.amount ? ` · ${inr(r.amount)}` : ""}`}
                  </span>
                  {r.latency_ms != null && <span className="shrink-0 font-mono text-caption-2 text-label-tertiary">{r.latency_ms.toFixed(0)} ms</span>}
                </li>
              );
            })}
            {!rows.length && <li className="text-footnote text-label-tertiary">No decisions yet.</li>}
          </ul>
        </>
      )}
    </Panel>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[0.7rem] bg-fill-quaternary px-2 py-2">
      <p className="font-mono text-headline">{value}</p>
      <p className="text-caption-2 text-label-tertiary">{label}</p>
    </div>
  );
}
