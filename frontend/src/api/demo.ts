import type { PersonaId } from "@/config/personas";
import type { ScenarioId } from "@/config/scenarios";
import { RECORDED } from "@/data";
import type { CampaignData, CaseGraph, DemoInput, DemoReplay, Fleet } from "@/types/demo";

/**
 * Data access. With NEXT_PUBLIC_PRAMAAN_API set (e.g. http://127.0.0.1:8000) the page asks the running backend;
 * otherwise, or if a call fails, it uses recordings made from the same endpoints by `python -m backend.record_demo`.
 */
export const API = process.env.NEXT_PUBLIC_PRAMAAN_API?.replace(/\/$/, "");

export { RECORDED };
export type Source = "live" | "recorded";

export async function loadReplay(typology: ScenarioId, persona: PersonaId, signal?: AbortSignal): Promise<{ data: DemoReplay; source: Source }> {
  if (API) {
    try {
      // All demo sessions share one simulated user per persona; reset the policy's per-user history so a replay doesn't
      // depend on which scenarios ran before it (demo server only: this clears every in-memory session).
      await fetch(`${API}/v1/admin/reset?services=session`, { method: "POST", signal });
      const r = await fetch(`${API}/v1/demo/${typology}?persona=${persona}`, { method: "POST", signal });
      if (r.ok) return { data: (await r.json()) as DemoReplay, source: "live" };
    } catch (e) {
      if ((e as Error).name === "AbortError") throw e;
    }
  }
  return { data: RECORDED[persona][typology], source: "recorded" };
}

/** A recorded day of held-out simulator sessions run through the pipeline (static file, fetched on demand). */
export async function loadFleet(signal?: AbortSignal): Promise<Fleet> {
  const r = await fetch("/data/fleet.json", { signal });
  return (await r.json()) as Fleet;
}

/**
 * Payee-side cases and their money-flow graphs: live when the API has a ledger loaded, else the recording. Loading one
 * (POST /v1/campaign/demo/load) takes minutes on a CPU, so opening the page doesn't start it.
 */
export async function loadCampaign(signal?: AbortSignal): Promise<{ data: CampaignData; source: Source }> {
  if (API) {
    try {
      const cases = await fetch(`${API}/v1/campaign/cases?top=12`, { signal }).then((r) => r.json());
      if (!cases.cases?.length) throw new Error("no live cases");
      const graphs: Record<string, CaseGraph> = {};
      await Promise.all(
        cases.cases.map(async (c: { case_id: string }) => {
          graphs[c.case_id] = await fetch(`${API}/v1/campaign/cases/${c.case_id}/graph`, { signal }).then((r) => r.json());
        }),
      );
      return { data: { until_day: cases.summary?.now_day ?? 60, ...cases, graphs }, source: "live" };
    } catch (e) {
      if ((e as Error).name === "AbortError") throw e;
    }
  }
  const r = await fetch("/data/campaign.json", { signal });
  return { data: (await r.json()) as CampaignData, source: "recorded" };
}

/** Analyst credit hold on a case (live API only). */
export async function holdCase(caseId: string) {
  if (!API) return null;
  const r = await fetch(`${API}/v1/campaign/cases/${caseId}/hold`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ analyst: "demo-analyst", reason: "confirmed campaign" }),
  });
  return r.ok ? r.json() : null;
}

// ---------------------------------------------------------------- session builder (live API only)
export async function apiHealthy(signal?: AbortSignal) {
  if (!API) return false;
  try {
    const r = await fetch(`${API}/health`, { signal });
    const h = await r.json();
    return Array.isArray(h.loaded) && h.loaded.includes("session");
  } catch {
    return false;
  }
}

export async function startSession(id: string, avgTxnAmount: number, startIso: string, hmogSubject?: number) {
  const r = await fetch(`${API}/v1/session/${id}/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user: { user_id: `builder-${id}`, avg_txn_amount: avgTxnAmount, hmog_subject: hmogSubject ?? null },
      start_time: startIso,
    }),
  });
  if (!r.ok) throw new Error(await r.text());
}

/** A real HMOG touch window for the builder's demo customer: own hands, modelled stress, or someone else's hands. */
export async function demoTouch(profile: "normal" | "coerced" | "remote") {
  const r = await fetch(`${API}/v1/demo/touch?profile=${profile}`);
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as { subject: number; gestures: Record<string, number | null>[] };
}

/** Numbers on (and not on) the demo telecom's reported list, for the builder's call buttons. */
export async function demoNumbers() {
  const r = await fetch(`${API}/v1/demo/numbers`);
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as { reported: string[]; clean: string[] };
}

export async function sendEvent(id: string, ev: DemoInput) {
  const r = await fetch(`${API}/v1/session/${id}/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(ev),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
