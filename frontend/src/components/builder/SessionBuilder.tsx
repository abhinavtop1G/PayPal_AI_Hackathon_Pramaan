"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { Loader2, Play, RotateCcw, Terminal, Wrench } from "lucide-react";
import { API, apiHealthy, demoNumbers, demoTouch, RECORDED, sendEvent, startSession } from "@/api/demo";
import { Button } from "@/components/common/Button";
import { SegmentedControl } from "@/components/common/SegmentedControl";
import { Panel } from "@/components/layout/Panel";
import { customPersona } from "@/config/personas";
import { ACTION_COLOR, ACTION_LABEL, riskColor } from "@/config/policy";
import { genericScenario } from "@/config/scenarios";
import { spring } from "@/config/motion";
import { useDemo } from "@/context/DemoContext";
import type { DemoInput, DemoReplay, TimelineEntry } from "@/types/demo";
import { describe } from "@/utils/events";
import { pct, rupees, since } from "@/utils/format";

const START = "2026-03-15T11:00:00";

/** Customer profiles: usual payment amount (the server falls back to population-typical touch baselines). */
const PROFILES = [
  { value: "1127", label: "Senior · ₹1,127", name: "Senior customer" },
  { value: "403", label: "Student · ₹403", name: "Student" },
  { value: "4312", label: "Professional · ₹4,312", name: "Professional" },
];

/** Payee choices, sent as client-side payee intelligence (the slot the payee model / GNN fills). */
const PAYEES = {
  clean: { label: "Old clean account", payee_id: "B_CLEAN_01", payee_is_new: true, payee_is_merchant: false, payee_vpa_age_days: 2200, payee_mule_score: 0.02 },
  fresh: { label: "Brand-new account", payee_id: "B_FRESH_01", payee_is_new: true, payee_is_merchant: false, payee_vpa_age_days: 9, payee_mule_score: 0.28 },
  mule: { label: "Mule-linked account", payee_id: "B_MULE_01", payee_is_new: true, payee_is_merchant: false, payee_vpa_age_days: 60, payee_mule_score: 0.7 },
  shop: { label: "Shop paid before", payee_id: "B_SHOP_01", payee_is_new: false, payee_is_merchant: true, payee_vpa_age_days: 1600, payee_mule_score: 0.05 },
} as const;
type PayeeKey = keyof typeof PAYEES;

// touch telemetry windows: the server's default baselines vs. a coerced, hesitant pattern
// Each touch window sends the 5 summary numbers the stage tracker reads *and* 10 real HMOG gestures that the
// biometrics model scores against the customer's enrolled profile (`touch` picks whose hands / which state).
const CALM = { bio_pressure: 0.52, bio_swipe_velocity: 1.0, bio_tap_interval_ms: 480, bio_hesitation_ms: 1800, bio_orientation_var: 0.05, touch: "normal" as const };
const STRESSED = { bio_pressure: 0.95, bio_swipe_velocity: 0.75, bio_tap_interval_ms: 690, bio_hesitation_ms: 3600, bio_orientation_var: 0.09, touch: "coerced" as const };
const OTHER_HANDS = { bio_pressure: 0.5, bio_swipe_velocity: 2.2, bio_tap_interval_ms: 140, bio_hesitation_ms: 200, bio_orientation_var: 0.004, touch: "remote" as const };

type Step = Omit<DemoInput, "ts"> & { gap?: number; touch?: "normal" | "coerced" | "remote"; number?: "reported" | "clean" };

/**
 * A digital-arrest session from the simulator, up to its first payment attempt, with real gestures on each touch window.
 * The workflow model has only seen simulated sessions, so a shorter hand-written version of this pattern scores low.
 */
function simulatedArrestSteps(): Step[] {
  const timeline = RECORDED.senior.digital_arrest.timeline;
  const end = timeline.findIndex((row) => row.input.event === "PAYMENT_ATTEMPT");
  return timeline.slice(0, end + 1).map((row, i) => {
    const gap = i < end ? timeline[i + 1].ts_min - row.ts_min : 1;
    return { ...row.input, gap, ...(row.input.event === "BIO_WINDOW" ? { touch: "coerced" as const } : {}) }; // send() sets ts
  });
}

const PRESETS: Record<string, { label: string; steps: Step[] }> = {
  arrest: { label: "Digital-arrest pattern", steps: simulatedArrestSteps() },
  family: {
    label: "Genuine family emergency",
    steps: [
      { event: "CALL_START", caller_kind: "unknown", call_video: false, number: "clean", gap: 1.2 },
      { event: "UPI_APP_OPEN", gap: 0.1 },
      { event: "PAYEE_ADD", ...PAYEES.clean, gap: 0.3 },
      { event: "BIO_WINDOW", ...CALM, gap: 0.1 },
      { event: "PAYMENT_ATTEMPT", ...PAYEES.clean, amount: 18000, gap: 1 },
    ],
  },
};

/**
 * Build a session by hand: each button sends one raw event to the running API (`/v1/session/{id}/events`) at the
 * current session time, and the console on the right shows exactly what the models returned.
 */
export function SessionBuilder() {
  const { updateBuilder, custom } = useDemo();
  const [ok, setOk] = useState<boolean | null>(null);
  // coming back to this view restores the session built earlier (it lives in the demo context)
  const prior = custom?.from === "builder" ? custom.replay : null;
  const [profile, setProfile] = useState(() => (prior ? String(prior.user.avg_txn_amount) : "1127"));
  const [sid, setSid] = useState(() => prior?.session_id ?? `b${Date.now().toString(36)}`);
  const [started, setStarted] = useState(() => !!prior);
  const [clockMin, setClockMin] = useState(() => (prior?.timeline.length ? prior.timeline.at(-1)!.ts_min + 1 : 0));
  const [gap, setGap] = useState(1);
  const [payee, setPayee] = useState<PayeeKey>("mule");
  const [amount, setAmount] = useState(12000);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [rows, setRows] = useState<TimelineEntry[]>(() => prior?.timeline ?? []);

  useEffect(() => {
    const ac = new AbortController();
    apiHealthy(ac.signal).then(setOk);
    return () => ac.abort();
  }, []);

  const prof = PROFILES.find((p) => p.value === profile) ?? PROFILES[0];
  const publish = (timeline: TimelineEntry[]) => {
    const replay: DemoReplay = {
      session_id: sid,
      typology: "builder",
      is_scam: false,
      extraction_ts_min: null,
      start_time: START,
      user: { avg_txn_amount: Number(profile), age_group: prof.name },
      timeline,
    };
    updateBuilder({
      replay,
      scenario: genericScenario("Your session", false, "A session you built, scored live by the API."),
      persona: customPersona(prof.name, `usual payment ${rupees(Number(profile))}`),
      noStop: true,
      from: "builder",
    });
  };

  async function send(steps: Step[]) {
    setBusy(true);
    setErr(null);
    try {
      if (!started) {
        // the demo customer's touch profile is enrolled from a held-out HMOG subject
        const { subject } = await demoTouch("normal");
        await startSession(sid, Number(profile), START, subject);
        setStarted(true);
      }
      const nums = steps.some((s) => s.number) ? await demoNumbers() : null;
      let t = clockMin;
      let cur = rows;
      for (const { gap: g, touch, number, ...st } of steps) {
        const extra: Partial<DemoInput> = {};
        if (touch) extra.gestures = (await demoTouch(touch)).gestures;
        if (number && nums) extra.caller_number = number === "reported" ? nums.reported[0] : nums.clean[0];
        const ev = { ...st, ...extra, ts: Math.round(t * 60 * 100) / 100 } as DemoInput;
        const res = await sendEvent(sid, ev);
        const { gestures, ...shown } = ev;
        const input = gestures ? { ...shown, gestures_n: gestures.length } : shown;
        const entry = { ts_min: Math.round(t * 100) / 100, true_stage: "none", input, ...res } as TimelineEntry;
        cur = [...cur, entry];
        setRows(cur);
        publish(cur);
        t += g ?? gap;
      }
      setClockMin(t);
    } catch (e) {
      setErr(String((e as Error).message).slice(0, 200));
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setRows([]);
    setStarted(false);
    setClockMin(0);
    setSid(`b${Date.now().toString(36)}`);
    updateBuilder(null);
  }

  if (ok === false)
    return (
      <Panel eyebrow="Try it" title="Start the API to build sessions">
        <div className="flex flex-col gap-3 text-subheadline text-label-secondary">
          <p>The builder scores every event live, so it needs the backend running{API ? ` at ${API}` : ""}.</p>
          <pre className="rounded-[0.8rem] bg-black/40 p-3 font-mono text-footnote text-label">
            {`python run.py`}
          </pre>
        </div>
      </Panel>
    );

  const P = PAYEES[payee];
  const add = (s: Step) => send([s]);
  const btn = "justify-start";

  return (
    <div className="flex flex-col gap-4">
      <Panel
        eyebrow="Try it · live API"
        title="Build a session"
        icon={Wrench}
        tint="var(--color-sys-green)"
        accessory={
          <Button size="small" variant="tinted" tint="gray" onClick={reset} disabled={busy}>
            <RotateCcw className="size-3.5" /> New
          </Button>
        }
      >
        <div className="flex flex-col gap-4">
          <Group title="Customer">
            <SegmentedControl label="Customer profile" size="small" value={profile} onChange={(v) => !started && setProfile(v)} options={PROFILES} />
            {started && <p className="text-caption-2 text-label-tertiary">Profile is fixed once the session starts. Press New to change it.</p>}
          </Group>

          <Group title={`Next event at ${since(clockMin)} · then advance`}>
            <SegmentedControl
              label="Time between events"
              size="small"
              value={String(gap)}
              onChange={(v) => setGap(Number(v))}
              options={[
                { value: "0.1", label: "6 s" },
                { value: "1", label: "1 min" },
                { value: "5", label: "5 min" },
                { value: "30", label: "30 min" },
                { value: "240", label: "4 h" },
              ]}
            />
          </Group>

          <Group title="Contact">
            <div className="grid grid-cols-2 gap-1.5">
              <Button size="small" variant="tinted" className={btn} disabled={busy} onClick={() => add({ event: "CALL_START", caller_kind: "unknown", call_video: false, number: "clean" })}>Call · unknown no.</Button>
              <Button size="small" variant="tinted" tint="red" className={btn} disabled={busy} onClick={() => add({ event: "CALL_START", caller_kind: "unknown", call_video: false, number: "reported" })}>Call · reported no.</Button>
              <Button size="small" variant="tinted" className={btn} disabled={busy} onClick={() => add({ event: "CALL_START", caller_kind: "voip_intl", call_video: false })}>Call · internet (VoIP)</Button>
              <Button size="small" variant="tinted" className={btn} disabled={busy} onClick={() => add({ event: "CALL_START", caller_kind: "voip_intl", call_video: true })}>Video call · VoIP</Button>
              <Button size="small" variant="tinted" className={btn} disabled={busy} onClick={() => add({ event: "CALL_START", caller_kind: "contact", call_video: false })}>Call · saved contact</Button>
              <Button size="small" variant="tinted" tint="gray" className={btn} disabled={busy} onClick={() => add({ event: "CALL_END" })}>End call</Button>
              <Button size="small" variant="tinted" className={btn} disabled={busy} onClick={() => add({ event: "SMS_RECEIVED", sms_sender_kind: "unknown", sms_has_link: true })}>SMS + link · unknown</Button>
              <Button size="small" variant="tinted" className={btn} disabled={busy} onClick={() => add({ event: "SMS_RECEIVED", sms_sender_kind: "bank_shortcode", sms_has_link: true })}>SMS + link · bank-style</Button>
            </div>
          </Group>

          <Group title="Device">
            <div className="grid grid-cols-2 gap-1.5">
              <Button size="small" variant="tinted" className={btn} disabled={busy} onClick={() => add({ event: "LINK_CLICK" })}>Open link</Button>
              <Button size="small" variant="tinted" className={btn} disabled={busy} onClick={() => add({ event: "APP_INSTALL", app_source: "play_store" })}>Install app · store</Button>
              <Button size="small" variant="tinted" tint="red" className={btn} disabled={busy} onClick={() => add({ event: "APP_INSTALL", app_source: "sideload" })}>Install app · sideload</Button>
              <Button size="small" variant="tinted" tint="red" className={btn} disabled={busy} onClick={() => add({ event: "ACCESSIBILITY_GRANT" })}>Grant screen control</Button>
              <Button size="small" variant="tinted" className={btn} disabled={busy} onClick={() => add({ event: "SCREEN_SHARE_START" })}>Start screen share</Button>
              <Button size="small" variant="tinted" tint="gray" className={btn} disabled={busy} onClick={() => add({ event: "SCREEN_SHARE_END" })}>End screen share</Button>
              <Button size="small" variant="tinted" className={btn} disabled={busy} onClick={() => add({ event: "OTP_RECEIVED" })}>OTP arrives</Button>
            </div>
          </Group>

          <Group title="UPI app">
            <div className="grid grid-cols-2 gap-1.5">
              <Button size="small" variant="tinted" className={btn} disabled={busy} onClick={() => add({ event: "UPI_APP_OPEN" })}>Open UPI app</Button>
              <Button size="small" variant="tinted" className={btn} disabled={busy} onClick={() => add({ event: "BALANCE_CHECK" })}>Check balance</Button>
              <Button size="small" variant="tinted" tint="green" className={btn} disabled={busy} onClick={() => add({ event: "BIO_WINDOW", ...CALM })}>Touch · calm</Button>
              <Button size="small" variant="tinted" tint="red" className={btn} disabled={busy} onClick={() => add({ event: "BIO_WINDOW", ...STRESSED })}>Touch · hesitant</Button>
              <Button size="small" variant="tinted" tint="red" className={btn} disabled={busy} onClick={() => add({ event: "BIO_WINDOW", ...OTHER_HANDS })}>Touch · someone else</Button>
            </div>
          </Group>

          <Group title="Payee and payment">
            <SegmentedControl<PayeeKey>
              label="Payee"
              size="small"
              value={payee}
              onChange={setPayee}
              options={(Object.keys(PAYEES) as PayeeKey[]).map((k) => ({ value: k, label: PAYEES[k].label.split(" ")[0] }))}
            />
            <p className="text-caption-1 text-label-tertiary">
              {P.label}: {P.payee_vpa_age_days} days old, payee risk {P.payee_mule_score}
              {P.payee_is_new ? ", never paid before" : ", paid before"}
            </p>
            <div className="flex items-center gap-2">
              <label className="flex flex-1 items-center gap-2 rounded-[0.75rem] bg-fill-tertiary px-3 py-1.5">
                <span className="text-footnote text-label-secondary">₹</span>
                <input
                  type="number"
                  min={1}
                  value={amount}
                  onChange={(e) => setAmount(Math.max(1, Number(e.target.value) || 1))}
                  className="w-full bg-transparent text-headline tabular-nums outline-none"
                  aria-label="Amount in rupees"
                />
              </label>
              <Button size="small" variant="tinted" className={btn} disabled={busy} onClick={() => add({ event: "PAYEE_ADD", ...P })}>Add payee</Button>
              <Button size="small" tint="blue" disabled={busy} onClick={() => add({ event: "PAYMENT_ATTEMPT", ...P, amount })}>
                Pay
              </Button>
            </div>
          </Group>

          <Group title="Or run a preset">
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(PRESETS).map(([k, p]) => (
                <Button key={k} size="small" variant="tinted" tint={k === "arrest" ? "red" : "green"} disabled={busy || rows.length > 0} onClick={() => send(p.steps)}>
                  <Play className="size-3.5" /> {p.label}
                </Button>
              ))}
            </div>
            {rows.length > 0 && <p className="text-caption-2 text-label-tertiary">Presets start from an empty session (press New).</p>}
          </Group>

          {busy && (
            <p className="flex items-center gap-2 text-footnote text-label-secondary">
              <Loader2 className="size-4 animate-spin" /> scoring…
            </p>
          )}
          {err && <p className="rounded-[0.7rem] bg-sys-red/15 px-3 py-2 font-mono text-caption-1 text-sys-red">{err}</p>}
        </div>
      </Panel>

      <Panel eyebrow={`${rows.length} events`} title="What the API returned" icon={Terminal} tint="var(--color-sys-cyan)">
        <ol className="flex max-h-[24rem] flex-col gap-1 overflow-y-auto">
          <AnimatePresence initial={false}>
            {[...rows].reverse().map((e) => {
              const { icon: Icon, label } = describe(e.input);
              const p = e.workflow.p_scam_in_progress;
              const d = e.decision;
              return (
                <motion.li
                  key={e.event_index}
                  layout="position"
                  initial={{ opacity: 0, y: -8, filter: "blur(4px)" }}
                  animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                  transition={spring.default}
                  className="flex items-center gap-2.5 rounded-[0.75rem] bg-fill-quaternary px-2.5 py-2"
                >
                  <Icon className="size-4 shrink-0" style={{ color: riskColor(p) }} aria-hidden />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-footnote">{label}</span>
                    <span className="block text-caption-2 text-label-tertiary tabular-nums">
                      {since(e.ts_min)} · {e.workflow.stage} · {e.latency_ms.toFixed(0)} ms
                    </span>
                  </span>
                  {d && (
                    <span className="rounded-full px-2 py-0.5 text-caption-2 font-bold uppercase" style={{ color: ACTION_COLOR[d.action], background: `color-mix(in srgb, ${ACTION_COLOR[d.action]} 15%, transparent)` }}>
                      {ACTION_LABEL[d.action]} {pct(d.fused_risk)}
                    </span>
                  )}
                  <span className="w-12 text-right text-caption-1 font-semibold tabular-nums" style={{ color: riskColor(p) }}>
                    {pct(p)}
                  </span>
                </motion.li>
              );
            })}
          </AnimatePresence>
          {!rows.length && (
            <li className="flex items-center gap-2 py-4 text-footnote text-label-tertiary">
              <Terminal className="size-4" /> Add an event or run a preset. Each one is a real call to the API.
            </li>
          )}
        </ol>
      </Panel>
    </div>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-1.5">
      <h3 className="text-eyebrow text-label-tertiary">{title}</h3>
      {children}
    </section>
  );
}
