"use client";

import { useMemo, useState } from "react";
import { BadgeIndianRupee, CircleCheck, RotateCcw, Scale, ShieldCheck, SlidersHorizontal, Swords, UserX } from "lucide-react";
import { useReport, useTraffic } from "@/api/console";
import { BarList } from "@/components/charts/BarList";
import { Button } from "@/components/common/Button";
import { Panel } from "@/components/layout/Panel";
import { StatTile } from "@/components/ui/StatTile";
import { ATTACK_LABEL, CHALLENGE_LABEL, inr, inrCompact } from "@/config/authSignals";
import type { ChallengeType } from "@/types/auth";
import type { AttackType, PolicyConstants, TrafficRow } from "@/types/console";
import { defaults, evaluate, frontier, type Outcome, type PolicyParams } from "./simulate";
import { TradeoffChart } from "./TradeoffChart";

const ATTACKS: AttackType[] = ["ato_new_device", "sim_swap", "bot", "remote_access", "coerced"];
const CHALLENGES: ChallengeType[] = ["sms_otp", "passkey", "bank_callback", "cool_off"];

/**
 * Tune the decision policy on a held-out day: the model's risk for every request stays fixed; what changes is how
 * the policy weighs a customer's friction against fraud that gets through, when it may block, and the device-binding
 * rule. The whole day is re-decided in the browser with the service's own decision rule.
 */
export function PolicyTuner() {
  const { data: traffic, error: e1 } = useTraffic();
  const { data: report, error: e2 } = useReport();
  if (e1 || e2) return <p className="text-sys-red">Could not load the data: {e1 ?? e2}</p>;
  if (!traffic || !report) return <div className="mx-auto max-w-[96rem] space-y-5"><div className="skeleton h-24 rounded-2xl" /><div className="skeleton h-96 rounded-3xl" /></div>;
  return <Tuner rows={traffic.rows} P={report.policy} date={traffic.meta.date} />;
}

function Tuner({ rows, P, date }: { rows: TrafficRow[]; P: PolicyConstants; date: string }) {
  const base = useMemo(() => defaults(P), [P]);
  const [q, setQ] = useState<PolicyParams>(base);
  const service = useMemo(() => evaluate(rows, P, base), [rows, P, base]);
  const tuned = useMemo(() => evaluate(rows, P, q), [rows, P, q]);
  const otp = useMemo(() => evaluate(rows, P, "otp_always"), [rows, P]);
  const curve = useMemo(() => frontier(rows, P, q), [rows, P, q]);
  const pt = (o: Outcome) => ({ friction: (100 * o.genuineChallenged) / o.genuine, stopped: (100 * o.attacksStopped) / o.attacks });
  const set = (k: keyof PolicyParams, v: number | boolean) => setQ((x) => ({ ...x, [k]: v }));

  return (
    <div className="mx-auto max-w-[96rem] space-y-5">
      <header>
        <p className="text-eyebrow text-label-tertiary">Policy tuner · held-out day {date} · {rows.length.toLocaleString("en-IN")} requests</p>
        <h1 className="mt-1 text-large-title">Friction against fraud, your call</h1>
        <p className="mt-1 max-w-[56rem] text-subheadline text-label-secondary">
          The model gives every request a risk; the policy turns it into allow, a step-up or a block by comparing expected
          costs. Change what a step-up costs a customer, when blocking is allowed and the device-binding rule, and the whole
          day is re-decided here with the service&apos;s own decision rule (ml/auth/policy.py).
        </p>
      </header>

      <div className="grid gap-5 xl:grid-cols-[22rem_minmax(0,1fr)]">
        <Panel eyebrow="Policy" title="Settings" icon={SlidersHorizontal} tint="var(--color-sys-blue)" className="xl:sticky xl:top-6 xl:self-start">
          <div className="space-y-5">
            <Slider label="What a step-up costs the customer" value={Math.log10(q.frictionX)} min={-1.3} max={1.3} step={0.01}
              onChange={(v) => set("frictionX", 10 ** v)} display={`× ${q.frictionX.toFixed(q.frictionX < 1 ? 2 : 1)}`}
              hint={`OTP ${inr(P.friction.sms_otp * q.frictionX)} · passkey ${inr(P.friction.passkey * q.frictionX)} · call-back ${inr(P.friction.bank_callback * q.frictionX)} · cool-off ${inr(P.friction.cool_off * q.frictionX)}`} />
            <Slider label="Block only when an attack is at least this likely" value={q.blockMinP} min={0.2} max={0.95} step={0.01}
              onChange={(v) => set("blockMinP", v)} display={`${Math.round(100 * q.blockMinP)}%`}
              hint="Below it, a risky request is challenged instead, so a genuine big purchase is verified, not refused." />
            <Slider label="Value at risk behind a login" value={q.loginExposure} min={2000} max={100000} step={1000}
              onChange={(v) => set("loginExposure", v)} display={inrCompact(q.loginExposure)} hint="A login has no amount; this is what an account takeover would cost." />
            <label className="flex items-start justify-between gap-3 rounded-[0.8rem] bg-fill-quaternary px-3 py-2.5">
              <span>
                <span className="block text-footnote">Device binding</span>
                <span className="block text-caption-1 text-label-tertiary">Step up the first payment from a device never seen on the account, however low its risk</span>
              </span>
              <input type="checkbox" checked={q.deviceBinding} onChange={(e) => set("deviceBinding", e.target.checked)} className="mt-1 size-5 accent-[var(--color-sys-blue)]" />
            </label>
            <div className="flex flex-wrap gap-2">
              <Button size="small" tint="gray" variant="tinted" onClick={() => setQ(base)}><RotateCcw className="size-3.5" aria-hidden /> Service setting</Button>
              <Button size="small" tint="gray" variant="tinted" onClick={() => setQ({ ...base, frictionX: 5 })}>Fewer interruptions</Button>
              <Button size="small" tint="gray" variant="tinted" onClick={() => setQ({ ...base, frictionX: 0.15, blockMinP: 0.35 })}>Maximum protection</Button>
            </div>
            <p className="flex items-start gap-2 rounded-[0.8rem] bg-sys-green/10 px-3 py-2.5 text-caption-1 text-label-secondary">
              <CircleCheck className="mt-px size-4 shrink-0 text-sys-green" aria-hidden />
              <span>At the service&apos;s setting this re-decides {service.matches.toLocaleString("en-IN")} of {rows.length.toLocaleString("en-IN")} requests
                exactly as the service did (decision and step-up).</span>
            </p>
          </div>
        </Panel>

        <div className="min-w-0 space-y-5">
          <section className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="Outcome of the setting">
            <StatTile icon={ShieldCheck} label="Genuine requests challenged" accent="var(--color-sys-blue)"
              value={`${pt(tuned).friction.toFixed(2)}%`} detail={<Delta v={pt(tuned).friction - pt(service).friction} unit=" pts" goodDown />} />
            <StatTile icon={UserX} label="Genuine payments lost" accent="var(--color-sys-orange)"
              value={tuned.genuineLost.toFixed(1)} detail={<Delta v={tuned.genuineLost - service.genuineLost} unit="" goodDown suffix=" (blocked or abandoned, expected)" />} />
            <StatTile icon={Swords} label="Attack requests stopped" accent="var(--color-sys-red)"
              value={`${pt(tuned).stopped.toFixed(1)}%`} detail={<Delta v={pt(tuned).stopped - pt(service).stopped} unit=" pts" />} />
            <StatTile icon={BadgeIndianRupee} label="Attack money stopped" accent="var(--color-sys-green)"
              value={inrCompact(tuned.moneyStopped)} detail={<Delta v={tuned.moneyStopped - service.moneyStopped} unit="" money />} />
          </section>

          <Panel eyebrow="Trade-off" title="Every setting of the friction cost, on this day" icon={Scale} tint="var(--color-sys-indigo)">
            <TradeoffChart curve={curve} current={pt(tuned)} service={pt(service)} otp={pt(otp)} />
            <p className="mt-2 text-caption-1 text-label-tertiary">
              The curve sweeps the friction cost with your other settings fixed. An SMS OTP on every payment challenges every customer
              and still stops fewer attacks: it does nothing against a SIM swap and little against a coached victim.
            </p>
          </Panel>

          <div className="grid gap-5 lg:grid-cols-2">
            <Panel eyebrow="By attack type" title="Expected attack requests stopped">
              <BarList ariaLabel="Expected attack requests stopped by type, tuned setting" rows={ATTACKS.filter((a) => tuned.byAttack[a].n).map((a) => ({
                key: a, label: ATTACK_LABEL[a], value: tuned.byAttack[a].stopped, ghost: tuned.byAttack[a].n, color: "var(--color-sys-green)",
                display: `${tuned.byAttack[a].stopped.toFixed(1)} / ${tuned.byAttack[a].n}`,
                sub: `service setting: ${service.byAttack[a].stopped.toFixed(1)} · OTP always: ${otp.byAttack[a].stopped.toFixed(1)}`,
              }))} max={Math.max(...ATTACKS.map((a) => tuned.byAttack[a].n), 1)} />
            </Panel>
            <Panel eyebrow="Step-ups" title="Which challenges it would issue">
              <BarList ariaLabel="Step-ups issued by type, tuned setting" rows={CHALLENGES.map((c) => ({
                key: c, label: CHALLENGE_LABEL[c].title, value: tuned.mix[c], color: "var(--color-sys-orange)",
                sub: `service setting: ${service.mix[c]}`,
              }))} />
              <p className="mt-3 text-caption-1 text-label-tertiary">
                Expected values with the evaluation&apos;s assumed step-up efficacies and pass rates (ml/auth/policy.py). The service&apos;s
                own recorded outcomes for this day are one random draw of these.
              </p>
            </Panel>
          </div>
        </div>
      </div>
    </div>
  );
}

function Slider({ label, value, min, max, step, onChange, display, hint }: {
  label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void; display: string; hint?: string;
}) {
  return (
    <label className="block">
      <span className="flex items-baseline justify-between gap-3">
        <span className="text-footnote">{label}</span>
        <span className="font-mono text-footnote font-semibold tabular-nums">{display}</span>
      </span>
      <input type="range" value={value} min={min} max={max} step={step} onChange={(e) => onChange(Number(e.target.value))}
        className="mt-2 w-full accent-[var(--color-sys-blue)]" />
      {hint && <span className="mt-1 block text-caption-1 text-label-tertiary">{hint}</span>}
    </label>
  );
}

/** Change vs the service's setting; green when it moves the good way, red otherwise, gray when unchanged. */
function Delta({ v, unit, goodDown, money, suffix }: { v: number; unit: string; goodDown?: boolean; money?: boolean; suffix?: string }) {
  const zero = Math.abs(v) < (money ? 1 : 0.005);
  const good = goodDown ? v < 0 : v > 0;
  const text = zero ? "same as the service" : `${v > 0 ? "+" : "−"}${money ? inrCompact(Math.abs(v)) : Math.abs(v).toFixed(unit ? 2 : 1)}${unit} vs the service`;
  return <span className={zero ? "" : good ? "text-sys-green" : "text-sys-red"}>{text}{suffix ?? ""}</span>;
}
