import type { DemoInput, DemoReplay, TimelineEntry } from "@/types/demo";

export interface CallState {
  kind: NonNullable<DemoInput["caller_kind"]>;
  video: boolean;
  startIndex: number;
  startMin: number;
  number?: string;
  /** telecom PSI: true = reported to 1930, false = not reported, null = not checked (no consent / no number) */
  reported: boolean | null;
}

export type TouchVerdict = NonNullable<NonNullable<TimelineEntry["signals"]>["touch"]>;

export type Screen = "lock" | "browser" | "permission" | "home" | "pay";

/** A phone notification raised by an event (SMS, OTP, app install, money credited). */
export interface Note {
  index: number;
  kind: "sms" | "otp" | "install" | "credit";
  min: number;
  input: DemoInput;
}

/** Everything the phone and console show at replay position `index` (−1 = before the first event). */
export interface SessionView {
  seen: TimelineEntry[];
  current: TimelineEntry | null;
  call: CallState | null;
  screen: Screen;
  notes: Note[];
  /** device context the server tracks, mirrored for display */
  sideloaded: boolean;
  accessibility: boolean;
  appInstalled: boolean;
  balanceChecks: number;
  /** the real biometrics model's verdict on the latest touch window (null before any / without gestures) */
  touch: (TouchVerdict & { index: number }) | null;
  /** the payee on the pay screen: from PAYEE_ADD, or from the payment itself for known payees */
  payee: DemoInput | null;
  /** the latest payment attempt (with its engine decision) on the current pay screen */
  payment: TimelineEntry | null;
  paid: boolean;
  /** the latest payment decision anywhere in the session so far */
  lastDecision: TimelineEntry | null;
  decisions: TimelineEntry[];
  nowMin: number;
}

/**
 * Where the replay stops. For a scam, the first hold is the end of the story: the payment was stopped, so the later
 * attempts in the simulator log (which assume the victim got through) never happen. Genuine sessions play to the end.
 */
export function stopIndex(r: DemoReplay) {
  const held = r.timeline.findIndex((e) => e.decision?.notify && e.decision.action === "hold");
  return held >= 0 ? held : r.timeline.length - 1;
}

export function deriveView(r: DemoReplay, index: number): SessionView {
  const seen = r.timeline.slice(0, index + 1);
  const v: SessionView = {
    seen,
    current: seen.at(-1) ?? null,
    call: null,
    screen: "lock",
    notes: [],
    sideloaded: false,
    accessibility: false,
    appInstalled: false,
    balanceChecks: 0,
    touch: null,
    payee: null,
    payment: null,
    paid: false,
    lastDecision: null,
    decisions: [],
    nowMin: seen.at(-1)?.ts_min ?? 0,
  };
  seen.forEach((e, i) => {
    const x = e.input;
    switch (x.event) {
      case "CALL_START":
        v.call = {
          kind: x.caller_kind ?? "unknown",
          video: !!x.call_video,
          startIndex: i,
          startMin: e.ts_min,
          number: x.caller_number,
          reported: e.signals?.caller_reported ?? null,
        };
        break;
      case "CALL_END":
        v.call = null;
        break;
      case "SMS_RECEIVED":
        v.notes.push({ index: i, kind: "sms", min: e.ts_min, input: x });
        break;
      case "OTP_RECEIVED":
        v.notes.push({ index: i, kind: "otp", min: e.ts_min, input: x });
        break;
      case "CREDIT_RECEIVED":
        v.notes.push({ index: i, kind: "credit", min: e.ts_min, input: x });
        break;
      case "LINK_CLICK":
        v.screen = "browser";
        break;
      case "APP_INSTALL":
        v.appInstalled = true;
        v.sideloaded ||= x.app_source === "sideload";
        v.notes.push({ index: i, kind: "install", min: e.ts_min, input: x });
        v.screen = "lock";
        break;
      case "ACCESSIBILITY_GRANT":
        v.accessibility = true;
        v.screen = "permission";
        break;
      case "UPI_APP_OPEN":
        v.screen = "home";
        v.payee = null;
        v.payment = null;
        v.paid = false;
        break;
      case "BALANCE_CHECK":
        v.balanceChecks += 1;
        break;
      case "BIO_WINDOW":
        if (e.signals?.touch) v.touch = { ...e.signals.touch, index: i };
        break;
      case "PAYEE_ADD":
        v.screen = "pay";
        v.payee = x;
        v.payment = null;
        v.paid = false;
        break;
      case "PAYMENT_ATTEMPT":
        v.screen = "pay";
        if (!v.payee || v.payee.payee_id !== x.payee_id) v.payee = x;
        v.payment = e;
        v.paid = false;
        break;
      case "PAYMENT_SUCCESS":
        v.paid = true;
        break;
    }
    if (e.decision) {
      v.lastDecision = e;
      v.decisions.push(e);
    }
  });
  return v;
}

/** How many times this event type has already happened before position `index`. */
export function nthOfType(r: DemoReplay, index: number) {
  const t = r.timeline[index]?.event;
  return r.timeline.slice(0, index).filter((e) => e.event === t).length;
}

/**
 * What the session would have cost without the hold: every payment attempt from the held one onwards in the
 * simulator log (the victim keeps paying), minus any "returns" the scammer credited back in that stretch.
 */
export function counterfactual(r: DemoReplay) {
  const held = r.timeline.findIndex((e) => e.decision?.notify && e.decision.action === "hold");
  if (held < 0) {
    const paid = r.timeline.filter((e) => e.event === "PAYMENT_ATTEMPT");
    return { held: false as const, payments: paid.length, amount: paid.reduce((s, e) => s + (e.input.amount ?? 0), 0) };
  }
  const after = r.timeline.slice(held);
  const attempts = after.filter((e) => e.event === "PAYMENT_ATTEMPT");
  const credits = after.filter((e) => e.event === "CREDIT_RECEIVED");
  const blocked = attempts.reduce((s, e) => s + (e.input.amount ?? 0), 0);
  const returned = credits.reduce((s, e) => s + (e.input.amount ?? 0), 0);
  return { held: true as const, payments: attempts.length, amount: blocked, returned, net: blocked - returned };
}

/** Share of seen events where the model's stage matches the simulator's ground-truth stage. */
export function stageAgreement(seen: TimelineEntry[]) {
  if (!seen.length) return null;
  return seen.filter((e) => e.workflow.stage === e.true_stage).length / seen.length;
}
