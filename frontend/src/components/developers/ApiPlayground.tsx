"use client";

import { useState } from "react";
import { Send, Terminal } from "lucide-react";
import { PramaanError } from "@pramaan/web-sdk";
import { Button } from "@/components/common/Button";
import { SegmentedControl } from "@/components/common/SegmentedControl";
import { Panel } from "@/components/layout/Panel";
import { CodeBlock } from "@/components/ui/CodeBlock";
import { useConsole } from "@/context/ConsoleContext";

type Ep = "authenticate" | "typing" | "health";

const EXAMPLES: Record<Ep, { method: "GET" | "POST"; path: string; body?: unknown }> = {
  authenticate: {
    method: "POST", path: "/v1/authenticate", body: {
      user_id: "demo-asha", channel: "mobile", event_type: "payment",
      device: { device_id: "asha-pixel-7", platform: "android", sim_change_hours: null },
      network: { ip: "49.36.112.45", city: "Ludhiana", lat: 30.901, lon: 75.857 },
      behaviour: { time_to_submit_s: 14, input_events: 30, unknown_call_active: false },
      transaction: { amount: 640, payee_id: "kirana-sharma", payee_is_merchant: true },
    },
  },
  typing: {
    method: "POST", path: "/v1/keystroke/verify", body: {
      user_id: "demo-asha",
      attempt: [0.11, 0.25, 0.14, 0.09, 0.12, 0.03, 0.08, 0.13, 0.05, 0.07, 0.6, 0.53, 0.09, 0.4, 0.31, 0.11, 0.3, 0.19,
        0.1, 0.13, 0.03, 0.12, 0.17, 0.05, 0.1, 0.21, 0.11, 0.08, 0.45, 0.37, 0.12],
    },
  },
  health: { method: "GET", path: "/health" },
};

/** Send a request to the running service and read the answer, from the page (open development mode or open paths). */
export function ApiPlayground() {
  const { client } = useConsole();
  const [ep, setEp] = useState<Ep>("authenticate");
  const [body, setBody] = useState(JSON.stringify(EXAMPLES.authenticate.body, null, 2));
  const [out, setOut] = useState<{ status: string; ms: number; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const e = EXAMPLES[ep];

  const pick = (v: Ep) => {
    setEp(v);
    setBody(EXAMPLES[v].body ? JSON.stringify(EXAMPLES[v].body, null, 2) : "");
    setOut(null);
  };
  const send = async () => {
    if (!client) return;
    let payload: unknown;
    try {
      payload = e.method === "POST" ? JSON.parse(body) : undefined;
    } catch (err) {
      setOut({ status: "invalid JSON", ms: 0, text: (err as Error).message });
      return;
    }
    setBusy(true);
    const t0 = performance.now();
    try {
      const r = await client.call(e.method, e.path, payload);
      setOut({ status: "200 OK", ms: performance.now() - t0, text: JSON.stringify(r, null, 2) });
    } catch (err) {
      const pe = err as PramaanError;
      setOut({ status: pe.status ? `${pe.status} ${pe.code}` : pe.code ?? "error", ms: performance.now() - t0,
        text: JSON.stringify(pe.detail ?? pe.message, null, 2) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel eyebrow="Playground" title="Try the API" icon={Terminal} tint="var(--color-sys-teal)">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SegmentedControl<Ep> size="small" label="Endpoint" value={ep} onChange={pick} options={[
          { value: "authenticate", label: "POST /v1/authenticate" }, { value: "typing", label: "POST /v1/keystroke/verify" },
          { value: "health", label: "GET /health" },
        ]} />
        <Button size="small" onClick={send} disabled={!client || busy}><Send className="size-3.5" aria-hidden /> Send</Button>
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div className="min-w-0">
          {e.method === "POST" ? (
            <textarea value={body} onChange={(x) => setBody(x.target.value)} spellCheck={false} aria-label="Request body (JSON)"
              className="h-[22rem] w-full resize-y rounded-[var(--radius-card)] bg-[#0b0b0d] p-3.5 font-mono text-[0.78rem] leading-[1.6] text-label outline-none ring-1 ring-white/[0.07] focus:ring-sys-blue" />
          ) : (
            <p className="rounded-[var(--radius-card)] bg-fill-quaternary p-3.5 text-footnote text-label-secondary">No body. Returns the loaded services, security mode and model version.</p>
          )}
        </div>
        <div className="min-w-0">
          {out ? (
            <CodeBlock lang="json" title={`${out.status} · ${out.ms.toFixed(0)} ms round trip`} code={out.text} maxHeight="20rem" />
          ) : (
            <p className="rounded-[var(--radius-card)] bg-fill-quaternary p-3.5 text-footnote text-label-tertiary">
              {client ? "Edit the request and send it; the response appears here." :
                "Connect the console to a running service (NEXT_PUBLIC_PRAMAAN_API) to send requests. A secured deployment needs the key and signature from a server: see the quickstarts."}
            </p>
          )}
        </div>
      </div>
    </Panel>
  );
}
