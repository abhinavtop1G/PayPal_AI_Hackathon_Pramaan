import { type GestureFeatures, type Gesture } from "../core/gestures";
import { KEYSTROKE_KEYS, KeystrokeRecorder, type KeystrokeAttempt } from "../core/keystrokes";
import { TouchTracker } from "../core/touch";
import type { AuthNetwork, AuthRequest, AuthTransaction, EventType } from "../core/types";
import { environment, webDevice, type Environment } from "./device";

export interface PramaanOptions {
  /** element whose touches are observed (default: the whole document); an element is treated as the screen, so
   *  positions are normalised to its box */
  root?: Document | HTMLElement;
  /** observe touch / pen gestures (mouse is ignored: the model was trained on fingers) */
  touch?: boolean;
  /** read the accelerometer and gyroscope around each touch (iOS asks the customer: see requestMotionPermission) */
  motion?: boolean;
  /**
   * The customer agreed to behavioural biometrics (DPDP purpose `behavioural_biometrics`). Without it no touch,
   * motion or typing data is collected; device and session signals still are.
   */
  consent?: boolean;
  /** also accept mouse drags as gestures (demos on a laptop; off in production) */
  mouseAsTouch?: boolean;
  /** gestures kept for the next request; the model reads windows of 10 or 20 */
  keepGestures?: number;
  deviceIdKey?: string;
  onGesture?: (f: GestureFeatures, raw: Gesture) => void;
  onTypingAttempt?: (a: KeystrokeAttempt) => void;
  onTypingReset?: (why: string) => void;
}

export interface CollectOptions {
  userId: string;
  eventType?: EventType;
  transaction?: AuthTransaction;
  network?: AuthNetwork;
  requestId?: string;
}

export interface Snapshot {
  gestures: number;
  typing: KeystrokeAttempt | null;
  inputEvents: number;
  elapsedS: number | null;
  motionSamples: number;
  consent: boolean;
}

const now = () => (typeof performance !== "undefined" ? performance.now() : Date.now());

/**
 * The browser SDK. Observes the page and builds the request PRAMAAN scores:
 *   behaviour  touch gestures (21 features each), one typing attempt (31 timings), time to submit, input count
 *   device     a stable install ID and automation flags
 * Send the result of collect() to your backend, which adds its API key / signature and calls /v1/authenticate.
 *
 *   const pramaan = Pramaan.init({ consent: true });
 *   pramaan.startFlow();                               // the payment screen opened
 *   pramaan.watchTyping(pinInput);                     // typing rhythm on the PIN / password field
 *   const req = await pramaan.collect({ userId, transaction: { amount: 2500, payee_id: "kirana-sharma" } });
 */
export class Pramaan {
  readonly touch: TouchTracker;
  readonly typing: KeystrokeRecorder;
  private opts: PramaanOptions;
  private flowStart: number | null = null;
  private inputs = 0;
  private off: (() => void)[] = [];
  private settleTimer: ReturnType<typeof setInterval> | null = null;

  static init(opts: PramaanOptions = {}): Pramaan {
    return new Pramaan(opts);
  }

  constructor(opts: PramaanOptions = {}) {
    this.opts = { touch: true, motion: true, consent: true, keepGestures: 20, ...opts };
    this.touch = new TouchTracker({ screen: screenPx(), keep: this.opts.keepGestures, onGesture: this.opts.onGesture });
    this.typing = new KeystrokeRecorder({ onAttempt: this.opts.onTypingAttempt, onReset: this.opts.onTypingReset });
    if (typeof window !== "undefined") this.attach();
  }

  /** The screen where the customer starts a payment or login opened: starts the time-to-submit clock. */
  startFlow(): void {
    this.flowStart = now();
    this.inputs = 0;
  }

  setConsent(consent: boolean): void {
    this.opts.consent = consent;
    if (!consent) {
      this.touch.reset();
      this.typing.reset();
    }
  }

  /** Record typing rhythm on a password / PIN field. Returns a function that stops watching. */
  watchTyping(input: HTMLElement): () => void {
    const down = (e: Event) => {
      const k = e as KeyboardEvent;
      if (!this.opts.consent || !k.code || k.isComposing) return; // soft keyboards report no key codes
      this.typing.down(k.code, k.timeStamp, k.repeat);
    };
    const up = (e: Event) => {
      const k = e as KeyboardEvent;
      if (!this.opts.consent || !k.code || k.isComposing) return;
      this.typing.up(k.code, k.timeStamp);
    };
    const paste = () => this.typing.paste();
    const blur = () => this.typing.blur();
    input.addEventListener("keydown", down);
    input.addEventListener("keyup", up);
    input.addEventListener("paste", paste);
    input.addEventListener("blur", blur);
    const stop = () => {
      input.removeEventListener("keydown", down);
      input.removeEventListener("keyup", up);
      input.removeEventListener("paste", paste);
      input.removeEventListener("blur", blur);
    };
    this.off.push(stop);
    return stop;
  }

  /** iOS Safari only gives motion data after the customer allows it, from a tap. Elsewhere resolves true. */
  async requestMotionPermission(): Promise<boolean> {
    const DME = (globalThis as unknown as { DeviceMotionEvent?: { requestPermission?: () => Promise<string> } }).DeviceMotionEvent;
    if (!DME?.requestPermission) return typeof DME !== "undefined";
    try {
      return (await DME.requestPermission()) === "granted";
    } catch {
      return false;
    }
  }

  /** Build the request for /v1/authenticate from what was observed. */
  async collect(o: CollectOptions): Promise<AuthRequest> {
    const attempt = this.opts.consent ? await this.typing.settle() : null;
    this.touch.settle(now(), true);
    const gestures = this.opts.consent && this.touch.count >= 10 ? this.touch.window(Math.min(20, this.touch.count)) : null;
    const elapsed = this.flowStart === null ? null : (now() - this.flowStart) / 1000;
    return {
      ...(o.requestId ? { request_id: o.requestId } : {}),
      user_id: o.userId,
      ts: new Date().toISOString(),
      channel: "web",
      event_type: o.eventType ?? "payment",
      device: webDevice(this.opts.deviceIdKey),
      network: o.network ?? {},
      behaviour: {
        gestures,
        keystrokes: attempt && attempt.keys === KEYSTROKE_KEYS ? attempt.timings : null,
        time_to_submit_s: elapsed === null ? null : Math.round(elapsed * 100) / 100,
        input_events: this.flowStart === null ? null : this.inputs,
        unknown_call_active: false,
      },
      transaction: { amount: 0, ...o.transaction },
    };
  }

  /** What the SDK holds right now (for debugging and demo UIs). */
  snapshot(): Snapshot {
    return {
      gestures: this.touch.count,
      typing: this.typing.lastAttempt,
      inputEvents: this.inputs,
      elapsedS: this.flowStart === null ? null : (now() - this.flowStart) / 1000,
      motionSamples: this.touch.acc.length,
      consent: !!this.opts.consent,
    };
  }

  environment(): Environment {
    return environment();
  }

  destroy(): void {
    this.off.forEach((f) => f());
    this.off = [];
    if (this.settleTimer) clearInterval(this.settleTimer);
    this.settleTimer = null;
  }

  // ------------------------------------------------------------------ DOM wiring
  private attach(): void {
    const root = this.opts.root ?? document;
    const listen = <K extends keyof GlobalEventHandlersEventMap>(target: EventTarget, type: K,
      fn: (e: GlobalEventHandlersEventMap[K]) => void, options?: AddEventListenerOptions) => {
      target.addEventListener(type, fn as EventListener, options);
      this.off.push(() => target.removeEventListener(type, fn as EventListener, options));
    };
    const usable = (e: PointerEvent) => this.opts.touch && this.opts.consent &&
      (e.pointerType === "touch" || e.pointerType === "pen" || (this.opts.mouseAsTouch && e.pointerType === "mouse"));
    // an observed element is the "screen" (a payment widget, a demo pad); the whole document uses the viewport
    const origin = () => (root instanceof HTMLElement ? root.getBoundingClientRect() : { left: 0, top: 0 });
    const sample = (e: PointerEvent) => {
      const dpr = window.devicePixelRatio || 1, o = origin();
      return { pointerId: e.pointerId, t: e.timeStamp, x: (e.clientX - o.left) * dpr, y: (e.clientY - o.top) * dpr, size: null };
    };
    const opts = { passive: true, capture: true };
    listen(root, "pointerdown", (e) => {
      this.inputs++;
      if (!usable(e)) return;
      this.touch.screen = screenPx(root instanceof HTMLElement ? root : undefined);
      this.touch.rotated = rotated();
      this.touch.down(sample(e));
    }, opts);
    listen(root, "pointermove", (e) => usable(e) && this.touch.move(sample(e)), opts);
    listen(root, "pointerup", (e) => usable(e) && this.touch.up(sample(e)), opts);
    listen(root, "pointercancel", (e) => this.touch.cancel(e.pointerId), opts);
    listen(root, "keydown", () => this.inputs++, opts);

    if (this.opts.motion) {
      listen(window, "devicemotion" as keyof GlobalEventHandlersEventMap, ((e: DeviceMotionEvent) => {
        if (!this.opts.consent) return;
        const a = e.accelerationIncludingGravity, r = e.rotationRate;
        if (a && a.x !== null && a.y !== null && a.z !== null) this.touch.acc.push(e.timeStamp, a.x, a.y, a.z);
        if (r && r.alpha !== null && r.beta !== null && r.gamma !== null) {
          const k = Math.PI / 180; // browsers report deg/s; the model was trained on rad/s
          this.touch.gyr.push(e.timeStamp, r.beta * k, r.gamma * k, r.alpha * k);
        }
      }) as unknown as (e: Event) => void, { passive: true });
    }
    // gestures are encoded once their 100 ms of motion context has arrived
    this.settleTimer = setInterval(() => this.touch.settle(now()), 250);
  }
}

function screenPx(el?: HTMLElement) {
  if (typeof window === "undefined") return { width: 1080, height: 1920 };
  const dpr = window.devicePixelRatio || 1;
  const r = el?.getBoundingClientRect();
  const w = r && r.width > 0 ? r.width : window.innerWidth, h = r && r.height > 0 ? r.height : window.innerHeight;
  return { width: Math.max(1, w * dpr), height: Math.max(1, h * dpr) };
}

function rotated(): boolean {
  const o = (globalThis as unknown as { screen?: { orientation?: { angle?: number } } }).screen?.orientation;
  return !!o && typeof o.angle === "number" && o.angle !== 0;
}
