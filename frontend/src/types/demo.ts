/** Shapes of `POST /v1/demo/{typology}` (backend/app.py, backend/session_service.py). */

export type Stage = "none" | "contact" | "pretext" | "isolation" | "extraction";
export type Action = "allow" | "monitor" | "nudge" | "cool_off" | "hold";
export type TierName = "allow" | "nudge" | "cool_off" | "hold";

export type EventType =
  | "CALL_START" | "CALL_END" | "SMS_RECEIVED" | "LINK_CLICK" | "APP_INSTALL" | "ACCESSIBILITY_GRANT"
  | "SCREEN_SHARE_START" | "SCREEN_SHARE_END" | "OTP_RECEIVED" | "UPI_APP_OPEN" | "BALANCE_CHECK"
  | "PAYEE_ADD" | "PAYMENT_ATTEMPT" | "PAYMENT_SUCCESS" | "CREDIT_RECEIVED" | "BIO_WINDOW" | "DEVICE_CHANGE";

/** The raw event as sent to the session pipeline. */
export interface DemoInput {
  event: EventType;
  ts: number;
  caller_kind?: "contact" | "unknown" | "voip_intl";
  call_video?: boolean;
  caller_number?: string;
  /** BIO_WINDOW: how many real gestures the device sent (the gestures themselves are not echoed back) */
  gestures_n?: number;
  /** BIO_WINDOW (outgoing only): the per-gesture feature dicts the real biometrics model scores */
  gestures?: Record<string, number | null>[];
  sms_sender_kind?: "bank_shortcode" | "unknown";
  sms_has_link?: boolean;
  app_source?: "play_store" | "sideload";
  payee_id?: string;
  payee_is_merchant?: boolean;
  payee_is_new?: boolean;
  payee_vpa_age_days?: number;
  payee_mule_score?: number;
  amount?: number;
  bio_pressure?: number;
  bio_swipe_velocity?: number;
  bio_hesitation_ms?: number;
  bio_tap_interval_ms?: number;
  bio_orientation_var?: number;
}

export interface DecisionComponents {
  gru_p: number;
  mule_score: number;
  bio_dev: number;
  log_amt_vs_avg: number;
  payee_is_new: number;
  unknown_call_active: number;
  caller_reported_active?: number;
  payee_known_trusted: number;
}

export interface Decision {
  action: Action;
  notify: boolean;
  fused_risk: number;
  ev_choice: TierName;
  suppressed_by: string | null;
  reasons: string[];
  message_en: string;
  message_hi: string;
  components: DecisionComponents;
}

export interface TimelineEntry {
  ts_min: number;
  true_stage: Stage;
  input: DemoInput;
  event_index: number;
  event: EventType;
  workflow: { p_scam_in_progress: number; stage: Stage; typology_top3: Record<string, number> };
  decision: Decision | null;
  payee?: { source: string; risk: number } | null;
  /** per-event signals computed server-side: telecom PSI result and the real biometrics model's verdict */
  signals?: {
    caller_reported: boolean | null;
    touch: { behavioural_deviation: number; matches_profile: boolean; fused_score: number } | null;
  };
  latency_ms: number;
}

export interface DemoReplay {
  session_id: string;
  typology: string;
  persona?: string;
  is_scam: boolean;
  extraction_ts_min: number | null;
  start_time: string;
  user: { avg_txn_amount: number; age_group: string };
  timeline: TimelineEntry[];
}

// ---------------------------------------------------------------- bank-wide fleet (backend/record_demo.py --only fleet)
export interface FleetSession extends Omit<DemoReplay, "user"> {
  user: { id: string; avg_txn_amount: number; age_group: string };
}

export interface Fleet {
  window: { start: string; hours: number };
  note: string;
  sessions: FleetSession[];
}

// ---------------------------------------------------------------- payee side (/v1/campaign/cases, /graph)
export interface CaseAction {
  action: string;
  label: string;
  needs_human: boolean;
}

export interface Case {
  case_id: string;
  opened_ts: number;
  accounts: string[];
  n_accounts: number;
  n_flagged: number;
  n_victims: number;
  victims_24h: number;
  loss_in: number;
  recoverable: number;
  inflow_24h: number;
  last_victim_ts: number | null;
  risk: number;
  novel: boolean;
  priority: number;
  reasons: string[];
  held_accounts: number;
  summary: { en: string; hi: string; actions: CaseAction[] };
}

export interface GraphNode {
  id: string;
  kind: "account" | "victim" | "exit";
  hop: number;
  risk?: number;
  flagged?: boolean;
  held?: boolean;
  balance?: number;
  victims?: number;
  amount?: number;
}

export interface CaseGraph {
  case_id: string;
  nodes: GraphNode[];
  edges: { src: string; dst: string; amount: number; count: number }[];
  totals: { victims: number; victim_amount: number; exits: number; exit_amount: number; inner_amount: number };
}

export interface CampaignData {
  until_day: number;
  summary: { now_day: number; accounts_tracked: number; flagged: number; watchlist: number; held: number };
  cases: Case[];
  graphs: Record<string, CaseGraph>;
}
