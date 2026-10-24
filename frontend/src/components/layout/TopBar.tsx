"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { ChevronLeft, ChevronRight, Pause, Play, RotateCcw, ShieldCheck } from "lucide-react";
import { IconButton } from "@/components/common/Button";
import { SegmentedControl } from "@/components/common/SegmentedControl";
import { PERSONAS, type PersonaId } from "@/config/personas";
import { spring } from "@/config/motion";
import { useDemo, type AppView, type Speed } from "@/context/DemoContext";
import { ScenarioPicker } from "./ScenarioPicker";
import { ShortcutsSheet } from "@/components/common/ShortcutsSheet";

const VIEWS: { value: AppView; label: string }[] = [
  { value: "session", label: "Session" },
  { value: "wall", label: "Bank wall" },
  { value: "network", label: "Mule network" },
  { value: "builder", label: "Try it" },
];

/** App bar: brand, view switcher, and for the session view the scenario, customer and transport controls. */
export function TopBar() {
  const { appView, setAppView, source, custom } = useDemo();
  return (
    <header className="material-thick relative z-30 flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-separator/50 px-4 py-2.5 sm:px-6">
      <Link href="/console" className="flex items-center gap-2.5 rounded-xl" title="Back to the PRAMAAN console">
        <span className="squircle flex size-8 items-center justify-center rounded-[0.6rem] bg-gradient-to-br from-sys-blue to-sys-indigo shadow-[0_4px_14px_rgb(10_132_255/0.35)]">
          <ShieldCheck className="size-4.5 text-white" aria-hidden />
        </span>
        <span className="hidden text-headline tracking-[0.02em] min-[1500px]:inline">RAKSHAM</span>
        <span className="hidden items-center gap-1 rounded-full bg-fill-tertiary px-2 py-0.5 text-caption-1 text-label-secondary sm:flex">
          <ChevronLeft className="size-3" aria-hidden /> PRAMAAN console
        </span>
      </Link>

      <SegmentedControl label="View" value={appView} onChange={setAppView} options={VIEWS} />

      {appView === "session" && (
        <>
          <ScenarioPicker />
          {!custom && <PersonaSwitch />}
        </>
      )}

      <div className="ml-auto flex flex-wrap items-center gap-2">
        {(appView === "session" || appView === "builder") && <span
          className={`hidden items-center gap-1.5 rounded-full px-2.5 py-1 text-caption-1 sm:flex ${
            source === "live" ? "bg-sys-green/12 text-sys-green" : "bg-fill-tertiary text-label-secondary"
          }`}
          title={source === "live" ? "Scored by the running API" : "Playing a recording of the API's output"}
        >
          <span className={`size-1.5 rounded-full ${source === "live" ? "bg-sys-green" : "bg-label-tertiary"}`} aria-hidden />
          <span className="hidden min-[1500px]:inline">{source === "live" ? "Live API" : "Recorded API replay"}</span>
          <span className="min-[1500px]:hidden">{source === "live" ? "Live" : "Rec"}</span>
        </span>}
        {appView === "session" && <Transport />}
        <ShortcutsSheet />
      </div>
    </header>
  );
}

function PersonaSwitch() {
  const { persona, setPersona } = useDemo();
  return (
    <SegmentedControl<PersonaId>
      label="Customer"
      size="small"
      value={persona.id as PersonaId}
      onChange={setPersona}
      options={PERSONAS.map((p) => ({
        value: p.id as PersonaId,
        label: (
          <span className="flex items-center gap-1.5" title={`${p.name} · ${p.about}`}>
            <span className="flex size-4 items-center justify-center rounded-full bg-sys-indigo/60 text-[0.5rem] font-bold text-white">
              {p.initials}
            </span>
            <span className="hidden min-[1500px]:inline">{p.first}</span>
          </span>
        ),
      }))}
    />
  );
}

function Transport() {
  const { playing, toggle, restart, step, index, last, speed, setSpeed } = useDemo();
  return (
    <>
      <IconButton label="Previous event (←)" onClick={() => step(-1)} disabled={index < 0} className="disabled:opacity-30">
        <ChevronLeft className="size-4" />
      </IconButton>
      <IconButton
        label={playing ? "Pause (Space)" : index >= last ? "Replay (Space)" : "Play (Space)"}
        onClick={toggle}
        className="size-10 bg-sys-blue text-white hover:bg-sys-blue/85"
      >
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.span
            key={playing ? "pause" : "play"}
            initial={{ opacity: 0, scale: 0.5, filter: "blur(4px)" }}
            animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0, scale: 0.5, filter: "blur(4px)" }}
            transition={spring.snappy}
          >
            {playing ? <Pause className="size-4 fill-current" /> : <Play className="size-4 translate-x-px fill-current" />}
          </motion.span>
        </AnimatePresence>
      </IconButton>
      <IconButton label="Next event (→)" onClick={() => step(1)} disabled={index >= last} className="disabled:opacity-30">
        <ChevronRight className="size-4" />
      </IconButton>
      <IconButton label="Restart (R)" onClick={restart}>
        <RotateCcw className="size-4" />
      </IconButton>
      <SegmentedControl<string>
        label="Playback speed"
        size="small"
        value={String(speed)}
        onChange={(v) => setSpeed(Number(v) as Speed)}
        options={[
          { value: "1", label: "1×" },
          { value: "2", label: "2×" },
          { value: "4", label: "4×" },
        ]}
      />
    </>
  );
}
