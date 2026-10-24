import { signRequest } from "./signing";
import type {
  AuthRequest, AuthResponse, ChallengeOutcome, ChallengeType, EnrollResult, Health, TouchVerifyResult, TypingVerifyResult,
} from "./types";
import type { GestureFeatures } from "./gestures";

export interface ClientOptions {
  /** e.g. https://pramaan.example.in (no trailing slash needed) */
  baseUrl: string;
  /** X-API-Key; server-side only */
  apiKey?: string;
  /** HMAC signing secret; server-side only */
  hmacSecret?: string;
  /** per attempt; the service answers in tens of ms, so a slow answer is better treated as an outage */
  timeoutMs?: number;
  /** extra attempts after a network error, timeout, 429 or 502/503/504 */
  retries?: number;
  /**
   * What authenticate() returns when the service cannot be reached after the retries:
   *   "challenge"  (default) step up with an SMS OTP, so an outage costs friction, not fraud
   *   "allow"      let the payment through (fail open)
   *   "throw"      raise PramaanError and let the caller decide
   */
  fallback?: "challenge" | "allow" | "throw";
  fetch?: typeof fetch;
}

export type ErrorCode = "timeout" | "network" | "rate_limited" | "unauthorized" | "invalid_request" | "not_found" | "server";

export class PramaanError extends Error {
  constructor(
    message: string,
    readonly code: ErrorCode,
    readonly status?: number,
    readonly detail?: unknown,
  ) {
    super(message);
    this.name = "PramaanError";
  }

  get retryable(): boolean {
    return this.code === "timeout" || this.code === "network" || this.code === "rate_limited" ||
      (this.code === "server" && (this.status === 502 || this.status === 503 || this.status === 504));
  }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function newRequestId(): string {
  const c = (globalThis as { crypto?: Crypto }).crypto;
  if (c?.randomUUID) return c.randomUUID().replace(/-/g, "").slice(0, 16);
  return Array.from({ length: 16 }, () => Math.floor(Math.random() * 16).toString(16)).join("");
}

const FALLBACK_COPY: Record<"allow" | "challenge", [string, string]> = {
  challenge: ["Verify with the one-time password sent to your registered number.",
    "अपने पंजीकृत नंबर पर भेजे गए वन-टाइम पासवर्ड से पुष्टि करें।"],
  allow: ["Payment approved.", "भुगतान स्वीकृत।"],
};

/**
 * Typed client for the PRAMAAN API, for Node / server use (a bank backend forwarding what the browser or app SDK
 * collected) and for demo consoles calling the service's open paths. Retries are spaced at least a second apart:
 * the signature covers the timestamp in whole seconds, and the gateway rejects a repeated signature as a replay.
 */
export class PramaanClient {
  private base: string;
  private opts: Required<Pick<ClientOptions, "timeoutMs" | "retries" | "fallback">> & ClientOptions;

  constructor(opts: ClientOptions) {
    this.base = opts.baseUrl.replace(/\/+$/, "");
    this.opts = { timeoutMs: 3000, retries: 1, fallback: "challenge", ...opts };
  }

  /** Decide a login or payment. The request gets a request_id (→ decision_id) if it has none, so retries are
   *  correlated. When the service is unreachable the configured fallback answers, marked `degraded: true`. */
  async authenticate(req: AuthRequest): Promise<AuthResponse> {
    const body = { ...req, request_id: req.request_id ?? newRequestId() };
    try {
      return await this.call<AuthResponse>("POST", "/v1/authenticate", body);
    } catch (e) {
      if (this.opts.fallback === "throw" || !(e instanceof PramaanError) || !e.retryable) throw e;
      return degraded(body, this.opts.fallback);
    }
  }

  /** Report the step-up result: passed → allow (a passkey or bank call-back also trusts the device), failed → block
   *  and a 30-minute lock on further attempts. */
  verifyChallenge(decisionId: string, passed: boolean): Promise<ChallengeOutcome> {
    return this.call("POST", "/v1/challenge/verify", { decision_id: decisionId, passed });
  }

  /** Enrol a typing profile from at least 5 attempts (31 timings each). */
  enrollTyping(userId: string, attempts: number[][]): Promise<EnrollResult> {
    return this.call("POST", "/v1/keystroke/enroll", { user_id: userId, attempts });
  }

  /** Score one attempt against the user's typing profile. */
  verifyTyping(userId: string, attempt: number[]): Promise<TypingVerifyResult> {
    return this.call("POST", "/v1/keystroke/verify", { user_id: userId, attempt });
  }

  /** Enrol a touch profile from at least 20 gestures. */
  enrollTouch(userId: string, gestures: GestureFeatures[]): Promise<EnrollResult> {
    return this.call("POST", "/v1/biometrics/enroll", { user_id: userId, gestures });
  }

  /** Score a window of 10–20 gestures against the user's touch profile. */
  verifyTouch(userId: string, gestures: GestureFeatures[]): Promise<TouchVerifyResult> {
    return this.call("POST", "/v1/biometrics/verify", { user_id: userId, gestures });
  }

  health(): Promise<Health> {
    return this.call("GET", "/health");
  }

  /** The audit feed: latest decisions and challenge results. */
  decisions(limit = 50): Promise<Record<string, unknown>[]> {
    return this.call("GET", `/v1/auth/decisions?limit=${limit}`);
  }

  stats(): Promise<Record<string, unknown>> {
    return this.call("GET", "/v1/auth/stats");
  }

  /** Any endpoint, with the client's auth, signing, timeout and retries. */
  async call<T>(method: "GET" | "POST", path: string, payload?: unknown): Promise<T> {
    const body = payload === undefined ? undefined : JSON.stringify(payload);
    let lastErr: PramaanError | null = null;
    for (let attempt = 0; attempt <= this.opts.retries; attempt++) {
      if (attempt) await sleep(retryDelay(attempt, lastErr));
      try {
        return await this.once<T>(method, path, body);
      } catch (e) {
        if (!(e instanceof PramaanError) || !e.retryable) throw e;
        lastErr = e;
      }
    }
    throw lastErr!;
  }

  private async once<T>(method: string, path: string, body?: string): Promise<T> {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (this.opts.apiKey) headers["X-API-Key"] = this.opts.apiKey;
    if (this.opts.hmacSecret) Object.assign(headers, await signRequest(this.opts.hmacSecret, body ?? ""));
    const ac = new AbortController();
    const timer = setTimeout(() => ac.abort(), this.opts.timeoutMs);
    const f = this.opts.fetch ?? globalThis.fetch;
    let r: Response;
    try {
      r = await f(`${this.base}${path}`, { method, headers, body, signal: ac.signal });
    } catch (e) {
      const timedOut = ac.signal.aborted;
      throw new PramaanError(timedOut ? `${path}: no answer in ${this.opts.timeoutMs} ms` : `${path}: ${(e as Error).message}`,
        timedOut ? "timeout" : "network");
    } finally {
      clearTimeout(timer);
    }
    if (r.ok) return (await r.json()) as T;
    let detail: unknown;
    try {
      detail = await r.json();
    } catch {
      detail = await r.text().catch(() => undefined);
    }
    const msg = `${path}: ${r.status} ${typeof detail === "object" && detail && "detail" in detail ? (detail as { detail: unknown }).detail : ""}`.trim();
    const err = new PramaanError(msg, codeFor(r.status), r.status, detail);
    (err as PramaanError & { retryAfter?: number }).retryAfter = Number(r.headers.get("Retry-After")) || undefined;
    throw err;
  }
}

function codeFor(status: number): ErrorCode {
  if (status === 429) return "rate_limited";
  if (status === 401 || status === 403 || status === 409) return "unauthorized";
  if (status === 404) return "not_found";
  if (status === 400 || status === 422) return "invalid_request";
  return "server";
}

function retryDelay(attempt: number, err: PramaanError | null): number {
  const after = (err as (PramaanError & { retryAfter?: number }) | null)?.retryAfter;
  if (after) return after * 1000;
  return 1000 * 2 ** (attempt - 1) + Math.floor(Math.random() * 250);
}

function degraded(req: AuthRequest & { request_id: string }, mode: "challenge" | "allow"): AuthResponse {
  const [en, hi] = FALLBACK_COPY[mode];
  const challenge: ChallengeType | null = mode === "challenge" ? "sms_otp" : null;
  return {
    decision_id: req.request_id, user_id: req.user_id, decision: mode, risk_score: NaN, challenge_type: challenge,
    rule: "service_unreachable", message_en: en, message_hi: hi, reasons: [],
    family_contribution: { behaviour: 0, device: 0, transaction: 0 }, signals: [], features: {}, expected_cost: {},
    amount: req.transaction?.amount ?? 0, model_version: "fallback", latency_ms: 0, degraded: true,
  };
}
