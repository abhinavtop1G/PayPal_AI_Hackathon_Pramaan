import type { Action, Stage, TierName } from "@/types/demo";

/**
 * Alert tiers, mirrored from ml/engine/policy.py. Efficacy = share of scams the action stops; friction = cost of
 * interrupting a genuine user, in rupee-equivalents. Both are stated assumptions, to be tuned with a bank.
 *   EV(tier) = p · amount · efficacy − (1 − p) · friction
 */
export const TIERS: { name: TierName; label: string; efficacy: number; friction: number; color: string }[] = [
  { name: "allow", label: "Allow", efficacy: 0, friction: 0, color: "var(--color-sys-green)" },
  { name: "nudge", label: "Nudge", efficacy: 0.2, friction: 10, color: "var(--color-sys-yellow)" },
  { name: "cool_off", label: "Cool-off", efficacy: 0.5, friction: 60, color: "var(--color-sys-orange)" },
  { name: "hold", label: "Hold", efficacy: 0.9, friction: 250, color: "var(--color-sys-red)" },
];

export const ev = (p: number, amount: number, t: (typeof TIERS)[number]) =>
  p * amount * t.efficacy - (1 - p) * t.friction;

export const ACTION_LABEL: Record<Action, string> = {
  allow: "Allow",
  monitor: "Monitor",
  nudge: "Nudge",
  cool_off: "Cool-off",
  hold: "Hold",
};

export const ACTION_COLOR: Record<Action, string> = {
  allow: "var(--color-sys-green)",
  monitor: "var(--color-sys-teal)",
  nudge: "var(--color-sys-yellow)",
  cool_off: "var(--color-sys-orange)",
  hold: "var(--color-sys-red)",
};

export const STAGE_LABEL: Record<Stage, string> = {
  none: "No scam pattern",
  contact: "Contact",
  pretext: "Pretext",
  isolation: "Isolation",
  extraction: "Extraction",
};

export const STAGE_COLOR: Record<Stage, string> = {
  none: "var(--color-gray-2)",
  contact: "var(--color-sys-blue)",
  pretext: "var(--color-sys-indigo)",
  isolation: "var(--color-sys-orange)",
  extraction: "var(--color-sys-red)",
};

export const TYPOLOGY_LABEL: Record<string, string> = {
  digital_arrest: "Digital arrest",
  fake_kyc_apk: "Fake KYC app",
  investment_task: "Investment / task scam",
  voice_clone_relative: "Voice-clone relative",
};

/** Every simulator session type (scams and genuine), for the fleet wall. */
export const SESSION_LABEL: Record<string, string> = {
  ...TYPOLOGY_LABEL,
  routine: "Routine payments",
  family_transfer: "Family transfer",
  new_payee_service: "New payee (service)",
  large_new_payee: "Large new payee (rent)",
  urgent_bill: "Urgent bill",
  support_install: "Support app install",
  hospital_emergency: "Hospital emergency",
  bank_app_update: "Bank app update",
  legit_investing: "Legit investing",
  genuine_urgent_family: "Family emergency",
  builder: "Your session",
};

/** Risk → semantic colour (safe / watch / elevated / critical). */
export function riskColor(p: number) {
  if (p < 0.2) return "var(--color-risk-safe)";
  if (p < 0.5) return "var(--color-risk-watch)";
  if (p < 0.8) return "var(--color-risk-elevated)";
  return "var(--color-risk-critical)";
}
