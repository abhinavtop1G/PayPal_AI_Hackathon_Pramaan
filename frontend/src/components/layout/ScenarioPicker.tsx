"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import { PAIRS, SCENARIOS } from "@/config/scenarios";
import { spring } from "@/config/motion";
import { useDemo } from "@/context/DemoContext";

/**
 * Scenario menu: four pairs, each a scam next to its genuine look-alike. The panel materialises from the trigger
 * (scale + blur from its top-left corner) and leaves the same way.
 */
export function ScenarioPicker() {
  const { scenario, setScenario } = useDemo();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("pointerdown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="dialog"
        className="material-thin flex h-9 items-center gap-2 rounded-full pl-3 pr-2.5 text-footnote font-semibold transition-[scale] duration-150 active:scale-[0.97]"
      >
        <span className={`size-2 rounded-full ${scenario.kind === "Scam" ? "bg-sys-red" : "bg-sys-green"}`} aria-hidden />
        {scenario.title}
        <motion.span animate={{ rotate: open ? 180 : 0 }} transition={spring.snappy}>
          <ChevronDown className="size-4 text-label-secondary" aria-hidden />
        </motion.span>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            role="dialog"
            aria-label="Choose a scenario"
            initial={{ opacity: 0, scale: 0.94, filter: "blur(8px)" }}
            animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0, scale: 0.96, filter: "blur(6px)" }}
            transition={spring.snappy}
            style={{ transformOrigin: "0% 0%" }}
            className="squircle absolute left-0 top-11 z-50 w-[min(40rem,calc(100vw-2rem))] rounded-[1.5rem] bg-[#1c1c1e]/95 p-3 shadow-[inset_0_0.5px_0_rgb(255_255_255/0.1),0_0_0_0.5px_rgb(255_255_255/0.08),0_30px_80px_rgb(0_0_0/0.6)] backdrop-blur-2xl"
          >
            <div className="mb-2 grid grid-cols-[7.5rem_1fr_1fr] gap-2 px-2 text-eyebrow text-label-tertiary">
              <span>Workflow</span>
              <span className="text-sys-red/80">Scam</span>
              <span className="text-sys-green/80">Genuine look-alike</span>
            </div>
            {PAIRS.map((pair, p) => (
              <div key={pair} className="grid grid-cols-[7.5rem_1fr_1fr] items-stretch gap-2 py-1">
                <span className="flex items-center px-2 text-footnote text-label-secondary">{pair}</span>
                {SCENARIOS.filter((s) => s.pair === p).map((s) => {
                  const on = s.id === scenario.id;
                  const n = SCENARIOS.indexOf(s) + 1;
                  return (
                    <button
                      key={s.id}
                      onClick={() => {
                        setScenario(s.id);
                        setOpen(false);
                      }}
                      className={`squircle relative flex flex-col items-start rounded-[0.9rem] px-3 py-2 text-left transition-[scale,background-color] duration-150 active:scale-[0.98] ${
                        on ? "bg-fill-secondary" : "hover:bg-fill-quaternary"
                      }`}
                    >
                      <span className="flex w-full items-center gap-1.5 text-subheadline font-semibold">
                        {s.title}
                        {on && <Check className="size-4 text-sys-blue" aria-hidden />}
                        <kbd className="ml-auto rounded-[0.3rem] bg-fill-tertiary px-1.5 text-caption-2 text-label-tertiary">{n}</kbd>
                      </span>
                      <span className="text-caption-1 text-label-secondary">{s.blurb}</span>
                    </button>
                  );
                })}
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
