/** Shapes of the PRAMAAN authentication API (backend/app.py, ml/auth/engine.py). */
export type Decision = "allow" | "challenge" | "block";
export type ChallengeType = "sms_otp" | "passkey" | "bank_callback" | "cool_off";
export type Family = "behaviour" | "device" | "transaction";

export interface Signal {
  name: string;
  family: Family;
  value: number | null;
  contribution: number;
}

export interface Reason {
  signal: string;
  family: Family;
  text_en: string;
  text_hi: string;
  contribution: number;
}

export interface AuthResponse {
  decision_id: string;
  user_id: string;
  decision: Decision;
  risk_score: number;
  challenge_type: ChallengeType | null;
  rule: string | null;
  message_en: string;
  message_hi: string;
  reasons: Reason[];
  family_contribution: Record<Family, number>;
  signals: Signal[];
  features: Record<string, number | null>;
  expected_cost: Record<string, number | null>;
  amount: number;
  model_version: string;
  latency_ms: number;
  /** ms per stage: touch, typing, payee, features, model, policy (recordings made before this field omit it) */
  timings_ms?: Record<string, number>;
  /** prior-corrected log-odds before any signal; base + Σ contributions = logit(risk_score) */
  base_logit?: number | null;
}

export interface AuthRequestShown {
  user_id: string;
  ts: number;
  channel: "mobile" | "web";
  event_type: "payment" | "login";
  device: {
    device_id: string;
    platform?: string;
    is_emulator?: boolean;
    is_rooted?: boolean;
    remote_access_app?: boolean;
    screen_share_active?: boolean;
    sim_change_hours?: number | null;
  };
  network: { ip?: string; city?: string; lat?: number; lon?: number };
  behaviour: { gestures?: string | null; keystrokes?: string | null; time_to_submit_s?: number; input_events?: number; unknown_call_active?: boolean };
  transaction: { amount: number; payee_id?: string | null; payee_is_merchant?: boolean; payee_risk?: number | null };
}

export interface DemoRun {
  scenario: string;
  title: string;
  story: string;
  is_attack: boolean | null;
  request: AuthRequestShown;
  response: AuthResponse;
}

export interface Scenario {
  id: string;
  title: string;
  story: string;
  is_attack: boolean | null;
}

export interface ChallengeOutcome {
  decision_id: string;
  challenge_type: ChallengeType;
  passed: boolean;
  decision: "allow" | "block";
  device_trusted: boolean;
  message_en: string;
  message_hi: string;
}

export interface FeedRow {
  kind: "decision" | "challenge";
  ts: number;
  decision_id: string;
  user_id: string;
  decision: string;
  risk_score?: number;
  challenge_type?: string | null;
  amount?: number;
  latency_ms?: number;
  reasons?: string[];
  passed?: boolean;
}

export interface AuthStats {
  decisions: number;
  by_decision: Record<string, number>;
  challenge_types: Record<string, number>;
  latency_ms: { p50: number | null; p95: number | null };
  model_version?: string;
  state_backend?: string;
  audit_backend?: string;
  touch_biometrics?: boolean;
}

/** A custom request built in the console (merged into the demo customer's routine payment). */
export interface Overrides {
  device?: Partial<AuthRequestShown["device"]>;
  network?: Partial<AuthRequestShown["network"]>;
  behaviour?: { touch_profile?: "normal" | "coerced" | "remote" | "none"; typing_profile?: "normal" | "remote" | "bot" | "none"; unknown_call_active?: boolean; time_to_submit_s?: number; input_events?: number };
  transaction?: Partial<AuthRequestShown["transaction"]>;
  channel?: "mobile" | "web";
  event_type?: "payment" | "login";
}
