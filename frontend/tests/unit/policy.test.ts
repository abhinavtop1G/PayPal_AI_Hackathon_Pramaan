/** The policy tuner's port of ml/auth/policy.py must make the service's own decisions on the recorded day. */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { decide, defaults, evaluate, frontier } from "../../src/components/policy/simulate";
import type { ModelReport, Traffic } from "../../src/types/console";

const traffic = JSON.parse(readFileSync(new URL("../../public/data/auth_traffic.json", import.meta.url), "utf-8")) as Traffic;
const report = JSON.parse(readFileSync(new URL("../../public/data/model_report.json", import.meta.url), "utf-8")) as ModelReport;
const P = report.policy, rows = traffic.rows, base = defaults(P);

describe("policy tuner", () => {
  it("reproduces every recorded decision and step-up at the service's setting", () => {
    const off = rows.filter((r) => {
      const d = decide(r, P, base);
      return d.d !== r.d || d.c !== r.c;
    });
    expect(off).toEqual([]);
    expect(evaluate(rows, P, base).matches).toBe(rows.length);
  });

  it("challenges fewer genuine customers as a step-up gets dearer", () => {
    const cheap = evaluate(rows, P, { ...base, frictionX: 0.1 }), dear = evaluate(rows, P, { ...base, frictionX: 10 });
    expect(dear.genuineChallenged).toBeLessThan(cheap.genuineChallenged);
    expect(dear.attacksStopped).toBeLessThanOrEqual(cheap.attacksStopped);
    const f = frontier(rows, P, base);
    for (let i = 1; i < f.length; i++) expect(f[i].friction).toBeLessThanOrEqual(f[i - 1].friction + 1e-9);
  });

  it("never blocks below the block threshold, and device binding steps up new devices", () => {
    const strict = { ...base, blockMinP: 0.9 };
    for (const r of rows) if (r.p < 0.9 && r.rule !== "recent_failed_challenge") expect(decide(r, P, strict).d).not.toBe("block");
    const bound = rows.filter((r) => r.rule === "new_device_binding");
    expect(bound.length).toBeGreaterThan(0);
    for (const r of bound) expect(decide(r, P, { ...base, deviceBinding: false }).d).toBe("allow");
  });

  it("an SMS OTP on every payment stops no SIM swap", () => {
    const otp = evaluate(rows, P, "otp_always");
    expect(otp.genuineChallenged).toBe(otp.genuine);
    expect(otp.byAttack.sim_swap.stopped).toBe(0);
  });
});
