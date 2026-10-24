import { ShieldAlert, ShieldCheck, ShieldX } from "lucide-react";
import { DECISION_STYLE } from "@/config/authSignals";
import type { Decision } from "@/types/auth";

const ICON = { allow: ShieldCheck, challenge: ShieldAlert, block: ShieldX };

/** A decision as a status pill: icon + label + status colour, never colour alone. */
export function DecisionBadge({ decision, size = "sm", label }: { decision: Decision; size?: "xs" | "sm" | "md"; label?: string }) {
  const st = DECISION_STYLE[decision];
  const Icon = ICON[decision];
  const s = size === "md" ? "gap-1.5 px-3 py-1 text-subheadline font-semibold" : size === "sm"
    ? "gap-1 px-2 py-0.5 text-caption-1 font-semibold" : "gap-1 px-1.5 py-px text-caption-2 font-semibold";
  return (
    <span className={`inline-flex shrink-0 items-center rounded-full ${st.bg} ${s}`} style={{ color: st.tint }}>
      <Icon className={size === "md" ? "size-4" : "size-3.5"} aria-hidden />
      {label ?? st.label}
    </span>
  );
}

export const DECISION_ICON = ICON;
