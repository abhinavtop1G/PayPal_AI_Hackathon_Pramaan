/** Recorded data the console reads (frontend/public/data, written by backend/record_auth_traffic.py and
 *  backend/export_console_report.py). */
import type { ChallengeType, Decision } from "./auth";

export type AttackType = "ato_new_device" | "sim_swap" | "bot" | "remote_access" | "coerced";

/** One request of the recorded test day. */
export interface TrafficRow {
  /** seconds since midnight of the recorded day (IST) */
  t: number;
  u: string;
  ch: "mobile" | "web";
  ev: "payment" | "login";
  pf: string;
  city: string | null;
  amt: number;
  /** first decision */
  d: Decision;
  c: ChallengeType | null;
  /** final decision after the (simulated) challenge */
  f: "allow" | "block";
  pass: boolean | null;
  p: number;
  ms: number;
  /** ground truth: the attack type, null for a genuine customer */
  atk: AttackType | null;
  /** simulator scenario (genuine kinds: routine, new_phone, travel, big_purchase, web...) */
  kind: string;
  diff: number | null;
  /** behaviour, device, transaction contributions (log-odds) */
  fam: [number, number, number];
  top: [string, number][];
  rule: string | null;
  /** the step-up the policy would choose for this request if it challenged it */
  cc?: ChallengeType;
  /** the SIM changed recently (a bank call-back would reach the new SIM, so it is not an option) */
  sf?: boolean;
}

/** Decision policy parameters (ml/auth/policy.py). */
export interface PolicyConstants {
  /** what the policy assumes each step-up stops */
  assumed_efficacy: Record<ChallengeType, number>;
  /** ₹-equivalent cost of putting a genuine customer through each step-up */
  friction: Record<ChallengeType, number>;
  block_cost: number;
  login_exposure: number;
  block_min_p: number;
  /** what the evaluation simulates each step-up stopping, per attack type (assumptions) */
  simulated_efficacy: Record<ChallengeType, Record<AttackType, number>>;
  genuine_pass: Record<ChallengeType, number>;
}

export interface Traffic {
  meta: {
    about: string;
    day: number;
    date: string;
    seed: number;
    model_version: string;
    requests: number;
    attacks: number;
    attack_types: AttackType[];
    all_attack_types: AttackType[];
    places: Record<string, [number, number]>;
  };
  rows: TrafficRow[];
}

export interface DesignResult {
  genuine_challenged_pct: number;
  genuine_blocked_pct: number;
  attacks_stopped_pct: number;
  attack_money_stopped_pct: number;
  campaigns_with_any_success_pct: number;
  challenge_mix: Record<string, number>;
  attack_requests: number;
  genuine_requests: number;
  /** % of each scenario's requests finally blocked */
  per_scenario: Record<string, number>;
  /** % allowed / challenged / blocked at the first decision */
  first: Record<string, [number, number, number]>;
}

export interface ModelReport {
  auth: {
    data: { users: number; requests: number; attack_requests: number; bio: string; typing: string; seed: number };
    model: { real_prior: number; fit_prior: number; best_iteration: number };
    ranking: Record<string, { roc_auc: number; pr_auc: number }>;
    difficulty: Record<string, { n: number; stopped: number }>;
    importance: [string, number][];
    latency: { n: number; p50_ms: number; p95_ms: number; p99_ms: number; note: string };
    designs: Record<string, DesignResult>;
  };
  http_latency: { what: string; n: number; p50: number; p95: number; p99: number }[];
  keystroke: {
    published: Record<string, number>;
    all_users: Record<string, [number, number]>;
    users: { train: number; valid: number; test: number };
    heldout: Record<string, [number, number]>;
    /** protocol A (enrol sessions 1-4, test 5-8, unseen users): per-user EER [mean, std over seeds] */
    sessions: Record<string, Record<"one_try" | "three_tries", [number, number]>>;
    selected_seed: number;
  };
  touch: Record<"valid" | "test", Record<"n10" | "n20", Record<string, number>>>;
  typing_demo: {
    password: string;
    profile: { mean: number[]; mad: number[]; n: number };
    distances: Record<"normal" | "coerced" | "remote" | "bot", number[]>;
  };
  policy: PolicyConstants;
}
