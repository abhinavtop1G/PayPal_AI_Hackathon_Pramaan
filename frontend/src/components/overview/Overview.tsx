"use client";

import { useEffect, useMemo, useState } from "react";
import { BadgeIndianRupee, Clock3, FastForward, Pause, Play, ShieldCheck, Swords, UsersRound } from "lucide-react";
import { useTraffic } from "@/api/console";
import { BarList } from "@/components/charts/BarList";
import { Columns } from "@/components/charts/Columns";
import { RiskHistogram } from "@/components/charts/RiskHistogram";
import { AnimatedNumber } from "@/components/common/AnimatedNumber";
import { IconButton } from "@/components/common/Button";
import { SegmentedControl } from "@/components/common/SegmentedControl";
import { Panel } from "@/components/layout/Panel";
import { StatTile } from "@/components/ui/StatTile";
import { ATTACK_LABEL, CHALLENGE_LABEL, FAMILY_TINT, GENUINE_KIND_LABEL, SIGNAL_FAMILY, SIGNAL_LABEL, inr, inrCompact } from "@/config/authSignals";
import type { ChallengeType } from "@/types/auth";
import type { AttackType, TrafficRow } from "@/types/console";
import { AttackLane } from "./AttackLane";
import { LiveFeed } from "./LiveFeed";
import { LiveService } from "./LiveService";
import { DAY_S, hhmm, upTo, useReplay } from "./useReplay";

const START = 7 * 3600;
const interrupted = (r: TrafficRow) => r.d !== "allow";
const quantile = (xs: number[], q: number) => {
  if (!xs.length) return NaN;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.floor(q * s.length))];
};

/**
 * Operations overview: one held-out test day of the simulator replayed through the trained service on a compressed
 * clock. Everything on the page is computed from the recorded decisions up to the replay time.
 */
export function Overview() {
  const { data, error } = useTraffic();
  if (error) return <p className="text-callout text-sys-red">Could not load the traffic recording: {error}</p>;
  if (!data) return <OverviewSkeleton />;
  return <Dashboard rows={data.rows} date={data.meta.date} model={data.meta.model_version} about={data.meta.about} />;
}

function Dashboard({ rows, date, model, about }: { rows: TrafficRow[]; date: string; model: string; about: string }) {
  const r = useReplay(START, 300);
  const [stream, setStream] = useState<"all" | "interrupted">("all");
  const { toggle, seek, clock } = r;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || (e.target as HTMLElement).closest("input, textarea, select, button")) return;
      if (e.key === " ") toggle();
      else if (e.key === "ArrowRight") seek(clock + 1800);
      else if (e.key === "ArrowLeft") seek(clock - 1800);
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle, seek, clock]);
  const ts = useMemo(() => Float64Array.from(rows, (x) => x.t), [rows]);
  const n = upTo(ts, r.clock);
  const s = useMemo(() => summarise(rows.slice(0, n)), [rows, n]);
  const bucket = Math.floor(Math.min(r.clock, DAY_S - 1) / 1800);

  return (
    <div className="mx-auto max-w-[96rem] space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-eyebrow text-label-tertiary">Operations overview</p>
          <h1 className="mt-1 text-large-title">A day of payments, decided</h1>
          <p className="mt-1 max-w-[52rem] text-subheadline text-label-secondary">
            Every request from one held-out test day ({date}) of 3,000 simulated customers, replayed through the trained
            service ({model}) with simulated challenge outcomes. The model never saw this day.
          </p>
        </div>
        <div className="material-regular squircle flex items-center gap-2 rounded-full p-1.5 pr-3">
          <IconButton label={r.playing ? "Pause" : "Play"} onClick={r.toggle} className="size-9 bg-sys-blue text-white hover:bg-sys-blue/85">
            {r.playing ? <Pause className="size-4 fill-current" /> : <Play className="size-4 translate-x-px fill-current" />}
          </IconButton>
          <span className="w-[4.5rem] text-center font-mono text-title-3 tabular-nums" aria-live="off">{hhmm(r.clock)}</span>
          <SegmentedControl<string> size="small" label="Replay speed" value={String(r.speed)} onChange={(v) => r.setSpeed(Number(v))}
            options={[{ value: "60", label: "60×" }, { value: "300", label: "300×" }, { value: "1200", label: "1200×" }]} />
          <IconButton label="Jump to end of day" onClick={() => r.seek(DAY_S)}><FastForward className="size-4" /></IconButton>
        </div>
      </header>

      <div className="space-y-1">
        <input type="range" min={0} max={DAY_S} step={60} value={Math.round(r.clock)} onChange={(e) => r.seek(Number(e.target.value))}
          aria-label="Replay time" className="w-full accent-[var(--color-sys-blue)]" />
        <p className="text-right text-caption-2 text-label-tertiary">Space play / pause · ← → 30 minutes</p>
      </div>

      <LiveService />

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-5" aria-label="Key figures">
        <StatTile icon={UsersRound} label="Requests decided" accent="var(--color-sys-blue)"
          value={<AnimatedNumber value={s.n} format={(v) => Math.round(v).toLocaleString("en-IN")} />}
          detail={`${s.mobile.toLocaleString("en-IN")} mobile · ${s.web.toLocaleString("en-IN")} web`} />
        <StatTile icon={ShieldCheck} label="Genuine customers interrupted" accent="var(--color-sys-green)"
          value={`${s.genuine ? ((100 * s.genuineInterrupted) / s.genuine).toFixed(1) : "0.0"}%`}
          detail={`${s.genuineInterrupted} of ${s.genuine.toLocaleString("en-IN")} · ${s.genuineBlocked} finally blocked`} />
        <StatTile icon={Swords} label="Attack requests stopped" accent="var(--color-sys-red)"
          value={s.attacks ? `${s.stopped}/${s.attacks}` : "—"}
          detail={s.attacks ? `${Math.round((100 * s.stopped) / s.attacks)}% stopped (SMS OTP on every payment: 24%)` : "no attacks yet today"} />
        <StatTile icon={BadgeIndianRupee} label="Attack money stopped" accent="var(--color-sys-orange)"
          value={<AnimatedNumber value={s.moneyStopped} format={(v) => inrCompact(v)} />}
          detail={s.moneyAttempted ? `of ${inr(s.moneyAttempted)} attempted` : "—"} />
        <StatTile icon={Clock3} label="Decision time, p95" accent="var(--color-sys-indigo)"
          value={Number.isFinite(s.p95) ? `${s.p95.toFixed(0)} ms` : "—"} detail={`p50 ${Number.isFinite(s.p50) ? s.p50.toFixed(0) : "—"} ms · in-process, SHAP included`} />
      </section>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_25rem]">
        <div className="min-w-0 space-y-5">
          <Panel eyebrow="Ground truth from the simulator" title="Attacks through the day" icon={Swords} tint="var(--color-sys-red)">
            <AttackLane rows={rows} clock={r.clock} />
          </Panel>
          <div className="grid gap-5 lg:grid-cols-2">
            <Panel eyebrow="Traffic" title="Requests every 30 minutes">
              <Columns ariaLabel="Requests per 30 minutes" data={s.halfHours} upTo={bucket} tickEvery={8}
                series={[{ name: "requests", color: "var(--color-series-1)" }]} />
            </Panel>
            <Panel eyebrow="Friction vs catches" title="Interrupted requests per hour">
              <Columns ariaLabel="Interrupted genuine and attack requests per hour" data={s.hours} upTo={Math.floor(bucket / 2)} tickEvery={4}
                series={[{ name: "genuine (challenged)", color: "var(--color-series-1)" }, { name: "attack (challenged or blocked)", color: "var(--color-series-2)" }]} />
              <Legend items={[["genuine customer", "var(--color-series-1)"], ["attack", "var(--color-series-2)"]]} />
            </Panel>
          </div>
          <Panel eyebrow="Separation" title="Risk scores: customers vs attackers">
            <RiskHistogram genuine={s.riskGenuine} attacks={s.riskAttack} />
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              <Legend items={[["genuine requests (share, up)", "var(--color-series-1)"], ["attack requests (share, down)", "var(--color-series-2)"]]} />
              <p className="text-caption-1 text-label-tertiary">Log scale. The policy decides by expected cost, so where a request lands sets allow vs challenge; blocks need risk ≥ 50%.</p>
            </div>
          </Panel>
          <div className="grid gap-5 lg:grid-cols-2">
            <Panel eyebrow="By attack type" title="What got stopped">
              <BarList ariaLabel="Attack requests stopped by type" rows={s.byAttack.map((a) => ({
                key: a.type, label: ATTACK_LABEL[a.type], value: a.stopped, ghost: a.n, display: `${a.stopped}/${a.n}`,
                color: "var(--color-sys-green)",
                sub: `${inrCompact(a.moneyStopped)} of ${inrCompact(a.money)} stopped${a.how ? ` · ${a.how}` : ""}`,
              }))} max={Math.max(1, ...s.byAttack.map((a) => a.n))} />
              <p className="mt-3 text-caption-1 text-label-tertiary">Bar: stopped; lighter bar behind: all attempts. Coached victims are the hardest case (the real owner on their own phone).</p>
            </Panel>
            <Panel eyebrow="Explainability" title="Signals behind interruptions">
              <BarList ariaLabel="Most frequent top signals on challenged or blocked requests" rows={s.signals.map(([name, count]) => ({
                key: name, label: SIGNAL_LABEL[name] ?? name, value: count, color: FAMILY_TINT[SIGNAL_FAMILY[name] ?? "device"],
              }))} />
              <Legend items={[["behaviour", FAMILY_TINT.behaviour], ["device", FAMILY_TINT.device], ["transaction", FAMILY_TINT.transaction]]} />
            </Panel>
          </div>
        </div>

        <div className="min-w-0 space-y-5">
          <Panel eyebrow={`Replay · ${hhmm(r.clock)} · ${r.playing ? "playing" : "paused"}`} title="Decision stream" accessory={
            <SegmentedControl<"all" | "interrupted"> size="small" label="Stream filter" value={stream} onChange={setStream}
              options={[{ value: "all", label: "All" }, { value: "interrupted", label: "Interrupted" }]} />}>
            <LiveFeed rows={stream === "all" ? s.latest : s.latestInterrupted} />
            {stream === "interrupted" && !s.latestInterrupted.length && <p className="text-footnote text-label-tertiary">Nothing interrupted yet today.</p>}
          </Panel>
          <Panel eyebrow="Step-up" title="Challenges chosen">
            <BarList ariaLabel="Challenges issued by type" rows={s.challenges.map((c) => ({
              key: c.type, label: CHALLENGE_LABEL[c.type].title, value: c.n, color: "var(--color-sys-orange)",
              sub: `${c.attacks} on attacks · ${c.genuine} on genuine (${c.genuine ? Math.round((100 * c.passed) / c.genuine) : 0}% passed)`,
            }))} />
            <p className="mt-3 text-caption-1 text-label-tertiary">The challenge is matched to the signals: a SIM change gets a passkey, not an OTP that would reach the attacker.</p>
          </Panel>
          <Panel eyebrow="Friction" title="Which customers get interrupted">
            <BarList ariaLabel="Share of genuine requests challenged, by kind of request" max={100} rows={s.friction.map((k) => ({
              key: k.kind, label: GENUINE_KIND_LABEL[k.kind] ?? k.kind, value: k.n ? (100 * k.interrupted) / k.n : 0,
              display: `${k.n ? ((100 * k.interrupted) / k.n).toFixed(1) : "0.0"}%`, color: "var(--color-series-1)",
              sub: `${k.interrupted} of ${k.n.toLocaleString("en-IN")}${k.blocked ? ` · ${k.blocked} finally blocked` : ""}`,
            }))} />
            <p className="mt-3 text-caption-1 text-label-tertiary">
              Everyday payments almost never see a step-up. Most friction falls on big purchases, where a large amount to a new
              merchant earns an OTP; only the first payment from a new phone is stepped up (device binding), not the ones after it.
            </p>
          </Panel>
          <details className="material-regular squircle rounded-[var(--radius-card)] p-4 text-caption-1 text-label-secondary">
            <summary className="cursor-pointer text-footnote text-label">About this data</summary>
            <p className="mt-2">{about}</p>
          </details>
        </div>
      </div>
    </div>
  );
}

function Legend({ items }: { items: [string, string][] }) {
  return (
    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-caption-1 text-label-secondary">
      {items.map(([l, c]) => (
        <span key={l} className="flex items-center gap-1.5"><span className="size-2.5 rounded-[3px]" style={{ background: c }} aria-hidden />{l}</span>
      ))}
    </div>
  );
}

function summarise(rows: TrafficRow[]) {
  const genuine = rows.filter((r) => !r.atk), attacks = rows.filter((r) => r.atk);
  const halfHours = Array.from({ length: 48 }, (_, i) => ({ key: `h${i}`, tick: hhmm(i * 1800), title: `${hhmm(i * 1800)}–${hhmm((i + 1) * 1800)}`, values: [0] }));
  const hours = Array.from({ length: 24 }, (_, i) => ({ key: `H${i}`, tick: hhmm(i * 3600), title: `${hhmm(i * 3600)}–${hhmm((i + 1) * 3600 - 1)}`, values: [0, 0] }));
  for (const r of rows) {
    halfHours[Math.min(47, Math.floor(r.t / 1800))].values[0]++;
    if (interrupted(r)) hours[Math.min(23, Math.floor(r.t / 3600))].values[r.atk ? 1 : 0]++;
  }
  const types = [...new Set(attacks.map((a) => a.atk as AttackType))];
  const byAttack = (["ato_new_device", "sim_swap", "bot", "remote_access", "coerced"] as AttackType[])
    .filter((t) => types.includes(t))
    .map((type) => {
      const xs = attacks.filter((a) => a.atk === type);
      const stoppedRows = xs.filter((a) => a.f === "block");
      const viaChallenge = stoppedRows.filter((a) => a.d === "challenge").length;
      return {
        type, n: xs.length, stopped: stoppedRows.length, money: xs.reduce((s, a) => s + a.amt, 0),
        moneyStopped: stoppedRows.reduce((s, a) => s + a.amt, 0),
        how: stoppedRows.length ? `${stoppedRows.length - viaChallenge} blocked outright, ${viaChallenge} failed the challenge` : "",
      };
    });
  const sig = new Map<string, number>();
  rows.filter(interrupted).forEach((r) => r.top.forEach(([name]) => sig.set(name, (sig.get(name) ?? 0) + 1)));
  const challenges = (["sms_otp", "passkey", "bank_callback", "cool_off"] as ChallengeType[]).map((type) => {
    const xs = rows.filter((r) => r.c === type);
    const g = xs.filter((r) => !r.atk);
    return { type, n: xs.length, attacks: xs.length - g.length, genuine: g.length, passed: g.filter((r) => r.pass).length };
  }).filter((c) => c.n > 0);
  const ms = rows.map((r) => r.ms);
  const friction = ["routine", "web", "travel", "big_purchase", "new_phone"].map((kind) => {
    const xs = genuine.filter((r) => r.kind === kind);
    return { kind, n: xs.length, interrupted: xs.filter(interrupted).length, blocked: xs.filter((r) => r.f === "block").length };
  }).filter((k) => k.n > 0);
  return {
    friction,
    n: rows.length, mobile: rows.filter((r) => r.ch === "mobile").length, web: rows.filter((r) => r.ch === "web").length,
    genuine: genuine.length, genuineInterrupted: genuine.filter(interrupted).length, genuineBlocked: genuine.filter((r) => r.f === "block").length,
    attacks: attacks.length, stopped: attacks.filter((r) => r.f === "block").length,
    moneyAttempted: attacks.reduce((s, r) => s + r.amt, 0), moneyStopped: attacks.filter((r) => r.f === "block").reduce((s, r) => s + r.amt, 0),
    p50: quantile(ms, 0.5), p95: quantile(ms, 0.95),
    halfHours, hours, byAttack, challenges,
    signals: [...sig.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8),
    riskGenuine: genuine.map((r) => r.p), riskAttack: attacks.map((r) => r.p),
    latest: rows.slice(-12).reverse(),
    latestInterrupted: rows.filter(interrupted).slice(-12).reverse(),
  };
}

function OverviewSkeleton() {
  return (
    <div className="mx-auto max-w-[96rem] space-y-5" aria-busy="true">
      <div className="skeleton h-16 w-2/3 rounded-2xl" />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">{Array.from({ length: 5 }, (_, i) => <div key={i} className="skeleton h-28 rounded-2xl" />)}</div>
      <div className="skeleton h-72 rounded-3xl" />
    </div>
  );
}
