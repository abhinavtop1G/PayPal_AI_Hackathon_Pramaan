"use client";

import { Activity, Fingerprint, Gauge, Keyboard, Scale, Target, TriangleAlert } from "lucide-react";
import { useReport } from "@/api/console";
import { BarList } from "@/components/charts/BarList";
import { DesignScatter } from "@/components/charts/DesignScatter";
import { Heatmap } from "@/components/charts/Heatmap";
import { Panel } from "@/components/layout/Panel";
import { StatTile } from "@/components/ui/StatTile";
import { ATTACK_LABEL, FAMILY_TINT, SIGNAL_FAMILY, SIGNAL_LABEL } from "@/config/authSignals";
import type { ModelReport as Report } from "@/types/console";

const ENGINE = "risk engine (all signals)";
const SHORT: Record<string, string> = {
  [ENGINE]: "PRAMAAN (all signals)", "behaviour signals only": "behaviour only", "device signals only": "device only",
  "transaction signals only": "transaction only", "SMS OTP on every payment": "SMS OTP always", "rules engine + SMS OTP": "rules + OTP",
};
const ATTACKS = ["ato_new_device", "sim_swap", "bot", "remote_access", "coerced"];
const TOUCH_METHOD: Record<string, string> = { stats_cosine: "window statistics, cosine", stats_lda: "window statistics + LDA", bilstm: "BiLSTM", "bilstm+lda_fused": "BiLSTM + LDA (served)" };
const TYPING_METHOD: Record<string, string> = { manhattan: "scaled Manhattan", mahalanobis: "Mahalanobis", cnn: "1D-CNN", fusion: "CNN + Manhattan (served)" };

/** The evaluation, from the reports the training scripts wrote (ml/reports, backend/reports). */
export function ModelReport() {
  const { data, error } = useReport();
  if (error) return <p className="text-sys-red">Could not load the model report: {error}</p>;
  if (!data) return <div className="mx-auto max-w-[96rem] space-y-5"><div className="skeleton h-24 rounded-2xl" /><div className="skeleton h-96 rounded-3xl" /></div>;
  return <Body r={data} />;
}

function Body({ r }: { r: Report }) {
  const a = r.auth, eng = a.designs[ENGINE], otp = a.designs["SMS OTP on every payment"];
  const names = Object.keys(a.designs);
  const fmt = (v: number) => `${(100 * v).toFixed(1)}%`;
  return (
    <div className="mx-auto max-w-[96rem] space-y-5">
      <header>
        <p className="text-eyebrow text-label-tertiary">Model · {a.data.users.toLocaleString("en-IN")} simulated customers · {a.data.requests.toLocaleString("en-IN")} requests over 60 days</p>
        <h1 className="mt-1 text-large-title">How well it works, and against what</h1>
        <p className="mt-1 max-w-[56rem] text-subheadline text-label-secondary">
          Trained on days 0–35, test days 45–60 replayed through the service, challenge outcomes simulated. The same
          replay for one-family models, an SMS OTP on every payment and a rules engine. Touch windows are real HMOG
          gestures, typing real CMU keystrokes; attacks and genuine behaviour are simulated, so these numbers compare
          designs rather than predict real-world accuracy.
        </p>
      </header>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile icon={Target} label="Attack requests stopped" value={`${eng.attacks_stopped_pct}%`} accent="var(--color-sys-green)"
          detail={`SMS OTP on every payment: ${otp.attacks_stopped_pct}%`} />
        <StatTile icon={Scale} label="Genuine requests challenged" value={`${eng.genuine_challenged_pct}%`} accent="var(--color-sys-blue)"
          detail={`SMS OTP: 100% · finally blocked ${eng.genuine_blocked_pct}%`} />
        <StatTile icon={Activity} label="ROC-AUC, test days" value={a.ranking[ENGINE].roc_auc.toFixed(3)} accent="var(--color-sys-indigo)"
          detail={`PR-AUC ${a.ranking[ENGINE].pr_auc.toFixed(2)} at ${(100 * a.data.attack_requests / a.data.requests).toFixed(2)}% attacks`} />
        <StatTile icon={Gauge} label="Decision latency, p95" value={`${r.http_latency[0]?.p95 ?? a.latency.p95_ms} ms`} accent="var(--color-sys-orange)"
          detail={`over HTTP with key + HMAC checks · in-process ${a.latency.p95_ms} ms`} />
      </section>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Panel eyebrow="Friction vs protection" title="Every design on the same replay">
          <DesignScatter height={320} points={names.map((n) => ({ name: n, short: SHORT[n] ?? n, friction: a.designs[n].genuine_challenged_pct,
            stopped: a.designs[n].attacks_stopped_pct, highlight: n === ENGINE }))} />
          <p className="mt-2 text-caption-1 text-label-tertiary">Top-left is better: more attacks stopped while interrupting fewer customers. Log scale on friction.</p>
        </Panel>
        <Panel eyebrow="Table view" title="The numbers">
          <div className="relative overflow-x-auto">
            <table className="w-full text-footnote">
              <thead>
                <tr className="text-left text-caption-1 text-label-tertiary">
                  <th className="pb-2 font-medium">design</th><th className="pb-2 text-right font-medium">genuine challenged</th>
                  <th className="pb-2 text-right font-medium">attacks stopped</th><th className="pb-2 text-right font-medium">money stopped</th>
                </tr>
              </thead>
              <tbody>
                {names.map((n) => (
                  <tr key={n} className={`border-t border-separator/40 ${n === ENGINE ? "font-semibold" : "text-label-secondary"}`}>
                    <td className="py-2 pr-2">{SHORT[n] ?? n}</td>
                    <td className="py-2 text-right tabular-nums">{a.designs[n].genuine_challenged_pct}%</td>
                    <td className="py-2 text-right tabular-nums">{a.designs[n].attacks_stopped_pct}%</td>
                    <td className="py-2 text-right tabular-nums">{a.designs[n].attack_money_stopped_pct}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-caption-1 text-label-tertiary">
            Attack campaigns with any success: {eng.campaigns_with_any_success_pct}% with PRAMAAN, {otp.campaigns_with_any_success_pct}% with SMS OTP always.
          </p>
        </Panel>
      </div>

      <Panel eyebrow="Per attack type" title="Share of attack requests finally stopped" icon={Target} tint="var(--color-sys-red)">
        <Heatmap caption="Attack requests finally stopped, by design and attack type" rows={names} cols={ATTACKS}
          value={(d, c) => a.designs[d].per_scenario[c]} rowLabel={(d) => SHORT[d] ?? d} colLabel={(c) => ATTACK_LABEL[c]} highlightRow={ENGINE} />
        <p className="mt-3 text-caption-1 text-label-tertiary">
          An SMS OTP never stops a SIM swap (the OTP goes to the attacker&apos;s SIM) and rarely a coached victim (the owner types it). Matching the
          challenge to the signals is what moves those columns. The coached victim remains the hardest case.
        </p>
      </Panel>

      <div className="grid gap-5 lg:grid-cols-3">
        <Panel eyebrow="Robustness" title="Harder attacks hide more signals">
          <BarList ariaLabel="Attack requests stopped by difficulty" rows={Object.entries(a.difficulty).map(([k, v]) => ({
            key: k, label: k, value: v.stopped, display: `${v.stopped}%`, sub: `${v.n} attack requests`, color: "var(--color-series-1)",
          }))} max={100} />
          <p className="mt-3 text-caption-1 text-label-tertiary">Difficulty is the simulator&apos;s knob: residential proxies in the victim&apos;s city, human-like timing, calls on apps the bank cannot see.</p>
        </Panel>
        <Panel eyebrow="Ranking, test days" title="One model beats any one family">
          <BarList ariaLabel="ROC-AUC by model" rows={Object.entries(a.ranking).map(([k, v]) => ({
            key: k, label: SHORT[k] ?? k, value: v.roc_auc, display: v.roc_auc.toFixed(3), sub: `PR-AUC ${v.pr_auc.toFixed(2)}`,
            color: k === ENGINE ? "var(--color-brand-2)" : "var(--color-gray-1)",
          }))} max={1} />
        </Panel>
        <Panel eyebrow="Model" title="What it relies on (gain)">
          <BarList ariaLabel="Feature importance by gain" rows={a.importance.slice(0, 10).map(([f, g]) => ({
            key: f, label: SIGNAL_LABEL[f] ?? f, value: g, display: g.toFixed(0), color: FAMILY_TINT[SIGNAL_FAMILY[f] ?? "device"],
          }))} />
          <div className="mt-2 flex flex-wrap gap-3 text-caption-1 text-label-secondary">
            {(["behaviour", "device", "transaction"] as const).map((f) => (
              <span key={f} className="flex items-center gap-1.5"><span className="size-2.5 rounded-[3px]" style={{ background: FAMILY_TINT[f] }} />{f}</span>
            ))}
          </div>
        </Panel>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel eyebrow={`Typing rhythm · CMU, ${r.keystroke.users.test} people never seen in training`} title="Keystroke verification error (EER)" icon={Keyboard} tint="var(--color-fam-behaviour)">
          <BarList ariaLabel="Keystroke per-user equal error rate by method, lower is better" rows={["manhattan", "mahalanobis", "cnn", "fusion"]
            .filter((k) => r.keystroke.sessions[k]).map((k) => {
              const s = r.keystroke.sessions[k];
              return { key: k, label: TYPING_METHOD[k] ?? k, value: s.one_try[0], display: `${fmt(s.one_try[0])} · 3 tries ${fmt(s.three_tries[0])}`,
                color: k === "fusion" ? "var(--color-fam-behaviour)" : "var(--color-gray-1)" };
            })} max={0.25} />
          <p className="mt-3 text-caption-1 text-label-tertiary">
            Per-user EER, enrolled on 4 sessions and tested on 4 later ones, mean over 3 training seeds; lower is better. Sanity
            check on the paper&apos;s own protocol (Killourhy &amp; Maxion 2009): our scaled Manhattan gets {(100 * r.keystroke.all_users.manhattan[0]).toFixed(1)}%,
            published {(100 * (r.keystroke.published["Manhattan (scaled)"] ?? 0.096)).toFixed(1)}%.
          </p>
        </Panel>
        <Panel eyebrow="Touch dynamics · HMOG, held-out people" title="Touch verification error (EER)" icon={Fingerprint} tint="var(--color-fam-behaviour)">
          <BarList ariaLabel="Touch equal error rate by method and window, lower is better" rows={Object.entries(r.touch.test.n10).map(([k, v]) => ({
            key: k, label: `${TOUCH_METHOD[k] ?? k}`, value: v, display: `${fmt(v)} · 20 gestures ${fmt(r.touch.test.n20[k])}`,
            color: k === "bilstm+lda_fused" ? "var(--color-fam-behaviour)" : "var(--color-gray-1)",
          }))} max={0.25} />
          <p className="mt-3 text-caption-1 text-label-tertiary">Windows of 10 gestures (bar) and 20. Touch alone is a weak verifier; as one signal among 27 it is what separates remote-access takeovers from the owner.</p>
        </Panel>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel eyebrow="Latency" title="Fast enough to sit in the payment path" icon={Gauge} tint="var(--color-sys-orange)">
          <BarList ariaLabel="Decision latency percentiles" rows={[
            ...r.http_latency.map((h) => ({ key: h.what, label: h.what.replace("POST /v1/authenticate ", "HTTP "), value: h.p95,
              display: `p50 ${h.p50} · p95 ${h.p95} · p99 ${h.p99} ms`, color: "var(--color-series-1)" })),
            { key: "inproc", label: "in-process (features + model + SHAP + policy)", value: a.latency.p95_ms,
              display: `p50 ${a.latency.p50_ms} · p95 ${a.latency.p95_ms} ms`, color: "var(--color-series-1)" },
          ]} />
          <p className="mt-3 text-caption-1 text-label-tertiary">Laptop CPU, single client, keep-alive; API key and HMAC verified on every request.</p>
        </Panel>
        <Panel eyebrow="Honesty" title="What these numbers are not" icon={TriangleAlert} tint="var(--color-sys-yellow)">
          <ul className="space-y-2 text-footnote text-label-secondary">
            <li>• Attack and genuine behaviour are simulated; only touch windows (HMOG) and typing attempts (CMU) are real data.</li>
            <li>• Challenge efficacies (how often an OTP, passkey, call-back or cool-off stops each attack) are assumptions in ml/auth/policy.py.</li>
            <li>• No public dataset joins behaviour, device and transaction signals for the same people; a bank pilot with labelled fraud is the next step.</li>
            <li>• IP ranges are a demo subset; production needs a maintained IP-intelligence feed and device attestation (Play Integrity / App Attest).</li>
          </ul>
        </Panel>
      </div>
    </div>
  );
}
