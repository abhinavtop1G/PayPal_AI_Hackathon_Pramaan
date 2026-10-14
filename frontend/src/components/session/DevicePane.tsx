"use client";

import { AnimatePresence, motion } from "motion/react";
import { ChevronLeft } from "lucide-react";
import { narrate } from "@/config/scenarios";
import { describe } from "@/utils/events";
import { spring } from "@/config/motion";
import { personalise } from "@/config/personas";
import { useDemo } from "@/context/DemoContext";
import { nthOfType, type SessionView } from "@/utils/derive";
import { since } from "@/utils/format";
import { PhoneDemo } from "./PhoneDemo";
import { PhoneScaler } from "./PhoneScaler";

/** Left pane: scenario label, the phone (scaled to fit), and a one-line narration of the current event. */
export function DevicePane() {
  const { scenario, persona, replay, index, run, view, custom, setAppView, done } = useDemo();
  const cur = view.current;
  const caption = cur
    ? narrate(scenario, cur.input, nthOfType(replay, index), persona) || describe(cur.input).label
    : personalise(scenario.summary, persona);
  const glow = ambient(view, done, replay.is_scam);
  return (
    <div className="flex h-full min-h-[36rem] flex-col items-center gap-3 lg:min-h-0">
      <div className="flex w-full items-center justify-between gap-2">
        {custom && custom.from !== "session" ? (
          <button
            onClick={() => setAppView(custom.from)}
            className="flex items-center gap-1 rounded-full bg-fill-tertiary py-1 pl-1.5 pr-3 text-caption-1 font-semibold text-sys-blue transition-[scale] active:scale-95"
          >
            <ChevronLeft className="size-4" aria-hidden /> {custom.from === "wall" ? "Bank wall" : "Builder"}
          </button>
        ) : (
          <p className="text-eyebrow text-label-tertiary">Customer device</p>
        )}
        <span className="min-w-0 truncate text-caption-1 text-label-secondary">
          <span className="font-semibold text-label">{persona.name}</span> · {persona.about}
        </span>
        <span
          className={`rounded-full px-2.5 py-0.5 text-caption-2 font-semibold uppercase tracking-wider ${
            scenario.kind === "Scam" ? "bg-sys-red/15 text-sys-red" : "bg-sys-green/15 text-sys-green"
          }`}
        >
          {scenario.kind} · {scenario.title}
        </span>
      </div>

      <div className="relative flex min-h-0 w-full flex-1">
        {/* ambient light behind the device: calm indigo, warming to red as the session's risk climbs; green once a
            genuine session completes */}
        <motion.div
          aria-hidden
          className="pointer-events-none absolute left-1/2 top-1/2 aspect-square w-[min(80%,34rem)] -translate-x-1/2 -translate-y-1/2 rounded-full blur-[90px]"
          initial={false}
          animate={{ backgroundColor: glow.color, opacity: glow.opacity, scale: glow.scale }}
          transition={{ duration: 1.2, ease: "easeOut" }}
        />
        <PhoneScaler>
          <PhoneDemo key={`${replay.session_id}-${run}`} />
        </PhoneScaler>
      </div>

      <div className="relative flex min-h-[3.25rem] w-full max-w-[26rem] items-center justify-center text-center" aria-live="polite">
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.p
            key={`${scenario.id}-${index}`}
            initial={{ opacity: 0, y: 6, filter: "blur(6px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: -6, filter: "blur(6px)" }}
            transition={spring.default}
            className="text-callout text-label-secondary"
          >
            {cur && <span className="mr-2 text-label-tertiary tabular-nums">{since(cur.ts_min)}</span>}
            {caption}
          </motion.p>
        </AnimatePresence>
      </div>
    </div>
  );
}

function ambient(view: SessionView, done: boolean, isScam: boolean) {
  const cur = view.current;
  const d = view.lastDecision?.decision;
  if (d?.notify && d.action === "hold") return { color: "#ff453a", opacity: 0.42, scale: 1.08 };
  if (done && !isScam && !d?.notify) return { color: "#30d158", opacity: 0.28, scale: 1 };
  if (!cur) return { color: "#5e5ce6", opacity: 0.22, scale: 0.95 };
  const p = cur.workflow.p_scam_in_progress;
  const color = p < 0.2 ? "#0a84ff" : p < 0.5 ? "#ffd60a" : p < 0.8 ? "#ff9f0a" : "#ff453a";
  return { color, opacity: 0.2 + 0.16 * p, scale: 0.95 + 0.1 * p };
}
