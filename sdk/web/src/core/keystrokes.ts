/**
 * Typing rhythm of one password / PIN attempt, in the layout the keystroke model was trained on
 * (ml/models/keystroke/data.py COLUMNS): for each pair of consecutive keys a→b the hold of a, the down-down latency
 * a→b and the up-down latency a→b (negative when b goes down before a comes up), then the hold of the last key.
 * 11 keys (10 characters + Enter, as in the CMU benchmark) give the 31 timings the service scores.
 *
 * Only timings are kept: which keys were pressed is never recorded, so an attempt reveals nothing about the secret.
 */

/** timings per attempt the deployed model expects (11 keys) */
export const KEYSTROKE_TIMINGS = 31;
export const KEYSTROKE_KEYS = 11;

export interface KeyTiming {
  /** ms */
  down: number;
  up: number;
}

/** 3·(n−1)+1 timings in seconds for n keys, in model order. */
export function timingsFromKeys(keys: readonly KeyTiming[]): number[] {
  const out: number[] = [];
  for (let i = 0; i + 1 < keys.length; i++) {
    const a = keys[i], b = keys[i + 1];
    out.push((a.up - a.down) / 1000, (b.down - a.down) / 1000, (b.down - a.up) / 1000);
  }
  if (keys.length) out.push((keys[keys.length - 1].up - keys[keys.length - 1].down) / 1000);
  return out.map((v) => Math.round(v * 1e6) / 1e6);
}

export interface KeystrokeAttempt {
  /** keys in the attempt, Enter included */
  keys: number;
  /** seconds, model order; send when `keys` = 11 */
  timings: number[];
  /** completed with Enter */
  submitted: boolean;
}

/** Keys that are part of a chord, not keystrokes of their own (CMU counts Shift+R as one keystroke). */
const MODIFIERS = new Set([
  "ShiftLeft", "ShiftRight", "ControlLeft", "ControlRight", "AltLeft", "AltRight", "MetaLeft", "MetaRight",
  "CapsLock", "Fn", "FnLock", "NumLock", "OSLeft", "OSRight",
]);
const SUBMIT = new Set(["Enter", "NumpadEnter"]);
const EDIT = new Set(["Backspace", "Delete"]);
const NAV = new Set(["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "Tab", "Escape"]);

export interface KeystrokeRecorderOptions {
  /** called when Enter is released, with the finished attempt */
  onAttempt?: (a: KeystrokeAttempt) => void;
  /** called when the attempt restarts (correction, paste, focus lost) */
  onReset?: (why: "edit" | "paste" | "blur" | "navigation") => void;
}

/**
 * Records key-down / key-up times on a secret field. A correction (Backspace), a paste or leaving the field starts
 * the attempt over, because a corrected attempt is not comparable with clean enrolment attempts. Auto-repeat events
 * and modifier keys are ignored; keys are matched by physical code, so rollover (overlapping keys) is handled.
 */
export class KeystrokeRecorder {
  private keys: { code: string; down: number; up: number | null }[] = [];
  private last: KeystrokeAttempt | null = null;
  private waiters: ((a: KeystrokeAttempt | null) => void)[] = [];

  constructor(private opts: KeystrokeRecorderOptions = {}) {}

  down(code: string, t: number, repeat = false): void {
    if (repeat || MODIFIERS.has(code)) return;
    if (EDIT.has(code)) return this.restart("edit");
    if (NAV.has(code)) return this.restart("navigation");
    if (this.keys.some((k) => k.code === code && k.up === null)) return; // a second down without an up
    this.keys.push({ code, down: t, up: null });
  }

  up(code: string, t: number): void {
    if (MODIFIERS.has(code)) return;
    for (let i = this.keys.length - 1; i >= 0; i--) {
      if (this.keys[i].code === code && this.keys[i].up === null) {
        this.keys[i].up = t;
        break;
      }
    }
    if (SUBMIT.has(code)) this.finish(true);
  }

  paste(): void {
    this.restart("paste");
  }

  blur(): void {
    if (this.keys.length) this.restart("blur");
  }

  /** The attempt so far, without Enter (e.g. when a button submits instead). */
  current(): KeystrokeAttempt | null {
    if (!this.keys.length || this.keys.some((k) => k.up === null)) return null;
    return { keys: this.keys.length, timings: timingsFromKeys(this.keys as KeyTiming[]), submitted: false };
  }

  /** The last attempt finished with Enter. */
  get lastAttempt(): KeystrokeAttempt | null {
    return this.last;
  }

  /** Resolves with the attempt once Enter comes up, or with what there is after `timeoutMs`
   *  (a form that submits on Enter's key-down calls this before the key-up arrives). */
  settle(timeoutMs = 300): Promise<KeystrokeAttempt | null> {
    const pendingEnter = this.keys.some((k) => SUBMIT.has(k.code) && k.up === null);
    if (!pendingEnter) return Promise.resolve(this.last ?? this.current());
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        this.waiters = this.waiters.filter((w) => w !== done);
        resolve(this.last ?? this.current());
      }, timeoutMs);
      const done = (a: KeystrokeAttempt | null) => {
        clearTimeout(timer);
        resolve(a);
      };
      this.waiters.push(done);
    });
  }

  reset(): void {
    this.keys = [];
    this.last = null;
  }

  private finish(submitted: boolean): void {
    const ok = this.keys.length > 0 && this.keys.every((k) => k.up !== null);
    const a = ok ? { keys: this.keys.length, timings: timingsFromKeys(this.keys as KeyTiming[]), submitted } : null;
    this.keys = [];
    if (a) {
      this.last = a;
      this.opts.onAttempt?.(a);
    }
    const w = this.waiters;
    this.waiters = [];
    w.forEach((f) => f(a));
  }

  private restart(why: "edit" | "paste" | "blur" | "navigation"): void {
    this.keys = [];
    this.opts.onReset?.(why);
  }
}

// ---------------------------------------------------------------------------- on-device preview

/** Scaled-Manhattan profile (Killourhy & Maxion 2009; ml/models/keystroke/protocol.py): per-timing mean and mean
 *  absolute deviation, floored at 5 ms. The service fuses this detector with a 1D-CNN; on the device it is a preview. */
export interface ManhattanProfile {
  mean: number[];
  mad: number[];
  n: number;
}

export function manhattanProfile(attempts: readonly number[][], madFloor = 0.005): ManhattanProfile {
  if (!attempts.length) throw new Error("need at least one attempt");
  const d = attempts[0].length;
  const mean = new Array<number>(d).fill(0), mad = new Array<number>(d).fill(0);
  for (const a of attempts) for (let j = 0; j < d; j++) mean[j] += a[j] / attempts.length;
  for (const a of attempts) for (let j = 0; j < d; j++) mad[j] += Math.abs(a[j] - mean[j]) / attempts.length;
  return { mean, mad: mad.map((m) => Math.max(m, madFloor)), n: attempts.length };
}

/** Per-timing scaled deviations |x − mean| / mad, and their sum (the scaled-Manhattan distance; lower = closer). */
export function manhattanDistance(p: ManhattanProfile, attempt: readonly number[]): { distance: number; perTiming: number[] } {
  const perTiming = attempt.map((x, j) => Math.abs(x - p.mean[j]) / p.mad[j]);
  return { distance: perTiming.reduce((s, v) => s + v, 0), perTiming };
}
