import type { MotionSeries } from "./gestures";

/**
 * A rolling window of sensor magnitudes (accelerometer with gravity, or gyroscope), kept just long enough to give
 * each touch its 100 ms of context before and after. Samples must arrive in time order.
 */
export class MotionBuffer implements MotionSeries {
  t: Float64Array;
  m: Float64Array;
  length = 0;

  constructor(private keepMs = 8000, capacity = 2048) {
    this.t = new Float64Array(capacity);
    this.m = new Float64Array(capacity);
  }

  push(t: number, x: number, y: number, z: number): void {
    if (this.length && t < this.t[this.length - 1]) return; // out of order: drop rather than break the binary search
    if (this.length === this.t.length) this.compact(t);
    if (this.length === this.t.length) this.grow();
    this.t[this.length] = t;
    this.m[this.length] = Math.sqrt(x * x + y * y + z * z);
    this.length++;
  }

  /** Drop samples older than keepMs before `now`. */
  compact(now: number): void {
    let i = 0;
    while (i < this.length && this.t[i] < now - this.keepMs) i++;
    if (!i) return;
    this.t.copyWithin(0, i, this.length);
    this.m.copyWithin(0, i, this.length);
    this.length -= i;
  }

  clear(): void {
    this.length = 0;
  }

  private grow(): void {
    const t = new Float64Array(this.t.length * 2), m = new Float64Array(this.m.length * 2);
    t.set(this.t);
    m.set(this.m);
    this.t = t;
    this.m = m;
  }
}
