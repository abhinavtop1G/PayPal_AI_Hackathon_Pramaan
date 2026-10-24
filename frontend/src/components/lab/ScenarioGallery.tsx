"use client";

import { Bot, KeyRound, MonitorSmartphone, PhoneCall, Plane, Refrigerator, Signal, SlidersHorizontal, Store, TabletSmartphone, type LucideIcon } from "lucide-react";
import type { Scenario } from "@/types/auth";

const ICON: Record<string, LucideIcon> = {
  genuine_routine: Store, genuine_big_purchase: Refrigerator, genuine_new_phone: TabletSmartphone, genuine_travel: Plane,
  ato_new_device: KeyRound, sim_swap: Signal, bot: Bot, remote_access: MonitorSmartphone, coerced: PhoneCall, custom: SlidersHorizontal,
};

/** Every scenario is the same demo customer (Asha, Ludhiana) and history; genuine look-alikes sit next to attacks. */
export function ScenarioGallery({ scenarios, selected, busy, onPick }: {
  scenarios: Scenario[];
  selected: string | null;
  busy: boolean;
  onPick: (id: string) => void;
}) {
  const groups: [string, Scenario[], "genuine" | "attack" | "custom"][] = [
    ["Genuine look-alikes", scenarios.filter((s) => s.is_attack === false), "genuine"],
    ["Attacks", scenarios.filter((s) => s.is_attack === true), "attack"],
  ];
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,4fr)_minmax(0,5fr)]">
      {groups.map(([title, items, kind]) => (
        <div key={title}>
          <p className="mb-2 flex items-center gap-2 text-eyebrow text-label-tertiary">
            <span className={`size-1.5 rounded-full ${kind === "attack" ? "bg-sys-red" : "bg-sys-green"}`} aria-hidden /> {title}
          </p>
          <div className={`grid gap-2 ${kind === "attack" ? "grid-cols-2 sm:grid-cols-3 xl:grid-cols-5" : "grid-cols-2 sm:grid-cols-4"}`}>
            {items.map((s) => <Card key={s.id} s={s} on={s.id === selected} busy={busy} onPick={onPick} kind={kind} />)}
          </div>
        </div>
      ))}
    </div>
  );
}

function Card({ s, on, busy, onPick, kind }: { s: Scenario; on: boolean; busy: boolean; onPick: (id: string) => void; kind: string }) {
  const Icon = ICON[s.id] ?? SlidersHorizontal;
  const tint = kind === "attack" ? "var(--color-sys-red)" : "var(--color-sys-green)";
  return (
    <button onClick={() => onPick(s.id)} disabled={busy && !on} aria-pressed={on} title={s.story}
      className={`squircle group relative flex h-full flex-col items-start gap-2 rounded-[1rem] p-3 text-left transition-[background-color,box-shadow,transform] duration-200 active:scale-[0.98] disabled:opacity-60 ${
        on ? "bg-fill-secondary shadow-[inset_0_0_0_1px_rgb(255_255_255/0.14)]" : "material-ultrathin hover:bg-fill-tertiary"}`}>
      <span className="flex size-8 items-center justify-center rounded-[0.6rem]" style={{ background: `color-mix(in srgb, ${tint} ${on ? 26 : 14}%, transparent)`, color: tint }}>
        <Icon className="size-4" aria-hidden />
      </span>
      <span className="text-footnote font-semibold leading-tight">{s.title.replace(/^(Genuine|Attack): /, "")}</span>
      <span className="line-clamp-2 text-caption-2 text-label-tertiary">{s.story}</span>
    </button>
  );
}
