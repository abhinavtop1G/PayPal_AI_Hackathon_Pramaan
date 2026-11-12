"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Ban, Check, CreditCard, ExternalLink, KeyRound, Loader2, RotateCcw, ShieldCheck, Terminal } from "lucide-react";
import { paypalConfig, refundCheckout, startCheckout, verifyCheckout } from "@/api/paypal";
import { RiskGauge } from "@/components/charts/RiskGauge";
import { Button } from "@/components/common/Button";
import { Panel } from "@/components/layout/Panel";
import { ScenarioGallery } from "@/components/lab/ScenarioGallery";
import { CodeBlock } from "@/components/ui/CodeBlock";
import { DecisionBadge } from "@/components/ui/DecisionBadge";
import { CHALLENGE_LABEL, DECISION_STYLE, FAMILY_TINT, inr } from "@/config/authSignals";
import { useConsole } from "@/context/ConsoleContext";
import type { ChallengeOutcome } from "@/types/auth";
import type { Checkout, CheckoutStart, PayPalConfig, PayPalStatus } from "@/types/paypal";
import { PayPalButton } from "./PayPalButton";

const STATUS: Record<PayPalStatus, { label: string; tone: string }> = {
  connected: { label: "PayPal sandbox connected", tone: "bg-sys-green/12 text-sys-green" },
  not_configured: { label: "PayPal sandbox not connected", tone: "bg-fill-tertiary text-label-secondary" },
  bad_credentials: { label: "PayPal rejected the credentials", tone: "bg-sys-red/12 text-sys-red" },
  unreachable: { label: "Can't reach PayPal", tone: "bg-sys-red/12 text-sys-red" },
};

/**
 * A PayPal checkout with PRAMAAN in front of it. The decision comes first: a blocked payment never reaches PayPal, a challenged
 * one waits for its step-up, and an allowed one gets a real sandbox order that the server re-checks before capturing.
 */
export function PayPalCheckout() {
  const { source, checking, lang, logRun, logOutcome } = useConsole();
  const [config, setConfig] = useState<PayPalConfig | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [flow, setFlow] = useState<CheckoutStart | null>(null);
  const [checkout, setCheckout] = useState<Checkout | null>(null);
  const [outcome, setOutcome] = useState<ChallengeOutcome | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const latest = useRef(0); // only the most recent pick may update the page

  const pick = useCallback(async (id: string) => {
    const mine = ++latest.current;
    setSelected(id);
    setFlow(null);
    setCheckout(null);
    setOutcome(null);
    setProblem(null);
    setBusy(true);
    try {
      const started = await startCheckout(id);
      if (mine !== latest.current) return;
      setFlow(started);
      setCheckout(started.checkout);
      logRun(started.run, "live");
    } catch (e) {
      if (mine === latest.current) setProblem((e as Error).message);
    } finally {
      if (mine === latest.current) setBusy(false);
    }
  }, [logRun]);

  useEffect(() => {
    if (source !== "live") return;
    let on = true;
    paypalConfig().then((c) => {
      if (!on) return;
      setConfig(c);
      // deep link for demos: /console/checkout?scenario=sim_swap
      const id = new URLSearchParams(window.location.search).get("scenario");
      if (id && c.scenarios.some((s) => s.id === id)) void pick(id);
    }, (e: Error) => on && setProblem(e.message));
    return () => {
      on = false;
    };
  }, [source, pick]);

  const verify = async (passed: boolean) => {
    if (!checkout) return;
    setBusy(true);
    setProblem(null);
    try {
      const r = await verifyCheckout(checkout.id, passed);
      setCheckout(r.checkout);
      setOutcome(r.outcome);
      logOutcome(r.checkout.decision_id, r.outcome);
    } catch (e) {
      setProblem((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const refund = async () => {
    if (!checkout) return;
    setBusy(true);
    setProblem(null);
    try {
      setCheckout((await refundCheckout(checkout.id)).checkout);
    } catch (e) {
      setProblem((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (checking) {
    return <Loader2 className="size-6 animate-spin text-label-tertiary" aria-label="Connecting to the API" />;
  }

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-eyebrow text-label-tertiary">PayPal checkout</p>
          <h1 className="mt-1 text-large-title">Fraud stops before PayPal</h1>
          <p className="mt-1 max-w-[52rem] text-subheadline text-label-secondary">
            PRAMAAN decides every payment first. A blocked payment never reaches PayPal, a suspicious one waits for the right
            step-up, and a clean one goes straight to a real PayPal sandbox order. Pick who is paying.
          </p>
        </div>
        {config && <span className={`rounded-full px-3 py-1 text-caption-1 ${STATUS[config.status].tone}`}>{STATUS[config.status].label}</span>}
      </header>

      {source !== "live" ? (
        <Panel eyebrow="Needs the API" title="Start the API to use the checkout" icon={Terminal} tint="var(--color-sys-blue)">
          <p className="text-subheadline text-label-secondary">
            Every step here is a live call, so there is no recording to play. Run <code className="font-mono">python run.py</code> from
            the repository root.
          </p>
        </Panel>
      ) : (
        <>
          {config && <ScenarioGallery scenarios={config.scenarios} selected={selected} busy={busy} onPick={pick} />}
          {problem && <p role="alert" className="squircle rounded-[var(--radius-card)] bg-sys-red/12 p-3.5 text-footnote text-sys-red">{problem}</p>}
          {flow && checkout ? (
            <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
              <Decision flow={flow} checkout={checkout} outcome={outcome} busy={busy} lang={lang} onVerify={verify} />
              {config && (
                <PayPalStep config={config} flow={flow} checkout={checkout} busy={busy} onRefund={refund} onProblem={setProblem}
                  onCaptured={(c) => {
                    setProblem(null);
                    setCheckout(c);
                  }} />
              )}
            </div>
          ) : (
            !busy && config && <p className="text-subheadline text-label-tertiary">Pick a scenario above to start a payment.</p>
          )}
          {busy && !flow && <Loader2 className="size-6 animate-spin text-label-tertiary" aria-label="Deciding" />}
        </>
      )}
    </div>
  );
}

function Decision({ flow, checkout, outcome, busy, lang, onVerify }: {
  flow: CheckoutStart; checkout: Checkout; outcome: ChallengeOutcome | null; busy: boolean; lang: "en" | "hi"; onVerify: (passed: boolean) => void;
}) {
  const r = flow.run.response;
  const challenge = r.challenge_type ? CHALLENGE_LABEL[r.challenge_type] : null;
  return (
    <Panel eyebrow="Step 1 · PRAMAAN decides" title={flow.run.title.replace(/^(Genuine|Attack): /, "")} icon={ShieldCheck} tint={DECISION_STYLE[r.decision].tint}>
      <p className="text-subheadline text-label-secondary">{flow.run.story}</p>
      <div className="mt-3 grid gap-4 sm:grid-cols-[auto_minmax(0,1fr)]">
        <div className="flex flex-col items-center">
          <RiskGauge risk={r.risk_score} decision={r.decision} size={180} />
          <span className="rounded-full bg-fill-tertiary px-2.5 py-1 font-mono text-caption-1 text-label-secondary">{r.latency_ms.toFixed(0)} ms</span>
        </div>
        <div className="min-w-0 space-y-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <DecisionBadge decision={r.decision} size="md" />
            {challenge && (
              <span className="flex items-center gap-1.5 rounded-full bg-fill-tertiary px-3 py-1 text-subheadline">
                <KeyRound className="size-4 text-sys-orange" aria-hidden /> {challenge.title}
              </span>
            )}
          </div>
          {r.reasons.length > 0 ? (
            <ul className="space-y-1.5">
              {r.reasons.map((x) => (
                <li key={x.signal} className="flex items-start gap-2 text-footnote" lang={lang === "hi" ? "hi" : undefined}>
                  <span className="mt-[0.4rem] size-2 shrink-0 rounded-full" style={{ background: FAMILY_TINT[x.family] }} aria-hidden />
                  {lang === "hi" ? x.text_hi : x.text_en}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-footnote text-label-secondary">Nothing unusual against her history.</p>
          )}
          {checkout.gate === "step_up" && (
            <div className="space-y-2 pt-1">
              {challenge && <p className="text-footnote text-label-secondary">{challenge.why}</p>}
              <div className="flex flex-wrap gap-2">
                <Button tint="green" size="small" onClick={() => onVerify(true)} disabled={busy}>Customer passes the step-up</Button>
                <Button tint="red" variant="tinted" size="small" onClick={() => onVerify(false)} disabled={busy}>Step-up fails</Button>
              </div>
            </div>
          )}
          {outcome && (
            <p className="text-footnote" style={{ color: DECISION_STYLE[outcome.decision].tint }}>
              {outcome.passed ? "Step-up passed: the payment may go to PayPal." : "Step-up failed: blocked, and it can't be retried."}
            </p>
          )}
        </div>
      </div>
    </Panel>
  );
}

function PayPalStep({ config, flow, checkout, busy, onRefund, onCaptured, onProblem }: {
  config: PayPalConfig; flow: CheckoutStart; checkout: Checkout; busy: boolean;
  onRefund: () => void; onCaptured: (c: Checkout) => void; onProblem: (message: string) => void;
}) {
  const price = (
    <p className="text-title-2">
      ${checkout.amount} <span className="text-subheadline text-label-tertiary">{checkout.currency} · {inr(checkout.amount_inr)} at ₹{config.inr_per_usd} per $1 (demo rate)</span>
    </p>
  );

  if (checkout.gate === "blocked") {
    return (
      <Panel eyebrow="Step 2 · PayPal" title="Stopped before PayPal" icon={Ban} tint="var(--color-sys-red)">
        {price}
        <p className="mt-2 text-subheadline text-label-secondary">
          No PayPal order was created, and the server refuses to create one for this decision, whatever the browser asks.
        </p>
      </Panel>
    );
  }
  if (checkout.gate === "step_up") {
    return (
      <Panel eyebrow="Step 2 · PayPal" title="Waiting for the step-up" icon={KeyRound} tint="var(--color-sys-orange)">
        {price}
        <p className="mt-2 text-subheadline text-label-secondary">No PayPal order exists yet. One is created only if the step-up passes.</p>
      </Panel>
    );
  }
  if (checkout.capture) {
    return <Receipt checkout={checkout} busy={busy} onRefund={onRefund} />;
  }
  if (config.status !== "connected" || !config.client_id) {
    return (
      <Panel eyebrow="Step 2 · PayPal" title="This payment may go to PayPal" icon={CreditCard} tint="var(--color-sys-blue)">
        {price}
        <p className="mt-2 text-subheadline text-label-secondary">
          {config.status === "not_configured"
            ? "PayPal isn't connected yet, so nothing is sent. Add sandbox keys to .env and restart (README: Connect PayPal). This is the order PRAMAAN would create:"
            : config.status === "bad_credentials"
              ? "PayPal rejected the credentials in .env. Check them and restart. This is the order PRAMAAN would create:"
              : "PayPal can't be reached right now. This is the order PRAMAAN would create:"}
        </p>
        <div className="mt-3"><CodeBlock lang="json" title="Orders API request" code={JSON.stringify(flow.order_preview, null, 2)} /></div>
      </Panel>
    );
  }
  return (
    <Panel eyebrow="Step 2 · PayPal" title="Pay with PayPal" icon={CreditCard} tint="var(--color-sys-blue)">
      {price}
      <p className="mb-3 mt-2 text-footnote text-label-secondary">Sandbox: test money only. Log in with a sandbox buyer, or choose Debit or Credit Card and use PayPal&apos;s test card 4005 5192 0000 0004 with any future expiry, any 3-digit code and a made-up US address.</p>
      <PayPalButton clientId={config.client_id} currency={config.currency} checkoutId={checkout.id} onCaptured={onCaptured} onProblem={onProblem} />
    </Panel>
  );
}

function Receipt({ checkout, busy, onRefund }: { checkout: Checkout; busy: boolean; onRefund: () => void }) {
  const cap = checkout.capture!;
  const done = cap.status === "COMPLETED";
  const rows: [string, string][] = [
    ["Charged", `$${cap.amount} ${cap.currency}`],
    ["Capture status", cap.status],
    ["PayPal order", checkout.order_id ?? ""],
    ["PayPal capture", cap.id],
    ["PRAMAAN decision (custom_id)", checkout.decision_id],
  ];
  if (checkout.refund) rows.push(["Refund", `${checkout.refund.status} · ${checkout.refund.id}`]);
  return (
    <Panel eyebrow="Step 2 · PayPal" title={checkout.refund ? "Captured, then refunded" : done ? "Paid through PayPal" : `Capture ${cap.status.toLowerCase()}`}
      icon={Check} tint={done ? "var(--color-sys-green)" : "var(--color-sys-orange)"}>
      <dl className="space-y-1.5 text-footnote">
        {rows.map(([k, v]) => (
          <div key={k} className="flex flex-wrap justify-between gap-x-4 gap-y-0.5">
            <dt className="text-label-secondary">{k}</dt>
            <dd className="min-w-0 break-all font-mono">{v}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        {!checkout.refund && (
          <Button tint="red" variant="tinted" size="small" onClick={onRefund} disabled={busy}>
            <span className="flex items-center gap-1.5"><RotateCcw className="size-3.5" aria-hidden /> Refund: fraud reported later</span>
          </Button>
        )}
        <a href="https://www.sandbox.paypal.com" target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-footnote text-sys-blue hover:underline">
          See it in the PayPal sandbox <ExternalLink className="size-3.5" aria-hidden />
        </a>
      </div>
    </Panel>
  );
}
