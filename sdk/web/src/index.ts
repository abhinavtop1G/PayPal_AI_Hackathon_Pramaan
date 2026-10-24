/** @pramaan/web-sdk: browser entry. For your server (API key + signing), import "@pramaan/web-sdk/server". */
export { Pramaan, type PramaanOptions, type CollectOptions, type Snapshot } from "./browser/pramaan";
export { deviceId, webDevice, automationSignals, environment, type Environment } from "./browser/device";
export {
  GESTURE_FEATURES, GestureEncoder, REFERENCE_WIDTH_PX, windowStats,
  type Gesture, type GestureFeatures, type GestureFeatureName, type MotionSeries, type ScreenSize, type TouchPoint,
} from "./core/gestures";
export { MotionBuffer } from "./core/motion";
export { TouchTracker, type PointerSample, type TouchTrackerOptions } from "./core/touch";
export {
  KEYSTROKE_KEYS, KEYSTROKE_TIMINGS, KeystrokeRecorder, manhattanDistance, manhattanProfile, timingsFromKeys,
  type KeyTiming, type KeystrokeAttempt, type ManhattanProfile,
} from "./core/keystrokes";
export { PramaanClient, PramaanError, newRequestId, type ClientOptions, type ErrorCode } from "./core/client";
export * from "./core/types";
