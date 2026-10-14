"use client";

import { AnimatePresence, motion } from "motion/react";
import { riskColor } from "@/config/policy";
import { spring } from "@/config/motion";
import { useDemo } from "@/context/DemoContext";
import { describe } from "@/utils/events";
import { pct, since } from "@/utils/format";

/** Newest-first stream of raw session events with the workflow risk after each. */
export function EventFeed({ max = 7 }: { max?: number }) {
  const { view, inspect, inspected } = useDemo();
  const rows = view.seen.slice(-max).reverse();
  return (
    <ol className="flex flex-col gap-1" aria-live="polite" aria-label="Session events">
      <AnimatePresence initial={false} mode="popLayout">
        {rows.map((e, i) => {
          const { icon: Icon, label } = describe(e.input);
          const p = e.workflow.p_scam_in_progress;
          return (
            <motion.li
              key={e.event_index}
              layout
              initial={{ opacity: 0, y: -10, filter: "blur(4px)" }}
              animate={{ opacity: i === 0 ? 1 : Math.max(0.35, 1 - i * 0.1), y: 0, filter: "blur(0px)" }}
              exit={{ opacity: 0 }}
              transition={spring.default}
              className="rounded-[0.75rem]"
            >
              <button
                onClick={() => inspect(e.event_index)}
                title="Show in the inspector"
                className={`flex w-full items-center gap-2.5 rounded-[0.75rem] px-2.5 py-2 text-left transition-[background-color,scale] duration-150 hover:bg-fill-tertiary active:scale-[0.98] ${
                  e.event_index === inspected ? "bg-fill-tertiary" : i === 0 ? "bg-fill-quaternary" : ""
                }`}
              >
              <span
                className="flex size-7 shrink-0 items-center justify-center rounded-full"
                style={{ background: `color-mix(in srgb, ${riskColor(p)} 16%, transparent)`, color: riskColor(p) }}
              >
                <Icon className="size-3.5" aria-hidden />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-footnote">{label}</span>
                <span className="block text-caption-2 text-label-tertiary tabular-nums">{since(e.ts_min)}</span>
              </span>
              <span className="text-caption-1 font-semibold tabular-nums" style={{ color: riskColor(p) }}>
                {pct(p)}
              </span>
              </button>
            </motion.li>
          );
        })}
      </AnimatePresence>
      {rows.length === 0 && <li className="px-2.5 py-2 text-footnote text-label-tertiary">No events yet</li>}
    </ol>
  );
}
