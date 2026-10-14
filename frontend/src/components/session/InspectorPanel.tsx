"use client";

import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { ChevronLeft, ChevronRight, LocateFixed } from "lucide-react";
import { SegmentedControl } from "@/components/common/SegmentedControl";
import { spring } from "@/config/motion";
import { useDemo } from "@/context/DemoContext";
import { describe } from "@/utils/events";
import { since } from "@/utils/format";

/** Tiny JSON highlighter: keys, strings, numbers, booleans/null. */
function Json({ value }: { value: unknown }) {
  const text = JSON.stringify(value, null, 2);
  const parts = text.split(/("(?:\\.|[^"\\])*"(?:\s*:)?|-?\d+(?:\.\d+)?(?:e[+-]?\d+)?|\btrue\b|\bfalse\b|\bnull\b)/g);
  return (
    <pre className="m-0 overflow-auto whitespace-pre text-[0.75rem] leading-[1.15rem] text-label-secondary">
      {parts.map((p, i) => {
        if (/^".*":$/.test(p.trim())) return <span key={i} className="text-sys-cyan">{p}</span>;
        if (p.startsWith('"')) return <span key={i} className="text-sys-orange">{p}</span>;
        if (/^-?\d/.test(p)) return <span key={i} className="text-sys-purple">{p}</span>;
        if (/^(true|false|null)$/.test(p)) return <span key={i} className="text-sys-pink">{p}</span>;
        return p;
      })}
    </pre>
  );
}

/**
 * The raw API exchange for any event seen so far: what was sent (the device event) and what came back (stage
 * tracker output and, at payments, the full decision). Follows the live event unless one is picked.
 */
export function InspectorPanel() {
  const { replay, index, last, inspected, inspect } = useDemo();
  const [tab, setTab] = useState<"in" | "out">("out");
  const i = inspected;
  const e = i >= 0 ? replay.timeline[i] : null;
  const live = i === Math.min(index, last);
  const seenMax = Math.min(index, last);

  if (!e) return <p className="py-8 text-center text-footnote text-label-tertiary">Events appear here as the session replays.</p>;
  const { icon: Icon, label } = describe(e.input);
  const { input, ts_min, true_stage, ...output } = e;
  void ts_min;

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="flex size-7 items-center justify-center rounded-full bg-fill-tertiary">
          <Icon className="size-3.5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-subheadline font-semibold">{label}</p>
          <p className="text-caption-1 text-label-tertiary tabular-nums">
            event {i + 1} · {since(e.ts_min)} · ground truth: {true_stage}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <button
            aria-label="Previous event"
            disabled={i <= 0}
            onClick={() => inspect(i - 1)}
            className="flex size-7 items-center justify-center rounded-full bg-fill-tertiary transition-[scale] active:scale-90 disabled:opacity-30"
          >
            <ChevronLeft className="size-4" />
          </button>
          <button
            aria-label="Next event"
            disabled={i >= seenMax}
            onClick={() => inspect(i + 1)}
            className="flex size-7 items-center justify-center rounded-full bg-fill-tertiary transition-[scale] active:scale-90 disabled:opacity-30"
          >
            <ChevronRight className="size-4" />
          </button>
          <button
            onClick={() => inspect(null)}
            disabled={live}
            className="flex h-7 items-center gap-1 rounded-full bg-sys-blue/15 px-2.5 text-caption-1 font-semibold text-sys-blue transition-[scale,opacity] active:scale-95 disabled:opacity-0"
          >
            <LocateFixed className="size-3.5" aria-hidden /> Live
          </button>
        </div>
      </div>
      <SegmentedControl
        label="Inspector view"
        size="small"
        value={tab}
        onChange={setTab}
        options={[
          { value: "in", label: "Sent to API" },
          { value: "out", label: "Model output" },
        ]}
      />
      <div className="relative min-h-[14rem] flex-1 overflow-hidden rounded-[0.9rem] bg-black/40 p-3 font-mono">
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.div
            key={`${i}-${tab}`}
            initial={{ opacity: 0, filter: "blur(4px)" }}
            animate={{ opacity: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0 }}
            transition={spring.snappy}
            className="max-h-[22rem] overflow-auto"
          >
            <Json value={tab === "in" ? input : output} />
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
