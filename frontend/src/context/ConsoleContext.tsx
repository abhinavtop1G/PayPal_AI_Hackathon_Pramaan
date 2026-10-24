"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { PramaanClient, type Health } from "@pramaan/web-sdk";
import { AUTH_API, type Source } from "@/api/auth";
import type { ChallengeOutcome, DemoRun } from "@/types/auth";

export type Lang = "en" | "hi";

/** A decision made in this browser session (the decision lab and the capture lab), for the audit log offline. */
export interface SessionEntry {
  at: number;
  run: DemoRun;
  source: Source;
  outcome?: ChallengeOutcome;
}

interface ConsoleState {
  /** the console reaches the API (NEXT_PUBLIC_PRAMAAN_API set and /health answered) */
  source: Source;
  health: Health | null;
  checking: boolean;
  /** SDK client for the configured API (open demo paths), or null offline */
  client: PramaanClient | null;
  lang: Lang;
  setLang: (l: Lang) => void;
  session: SessionEntry[];
  logRun: (run: DemoRun, source: Source) => void;
  logOutcome: (decisionId: string, outcome: ChallengeOutcome) => void;
}

const Ctx = createContext<ConsoleState | null>(null);

export function ConsoleProvider({ children }: { children: React.ReactNode }) {
  const client = useMemo(() => (AUTH_API ? new PramaanClient({ baseUrl: AUTH_API, timeoutMs: 15000, retries: 0, fallback: "throw" }) : null), []);
  const [health, setHealth] = useState<Health | null>(null);
  const [checking, setChecking] = useState(!!client);
  const [lang, setLang] = useState<Lang>("en");
  const [session, setSession] = useState<SessionEntry[]>([]);

  useEffect(() => {
    if (!client) return;
    let live = true;
    const ping = () => client.health().then((h) => live && setHealth(h), () => live && setHealth(null)).finally(() => live && setChecking(false));
    ping();
    const t = setInterval(ping, 30_000);
    return () => {
      live = false;
      clearInterval(t);
    };
  }, [client]);

  const logRun = useCallback((run: DemoRun, source: Source) => {
    setSession((s) => [{ at: Date.now(), run, source }, ...s].slice(0, 200));
  }, []);
  const logOutcome = useCallback((decisionId: string, outcome: ChallengeOutcome) => {
    setSession((s) => s.map((e) => (e.run.response.decision_id === decisionId ? { ...e, outcome } : e)));
  }, []);

  const value = useMemo<ConsoleState>(() => ({
    source: health ? "live" : "recorded", health, checking, client: health ? client : null, lang, setLang, session, logRun, logOutcome,
  }), [health, checking, client, lang, session, logRun, logOutcome]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useConsole(): ConsoleState {
  const c = useContext(Ctx);
  if (!c) throw new Error("useConsole outside ConsoleProvider");
  return c;
}
