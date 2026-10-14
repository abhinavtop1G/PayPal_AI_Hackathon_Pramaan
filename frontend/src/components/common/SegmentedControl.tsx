"use client";

import { motion } from "motion/react";
import { useId } from "react";
import { spring } from "@/config/motion";

/** iOS segmented control: the selection thumb slides between segments on a critically damped spring. */
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  label,
  size = "regular",
}: {
  options: { value: T; label: React.ReactNode }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
  size?: "regular" | "small";
}) {
  const id = useId();
  const pad = size === "small" ? "px-2.5 py-1 text-caption-1" : "px-3.5 py-1.5 text-footnote";
  return (
    <div role="radiogroup" aria-label={label} className="flex rounded-[0.6rem] bg-fill-tertiary p-0.5">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            role="radio"
            aria-checked={on}
            onClick={() => onChange(o.value)}
            className={`relative flex-1 whitespace-nowrap rounded-[0.5rem] font-medium transition-[color,scale] duration-150 active:scale-[0.97] ${pad} ${
              on ? "text-label" : "text-label-secondary hover:text-label"
            }`}
          >
            {on && (
              <motion.span
                layoutId={`seg-${id}`}
                transition={spring.snappy}
                className="absolute inset-0 rounded-[0.5rem] bg-gray-3 shadow-[0_3px_8px_rgb(0_0_0/0.25),inset_0_0.5px_0_rgb(255_255_255/0.12)]"
              />
            )}
            <span className="relative">{o.label}</span>
          </button>
        );
      })}
    </div>
  );
}
