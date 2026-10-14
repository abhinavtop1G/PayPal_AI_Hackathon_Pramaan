"use client";

import { AnimatePresence, motion } from "motion/react";
import { ChevronDown } from "lucide-react";
import { useRef, useState } from "react";
import { SegmentedControl } from "@/components/common/SegmentedControl";
import { ACTION_COLOR, ACTION_LABEL, riskColor, STAGE_COLOR, STAGE_LABEL } from "@/config/policy";
import { spring } from "@/config/motion";
import { useDemo } from "@/context/DemoContext";
import { useElementSize } from "@/hooks/useElementSize";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import type { Stage } from "@/types/demo";
import { stageAgreement } from "@/utils/derive";
import { describe } from "@/utils/events";
import { niceStep, pct, since, tickLabel } from "@/utils/format";

const PADL = 92; // room for the row labels
const PADR = 18;

/**
 * The whole session on one track. Top band: the simulator's ground-truth scam chapters. Second band: the stage the
 * model inferred, revealed as the replay reaches it. Below: every event (click to jump, drag the playhead to scrub)
 * and the payment decisions. For a scam, what the simulator victim would have done after the hold is shown faded:
 * those events never happen because the payment was stopped.
 */
export function SessionTimeline() {
  const { replay, last, index, seek, view } = useDemo();
  const [ref, { width }] = useElementSize<HTMLDivElement>();
  const [scale, setScale] = useState<"steps" | "time">("steps");
  // starts collapsed on short screens so the phone keeps its size; the user's toggle wins after that
  const short = useMediaQuery("(max-height: 800px)");
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  const open = userOpen ?? !short;
  const setOpen = (f: (o: boolean) => boolean) => setUserOpen(f(open));
  const track = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  const all = replay.timeline;
  const n = all.length;
  const maxMin = all[n - 1].ts_min || 1;
  const w = Math.max(width - PADL - PADR, 1);
  const x = (i: number) => PADL + (scale === "steps" ? (n > 1 ? i / (n - 1) : 0) : all[i].ts_min / maxMin) * w;
  const head = index >= 0 ? x(Math.min(index, last)) : PADL;
  const prevented = last < n - 1;
  const agree = stageAgreement(view.seen);

  const segs = (stageOf: (i: number) => Stage, upto: number) =>
    all.slice(0, upto + 1).map((_, i) => {
      const x0 = x(i);
      const x1 = i < n - 1 ? x(i + 1) : x0 + 4;
      return { i, x0, w: Math.max(1.5, x1 - x0), stage: stageOf(i) };
    });
  const truth = segs((i) => all[i].true_stage, n - 1);
  const model = segs((i) => all[i].workflow.stage, Math.min(index, last));

  // chapter labels: one per run of the same ground-truth stage, if it fits
  const chapters: { stage: Stage; x0: number; x1: number }[] = [];
  truth.forEach((s) => {
    const c = chapters.at(-1);
    if (c && c.stage === s.stage) c.x1 = s.x0 + s.w;
    else chapters.push({ stage: s.stage, x0: s.x0, x1: s.x0 + s.w });
  });

  const nearest = (clientX: number) => {
    const r = track.current?.getBoundingClientRect();
    if (!r) return index;
    const px = clientX - r.left;
    let best = 0;
    for (let i = 0; i <= last; i++) if (Math.abs(x(i) - px) < Math.abs(x(best) - px)) best = i;
    return best;
  };

  const spacing = scale === "steps" ? w / Math.max(n - 1, 1) : 0;
  const markerSize = scale === "steps" && spacing >= 20 ? "lg" : "sm";
  const step = niceStep(maxMin);

  return (
    <section aria-label="Session timeline" className="flex flex-col gap-1.5 px-4 pb-2.5 pt-2 sm:px-6">
      <header className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <button
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="-ml-1.5 flex items-center gap-1.5 rounded-full py-0.5 pl-1.5 pr-2.5 transition-[background-color,scale] hover:bg-fill-quaternary active:scale-[0.97]"
        >
          <motion.span animate={{ rotate: open ? 0 : -90 }} transition={spring.snappy} className="flex">
            <ChevronDown className="size-4 text-label-secondary" aria-hidden />
          </motion.span>
          <h2 className="text-headline">Session timeline</h2>
        </button>
        <span className="text-footnote text-label-secondary tabular-nums">
          event {Math.max(0, Math.min(index, last) + 1)} of {last + 1} · {since(view.nowMin)} of {since(all[last].ts_min, false)}
        </span>
        {agree != null && (
          <span className="rounded-full bg-fill-tertiary px-2 py-0.5 text-caption-1 text-label-secondary tabular-nums">
            model stage = ground truth on {Math.round(agree * 100)}% of events
          </span>
        )}
        <div className="ml-auto flex items-center gap-3">
          <Legend />
          <SegmentedControl
            label="Timeline scale"
            size="small"
            value={scale}
            onChange={setScale}
            options={[
              { value: "steps", label: "Steps" },
              { value: "time", label: "Time" },
            ]}
          />
        </div>
      </header>

      {/* collapsed: a thin scrubbable progress rail; expanded: the full track */}
      {!open && (
        <div
          className="relative h-2 cursor-pointer rounded-full bg-fill-tertiary"
          onPointerDown={(e) => {
            const r = e.currentTarget.getBoundingClientRect();
            seek(Math.round(((e.clientX - r.left) / r.width) * last));
          }}
        >
          <motion.div
            className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-sys-blue via-sys-orange to-sys-red"
            initial={false}
            animate={{ width: `${last > 0 ? (Math.max(0, Math.min(index, last)) / last) * 100 : 0}%` }}
            transition={spring.move}
          />
        </div>
      )}
      <AnimatePresence initial={false}>
      {open && (
      <motion.div
        ref={ref}
        className="relative overflow-hidden"
        initial={{ height: 0, opacity: 0 }}
        animate={{ height: "auto", opacity: 1 }}
        exit={{ height: 0, opacity: 0 }}
        transition={spring.default}
      >
        <div
          ref={track}
          className="relative h-[6.75rem] cursor-pointer touch-none select-none"
          onPointerDown={(e) => {
            dragging.current = true;
            (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
            seek(nearest(e.clientX));
          }}
          onPointerMove={(e) => dragging.current && seek(nearest(e.clientX))}
          onPointerUp={() => (dragging.current = false)}
          onPointerCancel={() => (dragging.current = false)}
        >
          {/* ground truth chapters */}
          <span className="absolute left-0 top-[0.95rem] text-caption-2 leading-[0.875rem] text-label-tertiary">Ground truth</span>
          {truth.map((s) => (
            <span
              key={`t${s.i}`}
              className="absolute top-[0.95rem] h-[0.875rem]"
              style={{ left: s.x0, width: s.w, background: STAGE_COLOR[s.stage], opacity: s.i > last ? 0.18 : 0.55 }}
            />
          ))}
          {chapters.map((c, k) =>
            c.x1 - c.x0 > 64 ? (
              <span
                key={`c${k}`}
                className="pointer-events-none absolute top-[0.95rem] flex h-[0.875rem] items-center px-1.5 text-[0.625rem] font-semibold uppercase tracking-wider text-black/75"
                style={{ left: c.x0, width: c.x1 - c.x0 }}
              >
                <span className="truncate">{STAGE_LABEL[c.stage]}</span>
              </span>
            ) : null,
          )}

          {/* model stage (revealed) */}
          <span className="absolute left-0 top-[2.75rem] text-caption-2 text-label-tertiary">Model stage</span>
          <span className="absolute left-0 top-[4.4rem] text-caption-2 text-label-tertiary">Events</span>
          {model.map((s) => (
            <motion.span
              key={`m${s.i}`}
              initial={{ scaleX: 0 }}
              animate={{ scaleX: 1 }}
              transition={spring.default}
              className="absolute top-[3rem] h-[0.375rem] origin-left rounded-full"
              style={{ left: s.x0, width: s.w, background: STAGE_COLOR[s.stage] }}
            />
          ))}

          {/* prevented stretch */}
          {prevented && (
            <span
              className="absolute top-[0.8rem] h-[5.6rem] rounded-[0.5rem] border border-dashed border-sys-red/40"
              style={{
                left: x(last) + 6,
                width: Math.max(0, x(n - 1) - x(last) + 4),
                background: "repeating-linear-gradient(135deg, rgb(255 69 58 / 0.06) 0 6px, transparent 6px 12px)",
              }}
            >
              <span className="absolute -top-[0.85rem] right-0 text-caption-2 font-semibold text-sys-red/80">prevented by the hold</span>
            </span>
          )}

          {/* events */}
          {all.map((e, i) => {
            const seen = i <= index && i <= last;
            const after = i > last;
            const { icon: Icon, label } = describe(e.input);
            const p = e.workflow.p_scam_in_progress;
            const c = seen ? riskColor(p) : "var(--color-gray-3)";
            const d = e.decision;
            return (
              <button
                key={i}
                disabled={after}
                onPointerDown={(ev) => ev.stopPropagation()}
                onClick={() => seek(i)}
                title={`${since(e.ts_min)} · ${label}${seen ? ` · workflow risk ${pct(p)}` : ""}${d ? ` · ${ACTION_LABEL[d.action]} ${pct(d.fused_risk)}` : ""}`}
                aria-label={`Jump to ${label} at ${since(e.ts_min)}`}
                className="group absolute top-[4.1rem] -translate-x-1/2 transition-[scale] duration-150 hover:scale-110 active:scale-95 disabled:cursor-default"
                style={{ left: x(i), opacity: after ? 0.35 : 1 }}
              >
                {markerSize === "lg" ? (
                  <span
                    className="flex size-6 items-center justify-center rounded-full border"
                    style={{ borderColor: c, color: c, background: seen ? `color-mix(in srgb, ${c} 18%, var(--color-bg))` : "var(--color-bg)" }}
                  >
                    <Icon className="size-3" aria-hidden />
                  </span>
                ) : (
                  <span className="mt-2 block size-2 rounded-full" style={{ background: c }} />
                )}
                {d && (
                  <span
                    className="absolute left-1/2 top-[1.75rem] -translate-x-1/2 whitespace-nowrap rounded-full px-1.5 text-[0.625rem] font-bold uppercase tracking-wider"
                    style={{ color: ACTION_COLOR[d.action], background: `color-mix(in srgb, ${ACTION_COLOR[d.action]} 16%, transparent)` }}
                  >
                    {ACTION_LABEL[d.action]}
                  </span>
                )}
              </button>
            );
          })}

          {/* playhead */}
          <motion.div
            className="pointer-events-none absolute top-[0.6rem] h-[5.9rem] w-0"
            initial={false}
            animate={{ left: head }}
            transition={spring.move}
          >
            <span className="absolute -left-px top-0 h-full w-[2px] rounded-full bg-label/85 shadow-[0_0_10px_rgb(255_255_255/0.4)]" />
            <span className="absolute -left-[5px] -top-[3px] size-[12px] rounded-full border-2 border-bg bg-label" />
          </motion.div>
        </div>

        {/* time axis */}
        {scale === "time" && (
          <div className="relative h-4">
            {Array.from({ length: Math.floor(maxMin / step) + 1 }, (_, k) => k * step).map((t) => (
              <span key={t} className="absolute -translate-x-1/2 text-caption-2 text-label-tertiary tabular-nums" style={{ left: PADL + (t / maxMin) * w }}>
                {tickLabel(t, maxMin)}
              </span>
            ))}
          </div>
        )}
      </motion.div>
      )}
      </AnimatePresence>
    </section>
  );
}

function Legend() {
  return (
    <div className="hidden items-center gap-2.5 text-caption-2 text-label-tertiary xl:flex">
      {(["contact", "pretext", "isolation", "extraction"] as Stage[]).map((s) => (
        <span key={s} className="flex items-center gap-1">
          <span className="size-2 rounded-full" style={{ background: STAGE_COLOR[s] }} aria-hidden />
          {STAGE_LABEL[s]}
        </span>
      ))}
    </div>
  );
}
