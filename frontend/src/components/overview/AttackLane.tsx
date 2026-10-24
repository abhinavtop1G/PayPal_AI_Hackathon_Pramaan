"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ChartTooltip } from "@/components/charts/ChartTooltip";
import { ATTACK_LABEL, inr } from "@/config/authSignals";
import { useElementSize } from "@/hooks/useElementSize";
import type { AttackType, TrafficRow } from "@/types/console";
import { DAY_S, hhmm } from "./useReplay";

const LANES: AttackType[] = ["ato_new_device", "sim_swap", "bot", "remote_access", "coerced"];

/**
 * Every attack request of the day on a 24-hour axis, one lane per attack type: a filled dot was finally stopped, a
 * hollow ring got through. The playhead is the replay clock.
 */
export function AttackLane({ rows, clock }: { rows: TrafficRow[]; clock: number }) {
  const [ref, { width }] = useElementSize<HTMLDivElement>();
  const [hover, setHover] = useState<TrafficRow | null>(null);
  const router = useRouter();
  const padL = 132, padR = 10, laneH = 26, padB = 20;
  const height = LANES.length * laneH + padB;
  const X = (t: number) => padL + (t / DAY_S) * Math.max(0, width - padL - padR);
  const shown = rows.filter((r) => r.atk && r.t <= clock);
  return (
    <div ref={ref} className="chart relative w-full" style={{ height }} onPointerLeave={() => setHover(null)}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label="Attack requests through the day by type and outcome">
          {LANES.map((l, i) => (
            <g key={l}>
              <line x1={padL} x2={width - padR} y1={i * laneH + laneH / 2} y2={i * laneH + laneH / 2} stroke="var(--color-chart-grid)" />
              <text x={0} y={i * laneH + laneH / 2 + 4} fontSize={11.5} fill="var(--color-label-secondary)">{ATTACK_LABEL[l]}</text>
            </g>
          ))}
          {[0, 3, 6, 9, 12, 15, 18, 21, 24].map((h) => (
            <text key={h} x={X(h * 3600)} y={height - 5} textAnchor="middle" fontSize={10.5} fill="var(--color-chart-muted)">{`${String(h).padStart(2, "0")}:00`}</text>
          ))}
          <rect x={X(Math.min(clock, DAY_S))} y={0} width={1.5} height={height - padB} fill="var(--color-label-tertiary)" />
          {shown.map((r, k) => {
            const i = LANES.indexOf(r.atk as AttackType);
            const stopped = r.f === "block";
            const cx = X(r.t), cy = i * laneH + laneH / 2;
            return (
              <g key={k} onPointerEnter={() => setHover(r)} onClick={() => router.push(`/console/audit?q=${encodeURIComponent(r.u)}`)}
                className="cursor-pointer" role="link" aria-label={`${ATTACK_LABEL[r.atk!]} at ${hhmm(r.t)}: open in the audit log`}>
                <circle cx={cx} cy={cy} r={12} fill="transparent" />
                <circle cx={cx} cy={cy} r={stopped ? 5 : 4.25} fill={stopped ? "var(--color-sys-green)" : "var(--color-chart-surface)"}
                  stroke={stopped ? "var(--color-chart-surface)" : "var(--color-sys-red)"} strokeWidth={stopped ? 2 : 1.75} />
              </g>
            );
          })}
        </svg>
      )}
      {hover && (
        <ChartTooltip x={X(hover.t)} y={LANES.indexOf(hover.atk as AttackType) * laneH - 40} width={width}
          title={`${hhmm(hover.t)} · ${ATTACK_LABEL[hover.atk!]}`}
          rows={[
            { label: hover.f === "block" ? "stopped" : "got through", value: hover.d === "challenge" ? `${hover.c} → ${hover.f}` : hover.d },
            { label: "amount", value: hover.amt > 0 ? inr(hover.amt) : "login" },
            { label: "risk", value: `${(100 * hover.p).toPrecision(2)}%` },
          ]} />
      )}
      <div className="mt-1 flex flex-wrap gap-4 pl-[132px] text-caption-1 text-label-secondary">
        <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-full bg-sys-green" aria-hidden /> stopped</span>
        <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-full border-[1.75px] border-sys-red" aria-hidden /> got through</span>
        <span className="text-label-tertiary">click a dot to open it in the audit log</span>
      </div>
    </div>
  );
}
