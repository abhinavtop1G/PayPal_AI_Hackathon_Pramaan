"use client";

import { AnimatePresence, motion } from "motion/react";
import { Phone } from "lucide-react";
import { spring } from "@/config/motion";

/**
 * The Dynamic Island. Idle it is a pill around the camera; during a call it widens into a live activity with a
 * green handset and the call timer (kept narrow enough to clear the status bar). Width and content animate on the same spring, so it reads as one object.
 */
export function DynamicIsland({ call }: { call: { label: string; elapsed: string } | null }) {
  return (
    <motion.div
      initial={false}
      animate={{ width: call ? "10.5rem" : "7.8rem" }}
      transition={spring.default}
      className="relative flex h-[2.3rem] items-center justify-between overflow-hidden rounded-full bg-black px-2.5"
    >
      <AnimatePresence initial={false} mode="popLayout">
        {call && (
          <motion.span
            key="call-left"
            initial={{ opacity: 0, scale: 0.6, filter: "blur(4px)" }}
            animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0, scale: 0.6, filter: "blur(4px)" }}
            className="flex items-center"
            aria-label={`On a call with ${call.label}`}
          >
            <span className="flex size-6 items-center justify-center rounded-full bg-sys-green">
              <Phone className="size-3.5 fill-black text-black" aria-hidden />
            </span>
          </motion.span>
        )}
      </AnimatePresence>
      <span className="ml-auto flex items-center gap-2">
        <AnimatePresence initial={false} mode="popLayout">
          {call && (
            <motion.span
              key="call-right"
              initial={{ opacity: 0, filter: "blur(4px)" }}
              animate={{ opacity: 1, filter: "blur(0px)" }}
              exit={{ opacity: 0, filter: "blur(4px)" }}
              className="text-caption-1 font-semibold tabular-nums text-sys-green"
            >
              {call.elapsed}
            </motion.span>
          )}
        </AnimatePresence>
        <span className="size-[0.7rem] rounded-full bg-[#0d0d1a] shadow-[inset_0_0_2px_rgb(80_80_160/0.6)]" aria-hidden />
      </span>
    </motion.div>
  );
}
