"use client";

import { motion } from "motion/react";
import { Globe, Smartphone } from "lucide-react";
import { DecisionBadge } from "@/components/ui/DecisionBadge";
import { ATTACK_LABEL, CHALLENGE_SHORT, inrCompact, pct } from "@/config/authSignals";
import { spring } from "@/config/motion";
import type { TrafficRow } from "@/types/console";

function clockText(t: number) {
  const s = Math.floor(t);
  return `${String(Math.floor(s / 3600)).padStart(2, "0")}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/** The latest decisions as the replay reaches them. Attack rows show the simulator's ground truth and the outcome. */
export function LiveFeed({ rows }: { rows: TrafficRow[] }) {
  // new rows fade in; nothing animates out or slides, so a fast replay never stacks rows mid-transition
  return (
    <ul className="space-y-1" aria-live="off">
      {rows.map((r) => (
        <motion.li key={`${r.t}-${r.u}`} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={spring.snappy}
          className={`grid grid-cols-[4.2rem_1fr_auto] items-center gap-2 rounded-[0.7rem] px-2.5 py-1.5 ${r.atk ? "bg-sys-red/[0.07] ring-1 ring-sys-red/20" : ""}`}>
          <span className="font-mono text-caption-1 tabular-nums text-label-tertiary">{clockText(r.t)}</span>
          <span className="min-w-0">
            <span className="flex items-center gap-1.5 text-footnote">
              {r.ch === "web" ? <Globe className="size-3.5 shrink-0 text-label-tertiary" aria-label="web" /> : <Smartphone className="size-3.5 shrink-0 text-label-tertiary" aria-label="mobile" />}
              <span className="truncate">{r.ev === "login" ? "Login" : inrCompact(r.amt)}{r.city ? ` · ${r.city}` : ""}</span>
            </span>
            {r.atk ? (
              <span className="block truncate text-caption-2 text-sys-red">
                {ATTACK_LABEL[r.atk]} · {r.f === "block" ? "stopped" : "got through"}
              </span>
            ) : r.d !== "allow" ? (
              <span className="block truncate text-caption-2 text-label-tertiary">genuine · risk {pct(r.p)}{r.c ? ` · ${r.pass ? "passed" : "abandoned"}` : ""}</span>
            ) : null}
          </span>
          <DecisionBadge decision={r.d} size="xs" label={r.d === "challenge" && r.c ? CHALLENGE_SHORT[r.c] : undefined} />
        </motion.li>
      ))}
    </ul>
  );
}
