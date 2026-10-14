"use client";

import { AnimatePresence, motion } from "motion/react";
import { useId } from "react";
import { ACTION_COLOR, ACTION_LABEL, riskColor, STAGE_COLOR } from "@/config/policy";
import { spring } from "@/config/motion";
import { useDemo } from "@/context/DemoContext";
import { useElementSize } from "@/hooks/useElementSize";
import { niceStep, pct, tickLabel } from "@/utils/format";

const PAD = { l: 44, r: 24, t: 26, b: 46 };

/**
 * Live risk timeline. The line is the workflow GRU's P(scam in progress) after every event, drawn as a step
 * (risk holds until the next event). Diamonds are the fused payment risk the alert policy acted on. The whole
 * session is laid out up front and revealed by a clip that springs to the latest event, so the scale never jumps.
 */
export function RiskTimeline() {
  const { replay, last, index } = useDemo();
  const [ref, { width: W, height: H }] = useElementSize<HTMLDivElement>();
  const uid = useId().replace(/:/g, "");
  const entries = replay.timeline.slice(0, last + 1);
  const xMax = Math.max(entries[last].ts_min * 1.03, 1);
  const plotW = Math.max(W - PAD.l - PAD.r, 1);
  const plotH = Math.max(H - PAD.t - PAD.b, 1);
  const x = (m: number) => PAD.l + (m / xMax) * plotW;
  const y = (p: number) => PAD.t + (1 - p) * plotH;
  const cur = index >= 0 ? entries[Math.min(index, last)] : null;
  const revealX = cur ? x(cur.ts_min) : PAD.l;

  const pts = entries.map((e) => [x(e.ts_min), y(e.workflow.p_scam_in_progress)] as const);
  const line = pts.map(([px, py], i) => (i === 0 ? `M${px},${py}` : `H${px}V${py}`)).join("");
  const area = `${line}V${y(0)}H${pts[0][0]}Z`;
  const step = niceStep(xMax);
  const xticks = Array.from({ length: Math.floor(xMax / step) + 1 }, (_, i) => i * step);
  const seen = entries.slice(0, index + 1);
  const ext = replay.extraction_ts_min;

  return (
    <div ref={ref} className="relative h-full min-h-[15rem] w-full">
      {W > 0 && (
        <svg width={W} height={H} className="absolute inset-0 overflow-visible" role="img" aria-label="Session risk over time">
          <defs>
            <linearGradient id={`stroke-${uid}`} gradientUnits="userSpaceOnUse" x1="0" y1={y(0)} x2="0" y2={y(1)}>
              <stop offset="0" stopColor="var(--color-sys-green)" />
              <stop offset="0.3" stopColor="var(--color-sys-yellow)" />
              <stop offset="0.6" stopColor="var(--color-sys-orange)" />
              <stop offset="0.85" stopColor="var(--color-sys-red)" />
            </linearGradient>
            <linearGradient id={`fill-${uid}`} gradientUnits="userSpaceOnUse" x1="0" y1={y(1)} x2="0" y2={y(0)}>
              <stop offset="0" stopColor="var(--color-sys-red)" stopOpacity="0.28" />
              <stop offset="1" stopColor="var(--color-sys-red)" stopOpacity="0" />
            </linearGradient>
            <clipPath id={`reveal-${uid}`}>
              <motion.rect
                x={0}
                y={0}
                height={H}
                initial={false}
                animate={{ width: cur ? revealX + 6 : 0 }}
                transition={spring.move}
              />
            </clipPath>
          </defs>

          {/* grid */}
          {[0, 0.25, 0.5, 0.75, 1].map((g) => (
            <g key={g}>
              <line x1={PAD.l} x2={W - PAD.r} y1={y(g)} y2={y(g)} stroke="var(--color-separator)" strokeWidth={g === 0 ? 1 : 0.5} strokeDasharray={g === 0 ? undefined : "2 4"} />
              <text x={PAD.l - 10} y={y(g)} dy="0.32em" textAnchor="end" className="fill-label-tertiary text-[0.6875rem] tabular-nums">
                {g * 100}%
              </text>
            </g>
          ))}
          {xticks.map((t) => (
            <text key={t} x={x(t)} y={H - 8} textAnchor="middle" className="fill-label-tertiary text-[0.6875rem] tabular-nums">
              {tickLabel(t, xMax)}
            </text>
          ))}

          <g clipPath={`url(#reveal-${uid})`}>
            <path d={area} fill={`url(#fill-${uid})`} />
            <path d={line} fill="none" stroke={`url(#stroke-${uid})`} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
            {pts.map(([px, py], i) => (
              <circle key={i} cx={px} cy={py} r={2.25} fill="var(--color-bg)" stroke={`url(#stroke-${uid})`} strokeWidth={1.25} />
            ))}
            {/* model-estimated scam stage under the plot */}
            {entries.map((e, i) => {
              const x0 = x(e.ts_min);
              const x1 = i < entries.length - 1 ? x(entries[i + 1].ts_min) : x0 + 6;
              return (
                <rect key={i} x={x0} y={H - PAD.b + 10} width={Math.max(x1 - x0, 1.5)} height={5} rx={2.5} fill={STAGE_COLOR[e.workflow.stage]} />
              );
            })}
          </g>

          {/* extraction: the moment money would leave */}
          {ext != null && cur && cur.ts_min >= ext && (
            <motion.g initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <line x1={x(ext)} x2={x(ext)} y1={PAD.t - 14} y2={y(0)} stroke="var(--color-sys-red)" strokeOpacity={0.5} strokeDasharray="3 3" />
              <text x={x(ext) - 6} y={PAD.t - 16} textAnchor="end" className="fill-sys-red text-[0.6875rem] font-semibold">
                Money about to leave
              </text>
            </motion.g>
          )}

          {/* payment decisions (fused risk) */}
          <AnimatePresence>
            {seen
              .filter((e) => e.decision)
              .map((e, k) => {
                const d = e.decision!;
                const px = x(e.ts_min);
                const py = y(d.fused_risk);
                const c = ACTION_COLOR[d.action];
                const above = py > PAD.t + 30;
                return (
                  <motion.g
                    key={e.event_index}
                    initial={{ opacity: 0, scale: 0.4 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ ...spring.sheet, delay: 0.3 }}
                    style={{ transformOrigin: `${px}px ${py}px` }}
                  >
                    <rect x={px - 6} y={py - 6} width={12} height={12} rx={2} transform={`rotate(45 ${px} ${py})`} fill="var(--color-bg)" stroke={c} strokeWidth={2.5} />
                    {(k === 0 || d.notify) && <g transform={`translate(${px - 120 > PAD.l ? px - 120 : px + 8}, ${above ? py - 34 : py + 14})`}>
                      <rect width={112} height={22} rx={11} fill={c} fillOpacity={0.16} />
                      <text x={56} y={11} dy="0.34em" textAnchor="middle" fill={c} className="text-[0.6875rem] font-semibold tabular-nums">
                        {ACTION_LABEL[d.action].toUpperCase()} · {pct(d.fused_risk)}
                      </text>
                    </g>}
                  </motion.g>
                );
              })}
          </AnimatePresence>

          {/* live head */}
          {cur && (
            <motion.g initial={false} animate={{ x: x(cur.ts_min), y: y(cur.workflow.p_scam_in_progress) }} transition={spring.move}>
              <motion.circle
                r={9}
                fill={riskColor(cur.workflow.p_scam_in_progress)}
                initial={{ opacity: 0.45, scale: 0.6 }}
                animate={{ opacity: 0, scale: 1.8 }}
                transition={{ duration: 1.4, repeat: Infinity, ease: "easeOut" }}
              />
              <circle r={5} fill={riskColor(cur.workflow.p_scam_in_progress)} stroke="var(--color-bg)" strokeWidth={2} />
            </motion.g>
          )}
        </svg>
      )}

      <AnimatePresence>
        {index < 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, filter: "blur(6px)" }}
            className="absolute inset-0 flex items-center justify-center"
          >
            <p className="material-thin rounded-full px-4 py-2 text-footnote text-label-secondary">
              Press Play (or Space) to replay the session through the models
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
