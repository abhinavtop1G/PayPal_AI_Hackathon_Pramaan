"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { AUTH_API, listScenarios, loadFeed, runScenario, verifyChallenge, type Source } from "@/api/auth";
import type { AuthStats, ChallengeOutcome, DemoRun, FeedRow, Overrides, Scenario } from "@/types/auth";
import { DecisionCard } from "./DecisionCard";
import { DecisionFeed } from "./DecisionFeed";
import { RequestCard } from "./RequestCard";
import { ScenarioRail } from "./ScenarioRail";
import { SignalPanel } from "./SignalPanel";

/**
 * BIOS console: one request at a time through the risk-authentication service.
 *   left    scenarios on the demo customer + a custom request builder
 *   centre  the decision (allow / challenge / block, which challenge, the customer's message, the challenge loop)
 *           and what the SDK sent, with the fired signals highlighted
 *   right   tree-SHAP signals behind the decision and the live audit feed
 */
export function AuthConsole() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [run, setRun] = useState<DemoRun | null>(null);
  const [source, setSource] = useState<Source>(AUTH_API ? "live" : "recorded");
  const [outcome, setOutcome] = useState<ChallengeOutcome | null>(null);
  const [busy, setBusy] = useState(false);
  const [feed, setFeed] = useState<{ rows: FeedRow[]; stats: AuthStats | null }>({ rows: [], stats: null });
  const abort = useRef<AbortController | null>(null);

  const refreshFeed = useCallback(() => {
    loadFeed().then(setFeed);
  }, []);

  const go = useCallback(async (id: string, overrides?: Overrides) => {
    abort.current?.abort();
    const ac = new AbortController();
    abort.current = ac;
    setSelected(id);
    setOutcome(null);
    setBusy(true);
    try {
      const res = await runScenario(id, overrides, ac.signal);
      setRun(res.data);
      setSource(res.source);
      return res;
    } catch (e) {
      if ((e as Error).name !== "AbortError") throw e;
    } finally {
      if (abort.current === ac) setBusy(false);
      refreshFeed();
    }
  }, [refreshFeed]);

  // deep link for presenting: /?scenario=sim_swap&verify=pass|fail opens that scenario (and resolves its challenge)
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    listScenarios().then(async ({ data }) => {
      setScenarios(data);
      const res = await go(q.get("scenario") ?? "genuine_routine");
      const v = q.get("verify");
      if (res && v && res.data.response.decision === "challenge") {
        setOutcome(await verifyChallenge(res.data, v === "pass", res.source));
        refreshFeed();
      }
    });
  }, [go, refreshFeed]);

  const verify = async (passed: boolean) => {
    if (!run) return;
    setBusy(true);
    try {
      setOutcome(await verifyChallenge(run, passed, source));
    } finally {
      setBusy(false);
      refreshFeed();
    }
  };

  return (
    <div className="space-backdrop min-h-dvh">
      <header className="material-thick sticky top-0 z-30 flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-separator/50 px-4 py-2.5 sm:px-6">
        <div className="flex items-center gap-2.5">
          <span className="squircle flex size-8 items-center justify-center rounded-[0.6rem] bg-gradient-to-br from-sys-blue to-sys-indigo shadow-[0_4px_14px_rgb(10_132_255/0.35)]">
            <ShieldCheck className="size-4.5 text-white" aria-hidden />
          </span>
          <div className="leading-tight">
            <p className="text-headline">Risk-based transaction authentication</p>
            <p className="text-caption-1 text-label-tertiary">behaviour · device · transaction → allow / challenge / block, with the signals behind it</p>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-caption-1 ${source === "live" ? "bg-sys-green/12 text-sys-green" : "bg-fill-tertiary text-label-secondary"}`}
            title={source === "live" ? `Decided by the running API (${AUTH_API})` : "Playing a recording of the API's output"}>
            <span className={`size-1.5 rounded-full ${source === "live" ? "bg-sys-green" : "bg-label-tertiary"}`} aria-hidden />
            {source === "live" ? "Live API" : "Recorded API replay"}
          </span>
          <Link href="/scam" className="rounded-full bg-fill-tertiary px-3 py-1 text-caption-1 text-label-secondary hover:text-label">
            Scam-session layer (RAKSHAM)
          </Link>
        </div>
      </header>

      <main className="grid gap-4 p-4 sm:p-6 xl:grid-cols-[19rem_minmax(0,1fr)_26rem]">
        <aside aria-label="Scenarios"><ScenarioRail scenarios={scenarios} selected={selected} busy={busy} onRun={go} /></aside>
        <section aria-label="Decision" className="min-w-0 space-y-4">
          <DecisionCard run={run} outcome={outcome} busy={busy} onVerify={verify} />
          <RequestCard run={run} />
        </section>
        <aside aria-label="Signals and audit" className="space-y-4">
          <SignalPanel response={run?.response ?? null} />
          <DecisionFeed rows={feed.rows} stats={feed.stats} live={source === "live"} />
        </aside>
      </main>
    </div>
  );
}
