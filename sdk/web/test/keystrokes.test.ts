import { describe, expect, it } from "vitest";
import { KeystrokeRecorder, manhattanDistance, manhattanProfile } from "../src/core/keystrokes";

function type(rec: KeystrokeRecorder, codes: string[], start = 0, gap = 120, hold = 80) {
  codes.forEach((c, i) => {
    rec.down(c, start + i * gap);
    rec.up(c, start + i * gap + hold);
  });
}

describe("KeystrokeRecorder", () => {
  it("restarts the attempt on a correction and reports why", () => {
    const resets: string[] = [];
    const rec = new KeystrokeRecorder({ onReset: (w) => resets.push(w) });
    type(rec, ["KeyA", "KeyB"]);
    rec.down("Backspace", 300);
    type(rec, ["KeyA", "KeyB", "Enter"], 1000);
    expect(resets).toEqual(["edit"]);
    expect(rec.lastAttempt?.keys).toBe(3);
  });

  it("treats a paste as no typing", () => {
    const rec = new KeystrokeRecorder();
    type(rec, ["KeyA"]);
    rec.paste();
    expect(rec.current()).toBeNull();
  });

  it("settles when Enter comes up after the form already submitted on key-down", async () => {
    const rec = new KeystrokeRecorder();
    type(rec, ["KeyA", "KeyB"]);
    rec.down("Enter", 500);
    const p = rec.settle(1000);
    rec.up("Enter", 560);
    const a = await p;
    expect(a?.keys).toBe(3);
    expect(a?.timings.at(-1)).toBeCloseTo(0.06, 6);
  });

  it("gives what it has when Enter never comes up", async () => {
    const rec = new KeystrokeRecorder();
    type(rec, ["KeyA", "KeyB"]);
    rec.down("Enter", 500);
    expect(await rec.settle(20)).toBeNull();
  });
});

describe("scaled Manhattan preview (ml/models/keystroke/protocol.py)", () => {
  it("floors the deviation at 5 ms and sums scaled distances", () => {
    const p = manhattanProfile([[0.1, 0.2], [0.1, 0.4]]);
    expect(p.mean).toEqual([0.1, 0.30000000000000004]);
    expect(p.mad[0]).toBe(0.005);
    expect(p.mad[1]).toBeCloseTo(0.1, 12);
    const d = manhattanDistance(p, [0.11, 0.3]);
    expect(d.perTiming[0]).toBeCloseTo(2, 9);
    expect(d.distance).toBeCloseTo(2, 9);
  });
});
