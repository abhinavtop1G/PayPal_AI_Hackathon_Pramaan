"use client";

import { MotionConfig } from "motion/react";
import { spring } from "@/config/motion";

/** App-wide motion defaults: critically damped spring, and honour the OS reduce-motion setting. */
export function MotionProvider({ children }: { children: React.ReactNode }) {
  return (
    <MotionConfig transition={spring.default} reducedMotion="user">
      {children}
    </MotionConfig>
  );
}
