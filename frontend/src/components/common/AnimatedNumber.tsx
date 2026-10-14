"use client";

import { motion, useReducedMotion, useSpring, useTransform } from "motion/react";
import { useEffect } from "react";

/** A number that springs from its current value to the next one (interruptible). Jumps when motion is reduced. */
export function AnimatedNumber({
  value,
  format,
  className,
}: {
  value: number;
  format: (v: number) => string;
  className?: string;
}) {
  const reduce = useReducedMotion();
  const mv = useSpring(value, { bounce: 0, visualDuration: 0.6 });
  useEffect(() => {
    if (reduce) mv.jump(value);
    else mv.set(value);
  }, [value, reduce, mv]);
  const text = useTransform(mv, format);
  return <motion.span className={`tabular-nums ${className ?? ""}`}>{text}</motion.span>;
}
