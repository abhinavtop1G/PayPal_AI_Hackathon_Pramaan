import { describe, expect, it, vi } from "vitest";
import { PramaanClient, PramaanError } from "../src/core/client";
import { hmacSha256Hex } from "../src/core/signing";

const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
const fail = (status: number, detail = "x", headers: Record<string, string> = {}) =>
  new Response(JSON.stringify({ detail }), { status, headers: { "Content-Type": "application/json", ...headers } });

const REQ = { user_id: "u1", device: { device_id: "d1" }, transaction: { amount: 500 } };

describe("PramaanClient", () => {
  it("sends the API key and an HMAC signature over the exact body", async () => {
    const fetch = vi.fn(async (_url: string, init: RequestInit) => ok({ decision: "allow", echo: init }));
    const c = new PramaanClient({ baseUrl: "https://api.test/", apiKey: "k1", hmacSecret: "s1", fetch: fetch as never });
    await c.authenticate(REQ);
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("https://api.test/v1/authenticate");
    const h = init.headers as Record<string, string>;
    expect(h["X-API-Key"]).toBe("k1");
    const body = init.body as string;
    expect(JSON.parse(body).request_id).toMatch(/^[0-9a-f]{16}$/);
    expect(h["X-Signature"]).toBe(`sha256=${await hmacSha256Hex("s1", `${h["X-Timestamp"]}.${body}`)}`);
  });

  it("retries a 503 a second later with a fresh signature, keeping the request id", async () => {
    const calls: { body: string; ts: string; sig: string }[] = [];
    const fetch = vi.fn(async (_u: string, init: RequestInit) => {
      const h = init.headers as Record<string, string>;
      calls.push({ body: init.body as string, ts: h["X-Timestamp"], sig: h["X-Signature"] });
      return calls.length === 1 ? fail(503) : ok({ decision: "allow" });
    });
    const c = new PramaanClient({ baseUrl: "https://api.test", hmacSecret: "s", retries: 1, fetch: fetch as never });
    await expect(c.authenticate(REQ)).resolves.toMatchObject({ decision: "allow" });
    expect(calls).toHaveLength(2);
    expect(JSON.parse(calls[0].body).request_id).toBe(JSON.parse(calls[1].body).request_id);
    expect(Number(calls[1].ts)).toBeGreaterThan(Number(calls[0].ts)); // a new second: not rejected as a replay
    expect(calls[1].sig).not.toBe(calls[0].sig);
  });

  it("does not retry a request the service rejected", async () => {
    const fetch = vi.fn(async () => fail(422, "amount must be >= 0"));
    const c = new PramaanClient({ baseUrl: "https://api.test", retries: 3, fetch: fetch as never });
    await expect(c.authenticate(REQ)).rejects.toMatchObject({ code: "invalid_request", status: 422 });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("falls back to an SMS OTP when the service is down (fail safe)", async () => {
    const fetch = vi.fn(async () => {
      throw new TypeError("fetch failed");
    });
    const c = new PramaanClient({ baseUrl: "https://api.test", retries: 0, fetch: fetch as never });
    const r = await c.authenticate({ ...REQ, request_id: "abc" });
    expect(r).toMatchObject({ decision: "challenge", challenge_type: "sms_otp", degraded: true, decision_id: "abc" });
  });

  it("can fail open or throw instead", async () => {
    const fetch = vi.fn(async () => fail(503));
    const open = new PramaanClient({ baseUrl: "https://api.test", retries: 0, fallback: "allow", fetch: fetch as never });
    expect((await open.authenticate(REQ)).decision).toBe("allow");
    const strict = new PramaanClient({ baseUrl: "https://api.test", retries: 0, fallback: "throw", fetch: fetch as never });
    await expect(strict.authenticate(REQ)).rejects.toBeInstanceOf(PramaanError);
  });

  it("times out a slow answer", async () => {
    const fetch = vi.fn((_u: string, init: RequestInit) => new Promise<Response>((_, reject) => {
      init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    }));
    const c = new PramaanClient({ baseUrl: "https://api.test", timeoutMs: 20, retries: 0, fallback: "throw", fetch: fetch as never });
    await expect(c.authenticate(REQ)).rejects.toMatchObject({ code: "timeout" });
  });

  it("honours Retry-After on 429", async () => {
    vi.useFakeTimers();
    try {
      const fetch = vi.fn()
        .mockResolvedValueOnce(fail(429, "rate limit exceeded", { "Retry-After": "2" }))
        .mockResolvedValueOnce(ok({ status: "ok" }));
      const c = new PramaanClient({ baseUrl: "https://api.test", retries: 1, fetch: fetch as never });
      const p = c.health();
      await vi.advanceTimersByTimeAsync(1500);
      expect(fetch).toHaveBeenCalledTimes(1);
      await vi.advanceTimersByTimeAsync(600);
      await expect(p).resolves.toEqual({ status: "ok" });
    } finally {
      vi.useRealTimers();
    }
  });
});
