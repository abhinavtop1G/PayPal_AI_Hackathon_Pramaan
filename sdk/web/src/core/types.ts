/**
 * Shapes of the PRAMAAN API (backend/schemas.py AuthRequest, ml/auth/engine.py responses). Field names are the wire
 * names, so a request built here can be posted as-is.
 */
import type { GestureFeatures } from "./gestures";

export type Platform = "android" | "ios" | "web";
export type Channel = "mobile" | "web";
export type EventType = "payment" | "login";
export type Decision = "allow" | "challenge" | "block";
export type ChallengeType = "sms_otp" | "passkey" | "bank_callback" | "cool_off";
export type Family = "behaviour" | "device" | "transaction";

export interface AuthDevice {
  /** stable per install (the SDK keeps one); the server learns which devices are trusted for each user */
  device_id: string;
  platform?: Platform;
  is_emulator?: boolean;
  is_rooted?: boolean;
  /** a remote-control / screen-mirroring app is running (Android SDK) */
  remote_access_app?: boolean;
  screen_share_active?: boolean;
  /** hours since the SIM in this phone changed; null = unknown */
  sim_change_hours?: number | null;
}

export interface AuthNetwork {
  /** the server reads the client IP from the connection; set only when forwarding from your backend */
  ip?: string | null;
  lat?: number | null;
  lon?: number | null;
  city?: string | null;
}

export interface AuthBehaviour {
  /** the last 10–20 touch gestures, as features (raw coordinates never leave the device) */
  gestures?: GestureFeatures[] | null;
  /** one password / PIN attempt: 31 key timings in seconds (11 keys) */
  keystrokes?: number[] | null;
  time_to_submit_s?: number | null;
  input_events?: number | null;
  unknown_call_active?: boolean;
}

export interface AuthTransaction {
  /** INR; 0 for a login */
  amount?: number;
  payee_id?: string | null;
  payee_is_merchant?: boolean | null;
  payee_risk?: number | null;
}

export interface AuthRequest {
  /** idempotency / correlation id; becomes the decision_id */
  request_id?: string;
  user_id: string;
  /** ISO time; default: when the server receives it */
  ts?: string;
  channel?: Channel;
  event_type?: EventType;
  device: AuthDevice;
  network?: AuthNetwork;
  behaviour?: AuthBehaviour;
  transaction?: AuthTransaction;
}

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
  /** time spent in each stage of the decision (ms) */
  timings_ms?: Record<string, number>;
  /** prior-corrected log-odds before any signal; base + Σ contributions = log-odds of risk_score */
  base_logit?: number;
  /** set by the SDK when the service could not be reached and the configured fallback decided instead */
  degraded?: boolean;
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

export interface TypingVerifyResult {
  user_id: string;
  score: number;
  threshold: number;
  matches_profile: boolean;
  typing_deviation: number;
}

export interface TouchVerifyResult {
  user_id: string;
  window_gestures: number;
  similarity_lstm: number;
  similarity_lda: number;
  fused_score: number;
  threshold_at_eer: number;
  matches_profile: boolean;
  behavioural_deviation: number;
  valid_eer: number;
}

export interface EnrollResult {
  user_id: string;
  enrolled: boolean;
  [k: string]: unknown;
}

export interface Health {
  status: "ok" | "degraded";
  loaded: string[];
  errors: Record<string, string>;
  security: { api_keys: boolean; hmac_signing: boolean; rate_limit_rps: number; mode: string; open_paths: string[] };
  auth: Record<string, unknown> | null;
  [k: string]: unknown;
}
