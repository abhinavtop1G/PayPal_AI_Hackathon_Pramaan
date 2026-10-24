import type { ChallengeType, Decision, Family } from "@/types/auth";

/** Short console labels for the model's 26 features (ml/auth/features.py SPEC). */
export const SIGNAL_LABEL: Record<string, string> = {
  bio_dev: "Touch pattern vs owner",
  typing_dev: "Typing rhythm vs owner",
  fast_submit: "Submitted in < 3 s",
  low_input: "Almost no input",
  unknown_call_active: "On a call with unknown number",
  screen_share_active: "Screen being shared",
  device_new: "New device",
  device_untrusted: "Device not yet trusted",
  n_devices_30d: "Devices on account (30 d)",
  accounts_on_device: "Other accounts on this device",
  emulator: "Emulator",
  rooted: "Rooted / jailbroken",
  remote_access_app: "Remote-access app running",
  sim_fresh: "SIM changed recently",
  ip_datacenter: "Hosting-provider IP",
  ip_anonymiser: "VPN / Tor",
  ip_accounts_1h: "Accounts on this IP (1 h)",
  geo_speed: "Travel speed since last payment",
  new_city: "City never used before",
  amt_z: "Amount vs usual",
  payee_new: "New payee",
  payee_risk: "Payee risk (payee intelligence)",
  txn_count_1h: "Payments in last hour",
  spend_24h_z: "24 h spend vs usual",
  hour_rarity: "Unusual hour",
  short_history: "Little history",
  fails_24h: "Failed challenges (24 h)",
};

export const FAMILY_TINT: Record<Family, string> = {
  behaviour: "var(--color-fam-behaviour)",
  device: "var(--color-fam-device)",
  transaction: "var(--color-fam-transaction)",
};

/** Which family each model feature belongs to (ml/auth/features.py FAMILY). */
export const SIGNAL_FAMILY: Record<string, Family> = {
  bio_dev: "behaviour", typing_dev: "behaviour", fast_submit: "behaviour", low_input: "behaviour",
  unknown_call_active: "behaviour", screen_share_active: "behaviour",
  device_new: "device", device_untrusted: "device", n_devices_30d: "device", accounts_on_device: "device",
  emulator: "device", rooted: "device", remote_access_app: "device", sim_fresh: "device", ip_datacenter: "device",
  ip_anonymiser: "device", ip_accounts_1h: "device", geo_speed: "device", new_city: "device",
  amt_z: "transaction", payee_new: "transaction", payee_risk: "transaction", txn_count_1h: "transaction",
  spend_24h_z: "transaction", hour_rarity: "transaction", short_history: "transaction", fails_24h: "transaction",
};

export const ATTACK_LABEL: Record<string, string> = {
  ato_new_device: "Stolen credentials",
  sim_swap: "SIM swap",
  bot: "Credential stuffing (bot)",
  remote_access: "Remote-access takeover",
  coerced: "Coached victim",
};

export const GENUINE_KIND_LABEL: Record<string, string> = {
  routine: "Everyday payment",
  new_phone: "New phone",
  travel: "Travelling",
  big_purchase: "Big purchase",
  web: "Web login / payment",
  genuine: "Genuine",
};

/** Risk as a short percentage that stays readable from 0.001% to 99%. */
export function pct(p: number): string {
  if (!Number.isFinite(p)) return "—";
  const v = 100 * p;
  if (v < 0.01) return "<0.01%";
  if (v < 1) return `${v.toFixed(2)}%`;
  if (v < 10) return `${v.toFixed(1)}%`;
  return `${Math.round(v)}%`;
}

/** Compact Indian-rupee amounts: ₹640, ₹18.5K, ₹4.2L, ₹1.3Cr. */
export function inrCompact(x: number): string {
  if (x >= 1e7) return `₹${(x / 1e7).toFixed(x >= 1e8 ? 0 : 1)}Cr`;
  if (x >= 1e5) return `₹${(x / 1e5).toFixed(x >= 1e6 ? 0 : 1)}L`;
  if (x >= 1e3) return `₹${(x / 1e3).toFixed(x >= 1e4 ? 0 : 1)}K`;
  return `₹${Math.round(x)}`;
}

export const FAMILY_LABEL: Record<Family, string> = { behaviour: "Behaviour", device: "Device", transaction: "Transaction" };

export const DECISION_STYLE: Record<Decision, { label: string; tint: string; bg: string }> = {
  allow: { label: "Allow", tint: "var(--color-sys-green)", bg: "bg-sys-green/12" },
  challenge: { label: "Challenge", tint: "var(--color-sys-orange)", bg: "bg-sys-orange/12" },
  block: { label: "Block", tint: "var(--color-sys-red)", bg: "bg-sys-red/12" },
};

export const CHALLENGE_LABEL: Record<ChallengeType, { title: string; why: string }> = {
  sms_otp: { title: "SMS one-time password", why: "No sign of a SIM change or a hijacked device: a standard OTP is enough." },
  passkey: { title: "Passkey on the registered device", why: "New device or new SIM: an SMS OTP could reach the attacker, so approve on the phone we already trust." },
  bank_callback: { title: "Bank call-back", why: "Someone else may be controlling the screen, the customer may be coached on a call, or the amount is large: a person from the bank confirms on the registered number." },
  cool_off: { title: "30-minute cool-off + scam warning", why: "The real owner, on their own phone, appears to be coached on a call: an OTP would not help." },
};

export const CHALLENGE_SHORT: Record<ChallengeType, string> = {
  sms_otp: "SMS OTP", passkey: "Passkey", bank_callback: "Bank call-back", cool_off: "Cool-off",
};

/** How a raw feature value is shown in the signal list. */
export function showValue(name: string, v: number | null): string {
  if (v === null || v === undefined) return "—";
  if (name === "geo_speed") return `${Math.round(Math.expm1(v)).toLocaleString("en-IN")} km/h`;
  if (name === "sim_fresh") return v > 0 ? `${Math.round((1 - v) * 168)} h ago` : "no";
  if (["amt_z", "spend_24h_z", "bio_dev", "typing_dev"].includes(name)) return v.toFixed(2);
  if (name === "payee_risk" || name === "hour_rarity") return v.toFixed(2);
  if (["n_devices_30d", "accounts_on_device", "ip_accounts_1h", "txn_count_1h", "fails_24h"].includes(name)) return String(v);
  return v >= 0.5 ? "yes" : "no";
}

export const inr = (x: number) => `₹${Math.round(x).toLocaleString("en-IN")}`;
