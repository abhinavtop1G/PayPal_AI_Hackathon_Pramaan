"use client";

import { useEffect, useRef, useState } from "react";

export const DAY_S = 86_400;

/**
 * A compressed clock over one day (seconds since midnight). `speed` is simulated seconds per real second; the clock
 * stops at the end of the day. Runs on requestAnimationFrame (pauses with the tab) and re-renders once per simulated
 * `step` seconds, not every frame.
 */
export function useReplay(start: number, initialSpeed = 300, step = 60) {
  const [clock, setClock] = useState(start);
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState(initialSpeed);
  const exact = useRef(start);
  const last = useRef<number | null>(null);

  useEffect(() => {
    if (!playing) {
      last.current = null;
      return;
    }
    let raf = 0;
    const tick = (t: number) => {
      const dt = last.current === null ? 0 : Math.min(0.25, (t - last.current) / 1000);
      last.current = t;
      const prev = exact.current;
      exact.current = Math.min(DAY_S, prev + dt * speed);
      if (Math.floor(exact.current / step) !== Math.floor(prev / step) || exact.current >= DAY_S) setClock(exact.current);
      if (exact.current >= DAY_S) {
        setPlaying(false);
        return;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed, step]);

  const seek = (s: number) => {
    exact.current = Math.min(DAY_S, Math.max(0, s));
    setClock(exact.current);
  };
  return {
    clock, playing, speed, setSpeed, seek,
    toggle: () => {
      if (exact.current >= DAY_S) seek(0);
      setPlaying((p) => !p);
    },
  };
}

export const hhmm = (s: number) => {
  const m = Math.floor(Math.min(DAY_S - 1, s) / 60);
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
};

/** Number of rows with t <= clock (rows sorted by t). */
export function upTo(ts: ArrayLike<number>, clock: number): number {
  let lo = 0, hi = ts.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (ts[mid] <= clock) lo = mid + 1; else hi = mid;
  }
  return lo;
}
