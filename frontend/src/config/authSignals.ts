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
  behaviour: "var(--color-sys-purple)",
  device: "var(--color-sys-cyan)",
  transaction: "var(--color-sys-orange)",
};

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
