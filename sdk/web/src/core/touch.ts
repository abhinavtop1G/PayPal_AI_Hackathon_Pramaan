import { GestureEncoder, SENSOR_POST_MS, type Gesture, type GestureFeatures, type ScreenSize, type TouchPoint } from "./gestures";
import { MotionBuffer } from "./motion";

export interface PointerSample extends TouchPoint {
  pointerId: number;
}

export interface TouchTrackerOptions {
  screen: ScreenSize;
  /** gestures kept for the next request (the model reads windows of 10 or 20) */
  keep?: number;
  /** called once a gesture is encoded (100 ms after it lifts, when its motion context is complete) */
  onGesture?: (f: GestureFeatures, raw: Gesture) => void;
}

/**
 * Platform-neutral touch state machine: feed it pointer down / move / up and it keeps the last N gestures as model
 * features. The first pointer is tracked; a second pointer landing during a gesture marks it multi-touch (dropped,
 * like the training data). Motion buffers are filled by the platform layer.
 */
export class TouchTracker {
  readonly acc = new MotionBuffer();
  readonly gyr = new MotionBuffer();
  private encoder: GestureEncoder;
  private active: { id: number; g: Gesture } | null = null;
  private pending: Gesture[] = [];
  private kept: GestureFeatures[] = [];
  private rotatedNow = false;
  private keep: number;
  private onGesture?: TouchTrackerOptions["onGesture"];

  constructor(opts: TouchTrackerOptions) {
    this.encoder = new GestureEncoder(opts.screen);
    this.keep = opts.keep ?? 20;
    this.onGesture = opts.onGesture;
  }

  set screen(s: ScreenSize) {
    this.encoder.screen = s;
  }

  set rotated(r: boolean) {
    this.rotatedNow = r;
  }

  down(s: PointerSample): void {
    if (this.active) {
      if (s.pointerId !== this.active.id) this.active.g.multiTouch = true;
      return;
    }
    this.active = { id: s.pointerId, g: { points: [pt(s)], rotated: this.rotatedNow, ended: false } };
  }

  move(s: PointerSample): void {
    if (this.active && s.pointerId === this.active.id) this.active.g.points.push(pt(s));
  }

  up(s: PointerSample): void {
    if (!this.active || s.pointerId !== this.active.id) return;
    const g = this.active.g;
    g.points.push(pt(s));
    g.ended = true;
    this.active = null;
    this.pending.push(g);
  }

  /** The gesture was interrupted (pointercancel, focus loss): it is dropped, as an unfinished gesture is in training. */
  cancel(pointerId?: number): void {
    if (this.active && (pointerId === undefined || pointerId === this.active.id)) this.active = null;
  }

  /** Encode lifted gestures whose 100 ms of motion context has arrived (or all of them with `force`). */
  settle(now: number, force = false): void {
    while (this.pending.length) {
      const g = this.pending[0];
      if (!force && g.points[g.points.length - 1].t + SENSOR_POST_MS > now) break;
      this.pending.shift();
      const f = this.encoder.encode(g, this.acc, this.gyr);
      if (!f) continue;
      this.kept.push(f);
      if (this.kept.length > this.keep) this.kept.shift();
      this.onGesture?.(f, g);
    }
    this.acc.compact(now);
    this.gyr.compact(now);
  }

  /** The last `n` encoded gestures, oldest first. */
  window(n = this.keep): GestureFeatures[] {
    return this.kept.slice(-n);
  }

  get count(): number {
    return this.kept.length;
  }

  reset(): void {
    this.active = null;
    this.pending = [];
    this.kept = [];
    this.encoder.reset();
    this.acc.clear();
    this.gyr.clear();
  }
}

const pt = (s: PointerSample): TouchPoint => ({ t: s.t, x: s.x, y: s.y, size: s.size ?? null });
