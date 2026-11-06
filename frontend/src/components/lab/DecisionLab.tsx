"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "motion/react";
import { Activity, ChevronDown, KeyRound, Languages, LayoutList, Loader2, Pause, Play, Scale, SlidersHorizontal, Smartphone, Waypoints } from "lucide-react";
import { listScenarios, runScenario, verifyChallenge, type Source } from "@/api/auth";
import { useReport } from "@/api/console";
import { RiskGauge } from "@/components/charts/RiskGauge";
import { Waterfall } from "@/components/charts/Waterfall";
import { Button } from "@/components/common/Button";
import { SegmentedControl } from "@/components/common/SegmentedControl";
import { toast } from "@/components/common/Toaster";
import { Panel } from "@/components/layout/Panel";
import { DecisionBadge } from "@/components/ui/DecisionBadge";
import { CHALLENGE_LABEL, DECISION_STYLE, FAMILY_LABEL, FAMILY_TINT, inr } from "@/config/authSignals";
import { spring } from "@/config/motion";
import { useConsole, type Lang } from "@/context/ConsoleContext";
import type { AuthResponse, ChallengeOutcome, DemoRun, Family, Overrides, Scenario } from "@/types/auth";
import { CustomerPhone } from "./CustomerPhone";
import { ExpectedCost } from "./ExpectedCost";
import { PipelineTrace } from "./PipelineTrace";
import { RequestBuilder } from "./RequestBuilder";
import { RequestInspector } from "./RequestInspector";
import { ScenarioGallery } from "./ScenarioGallery";
import { ScenarioMatrix } from "./ScenarioMatrix";

/**
 * One request end to end, for the demo customer: pick a scenario (or build one), and see the decision, the risk, the
 * pipeline it went through, the signals behind it (SHAP), why the policy chose this action (expected cost), what the
 * customer sees, and the challenge loop. Deep links: /console/lab?scenario=sim_swap&verify=pass|fail, ?autoplay.
 */
export function DecisionLab() {
  const { lang, setLang, logRun, logOutcome } = useConsole();
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [run, setRun] = useState<DemoRun | null>(null);
  const [source, setSource] = useState<Source>("recorded");
  const [outcome, setOutcome] = useState<ChallengeOutcome | null>(null);
  const [busy, setBusy] = useState(false);
  const [builder, setBuilder] = useState(false);
  const [auto, setAuto] = useState(false);
  const abort = useRef<AbortController | null>(null);

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
      logRun(res.data, res.source);
      return res;
    } catch (e) {
      if ((e as Error).name !== "AbortError") toast(`Could not decide: ${(e as Error).message}`, "alert");
    } finally {
      if (abort.current === ac) setBusy(false);
    }
  }, [logRun]);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    listScenarios().then(async ({ data }) => {
      setScenarios(data);
      if (q.has("autoplay")) setAuto(true);
      const res = await go(q.get("scenario") ?? "genuine_routine");
      const v = q.get("verify");
      if (res && v && res.data.response.decision === "challenge") {
        const o = await verifyChallenge(res.data, v === "pass", res.source);
        setOutcome(o);
        logOutcome(res.data.response.decision_id, o);
      }
    });
  }, [go, logOutcome]);

  const pick = (id: string) => {
    if (id === "custom") {
      setBuilder(true);
      return;
    }
    go(id);
  };

  const verify = useCallback(async (passed: boolean) => {
    if (!run || run.response.decision !== "challenge") return;
    setBusy(true);
    try {
      const o = await verifyChallenge(run, passed, source);
      setOutcome(o);
      logOutcome(run.response.decision_id, o);
    } catch (e) {
      toast(`Could not verify: ${(e as Error).message}`, "alert");
    } finally {
      setBusy(false);
    }
  }, [run, source, logOutcome]);

  // autoplay for a booth or a demo video: each scenario in turn; a genuine customer passes the challenge, an attacker fails
  const gallery = useMemo(() => scenarios.filter((s) => s.id !== "custom"), [scenarios]);
  useEffect(() => {
    if (!auto || !run || busy) return;
    const challenged = run.response.decision === "challenge" && !outcome;
    const t = setTimeout(() => {
      if (challenged) verify(!run.is_attack);
      else {
        const i = gallery.findIndex((s) => s.id === run.scenario);
        go(gallery[(i + 1) % gallery.length]?.id ?? "genuine_routine");
      }
    }, challenged ? 3500 : 6500);
    return () => clearTimeout(t);
  }, [auto, run, outcome, busy, gallery, go, verify]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (e.metaKey || e.ctrlKey || e.altKey || el.closest("input, textarea, select, [contenteditable=true]")) return;
      const n = Number(e.key);
      if (n >= 1 && n <= gallery.length) go(gallery[n - 1].id);
      else if (e.key === "p") verify(true);
      else if (e.key === "f") verify(false);
      else if (e.key === "a") setAuto((x) => !x);
      else if (e.key === "b") setBuilder((x) => !x);
      else if (e.key === "h") setLang(lang === "hi" ? "en" : "hi");
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [gallery, go, verify, lang, setLang]);

  return (
    <div className="mx-auto max-w-[96rem] space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-eyebrow text-label-tertiary">Decision lab</p>
          <h1 className="mt-1 text-large-title">One request, end to end</h1>
          <p className="mt-1 max-w-[50rem] text-subheadline text-label-secondary">
            Asha, Ludhiana: 30 days of ordinary payments from her own phone, touch and typing profiles enrolled from real
            HMOG and CMU data. Every scenario starts from that same history.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`rounded-full px-2.5 py-1 text-caption-1 ${source === "live" ? "bg-sys-green/12 text-sys-green" : "bg-fill-tertiary text-label-secondary"}`}>
            {source === "live" ? "Decided live by the API" : "Recorded API output"}
          </span>
          <button onClick={() => setAuto((a) => !a)} aria-pressed={auto} title="Autoplay every scenario (A)"
            className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-caption-1 transition-colors ${auto ? "bg-accent-strong text-white" : "bg-fill-tertiary text-label-secondary hover:text-label"}`}>
            {auto ? <Pause className="size-3 fill-current" aria-hidden /> : <Play className="size-3 fill-current" aria-hidden />} Autoplay
          </button>
          <Languages className="size-4 text-label-tertiary" aria-hidden />
          <SegmentedControl<Lang> size="small" label="Customer language" value={lang} onChange={setLang}
            options={[{ value: "en", label: "English" }, { value: "hi", label: "हिन्दी" }]} />
        </div>
      </header>

      <ScenarioGallery scenarios={gallery} selected={selected === "custom" ? null : selected} busy={busy} onPick={pick} />

      <section className="material-regular squircle rounded-[var(--radius-panel)]">
        <button onClick={() => setBuilder((b) => !b)} aria-expanded={builder}
          className="flex w-full items-center justify-between gap-3 px-5 py-3.5 text-left">
          <span className="flex items-center gap-3">
            <span className="flex size-8 items-center justify-center rounded-[0.6rem] bg-sys-blue/15 text-sys-blue"><SlidersHorizontal className="size-4" aria-hidden /></span>
            <span>
              <span className="block text-headline">Build your own request</span>
              <span className="block text-caption-1 text-label-tertiary">Change any signal the SDK would send and see how the decision moves{source === "recorded" ? " (needs the live API)" : ""}</span>
            </span>
          </span>
          <ChevronDown className={`size-4 text-label-tertiary transition-transform ${builder ? "rotate-180" : ""}`} aria-hidden />
        </button>
        {builder && (
          <div className="border-t border-separator/50 px-5 pb-5 pt-4">
            <RequestBuilder busy={busy} onRun={(o) => go("custom", o)} />
          </div>
        )}
      </section>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_19rem]">
        <div className="min-w-0 space-y-5">
          <Verdict run={run} outcome={outcome} busy={busy} lang={lang} onVerify={verify} />
          {run && (
            <Panel eyebrow={`decision ${run.response.decision_id} · ${run.response.latency_ms.toFixed(1)} ms in the service`} title="The path it took" icon={Waypoints} tint="var(--color-sys-indigo)">
              <PipelineTrace run={run} />
            </Panel>
          )}
          {run && (
            <div className="grid gap-5 md:grid-cols-2">
              <Panel eyebrow="By signal family" title="Where the risk came from">
                <FamilySplit response={run.response} />
              </Panel>
              <Panel eyebrow="Policy" title="Why this action" icon={Scale} tint="var(--color-sys-orange)">
                <ExpectedCost response={run.response} />
              </Panel>
            </div>
          )}
        </div>
        <Panel eyebrow="What the customer sees" title="Her phone" icon={Smartphone} tint="var(--color-sys-teal)" className="xl:sticky xl:top-6 xl:self-start">
          <CustomerPhone run={run} outcome={outcome} busy={busy} lang={lang} />
        </Panel>
      </div>

      {run && (
        <Panel eyebrow="Explainability · exact tree-SHAP" title="Signals behind the decision" icon={Activity} tint="var(--color-fam-behaviour)">
          <div className="grid gap-x-10 gap-y-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,1fr)]">
            <Waterfall response={run.response} top={9} />
            <div className="space-y-3 text-footnote text-label-secondary">
              <p>Each bar is one signal&apos;s exact contribution (tree-SHAP) to this request&apos;s log-odds of being an attack, starting from the base rate. Coloured bars push risk up, gray bars pull it down.</p>
              <p>Monotone model: a signal can only push risk up as it gets worse, so no signal can argue for an attacker, and every reason shown to an analyst points the right way.</p>
              <p className="text-caption-1 text-label-tertiary">Base rate includes the prior correction from the simulator&apos;s attack share to an assumed real-world 0.2%.</p>
            </div>
          </div>
        </Panel>
      )}

      {run && (
        <Panel eyebrow="Inspector" title="Request and response">
          <RequestInspector run={run} />
        </Panel>
      )}

      <Panel eyebrow={`At a glance · ${source === "live" ? "live" : "recorded"}`} title="All nine scenarios" icon={LayoutList} tint="var(--color-sys-teal)">
        <ScenarioMatrix selected={selected} onPick={go} />
        <p className="mt-3 text-caption-1 text-label-tertiary">
          Keyboard: <Kbd>1</Kbd>–<Kbd>9</Kbd> scenario · <Kbd>P</Kbd> pass / <Kbd>F</Kbd> fail the challenge · <Kbd>A</Kbd> autoplay ·
          <Kbd>B</Kbd> request builder · <Kbd>H</Kbd> English / हिन्दी
        </p>
      </Panel>
    </div>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd className="mx-0.5 rounded-[0.3rem] bg-fill-tertiary px-1.5 py-px font-mono text-caption-2 text-label-secondary">{children}</kbd>;
}

function Verdict({ run, outcome, busy, lang, onVerify }: {
  run: DemoRun | null; outcome: ChallengeOutcome | null; busy: boolean; lang: Lang; onVerify: (passed: boolean) => void;
}) {
  if (!run) {
    return (
      <section className="material-regular panel-sheen squircle flex min-h-[18rem] items-center justify-center rounded-[var(--radius-panel)]">
        <Loader2 className="size-6 animate-spin text-label-tertiary" aria-label="Deciding" />
      </section>
    );
  }
  const r = run.response;
  const st = DECISION_STYLE[r.decision];
  const ch = r.challenge_type ? CHALLENGE_LABEL[r.challenge_type] : null;
  return (
    <section className="material-regular panel-sheen squircle relative overflow-hidden rounded-[var(--radius-panel)] p-5 sm:p-6" aria-live="polite">
      <div aria-hidden className="pointer-events-none absolute -right-24 -top-24 size-72 rounded-full blur-3xl" style={{ background: `color-mix(in srgb, ${st.tint} 16%, transparent)` }} />
      <motion.div key={r.decision_id} initial={{ opacity: 0.4, y: 6 }} animate={{ opacity: busy ? 0.55 : 1, y: 0 }} transition={spring.snappy}
        className="relative grid gap-6 md:grid-cols-[auto_minmax(0,1fr)]">
        <div className="flex flex-col items-center justify-center">
          <RiskGauge risk={r.risk_score} decision={r.decision} />
          <div className="mt-1 flex flex-wrap justify-center gap-1.5 text-caption-1 text-label-secondary">
            <span className="rounded-full bg-fill-tertiary px-2.5 py-1 font-mono">{r.latency_ms.toFixed(1)} ms</span>
            {r.amount > 0 && <span className="rounded-full bg-fill-tertiary px-2.5 py-1">{inr(r.amount)}</span>}
            <span className="rounded-full bg-fill-tertiary px-2.5 py-1">{run.request.channel}</span>
          </div>
        </div>
        <div className="min-w-0 space-y-3">
          <div>
            <p className="text-eyebrow text-label-tertiary">{run.is_attack === null ? "Custom request" : run.is_attack ? "Attack scenario" : "Genuine scenario"}</p>
            <h2 className="mt-0.5 text-title-2">{run.title.replace(/^(Genuine|Attack): /, "")}</h2>
            <p className="mt-1 text-subheadline text-label-secondary">{run.story}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <DecisionBadge decision={r.decision} size="md" />
            {ch && <span className="flex items-center gap-1.5 rounded-full bg-fill-tertiary px-3 py-1 text-subheadline"><KeyRound className="size-4 text-sys-orange" aria-hidden />{ch.title}</span>}
            {r.rule && <span className="rounded-full bg-fill-tertiary px-3 py-1 font-mono text-caption-1 text-label-secondary">rule: {r.rule}</span>}
          </div>
          {ch && <p className="text-footnote text-label-secondary">{ch.why}</p>}
          {r.reasons.length > 0 && (
            <ul className="space-y-1.5">
              {r.reasons.map((x) => (
                <li key={x.signal} className="flex items-start gap-2 text-subheadline" lang={lang === "hi" ? "hi" : undefined}>
                  <span className="mt-[0.45rem] size-2 shrink-0 rounded-full" style={{ background: FAMILY_TINT[x.family] }} aria-hidden />
                  <span>{lang === "hi" ? x.text_hi : x.text_en} <span className="font-mono text-caption-1 text-label-tertiary">+{x.contribution.toFixed(2)}</span></span>
                </li>
              ))}
            </ul>
          )}
          {r.decision === "allow" && <p className="text-subheadline text-label-secondary">No signal stands out against her history: the payment goes straight through, no OTP.</p>}
          {r.decision === "challenge" && !outcome && (
            <div className="flex flex-wrap gap-2 pt-1">
              <Button tint="green" size="small" onClick={() => onVerify(true)} disabled={busy}>Customer passes the challenge</Button>
              <Button tint="red" variant="tinted" size="small" onClick={() => onVerify(false)} disabled={busy}>Challenge fails</Button>
            </div>
          )}
          {outcome && (
            <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} transition={spring.snappy}
              className={`squircle rounded-[var(--radius-card)] p-3.5 ${DECISION_STYLE[outcome.decision].bg}`}>
              <p className="text-headline" style={{ color: DECISION_STYLE[outcome.decision].tint }}>
                Final: {DECISION_STYLE[outcome.decision].label}{outcome.device_trusted ? " · device is now trusted" : ""}
              </p>
              <p className="mt-1 text-footnote text-label-secondary">
                {outcome.passed ? "Challenge passed: the payment goes through and joins her history." :
                  "Challenge failed: blocked, and further attempts on this account are blocked for 30 minutes."}
              </p>
            </motion.div>
          )}
        </div>
      </motion.div>
    </section>
  );
}

function FamilySplit({ response }: { response: AuthResponse }) {
  const auc = useReport().data?.auth.ranking;
  const fam = response.family_contribution;
  const scale = Math.max(1, ...Object.values(fam).map(Math.abs));
  return (
    <div className="space-y-3">
      {(Object.keys(FAMILY_LABEL) as Family[]).map((f) => {
        const v = fam[f] ?? 0;
        const w = Math.min(50, (50 * Math.abs(v)) / scale);
        return (
          <div key={f} className="grid grid-cols-[6.5rem_1fr_3rem] items-center gap-3">
            <span className="flex items-center gap-2 text-subheadline"><span className="size-2.5 rounded-[3px]" style={{ background: FAMILY_TINT[f] }} aria-hidden />{FAMILY_LABEL[f]}</span>
            <div className="relative h-2.5 rounded-full bg-fill-quaternary">
              <span className="absolute inset-y-[-3px] left-1/2 w-px bg-separator" aria-hidden />
              <motion.span className="absolute inset-y-0 rounded-[4px]" initial={{ width: 0 }} animate={{ width: `${w}%` }} transition={spring.default}
                style={{ background: v >= 0 ? FAMILY_TINT[f] : "var(--color-gray-2)", [v >= 0 ? "left" : "right"]: "50%" }} />
            </div>
            <span className={`text-right font-mono text-caption-1 tabular-nums ${v > 0.05 ? "text-label" : "text-label-tertiary"}`}>{v > 0 ? "+" : ""}{v.toFixed(2)}</span>
          </div>
        );
      })}
      <p className="text-caption-2 text-label-tertiary">Summed SHAP contributions (log-odds). Right of centre raises risk, left lowers it. One model over all three families{auc && `: no family alone comes close (ROC-AUC ${["behaviour signals only", "device signals only", "transaction signals only"].map((k) => auc[k].roc_auc.toFixed(2)).join(" / ")} vs ${auc["risk engine (all signals)"].roc_auc.toFixed(3)})`}.</p>
    </div>
  );
}
