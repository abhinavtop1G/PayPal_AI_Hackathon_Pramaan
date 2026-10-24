// @vitest-environment happy-dom
/** The DOM wiring: pointer and keyboard events on a page become the request the service scores. */
import { afterEach, describe, expect, it } from "vitest";
import { Pramaan } from "../src/browser/pramaan";

function pointer(type: string, x: number, y: number, init: Partial<PointerEventInit> = {}) {
  document.body.dispatchEvent(new PointerEvent(type, { bubbles: true, clientX: x, clientY: y, pointerId: 1, pointerType: "touch", ...init }));
}

function key(el: HTMLElement, type: "keydown" | "keyup", code: string) {
  el.dispatchEvent(new KeyboardEvent(type, { bubbles: true, code, key: code }));
}

let sdk: Pramaan | null = null;
afterEach(() => {
  sdk?.destroy();
  sdk = null;
  localStorage.clear();
});

describe("Pramaan (browser)", () => {
  it("turns finger gestures into a touch window once there are 10", async () => {
    sdk = Pramaan.init({ motion: false });
    sdk.startFlow();
    for (let i = 0; i < 12; i++) {
      pointer("pointerdown", 100 + i, 400);
      pointer("pointermove", 100 + i, 300);
      pointer("pointerup", 100 + i, 200);
    }
    const req = await sdk.collect({ userId: "u1", transaction: { amount: 900, payee_id: "p1" } });
    expect(req.channel).toBe("web");
    expect(req.behaviour?.gestures).toHaveLength(12);
    expect(req.behaviour?.gestures?.[0].log_gap_ms).toBeCloseTo(Math.log1p(60000), 9);
    expect(req.behaviour?.input_events).toBe(12);
    expect(req.transaction).toEqual({ amount: 900, payee_id: "p1" });
  });

  it("ignores the mouse unless asked, and collects nothing without consent", async () => {
    sdk = Pramaan.init({ motion: false });
    for (let i = 0; i < 10; i++) {
      pointer("pointerdown", 10, 10, { pointerType: "mouse" });
      pointer("pointerup", 50, 10, { pointerType: "mouse" });
    }
    expect(sdk.snapshot().gestures).toBe(0);
    sdk.destroy();
    sdk = Pramaan.init({ motion: false, consent: false });
    for (let i = 0; i < 10; i++) {
      pointer("pointerdown", 10, 10);
      pointer("pointerup", 50, 10);
    }
    expect((await sdk.collect({ userId: "u" })).behaviour?.gestures).toBeNull();
  });

  it("reads typing rhythm from a password field and sends it when it has 11 keys", async () => {
    sdk = Pramaan.init({ motion: false });
    const input = document.createElement("input");
    document.body.appendChild(input);
    sdk.watchTyping(input);
    for (const c of ["Period", "KeyT", "KeyI", "KeyE", "Digit5", "KeyR", "KeyO", "KeyA", "KeyN", "KeyL", "Enter"]) {
      key(input, "keydown", c);
      key(input, "keyup", c);
    }
    const req = await sdk.collect({ userId: "u1" });
    expect(req.behaviour?.keystrokes).toHaveLength(31);
  });

  it("treats an observed element as the screen", async () => {
    const pad = document.createElement("div");
    document.body.appendChild(pad);
    pad.getBoundingClientRect = () => ({ left: 100, top: 500, width: 200, height: 400, right: 300, bottom: 900, x: 100, y: 500, toJSON() {} });
    sdk = Pramaan.init({ motion: false, root: pad });
    for (let i = 0; i < 10; i++) {
      pad.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, clientX: 150, clientY: 700, pointerId: 1, pointerType: "touch" }));
      pad.dispatchEvent(new PointerEvent("pointerup", { bubbles: true, clientX: 150, clientY: 600, pointerId: 1, pointerType: "touch" }));
    }
    const g = (await sdk.collect({ userId: "u" })).behaviour!.gestures![0];
    expect(g.x0).toBeCloseTo(0.25, 9);
    expect(g.y0).toBeCloseTo(0.5, 9);
    expect(g.dy).toBeCloseTo(-0.25, 9);
  });

  it("keeps one device id per browser", async () => {
    sdk = Pramaan.init({ motion: false });
    const a = (await sdk.collect({ userId: "u" })).device.device_id;
    const b = (await sdk.collect({ userId: "u" })).device.device_id;
    expect(a).toMatch(/^web-/);
    expect(a).toBe(b);
  });
});
