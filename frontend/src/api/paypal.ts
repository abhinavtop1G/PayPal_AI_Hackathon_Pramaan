import { AUTH_API } from "@/api/auth";
import type { CheckoutStart, CheckoutUpdate, CheckoutVerified, OrderCreated, PayPalConfig } from "@/types/paypal";

/**
 * The PayPal checkout, through this project's own API. The browser never talks to PayPal's REST API and never holds the
 * secret: the server decides, creates and captures. Only the PayPal button (the JS SDK) runs here, with the public client id.
 */
export class CheckoutError extends Error {
  constructor(message: string, readonly status: number, readonly issue?: string, readonly debugId?: string) {
    super(message);
  }
}

async function call<T>(path: string, method: "GET" | "POST" = "POST", body?: unknown): Promise<T> {
  if (!AUTH_API) throw new CheckoutError("The console isn't connected to the API.", 0);
  const r = await fetch(`${AUTH_API}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (r.ok) return (await r.json()) as T;
  const detail = ((await r.json().catch(() => null)) as { detail?: string | { message?: string; issue?: string; debug_id?: string } } | null)?.detail;
  if (typeof detail === "string") throw new CheckoutError(detail, r.status);
  throw new CheckoutError(detail?.message ?? `The API answered ${r.status}.`, r.status, detail?.issue, detail?.debug_id);
}

export const paypalConfig = () => call<PayPalConfig>("/v1/paypal/config", "GET");
export const startCheckout = (scenario: string) => call<CheckoutStart>(`/v1/paypal/checkout/${scenario}`);
export const verifyCheckout = (id: string, passed: boolean) => call<CheckoutVerified>(`/v1/paypal/checkout/${id}/verify`, "POST", { passed });
export const createOrder = (id: string) => call<OrderCreated>(`/v1/paypal/checkout/${id}/order`);
export const captureOrder = (id: string, orderId: string) => call<CheckoutUpdate>(`/v1/paypal/checkout/${id}/capture`, "POST", { order_id: orderId });
export const refundCheckout = (id: string) => call<CheckoutUpdate>(`/v1/paypal/checkout/${id}/refund`);
