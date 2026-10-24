// @vitest-environment happy-dom
/** The drop-in step-up screens: each challenge type's interaction, and the outcome it resolves with. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { showChallenge } from "../src/browser/challenge";
import type { AuthResponse, ChallengeType } from "../src/core/types";

const decision = (c: ChallengeType): AuthResponse => ({
  decision_id: "d1", user_id: "u1", decision: "challenge", risk_score: 0.02, challenge_type: c, rule: null,
  message_en: "Please confirm this payment.", message_hi: "कृपया इस भुगतान की पुष्टि करें।", reasons: [],
  family_contribution: { behaviour: 0, device: 0, transaction: 0 }, signals: [], features: {}, expected_cost: {},
  amount: 500, model_version: "t", latency_ms: 1,
});

const button = (text: string) => [...document.querySelectorAll("button")].find((b) => b.textContent === text) as HTMLButtonElement;
const type = (input: HTMLInputElement, v: string) => {
  input.value = v;
  input.dispatchEvent(new Event("input", { bubbles: true }));
};
const tick = () => new Promise((r) => setTimeout(r, 0));

afterEach(() => {
  document.body.innerHTML = "";
});

describe("showChallenge", () => {
  it("OTP: a wrong code costs an attempt, the right one passes", async () => {
    const verifyOtp = vi.fn(async (c: string) => c === "123456");
    const p = showChallenge(document.body, decision("sms_otp"), { verifyOtp });
    const input = document.querySelector("input")!;
    type(input, "11ab1111");
    expect(input.value).toBe("111111");
    button("Verify").click();
    await tick();
    expect(document.body.textContent).toContain("Attempts left: 2");
    type(input, "123456");
    button("Verify").click();
    await expect(p).resolves.toEqual({ passed: true, challenge: "sms_otp", cancelled: false });
    expect(document.querySelector(".pramaan-ch")).toBeNull();
  });

  it("OTP: running out of attempts fails it", async () => {
    const p = showChallenge(document.body, decision("sms_otp"), { verifyOtp: async () => false, otpAttempts: 1 });
    type(document.querySelector("input")!, "000000");
    button("Verify").click();
    await expect(p).resolves.toMatchObject({ passed: false, cancelled: false });
  });

  it("passkey: resolves with the WebAuthn handler's result", async () => {
    const p = showChallenge(document.body, decision("passkey"), { passkey: async () => true });
    button("Approve").click();
    await expect(p).resolves.toMatchObject({ passed: true, challenge: "passkey" });
  });

  it("bank call-back: waits for the bank's outcome", async () => {
    let finish!: (ok: boolean) => void;
    const p = showChallenge(document.body, decision("bank_callback"), { outOfBand: () => new Promise((r) => (finish = r)) });
    expect(document.body.textContent).toContain("Your bank will call you");
    finish(false);
    await expect(p).resolves.toMatchObject({ passed: false, challenge: "bank_callback", cancelled: false });
  });

  it("cool-off: shows the scam warning in Hindi and lets the payment continue once the wait is over", async () => {
    const p = showChallenge(document.body, decision("cool_off"), { lang: "hi", coolOffSeconds: 0 });
    expect(document.body.textContent).toContain("1930");
    expect(document.body.textContent).toContain("कृपया इस भुगतान");
    const go = button("भुगतान जारी रखें");
    expect(go.disabled).toBe(false);
    go.click();
    await expect(p).resolves.toMatchObject({ passed: true, challenge: "cool_off" });
  });

  it("closes when its signal aborts", async () => {
    const ac = new AbortController();
    const p = showChallenge(document.body, decision("sms_otp"), {}, { inline: true, signal: ac.signal });
    expect(document.querySelector(".pramaan-ch[data-inline]")).not.toBeNull();
    ac.abort();
    await expect(p).resolves.toMatchObject({ passed: false, cancelled: true });
    expect(document.querySelector(".pramaan-ch")).toBeNull();
    await expect(showChallenge(document.body, decision("passkey"), {}, { signal: ac.signal })).resolves.toMatchObject({ cancelled: true });
    expect(document.querySelector(".pramaan-ch")).toBeNull();
  });

  it("Escape cancels", async () => {
    const p = showChallenge(document.body, decision("cool_off"), { coolOffSeconds: 60 });
    expect(button("Continue payment").disabled).toBe(true);
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await expect(p).resolves.toEqual({ passed: false, challenge: "cool_off", cancelled: true });
  });
});
