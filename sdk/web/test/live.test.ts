/**
 * End-to-end against a running service (skipped unless PRAMAAN_API is set):
 *
 *   PRAMAAN_SERVICES=biometrics,keystroke,campaign,auth uvicorn backend.app:app --port 8000
 *   PRAMAAN_API=http://127.0.0.1:8000 npm run test:live
 *
 * With PRAMAAN_SECURED_API (+ PRAMAAN_TEST_KEY, PRAMAAN_TEST_SECRET) pointing at an instance started with
 * PRAMAAN_API_KEYS / PRAMAAN_HMAC_SECRET, it also checks that signed requests pass the gateway and unsigned ones don't.
 */
import { describe, expect, it } from "vitest";
import { PramaanClient } from "../src/core/client";
import { timingsFromKeys } from "../src/core/keystrokes";
import { TouchTracker } from "../src/core/touch";

const API = process.env.PRAMAAN_API;
const SECURED = process.env.PRAMAAN_SECURED_API;

/** n synthetic finger gestures (swipes and taps with a steady rhythm), encoded by the SDK. */
function gestures(n: number, seed = 1) {
  const tr = new TouchTracker({ screen: { width: 1080, height: 2400 }, keep: n });
  let t = 1000, r = seed;
  const rnd = () => ((r = (r * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < n; i++) {
    for (let k = t - 200; k < t + 600; k += 10) tr.acc.push(k, 0.2 * rnd(), 0.3 * rnd(), 9.7 + 0.2 * rnd());
    const swipe = i % 3 !== 0, steps = swipe ? 12 : 2;
    for (let s = 0; s <= steps; s++) {
      const p = { pointerId: 0, t: t + s * 16, x: 500 + (swipe ? 0 : rnd() * 4), y: 1600 - (swipe ? s * 60 : rnd() * 4), size: 0.022 };
      if (s === 0) tr.down(p); else if (s === steps) tr.up(p); else tr.move(p);
    }
    t += 700 + rnd() * 500;
  }
  tr.settle(Infinity, true);
  return tr.window();
}

/** One 11-key attempt with a personal rhythm (hold, flight) and a little noise. */
function attempt(hold: number, flight: number, noise: number, seed: number) {
  let r = seed;
  const rnd = () => ((r = (r * 48271) % 2147483647) / 2147483647 - 0.5) * 2 * noise;
  let t = 0;
  const keys = Array.from({ length: 11 }, (_, i) => {
    const down = t;
    t += flight * (1 + rnd()) + (i === 5 ? 0.15 : 0);
    return { down: down * 1000, up: (down + hold * (1 + rnd())) * 1000 };
  });
  return timingsFromKeys(keys);
}

describe.skipIf(!API)("live service", () => {
  const c = new PramaanClient({ baseUrl: API ?? "", timeoutMs: 10_000, retries: 0, fallback: "throw" });
  const uid = `sdk-live-${Date.now().toString(36)}`;

  it("is up with the authentication model loaded", async () => {
    const h = await c.health();
    expect(h.loaded).toContain("auth");
  });

  it("scores an SDK-built request: touch and typing reach the models", async () => {
    const r = await c.authenticate({
      user_id: "demo-asha", channel: "mobile", event_type: "payment",
      device: { device_id: "asha-pixel-7", platform: "android" },
      network: { city: "Ludhiana", lat: 30.901, lon: 75.857, ip: "49.36.112.45" },
      behaviour: { gestures: gestures(12), keystrokes: attempt(0.09, 0.2, 0.2, 7), time_to_submit_s: 14, input_events: 30 },
      transaction: { amount: 640, payee_id: "kirana-sharma", payee_is_merchant: true },
    });
    expect(["allow", "challenge", "block"]).toContain(r.decision);
    expect(r.features.bio_dev).not.toBeNull();
    expect(r.features.typing_dev).not.toBeNull();
    expect(r.timings_ms).toBeTruthy();
    const logit = (r.base_logit ?? 0) + r.signals.reduce((s, x) => s + x.contribution, 0);
    expect(1 / (1 + Math.exp(-logit))).toBeCloseTo(r.risk_score, 3);
  });

  it("enrols typing and tells the owner from someone else", async () => {
    const own = Array.from({ length: 8 }, (_, i) => attempt(0.09, 0.2, 0.08, 11 + i));
    expect((await c.enrollTyping(uid, own)).enrolled).toBe(true);
    const me = await c.verifyTyping(uid, attempt(0.09, 0.2, 0.08, 99));
    const other = await c.verifyTyping(uid, attempt(0.16, 0.42, 0.25, 5));
    expect(me.typing_deviation).toBeLessThan(other.typing_deviation);
    expect(other.matches_profile).toBe(false);
  });

  it("enrols touch and verifies a window", async () => {
    expect((await c.enrollTouch(uid, gestures(24, 3))).enrolled).toBe(true);
    const v = await c.verifyTouch(uid, gestures(10, 4));
    expect(v.window_gestures).toBe(10);
    expect(typeof v.behavioural_deviation).toBe("number");
  });

  it("runs the challenge loop", async () => {
    const run = await c.call<{ response: { decision: string; decision_id: string } }>("POST", "/v1/auth/demo/genuine_big_purchase", {});
    expect(run.response.decision).toBe("challenge");
    const out = await c.verifyChallenge(run.response.decision_id, true);
    expect(out.decision).toBe("allow");
  });
});

describe.skipIf(!SECURED)("secured gateway", () => {
  const key = process.env.PRAMAAN_TEST_KEY ?? "", secret = process.env.PRAMAAN_TEST_SECRET ?? "";
  const req = { user_id: "sdk-signed", device: { device_id: "d-signed", platform: "web" as const }, transaction: { amount: 300 } };

  it("accepts a signed request", async () => {
    const c = new PramaanClient({ baseUrl: SECURED ?? "", apiKey: key, hmacSecret: secret, retries: 0, fallback: "throw", timeoutMs: 10_000 });
    expect(["allow", "challenge", "block"]).toContain((await c.authenticate(req)).decision);
  });

  it("rejects a missing key and a wrong signature", async () => {
    const noKey = new PramaanClient({ baseUrl: SECURED ?? "", retries: 0, fallback: "throw" });
    await expect(noKey.authenticate(req)).rejects.toMatchObject({ status: 401 });
    const badSig = new PramaanClient({ baseUrl: SECURED ?? "", apiKey: key, hmacSecret: "wrong", retries: 0, fallback: "throw" });
    await expect(badSig.authenticate(req)).rejects.toMatchObject({ status: 401 });
  });
});
