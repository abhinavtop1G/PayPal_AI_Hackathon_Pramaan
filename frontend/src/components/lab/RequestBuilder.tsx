"use client";

import { useState } from "react";
import { Play, RotateCcw } from "lucide-react";
import { Button } from "@/components/common/Button";
import { SegmentedControl } from "@/components/common/SegmentedControl";
import { inr } from "@/config/authSignals";
import type { Overrides } from "@/types/auth";

type Place = "home" | "delhi" | "jamtara" | "dubai";
const PLACES: Record<Place, { city: string; lat: number; lon: number; ip: string; label: string }> = {
  home: { city: "Ludhiana", lat: 30.901, lon: 75.857, ip: "49.36.112.45", label: "Home (Ludhiana)" },
  delhi: { city: "Delhi", lat: 28.614, lon: 77.209, ip: "106.211.40.12", label: "Delhi" },
  jamtara: { city: "Jamtara", lat: 23.963, lon: 86.803, ip: "117.201.4.9", label: "Jamtara" },
  dubai: { city: "Dubai", lat: 25.205, lon: 55.271, ip: "94.200.12.7", label: "Dubai" },
};
const FLAGS = { emulator: "Emulator", rooted: "Rooted", remote: "Remote-access app", share: "Screen share", call: "Unknown caller on the line",
  hosting: "Hosting-provider IP", scripted: "Scripted input" } as const;
type Flag = keyof typeof FLAGS;
const AMOUNTS = [640, 2500, 18500, 60000, 150000];

/** Any request for the demo customer: each control maps to one field of the SDK's request (merged into her routine
 *  payment). Touch and typing send real recorded HMOG gestures / CMU keystrokes of the chosen kind. */
export function RequestBuilder({ busy, onRun }: { busy: boolean; onRun: (o: Overrides) => void }) {
  const [amount, setAmount] = useState(2500);
  const [newPayee, setNewPayee] = useState(false);
  const [newDevice, setNewDevice] = useState(false);
  const [place, setPlace] = useState<Place>("home");
  const [touch, setTouch] = useState<"normal" | "coerced" | "remote" | "none">("normal");
  const [typing, setTyping] = useState<"normal" | "remote" | "bot" | "none">("normal");
  const [sim, setSim] = useState<"none" | "3" | "48">("none");
  const [channel, setChannel] = useState<"mobile" | "web">("mobile");
  const [flags, setFlags] = useState<Record<Flag, boolean>>({ emulator: false, rooted: false, remote: false, share: false, call: false, hosting: false, scripted: false });

  const reset = () => {
    setAmount(2500); setNewPayee(false); setNewDevice(false); setPlace("home"); setTouch("normal"); setTyping("normal"); setSim("none");
    setChannel("mobile"); setFlags({ emulator: false, rooted: false, remote: false, share: false, call: false, hosting: false, scripted: false });
  };

  const build = (): Overrides => {
    const p = PLACES[place];
    return {
      channel,
      device: {
        device_id: newDevice ? "asha-unknown-device" : "asha-pixel-7", platform: channel === "web" ? "web" : "android",
        is_emulator: flags.emulator, is_rooted: flags.rooted, remote_access_app: flags.remote, screen_share_active: flags.share,
        sim_change_hours: sim === "none" ? null : Number(sim),
      },
      network: { city: p.city, lat: p.lat, lon: p.lon, ip: flags.hosting ? "34.93.10.77" : p.ip },
      behaviour: {
        touch_profile: channel === "web" ? "none" : touch, typing_profile: typing, unknown_call_active: flags.call,
        time_to_submit_s: flags.scripted ? 0.9 : 16, input_events: flags.scripted ? 1 : 34,
      },
      transaction: { amount, payee_id: newPayee ? "new-payee-0147" : "kirana-sharma", payee_is_merchant: !newPayee },
    };
  };

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <Field label="Amount">
          <div className="flex flex-wrap gap-1.5">
            {AMOUNTS.map((a) => (
              <button key={a} onClick={() => setAmount(a)} aria-pressed={amount === a}
                className={`rounded-full px-2.5 py-1 text-caption-1 tabular-nums ${amount === a ? "bg-accent-strong text-white" : "bg-fill-tertiary text-label-secondary hover:text-label"}`}>
                {inr(a)}
              </button>
            ))}
            <input type="number" min={1} max={500000} value={amount} aria-label="Amount in rupees"
              onChange={(e) => setAmount(Math.max(1, Math.min(500000, Number(e.target.value) || 1)))}
              className="w-24 rounded-full bg-fill-tertiary px-2.5 py-1 text-right font-mono text-caption-1 text-label outline-none focus:ring-2 focus:ring-sys-blue" />
          </div>
        </Field>
        <Field label="Channel"><Seg value={channel} onChange={setChannel} options={[["mobile", "Mobile app"], ["web", "Web"]]} /></Field>
        <Field label="Payee"><Seg value={newPayee ? "new" : "usual"} onChange={(v) => setNewPayee(v === "new")} options={[["usual", "Usual grocer"], ["new", "New account"]]} /></Field>
        <Field label="Device"><Seg value={newDevice ? "new" : "own"} onChange={(v) => setNewDevice(v === "new")} options={[["own", "Her phone"], ["new", "Never seen"]]} /></Field>
        <Field label="Location"><Seg value={place} onChange={setPlace} options={(Object.keys(PLACES) as Place[]).map((k) => [k, PLACES[k].city])} /></Field>
        <Field label="SIM changed"><Seg value={sim} onChange={setSim} options={[["none", "No"], ["3", "3 h ago"], ["48", "2 days ago"]]} /></Field>
        <Field label="Touch (real HMOG gestures)" hint={channel === "web" ? "web requests carry no touch data" : undefined}>
          <Seg value={touch} onChange={setTouch} options={[["normal", "Her hands"], ["coerced", "Stressed"], ["remote", "Someone else"], ["none", "None"]]} />
        </Field>
        <Field label="Typing (real CMU keystrokes)">
          <Seg value={typing} onChange={setTyping} options={[["normal", "Hers"], ["remote", "Someone else"], ["bot", "Scripted"], ["none", "None"]]} />
        </Field>
        <Field label="Risk flags">
          <div className="flex flex-wrap gap-1.5">
            {(Object.keys(FLAGS) as Flag[]).map((k) => (
              <button key={k} onClick={() => setFlags((f) => ({ ...f, [k]: !f[k] }))} aria-pressed={flags[k]}
                className={`rounded-full px-2.5 py-1 text-caption-1 transition-colors ${flags[k] ? "bg-sys-red/20 text-sys-red" : "bg-fill-tertiary text-label-secondary hover:text-label"}`}>
                {FLAGS[k]}
              </button>
            ))}
          </div>
        </Field>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="small" onClick={() => onRun(build())} disabled={busy}><Play className="size-3.5" aria-hidden /> Decide this request</Button>
        <Button size="small" tint="gray" variant="tinted" onClick={reset}><RotateCcw className="size-3.5" aria-hidden /> Reset</Button>
      </div>
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="mb-1.5 text-caption-1 text-label-secondary">{label}{hint && <span className="text-label-tertiary"> · {hint}</span>}</p>
      <div className="overflow-x-auto">{children}</div>
    </div>
  );
}

function Seg<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: [T, string][] }) {
  return <SegmentedControl<T> size="small" label="option" value={value} onChange={onChange} options={options.map(([v, l]) => ({ value: v, label: l }))} />;
}
