import type { ChallengeOutcome, DemoRun, Scenario } from "@/types/auth";

export type PayPalStatus = "connected" | "not_configured" | "bad_credentials" | "unreachable";

export interface PayPalScenario extends Scenario {
  amount_inr: number;
  amount: string;
}

export interface PayPalConfig {
  status: PayPalStatus;
  environment: "sandbox";
  client_id: string | null;
  currency: string;
  inr_per_usd: number;
  scenarios: PayPalScenario[];
}

/** open: PayPal may be called · step_up: not until the step-up passes · blocked: never */
export type Gate = "open" | "step_up" | "blocked";

export interface Checkout {
  id: string;
  scenario: string;
  decision_id: string;
  gate: Gate;
  amount: string;
  amount_inr: number;
  currency: string;
  order_id: string | null;
  capture: { id: string; status: string; amount: string; currency: string } | null;
  refund: { id: string; status: string } | null;
}

export interface CheckoutStart {
  checkout: Checkout;
  run: DemoRun;
  order_preview: unknown;
}

export interface CheckoutVerified {
  checkout: Checkout;
  outcome: ChallengeOutcome;
}

export interface CheckoutUpdate {
  checkout: Checkout;
}

export interface OrderCreated extends CheckoutUpdate {
  order_id: string;
}
