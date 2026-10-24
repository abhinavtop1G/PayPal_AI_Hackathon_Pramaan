"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Braces, Cpu, RefreshCw, Send } from "lucide-react";
import { Pramaan, deviceId, type AuthRequest, type AuthResponse, type Environment } from "@pramaan/web-sdk";
import { Button } from "@/components/common/Button";
import { toast } from "@/components/common/Toaster";
import { Panel } from "@/components/layout/Panel";
import { CodeBlock } from "@/components/ui/CodeBlock";
import { DecisionBadge } from "@/components/ui/DecisionBadge";
import { CHALLENGE_LABEL, pct } from "@/config/authSignals";
import { useConsole } from "@/context/ConsoleContext";
import { DEMO_USER, newHub, type SdkBus, type SdkHub } from "./sdkBus";
import { TouchLab } from "./TouchLab";
import { TypingLab } from "./TypingLab";

/**
 * The web SDK running in this page, as a bank's own page would run it: typing rhythm on a password field, touch
 * gestures on a pad, device and session signals, and the exact request it would send.
 */
export function LiveCapture() {
  const [hub] = useState<SdkHub>(newHub);
  const [sdk, setSdk] = useState<Pramaan | null>(null);

  // the SDK lives as long as the touch pad it observes (a ref callback with cleanup, React 19)
  const padRef = useCallback((pad: HTMLDivElement | null) => {
    if (!pad) return;
    const p = Pramaan.init({
      root: pad, mouseAsTouch: true, consent: true,
      onGesture: (f) => hub.onGesture.forEach((h) => h(f)),
      onTypingAttempt: (a) => hub.onAttempt.forEach((h) => h(a)),
      onTypingReset: (w) => hub.onReset.forEach((h) => h(w)),
    });
    p.startFlow();
    setSdk(p);
    return () => {
      p.destroy();
      setSdk(null);
    };
  }, [hub]);
  const bus = useMemo<SdkBus>(() => ({ ...hub, sdk }), [hub, sdk]);

  return (
    <div className="mx-auto max-w-[96rem] space-y-5">
      <header>
        <p className="text-eyebrow text-label-tertiary">Live capture · @pramaan/web-sdk</p>
        <h1 className="mt-1 text-large-title">Your browser is the device</h1>
        <p className="mt-1 max-w-[54rem] text-subheadline text-label-secondary">
          The web SDK is running on this page, unmodified. Type and swipe below: it measures your typing rhythm and touch
          dynamics exactly as the models were trained (checked against the Python pipeline with shared golden vectors),
          and builds the request a bank page would send.
        </p>
      </header>
      <TypingLab bus={bus} />
      <TouchLab bus={bus} padRef={padRef} />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <DevicePanel sdk={sdk} />
        <PayloadPanel sdk={sdk} />
      </div>
    </div>
  );
}

function DevicePanel({ sdk }: { sdk: Pramaan | null }) {
  const [consent, setConsent] = useState(true);
  const env: Environment | null = useMemo(() => sdk?.environment() ?? null, [sdk]);
  const id = useMemo(() => (sdk ? deviceId() : ""), [sdk]);
  const rows: [string, string][] = env ? [
    ["Install ID (device_id)", id || "…"],
    ["Automation detected", env.automation.length ? env.automation.join(", ") : "none"],
    ["Viewport", `${env.viewport.width}×${env.viewport.height} @${env.viewport.dpr}x`],
    ["Touch points", String(env.touchPoints)],
    ["Motion sensors", env.motionSensors ? "available" : "not available"],
    ["Secure context", env.secureContext ? "yes" : "no"],
    ["Time zone", env.timezone],
    ["Language", env.language],
  ] : [];
  return (
    <Panel eyebrow="Device · what a browser can honestly report" title="This device" icon={Cpu} tint="var(--color-fam-device)">
      <dl className="space-y-1">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-baseline justify-between gap-3 border-b border-separator/40 py-1.5 text-footnote">
            <dt className="text-label-secondary">{k}</dt>
            <dd className="truncate text-right font-mono" title={v}>{v}</dd>
          </div>
        ))}
      </dl>
      <label className="mt-4 flex items-center justify-between gap-3 rounded-[0.8rem] bg-fill-quaternary px-3 py-2.5 text-footnote">
        <span>
          <span className="block">Behavioural-biometrics consent</span>
          <span className="block text-caption-1 text-label-tertiary">DPDP purpose <span className="font-mono">behavioural_biometrics</span>; off = no touch, motion or typing data</span>
        </span>
        <input type="checkbox" checked={consent} onChange={(e) => { setConsent(e.target.checked); sdk?.setConsent(e.target.checked); }}
          className="size-5 accent-[var(--color-sys-blue)]" />
      </label>
      <p className="mt-3 text-caption-1 text-label-tertiary">
        Root, SIM change, remote-access apps, screen recording and the caller on the line need the Android SDK; a browser cannot see them.
      </p>
    </Panel>
  );
}

function PayloadPanel({ sdk }: { sdk: Pramaan | null }) {
  const { client, logRun } = useConsole();
  const [req, setReq] = useState<AuthRequest | null>(null);
  const [res, setRes] = useState<AuthResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    if (!sdk) return;
    setReq(await sdk.collect({ userId: DEMO_USER, transaction: { amount: 2500, payee_id: "kirana-sharma", payee_is_merchant: true } }));
  }, [sdk]);
  useEffect(() => {
    const first = setTimeout(refresh, 0);
    const t = setInterval(refresh, 3000);
    return () => {
      clearTimeout(first);
      clearInterval(t);
    };
  }, [refresh]);

  const shown = req && {
    ...req,
    behaviour: {
      ...req.behaviour,
      gestures: req.behaviour?.gestures ? [req.behaviour.gestures[0], `… ${req.behaviour.gestures.length - 1} more gestures (21 features each)`] : null,
    },
  };
  const send = async () => {
    if (!client || !req) return;
    setBusy(true);
    try {
      const r = await client.authenticate(req);
      setRes(r);
      logRun({ scenario: "capture", title: "Live capture", story: "Request built by the web SDK on the capture page.", is_attack: null,
        request: { ...req, ts: Date.now() / 1000, channel: "web", event_type: "payment",
          behaviour: { ...req.behaviour, gestures: req.behaviour?.gestures ? `${req.behaviour.gestures.length} gestures from this browser` : null,
            keystrokes: req.behaviour?.keystrokes ? "1 attempt typed on this page" : null } } as never,
        response: r }, "live");
    } catch (e) {
      toast(`Could not decide: ${(e as Error).message}`, "alert");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel eyebrow="Request" title="What the SDK would send now" icon={Braces} tint="var(--color-sys-blue)" accessory={
      <div className="flex gap-2">
        <Button size="small" tint="gray" variant="tinted" onClick={refresh}><RefreshCw className="size-3.5" aria-hidden /> Refresh</Button>
        <Button size="small" onClick={send} disabled={!client || busy}><Send className="size-3.5" aria-hidden /> Decide it</Button>
      </div>}>
      {res && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-[0.8rem] bg-fill-quaternary p-3">
          <DecisionBadge decision={res.decision} size="md" />
          {res.challenge_type && <span className="text-subheadline">{CHALLENGE_LABEL[res.challenge_type].title}</span>}
          <span className="font-mono text-caption-1 text-label-secondary">risk {pct(res.risk_score)} · {res.latency_ms.toFixed(0)} ms</span>
          <p className="w-full text-caption-1 text-label-secondary">
            {res.reasons.map((r) => r.text_en).join(" · ") || "No signal stands out."}
            {res.rule === "new_device_binding" ? " This browser is a device Asha has never used: the first payment from a new device is always stepped up." : ""}
          </p>
        </div>
      )}
      {shown ? <CodeBlock lang="json" title="pramaan.collect() → POST /v1/authenticate" code={JSON.stringify(shown, null, 2)} maxHeight="24rem" />
        : <div className="skeleton h-64 rounded-2xl" />}
      {!client && <p className="mt-2 text-caption-1 text-label-tertiary">Connect the API to send it for a decision.</p>}
    </Panel>
  );
}
