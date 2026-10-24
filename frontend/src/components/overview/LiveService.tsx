"use client";

import { useEffect, useState } from "react";
import { Radio } from "lucide-react";
import { loadFeed } from "@/api/auth";
import { DecisionBadge } from "@/components/ui/DecisionBadge";
import { useConsole } from "@/context/ConsoleContext";
import type { AuthStats, Decision, FeedRow } from "@/types/auth";

/** What the running service itself reports (/v1/auth/stats, /v1/auth/decisions), refreshed every few seconds. */
export function LiveService() {
  const { source } = useConsole();
  const [feed, setFeed] = useState<{ rows: FeedRow[]; stats: AuthStats | null }>({ rows: [], stats: null });
  useEffect(() => {
    if (source !== "live") return;
    let live = true;
    const load = () => loadFeed().then((f) => live && setFeed(f));
    load();
    const t = setInterval(load, 4000);
    return () => {
      live = false;
      clearInterval(t);
    };
  }, [source]);
  if (source !== "live" || !feed.stats) return null;
  const s = feed.stats;
  return (
    <section className="material-regular panel-sheen squircle rounded-[var(--radius-panel)] p-4 sm:p-5" aria-label="Live service">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <p className="flex items-center gap-2 text-headline">
          <Radio className="pulse-ring size-4 rounded-full text-sys-green" aria-hidden /> Live service
        </p>
        {[
          ["decisions served", s.decisions.toLocaleString("en-IN")],
          ["p50 latency", s.latency_ms.p50 != null ? `${s.latency_ms.p50} ms` : "—"],
          ["p95 latency", s.latency_ms.p95 != null ? `${s.latency_ms.p95} ms` : "—"],
          ["model", s.model_version ?? "—"],
          ["state", s.state_backend ?? "—"],
        ].map(([k, v]) => (
          <div key={k}>
            <p className="text-headline tabular-nums">{v}</p>
            <p className="text-caption-2 text-label-tertiary">{k}</p>
          </div>
        ))}
        <div className="flex flex-wrap gap-1.5">
          {(["allow", "challenge", "block"] as Decision[]).map((d) => (
            <DecisionBadge key={d} decision={d} label={`${s.by_decision[d] ?? 0}`} />
          ))}
        </div>
      </div>
    </section>
  );
}
