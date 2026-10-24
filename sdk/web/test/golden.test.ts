/** The SDK's on-device math against the training pipeline's own outputs (sdk/spec/make_golden.py). */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { GESTURE_FEATURES, GestureEncoder, type Gesture } from "../src/core/gestures";
import { KeystrokeRecorder, timingsFromKeys } from "../src/core/keystrokes";
import { signRequest } from "../src/core/signing";
import { TouchTracker } from "../src/core/touch";

const golden = JSON.parse(readFileSync(new URL("../../spec/golden.json", import.meta.url), "utf-8"));
const T = golden.touch;
const DOWN = 0, UP = 1;

function feedTracker(tr: TouchTracker) {
  for (const s of T.acc) tr.acc.push(s.t, s.x, s.y, s.z);
  for (const s of T.gyr) tr.gyr.push(s.t, s.x, s.y, s.z);
  for (const f of T.frames) {
    tr.rotated = f.orientation !== 0;
    const s = { pointerId: 0, t: f.t, x: f.x, y: f.y, size: f.size };
    if (f.pointer_count > 1) tr.down({ ...s, pointerId: 1 }); // a second finger lands
    if (f.action === DOWN) tr.down(s);
    else if (f.action === UP) tr.up(s);
    else tr.move(s);
  }
}

describe("touch gestures match ml/models/biometrics/data.py", () => {
  it("uses the model's feature order", () => {
    expect([...GESTURE_FEATURES]).toEqual(T.feature_names);
  });

  it("reproduces every kept gesture, dropping the same ones", () => {
    const tr = new TouchTracker({ screen: T.screen, keep: 20 });
    feedTracker(tr);
    tr.settle(Number.MAX_SAFE_INTEGER, true);
    const got = tr.window();
    expect(got).toHaveLength(T.features.length);
    got.forEach((g, i) => {
      for (const k of GESTURE_FEATURES) {
        const want = T.features[i][k];
        if (want === null) expect(g[k], `${i}.${k}`).toBeNull();
        else expect(g[k], `${i}.${k}`).toBeCloseTo(want, 9);
      }
    });
  });

  it("waits for the 100 ms of motion after a gesture lifts before encoding it", () => {
    const tr = new TouchTracker({ screen: T.screen });
    tr.down({ pointerId: 0, t: 1000, x: 10, y: 10 });
    tr.up({ pointerId: 0, t: 1050, x: 11, y: 11 });
    tr.settle(1100);
    expect(tr.count).toBe(0);
    tr.settle(1150);
    expect(tr.count).toBe(1);
  });

  it("rescales path length to the 1080 px reference screen", () => {
    const g: Gesture = { points: [{ t: 0, x: 0, y: 0 }, { t: 100, x: 15, y: 0 }], ended: true };
    const phone = new GestureEncoder({ width: 1080, height: 1920 }).encode(g)!;
    const tablet = new GestureEncoder({ width: 2160, height: 3840 }).encode(g)!;
    expect(phone.is_tap).toBe(1);
    expect(Math.expm1(tablet.log_path_len!)).toBeCloseTo(7.5, 9);
    expect(tablet.dx).toBeCloseTo(phone.dx! / 2, 12);
  });
});

describe("typing rhythm matches ml/models/keystroke/data.py COLUMNS", () => {
  const K = golden.keystrokes;

  it("lays out the 31 timings in model order", () => {
    expect(timingsFromKeys(K.per_key)).toEqual(K.timings);
  });

  it("recovers the attempt from raw key events (rollover, Shift, auto-repeat)", () => {
    let attempt: number[] | null = null;
    const rec = new KeystrokeRecorder({ onAttempt: (a) => (attempt = a.timings) });
    for (const e of K.events) {
      if (e.type === "down") rec.down(e.code, e.t, !!e.repeat);
      else rec.up(e.code, e.t);
    }
    expect(attempt).toEqual(K.timings);
    expect(rec.lastAttempt?.keys).toBe(11);
  });
});

describe("request signing matches backend/security.py", () => {
  it("produces the gateway's signature for the same body", async () => {
    const S = golden.signing;
    expect(await signRequest(S.secret, S.body, S.timestamp)).toEqual(S.headers);
  });
});
