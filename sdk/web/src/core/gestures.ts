/**
 * Touch-gesture features, computed on the device exactly as the touch-biometrics model was trained
 * (ml/models/biometrics/data.py: extract_gestures + add_motion_features). Only these 21 numbers per gesture leave the
 * device; raw coordinates and sensor streams stay on it. Checked against sdk/spec/golden.json.
 */

export const GESTURE_FEATURES = [
  "log_duration_ms", "log_gap_ms", "size_mean", "size_max",
  "dx", "dy", "log_path_len", "log_speed", "log_n_points", "x0", "y0", "is_tap",
  "acc_mean", "acc_std", "acc_pre", "acc_resist", "gyr_mean", "gyr_std", "gyr_pre", "gyr_resist", "rotated",
] as const;
export type GestureFeatureName = (typeof GESTURE_FEATURES)[number];
/** One gesture as the model sees it; null = not measured on this device (the model treats it as average). */
export type GestureFeatures = Record<GestureFeatureName, number | null>;

/** Width of the HMOG phone the model was trained on. Path lengths are rescaled to it, so a tap (< 20 px of travel)
 *  and a swipe speed mean the same on every screen. */
export const REFERENCE_WIDTH_PX = 1080;
export const TAP_MAX_PATH_PX = 20;
export const MAX_DURATION_MS = 5000;
export const MAX_GAP_MS = 60_000;
/** hand-motion context around a touch: 100 ms before it lands, through 100 ms after it lifts */
export const SENSOR_PRE_MS = 100;
export const SENSOR_POST_MS = 100;

export interface TouchPoint {
  /** ms, monotonic clock shared with the motion samples */
  t: number;
  /** device pixels, origin top-left of the screen */
  x: number;
  y: number;
  /** normalised contact size (Android MotionEvent.getSize); null when the platform has no comparable value */
  size?: number | null;
}

export interface Gesture {
  /** one pointer from DOWN through the first UP */
  points: TouchPoint[];
  /** the screen was not in its natural orientation when the gesture started */
  rotated?: boolean;
  /** another finger touched during the gesture (dropped, as in training) */
  multiTouch?: boolean;
  /** false while the finger is still down or the gesture was cancelled (dropped) */
  ended?: boolean;
}

export interface ScreenSize {
  width: number;
  height: number;
}

/** Sensor magnitudes over time, sorted by time: accelerometer |a| in m/s² with gravity, gyroscope |ω| in rad/s. */
export interface MotionSeries {
  t: ArrayLike<number>;
  m: ArrayLike<number>;
  length: number;
}

const EMPTY: MotionSeries = { t: [], m: [], length: 0 };

function lowerBound(a: ArrayLike<number>, n: number, x: number): number {
  let lo = 0, hi = n;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (a[mid] < x) lo = mid + 1; else hi = mid;
  }
  return lo;
}

function upperBound(a: ArrayLike<number>, n: number, x: number): number {
  let lo = 0, hi = n;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (a[mid] <= x) lo = mid + 1; else hi = mid;
  }
  return lo;
}

/** Mean and population std of the magnitudes in [lo, hi] (both ends inclusive); NaN when too few samples. */
export function windowStats(s: MotionSeries, lo: number, hi: number): [mean: number, std: number] {
  const a = lowerBound(s.t, s.length, lo), b = upperBound(s.t, s.length, hi);
  const n = b - a;
  if (n <= 0) return [NaN, NaN];
  let sum = 0, sq = 0;
  for (let i = a; i < b; i++) {
    sum += s.m[i];
    sq += s.m[i] * s.m[i];
  }
  const mean = sum / n;
  return [mean, n > 1 ? Math.sqrt(Math.max(0, sq / n - mean * mean)) : NaN];
}

const num = (x: number): number | null => (Number.isFinite(x) ? x : null);

function motionFeatures(s: MotionSeries, tDown: number, tUp: number): [number, number, number, number] {
  const [mean, std] = windowStats(s, tDown, tUp + SENSOR_POST_MS);
  const [pre] = windowStats(s, tDown - SENSOR_PRE_MS, tDown);
  return [mean, std, pre, mean - pre];
}

/**
 * Turns finished gestures into features. Keeps the time the previous kept gesture lifted, because `log_gap_ms`
 * is the pause before each gesture; gestures the training pipeline drops (multi-touch, never lifted, held >= 5 s)
 * return null and do not count as the previous gesture.
 */
export class GestureEncoder {
  private lastUp: number | null = null;

  constructor(public screen: ScreenSize) {}

  reset(): void {
    this.lastUp = null;
  }

  encode(g: Gesture, acc: MotionSeries = EMPTY, gyr: MotionSeries = EMPTY): GestureFeatures | null {
    const p = g.points;
    if (!p.length || g.ended === false || g.multiTouch) return null;
    const first = p[0], last = p[p.length - 1];
    const tDown = first.t, tUp = last.t;
    const dur = Math.max(tUp - tDown, 1);
    if (dur >= MAX_DURATION_MS) return null;

    const gap = this.lastUp === null ? MAX_GAP_MS : Math.min(MAX_GAP_MS, Math.max(0, tDown - this.lastUp));
    this.lastUp = tUp;

    const { width: W, height: H } = this.screen;
    let path = 0, sizeSum = 0, sizeMax = -Infinity, sized = 0;
    for (let i = 0; i < p.length; i++) {
      if (i > 0) path += Math.hypot(p[i].x - p[i - 1].x, p[i].y - p[i - 1].y);
      const s = p[i].size;
      if (s !== null && s !== undefined && Number.isFinite(s)) {
        sizeSum += s;
        sizeMax = Math.max(sizeMax, s);
        sized++;
      }
    }
    path *= REFERENCE_WIDTH_PX / W;
    const [am, as, ap, ar] = motionFeatures(acc, tDown, tUp);
    const [gm, gs, gp, gr] = motionFeatures(gyr, tDown, tUp);
    return {
      log_duration_ms: Math.log1p(dur),
      log_gap_ms: Math.log1p(gap),
      size_mean: sized ? sizeSum / sized : null,
      size_max: sized ? sizeMax : null,
      dx: (last.x - first.x) / W,
      dy: (last.y - first.y) / H,
      log_path_len: Math.log1p(path),
      log_speed: Math.log1p((path / dur) * 1000),
      log_n_points: Math.log1p(p.length),
      x0: first.x / W,
      y0: first.y / H,
      is_tap: path < TAP_MAX_PATH_PX ? 1 : 0,
      acc_mean: num(am), acc_std: num(as), acc_pre: num(ap), acc_resist: num(ar),
      gyr_mean: num(gm), gyr_std: num(gs), gyr_pre: num(gp), gyr_resist: num(gr),
      rotated: g.rotated ? 1 : 0,
    };
  }
}
