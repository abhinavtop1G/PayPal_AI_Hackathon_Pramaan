import type { AuthStats, ChallengeOutcome, DemoRun, FeedRow, Overrides, Scenario } from "@/types/auth";

/**
 * BIOS authentication API. With NEXT_PUBLIC_BIOS_API (or NEXT_PUBLIC_RAKSHAM_API) set, the console calls the running
 * service; otherwise, or when a call fails, scenarios play from /data/auth_demo.json, recorded from the same endpoints
 * by `python -m backend.record_auth_demo`. The console only uses the open demo paths (BIOS_OPEN_PATHS), so no API key
 * or signing secret ever ships to the browser.
 */
export const AUTH_API = (process.env.NEXT_PUBLIC_BIOS_API ?? process.env.NEXT_PUBLIC_RAKSHAM_API)?.replace(/\/$/, "");
export type Source = "live" | "recorded";

interface Recording {
  scenarios: Scenario[];
  runs: Record<string, DemoRun>;
  outcomes: Record<string, { pass: ChallengeOutcome; fail: ChallengeOutcome }>;
}

let recording: Promise<Recording> | null = null;
function recorded(): Promise<Recording> {
  recording ??= fetch("/data/auth_demo.json").then((r) => r.json() as Promise<Recording>);
  return recording;
}

async function post<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const r = await fetch(`${AUTH_API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return (await r.json()) as T;
}

export async function listScenarios(): Promise<{ data: Scenario[]; source: Source }> {
  if (AUTH_API) {
    try {
      const r = await fetch(`${AUTH_API}/v1/auth/scenarios`);
      if (r.ok) return { data: (await r.json()) as Scenario[], source: "live" };
    } catch {}
  }
  return { data: (await recorded()).scenarios, source: "recorded" };
}

export async function runScenario(id: string, overrides?: Overrides, signal?: AbortSignal): Promise<{ data: DemoRun; source: Source }> {
  if (AUTH_API) {
    try {
      return { data: await post<DemoRun>(`/v1/auth/demo/${id}`, overrides ?? {}, signal), source: "live" };
    } catch (e) {
      if ((e as Error).name === "AbortError") throw e;
    }
  }
  const rec = await recorded();
  return { data: rec.runs[id] ?? rec.runs["genuine_routine"], source: "recorded" };
}

export async function verifyChallenge(run: DemoRun, passed: boolean, source: Source): Promise<ChallengeOutcome> {
  if (source === "live" && AUTH_API) {
    return post<ChallengeOutcome>("/v1/auth/demo/verify", { decision_id: run.response.decision_id, passed });
  }
  const o = (await recorded()).outcomes[run.scenario];
  if (o) return passed ? o.pass : o.fail;
  return {
    decision_id: run.response.decision_id,
    challenge_type: run.response.challenge_type ?? "sms_otp",
    passed,
    decision: passed ? "allow" : "block",
    device_trusted: passed && (run.response.challenge_type === "passkey" || run.response.challenge_type === "bank_callback"),
    message_en: passed ? "Payment approved." : "This payment was blocked to protect your account.",
    message_hi: passed ? "भुगतान स्वीकृत।" : "आपके खाते की सुरक्षा के लिए यह भुगतान रोका गया है।",
  };
}

export async function loadFeed(): Promise<{ rows: FeedRow[]; stats: AuthStats | null }> {
  if (!AUTH_API) return { rows: [], stats: null };
  try {
    const [rows, stats] = await Promise.all([
      fetch(`${AUTH_API}/v1/auth/decisions?limit=30`).then((r) => r.json() as Promise<FeedRow[]>),
      fetch(`${AUTH_API}/v1/auth/stats`).then((r) => r.json() as Promise<AuthStats>),
    ]);
    return { rows, stats };
  } catch {
    return { rows: [], stats: null };
  }
}
