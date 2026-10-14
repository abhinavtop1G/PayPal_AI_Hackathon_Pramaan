import type { DemoInput, EventType } from "@/types/demo";
import { rupees } from "@/utils/format";
import { personalise, type Persona } from "./personas";

/**
 * Story layer for the demo sessions. Everything the models see (events, timings, amounts, scores, decisions) comes
 * from the API replay; this file only names the people and screens and narrates each event for the audience.
 * Scenarios come in pairs: a scam and its genuine look-alike, run for the same user through the same models.
 */
export type ScenarioId =
  | "digital_arrest" | "hospital_emergency"
  | "voice_clone_relative" | "genuine_urgent_family"
  | "fake_kyc_apk" | "bank_app_update"
  | "investment_task" | "legit_investing";

type Narrate = string | ((e: DemoInput, nth: number) => string);

export interface Scenario {
  /** a scripted demo, or "custom" for a fleet session / builder session with no story layer */
  id: ScenarioId | "custom";
  pair: number;
  title: string;
  kind: "Scam" | "Genuine";
  /** one line for the picker */
  blurb: string;
  /** story text may use persona tokens: {first} {they} {their} … (see personalise) */
  summary: string;
  /** Caller ID as the phone shows it, by caller_kind. */
  callers: Partial<Record<NonNullable<DemoInput["caller_kind"]>, { id: string; detail: string }>>;
  /** Payee display by payee_id; `fallback` for any other. */
  payees: Record<string, { name: string; vpa: string; initials: string }>;
  sms?: { sender: string; body: string };
  otp?: { sender: string; body: string };
  page?: { url: string; title: string; body: string; cta: string; tone: "scam" | "legit" };
  app?: { name: string; permission?: string };
  credit?: (amount: number) => string;
  narration: Partial<Record<EventType, Narrate>>;
}

export const PAIRS = ["Digital arrest", "Voice clone", "Fake KYC app", "Investment scam"];

const P = (name: string, vpa: string) => ({
  name,
  vpa,
  initials: name.split(/\s+/).filter((w) => /^[A-Z]/.test(w)).slice(0, 2).map((w) => w[0]).join(""),
});

export type ScriptedScenario = Scenario & { id: ScenarioId };

export const SCENARIOS: ScriptedScenario[] = [
  {
    id: "digital_arrest",
    pair: 0,
    title: "Digital arrest",
    kind: "Scam",
    blurb: "Fake CBI officer keeps the victim on a call for an hour",
    summary: "A caller posing as a CBI officer keeps {first} on the line for an hour and tells {them} to move {their} savings.",
    callers: {
      unknown: { id: "+91 70XXX 41207", detail: "Mobile · Unknown" },
      voip_intl: { id: "+44 20 7946 0321", detail: "Internet call · Unknown" },
    },
    payees: { fallback: P("Safe Custody Account", "safecustody.verify@upi") },
    app: { name: "Remote Support" },
    narration: {
      CALL_START: (e) =>
        e.caller_kind === "voip_intl"
          ? "An internet call. The caller claims to be a CBI officer and says {first} is under ‘digital arrest’."
          : "An unknown number calls: ‘A parcel in your name was seized by customs.’",
      CALL_END: (_, n) => (n === 0 ? "The first call drops. The pressure is about to begin." : "The call ends."),
      BIO_WINDOW: "Touch telemetry sampled while {they} follows the caller’s instructions.",
      APP_INSTALL: "{They} is told to install a ‘secure verification’ app so the officer can ‘help’.",
      UPI_APP_OPEN: "{They} opens {their} UPI app while the caller stays on the line.",
      BALANCE_CHECK: (_, n) => (n === 0 ? "{They} reads out {their} balance to the caller." : "Asked to check {their} balance again."),
      PAYEE_ADD: "The caller dictates a ‘safe custody’ account to ‘verify’ {their} money.",
      PAYMENT_ATTEMPT: (e) => `{They} tries to send the first instalment of ${rupees(e.amount ?? 0)}.`,
    },
  },
  {
    id: "hospital_emergency",
    pair: 0,
    title: "Hospital emergency",
    kind: "Genuine",
    blurb: "Long call from an unknown number, a large payment to a new payee",
    summary: "A hospital calls about {their} {hospital}’s accident. A long call from an unknown number ends in a large payment to a new account. It is real.",
    callers: { unknown: { id: "+91 172 XXX 4410", detail: "Landline · Unknown" } },
    payees: { fallback: P("Arjun Mehta (billing)", "arjun.mehta@upi") },
    narration: {
      CALL_START: "The hospital calls: {their} {hospital} was in a road accident and needs surgery.",
      UPI_APP_OPEN: "After a long conversation {they} opens {their} UPI app.",
      PAYEE_ADD: "{They} adds the billing desk’s account: new to {them}, 83 days old.",
      BIO_WINDOW: "Touch telemetry sampled: stressed, but {their} own hands.",
      PAYMENT_ATTEMPT: (e) => `{They} pays the ${rupees(e.amount ?? 0)} surgery deposit, far above {their} usual payments.`,
      PAYMENT_SUCCESS: "Paid. A frightening call and a huge amount, yet no workflow pattern, so no alert.",
      CALL_END: "The call ends.",
    },
  },
  {
    id: "voice_clone_relative",
    pair: 1,
    title: "Voice-clone relative",
    kind: "Scam",
    blurb: "A relative calls from abroad, voice cloned by AI",
    summary: "An internet call in {their} {clone}’s cloned voice: arrested abroad, needs bail money now, don’t tell anyone.",
    callers: { voip_intl: { id: "+971 4 XXX 0198", detail: "Internet call · Unknown" } },
    payees: { fallback: P("Legal Aid Desk", "legalaid.bail@upi") },
    narration: {
      CALL_START: "An internet call. It sounds exactly like {their} {clone}: ‘{address}, I’ve been arrested in Dubai.’",
      UPI_APP_OPEN: "Two minutes later {they} opens {their} UPI app, still on the call.",
      PAYEE_ADD: "The ‘lawyer’s’ account: 4 years old, but tied to mule activity (payee risk 0.67).",
      BIO_WINDOW: "Touch telemetry sampled: rushed, hesitant taps.",
      PAYMENT_ATTEMPT: (e) => `{They} tries to send ${rupees(e.amount ?? 0)} for ‘bail’.`,
    },
  },
  {
    id: "genuine_urgent_family",
    pair: 1,
    title: "Family emergency",
    kind: "Genuine",
    blurb: "Niece on a new number needs money urgently",
    summary: "A call from a new number: {their} niece at a hospital needs a deposit. It is real.",
    callers: { unknown: { id: "+91 98XXX 22816", detail: "Mobile · Unknown" } },
    payees: { fallback: P("Simran Kaur", "simran.kaur@upi") },
    narration: {
      CALL_START: "A call from an unfamiliar number: {their} niece, phoning from a hospital.",
      UPI_APP_OPEN: "{They} opens {their} UPI app.",
      PAYEE_ADD: "{They} adds the niece’s account: new to {them}, but years old and clean.",
      BIO_WINDOW: "Touch telemetry sampled while {they} types.",
      PAYMENT_ATTEMPT: (e) => `{They} sends the ${rupees(e.amount ?? 0)} hospital deposit.`,
      PAYMENT_SUCCESS: "Paid.",
      CALL_END: "The call ends.",
    },
  },
  {
    id: "fake_kyc_apk",
    pair: 2,
    title: "Fake KYC app",
    kind: "Scam",
    blurb: "‘KYC expiring’ SMS, sideloaded app, OTP stolen",
    summary: "An SMS says {their} KYC expires today. A ‘bank officer’ talks {them} into a sideloaded app that reads {their} screen and OTPs.",
    callers: { unknown: { id: "+91 89XXX 66120", detail: "Mobile · Unknown" } },
    payees: {
      X00000: P("KYC Verification Charges", "kyc.verify.desk@upi"),
      X00002: P("Account Unblock Services", "unblock.services@upi"),
      fallback: P("KYC Verification Charges", "kyc.verify.desk@upi"),
    },
    sms: { sender: "AX-BNKKYC", body: "Dear customer, your KYC expires today and your account will be blocked. Update now: kyc-update-portal.in/u" },
    otp: { sender: "AX-BNKOTP", body: "482913 is your OTP. Do not share it with anyone." },
    page: { url: "kyc-update-portal.in", title: "Complete your e-KYC", body: "Your account will be blocked in 2 hours. Download the KYC Update app to verify your Aadhaar and PAN.", cta: "Download KYC Update.apk", tone: "scam" },
    app: { name: "KYC Update", permission: "Allow KYC Update to view and control your screen?" },
    narration: {
      SMS_RECEIVED: "An SMS from a bank-like sender: ‘Your KYC expires today.’",
      CALL_START: "A ‘bank officer’ calls to ‘help’ with the update.",
      LINK_CLICK: "{They} opens the link: a page that looks like {their} bank’s.",
      APP_INSTALL: "{They} installs ‘KYC Update’ from outside the Play Store.",
      ACCESSIBILITY_GRANT: "The app asks to control {their} screen. {They} taps Allow.",
      OTP_RECEIVED: "An OTP arrives. The app can now read it.",
      CALL_END: "The ‘officer’ hangs up.",
      UPI_APP_OPEN: "{Their} UPI app opens.",
      PAYEE_ADD: "A new payee is added for ‘verification charges’.",
      BIO_WINDOW: "Touch telemetry sampled: not {their} usual rhythm.",
      PAYMENT_ATTEMPT: (e) => `A payment of ${rupees(e.amount ?? 0)} starts.`,
    },
  },
  {
    id: "bank_app_update",
    pair: 2,
    title: "Bank app update",
    kind: "Genuine",
    blurb: "Real bank SMS, app update, OTP, everyday payments",
    summary: "{Their} bank asks {them} to update its app. Same SMS, link, install and OTP steps as the scam, then ordinary payments to shops {they} knows.",
    callers: {},
    payees: {
      M00019: P("Punjab Agro Inputs", "punjabagro@upi"),
      M00031: P("Sharma Kirana Store", "sharmakirana@upi"),
      M00020: P("Kisan Fertiliser Depot", "kisanfert@upi"),
      fallback: P("Punjab Agro Inputs", "punjabagro@upi"),
    },
    sms: { sender: "AX-MYBANK", body: "A new version of the MyBank app is available. Update from Google Play: play.google.com/store/apps" },
    otp: { sender: "AX-MYBANK", body: "731552 is your OTP to log in to MyBank. Never share it." },
    page: { url: "play.google.com", title: "MyBank · Update", body: "Version 8.4.1 · Bug fixes and faster UPI payments. Developer: MyBank Ltd (verified).", cta: "Update", tone: "legit" },
    app: { name: "MyBank" },
    narration: {
      SMS_RECEIVED: "An SMS from {their} bank: a new app version is available.",
      LINK_CLICK: "{They} opens the link: the official Play Store page.",
      APP_INSTALL: "{They} updates the bank app from the Play Store.",
      OTP_RECEIVED: "An OTP arrives to log in again.",
      UPI_APP_OPEN: "{They} opens {their} UPI app.",
      BIO_WINDOW: "Touch telemetry sampled: {their} usual rhythm.",
      PAYMENT_ATTEMPT: (e) => `{They} pays ${rupees(e.amount ?? 0)} to a shop {they} has paid before.`,
      PAYMENT_SUCCESS: "Paid, no interruption.",
    },
  },
  {
    id: "investment_task",
    pair: 3,
    title: "Investment / task scam",
    kind: "Scam",
    blurb: "‘Earn daily’ task app, small wins, then bigger deposits",
    summary: "An SMS offers money for ‘rating products’. Small deposits earn small payouts, then the asks grow over days.",
    callers: {},
    payees: { fallback: P("Task Wallet Deposit", "taskwallet.pay@upi") },
    sms: { sender: "+91 63XXX 90114", body: "Part-time job: earn ₹3,000–8,000 daily by rating products from home. Join: earn-daily-tasks.top/j" },
    page: { url: "earn-daily-tasks.top", title: "Earn Daily · Task Center", body: "Complete 30 rating tasks a day. Deposit ₹958 to unlock VIP tasks with 30% commission. 12,481 members paid today!", cta: "Join and deposit", tone: "scam" },
    credit: (a) => `${rupees(a)} credited: ‘task commission’`,
    narration: {
      SMS_RECEIVED: "An SMS from an unknown number: earn money daily by rating products.",
      LINK_CLICK: "{They} opens the link: a ‘task centre’ promising commissions.",
      UPI_APP_OPEN: "{They} opens {their} UPI app to deposit.",
      PAYEE_ADD: "The task centre’s deposit account: a personal account, payee risk 0.67.",
      BIO_WINDOW: "Touch telemetry sampled.",
      PAYMENT_ATTEMPT: (e) => `The first ‘VIP task’ deposit: ${rupees(e.amount ?? 0)}.`,
      CREDIT_RECEIVED: "A small ‘commission’ arrives to build trust.",
    },
  },
  {
    id: "legit_investing",
    pair: 3,
    title: "Legit investing",
    kind: "Genuine",
    blurb: "Registered broker, growing deposits over days",
    summary: "{They} starts a SIP with a registered fund house: growing deposits over days and real returns. The same shape as the scam.",
    callers: {},
    payees: { fallback: P("Kisan Mutual Fund", "kisanmf.sip@upi") },
    sms: { sender: "AX-KISANMF", body: "Start a SIP from ₹500/month in Kisan Mutual Fund. SEBI-registered. Learn more: kisanmf.in/sip" },
    page: { url: "kisanmf.in", title: "Kisan Mutual Fund · SIP", body: "SEBI Reg. No. INM000012345. Mutual fund investments are subject to market risks. Read all scheme documents carefully.", cta: "Start SIP", tone: "legit" },
    credit: (a) => `${rupees(a)} credited: Kisan MF redemption`,
    narration: {
      SMS_RECEIVED: "An SMS from a registered fund house about a SIP.",
      LINK_CLICK: "{They} reads the fund’s site.",
      UPI_APP_OPEN: "{They} opens {their} UPI app.",
      PAYEE_ADD: "{They} adds the fund as a payee: a 4-year-old registered merchant.",
      BIO_WINDOW: "Touch telemetry sampled.",
      PAYMENT_ATTEMPT: (e) => `{They} invests ${rupees(e.amount ?? 0)}.`,
      PAYMENT_SUCCESS: "Invested, no interruption.",
      CREDIT_RECEIVED: "A redemption arrives from the fund.",
    },
  },
];

export const SCENARIO_BY_ID = Object.fromEntries(SCENARIOS.map((s) => [s.id, s])) as Record<ScenarioId, ScriptedScenario>;

export function payeeDisplay(s: Scenario, payeeId?: string) {
  if (payeeId && s.payees[payeeId]) return s.payees[payeeId];
  if (s.id === "custom" && payeeId) return { name: `Payee ${payeeId}`, vpa: `${payeeId.toLowerCase()}@upi`, initials: payeeId.slice(0, 2) };
  return s.payees.fallback;
}

export function narrate(s: Scenario, e: DemoInput, nth: number, p: Persona): string {
  const n = s.narration[e.event];
  return personalise(typeof n === "function" ? n(e, nth) : n ?? "", p);
}

/** Story layer for a session that has none (fleet wall, builder): generic caller IDs and payee names from their ids. */
export function genericScenario(title: string, isScam: boolean, summary: string): Scenario {
  return {
    id: "custom",
    pair: -1,
    title,
    kind: isScam ? "Scam" : "Genuine",
    blurb: summary,
    summary,
    callers: {
      unknown: { id: "Unknown number", detail: "Mobile · Unknown" },
      voip_intl: { id: "Internet call", detail: "Internet call · Unknown" },
      contact: { id: "Contact", detail: "Mobile · Saved contact" },
    },
    payees: { fallback: P("New payee", "payee@upi") },
    narration: {},
  };
}
