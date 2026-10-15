"use client";

import { useState } from "react";
import { Bot, Play, ShieldAlert, SlidersHorizontal, UserCheck } from "lucide-react";
import { Button } from "@/components/common/Button";
import { SegmentedControl } from "@/components/common/SegmentedControl";
import { Panel } from "@/components/layout/Panel";
import type { Overrides, Scenario } from "@/types/auth";

/** Scenario list (genuine look-alikes and attacks on the same demo customer) and a builder for custom requests. */
export function ScenarioRail({
  scenarios,
  selected,
  busy,
  onRun,
}: {
  scenarios: Scenario[];
  selected: string | null;
  busy: boolean;
  onRun: (id: string, overrides?: Overrides) => void;
}) {
  const genuine = scenarios.filter((s) => s.is_attack === false);
  const attacks = scenarios.filter((s) => s.is_attack === true);
  return (
    <div className="space-y-4">
      <Panel eyebrow="Demo customer" title="Asha · Ludhiana" icon={UserCheck} tint="var(--color-sys-green)">
        <p className="-mt-2 mb-3 text-footnote text-label-secondary">
          30 days of ordinary payments from her own phone; touch profile enrolled from real HMOG gestures. Every scenario
          starts from that same history.
        </p>
        <Group title="Genuine" items={genuine} selected={selected} busy={busy} onRun={onRun} />
        <div className="h-3" />
        <Group title="Attacks" items={attacks} selected={selected} busy={busy} onRun={onRun} attack />
      </Panel>
      <CustomBuilder busy={busy} onRun={(o) => onRun("custom", o)} active={selected === "custom"} />
    </div>
  );
}

function Group({ title, items, selected, busy, onRun, attack }: {
  title: string; items: Scenario[]; selected: string | null; busy: boolean; onRun: (id: string) => void; attack?: boolean;
}) {
  return (
    <div>
      <p className="mb-1.5 text-eyebrow text-label-tertiary">{title}</p>
      <ul className="space-y-1">
        {items.map((s) => {
          const on = s.id === selected;
          const Icon = attack ? (s.id === "bot" ? Bot : ShieldAlert) : UserCheck;
          return (
            <li key={s.id}>
              <button
                onClick={() => onRun(s.id)}
                disabled={busy}
                title={s.story}
                className={`squircle flex w-full items-center gap-2.5 rounded-[0.8rem] px-3 py-2 text-left transition-colors disabled:opacity-60 ${
                  on ? "bg-fill-secondary" : "hover:bg-fill-quaternary"
                }`}
              >
                <Icon className={`size-4 shrink-0 ${attack ? "text-sys-red" : "text-sys-green"}`} aria-hidden />
                <span className="truncate text-subheadline">{s.title.replace(/^(Genuine|Attack): /, "")}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

type Place = "home" | "delhi" | "jamtara";
const PLACES: Record<Place, { city: string; lat: number; lon: number; ip: string }> = {
  home: { city: "Ludhiana", lat: 30.901, lon: 75.857, ip: "49.36.112.45" },
  delhi: { city: "Delhi", lat: 28.614, lon: 77.209, ip: "106.211.40.12" },
  jamtara: { city: "Jamtara", lat: 23.963, lon: 86.803, ip: "117.201.4.9" },
};

function CustomBuilder({ busy, onRun, active }: { busy: boolean; onRun: (o: Overrides) => void; active: boolean }) {
  const [amount, setAmount] = useState(2500);
  const [newPayee, setNewPayee] = useState(false);
  const [newDevice, setNewDevice] = useState(false);
  const [place, setPlace] = useState<Place>("home");
  const [touch, setTouch] = useState<"normal" | "coerced" | "remote" | "none">("normal");
  const [typing, setTyping] = useState<"normal" | "remote" | "bot" | "none">("normal");
  const [sim, setSim] = useState<"none" | "3" | "48">("none");
  const [flags, setFlags] = useState({ emulator: false, rooted: false, remote: false, share: false, call: false, hosting: false, scripted: false });
  const toggle = (k: keyof typeof flags) => setFlags((f) => ({ ...f, [k]: !f[k] }));

  const build = (): Overrides => {
    const p = PLACES[place];
    return {
      device: {
        device_id: newDevice ? "asha-unknown-device" : "asha-pixel-7",
        is_emulator: flags.emulator, is_rooted: flags.rooted, remote_access_app: flags.remote, screen_share_active: flags.share,
        sim_change_hours: sim === "none" ? null : Number(sim),
      },
      network: { city: p.city, lat: p.lat, lon: p.lon, ip: flags.hosting ? "34.93.10.77" : p.ip },
      behaviour: {
        touch_profile: touch, typing_profile: typing, unknown_call_active: flags.call,
        time_to_submit_s: flags.scripted ? 0.9 : 16, input_events: flags.scripted ? 1 : 34,
      },
      transaction: { amount, payee_id: newPayee ? "new-payee-0147" : "kirana-sharma", payee_is_merchant: !newPayee },
    };
  };

  const chip = (k: keyof typeof flags, label: string) => (
    <button key={k} onClick={() => toggle(k)} aria-pressed={flags[k]}
      className={`rounded-full px-2.5 py-1 text-caption-1 transition-colors ${flags[k] ? "bg-sys-red/20 text-sys-red" : "bg-fill-tertiary text-label-secondary hover:text-label"}`}>
      {label}
    </button>
  );

  return (
    <Panel eyebrow="Try it" title="Build a request" icon={SlidersHorizontal} tint={active ? "var(--color-sys-orange)" : "var(--color-sys-blue)"}>
      <div className="space-y-3 text-footnote">
        <label className="flex items-center justify-between gap-3">
          <span className="text-label-secondary">Amount (₹)</span>
          <input type="number" min={1} max={500000} value={amount} onChange={(e) => setAmount(Math.max(1, Number(e.target.value) || 1))}
            className="w-28 rounded-[0.5rem] bg-fill-tertiary px-2 py-1 text-right font-mono text-label outline-none focus:ring-2 focus:ring-sys-blue" />
        </label>
        <Row label="Payee"><SegmentedControl size="small" label="Payee" value={newPayee ? "new" : "usual"} onChange={(v) => setNewPayee(v === "new")}
          options={[{ value: "usual", label: "Usual" }, { value: "new", label: "New" }]} /></Row>
        <Row label="Device"><SegmentedControl size="small" label="Device" value={newDevice ? "new" : "own"} onChange={(v) => setNewDevice(v === "new")}
          options={[{ value: "own", label: "Her phone" }, { value: "new", label: "Unknown" }]} /></Row>
        <Row label="Location"><SegmentedControl size="small" label="Location" value={place} onChange={setPlace}
          options={[{ value: "home", label: "Home" }, { value: "delhi", label: "Delhi" }, { value: "jamtara", label: "Jamtara" }]} /></Row>
        <Row label="Typing"><SegmentedControl size="small" label="Typing" value={typing} onChange={setTyping}
          options={[{ value: "normal", label: "Hers" }, { value: "remote", label: "Other" }, { value: "bot", label: "Script" }, { value: "none", label: "None" }]} /></Row>
        <Row label="Touch"><SegmentedControl size="small" label="Touch" value={touch} onChange={setTouch}
          options={[{ value: "normal", label: "Hers" }, { value: "coerced", label: "Stressed" }, { value: "remote", label: "Other" }, { value: "none", label: "None" }]} /></Row>
        <Row label="SIM changed"><SegmentedControl size="small" label="SIM changed" value={sim} onChange={setSim}
          options={[{ value: "none", label: "No" }, { value: "3", label: "3 h ago" }, { value: "48", label: "2 days" }]} /></Row>
        <div className="flex flex-wrap gap-1.5 pt-1">
          {chip("emulator", "Emulator")}{chip("rooted", "Rooted")}{chip("remote", "Remote-access app")}{chip("share", "Screen share")}
          {chip("call", "Unknown call")}{chip("hosting", "Hosting IP")}{chip("scripted", "Scripted input")}
        </div>
        <Button size="small" className="w-full" onClick={() => onRun(build())} disabled={busy}><Play className="size-3.5" aria-hidden /> Decide</Button>
      </div>
    </Panel>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="shrink-0 text-label-secondary">{label}</span>
      <div className="min-w-0">{children}</div>
    </div>
  );
}
