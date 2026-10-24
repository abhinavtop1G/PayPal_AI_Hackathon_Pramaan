/**
 * The decision policy of ml/auth/policy.py (AuthPolicy.decide), re-run in the browser over recorded requests. The
 * model's risk for each request stays as the service computed it; only what the policy does with it changes. Outcomes
 * are expected values under the evaluation's assumed efficacies (ml/auth/policy.py EFFICACY, GENUINE_PASS), so the
 * service's own settings and any tuned setting are compared the same way.
 */
import type { ChallengeType, Decision } from "@/types/auth";
import type { AttackType, PolicyConstants, TrafficRow } from "@/types/console";

export interface PolicyParams {
  /** multiplies every step-up's friction cost */
  frictionX: number;
  /** block only at or above this risk */
  blockMinP: number;
  /** value at risk behind a login (no amount) */
  loginExposure: number;
  /** step up the first payment from a never-seen device, however low the risk */
  deviceBinding: boolean;
}

export const defaults = (P: PolicyConstants): PolicyParams => ({
  frictionX: 1, blockMinP: P.block_min_p, loginExposure: P.login_exposure, deviceBinding: true,
});

export function decide(r: TrafficRow, P: PolicyConstants, q: PolicyParams): { d: Decision; c: ChallengeType | null } {
  const p = r.p, A = r.amt > 0 ? r.amt : q.loginExposure;
  const first = r.cc ?? r.c ?? "sms_otp";
  // escalation: a large amount at moderate risk may get a call-back instead, except after a SIM change
  const options: ChallengeType[] = first === "bank_callback" || r.sf ? [first] : [first, "bank_callback"];
  let c = options[0], cc = Infinity;
  for (const o of options) {
    const v = p * A * (1 - P.assumed_efficacy[o]) + (1 - p) * P.friction[o] * q.frictionX;
    if (v < cc) {
      cc = v;
      c = o;
    }
  }
  const cost: Record<Decision, number> = { allow: p * A, challenge: cc, block: p >= q.blockMinP ? (1 - p) * P.block_cost : Infinity };
  let d: Decision = "allow";
  for (const k of ["challenge", "block"] as Decision[]) if (cost[k] < cost[d]) d = k;
  if (r.rule === "recent_failed_challenge") d = "block";
  else if (d === "allow" && r.rule === "emulator_on_hosting_ip") d = "challenge";
  else if (d === "allow" && r.rule === "new_device_binding" && q.deviceBinding) {
    d = "challenge";
    c = first;
  }
  return { d, c: d === "challenge" ? c : null };
}

export interface Outcome {
  genuine: number;
  genuineChallenged: number;
  /** expected: blocked outright, or failed / abandoned the step-up */
  genuineLost: number;
  attacks: number;
  attacksStopped: number;
  money: number;
  moneyStopped: number;
  byAttack: Record<AttackType, { n: number; stopped: number }>;
  mix: Record<ChallengeType, number>;
  /** requests decided exactly as the service decided them (decision and step-up) */
  matches: number;
}

export function evaluate(rows: TrafficRow[], P: PolicyConstants, q: PolicyParams | "otp_always"): Outcome {
  const o: Outcome = {
    genuine: 0, genuineChallenged: 0, genuineLost: 0, attacks: 0, attacksStopped: 0, money: 0, moneyStopped: 0, matches: 0,
    byAttack: { ato_new_device: { n: 0, stopped: 0 }, sim_swap: { n: 0, stopped: 0 }, bot: { n: 0, stopped: 0 },
      remote_access: { n: 0, stopped: 0 }, coerced: { n: 0, stopped: 0 } },
    mix: { sms_otp: 0, passkey: 0, bank_callback: 0, cool_off: 0 },
  };
  for (const r of rows) {
    const { d, c } = q === "otp_always" ? { d: "challenge" as Decision, c: "sms_otp" as ChallengeType } : decide(r, P, q);
    if (d === r.d && c === r.c) o.matches++;
    if (c) o.mix[c]++;
    if (r.atk) {
      const stop = d === "block" ? 1 : d === "challenge" && c ? P.simulated_efficacy[c][r.atk] : 0;
      o.attacks++;
      o.attacksStopped += stop;
      o.money += r.amt;
      o.moneyStopped += stop * r.amt;
      o.byAttack[r.atk].n++;
      o.byAttack[r.atk].stopped += stop;
    } else {
      o.genuine++;
      if (d === "challenge") o.genuineChallenged++;
      o.genuineLost += d === "block" ? 1 : d === "challenge" && c ? 1 - P.genuine_pass[c] : 0;
    }
  }
  return o;
}

/** The same day under friction costs from 0.05× to 20×: where every other setting of this one knob would land. */
export function frontier(rows: TrafficRow[], P: PolicyConstants, q: PolicyParams, n = 28) {
  return Array.from({ length: n }, (_, i) => {
    const frictionX = 0.05 * (400 ** (i / (n - 1)));
    const o = evaluate(rows, P, { ...q, frictionX });
    return { frictionX, friction: (100 * o.genuineChallenged) / Math.max(1, o.genuine), stopped: (100 * o.attacksStopped) / Math.max(1, o.attacks) };
  });
}
