/**
 * Spring presets, translated from Apple's damping-ratio + response parameters
 * (Designing Fluid Interfaces, WWDC 2018). In Motion, `bounce` ≈ 1 − damping ratio and
 * `visualDuration` ≈ response. Springs start from the current on-screen value, so every
 * animation built on these is interruptible.
 *
 *   default  damping 1.0, response 0.4   – most UI; no overshoot
 *   snappy   damping 1.0, response 0.3   – small controls, highlights
 *   move     damping 1.0, response 0.4   – repositioning (e.g. PiP)
 *   sheet    damping 0.8, response 0.3   – drawers / bottom sheets
 *   momentum damping 0.8, response 0.4   – only after a gesture carried velocity
 */
export const spring = {
  default: { type: "spring", bounce: 0, visualDuration: 0.4 },
  snappy: { type: "spring", bounce: 0, visualDuration: 0.3 },
  move: { type: "spring", bounce: 0, visualDuration: 0.4 },
  sheet: { type: "spring", bounce: 0.2, visualDuration: 0.3 },
  momentum: { type: "spring", bounce: 0.2, visualDuration: 0.4 },
} as const;

/** Reduced-motion replacement: a short cross-fade, no travel, no overshoot. */
export const crossfade = { duration: 0.2, ease: "easeOut" } as const;
