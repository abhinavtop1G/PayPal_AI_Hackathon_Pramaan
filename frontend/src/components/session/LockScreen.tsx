"use client";

import { AnimatePresence, motion } from "motion/react";
import type { Scenario } from "@/config/scenarios";
import { spring } from "@/config/motion";
import type { Note } from "@/utils/derive";
import { NotificationCard } from "./Notifications";

/** Lock screen: wallpaper, date, large clock, and the notification stack (newest on top). */
export function LockScreen({ time, date, notes, s }: { time: string; date: string; notes: Note[]; s: Scenario }) {
  const stack = notes.slice(-3).reverse();
  return (
    <div className="absolute inset-0 flex flex-col items-center pb-8 pt-[4.6rem]">
      <div className="absolute inset-0 -z-10 bg-[radial-gradient(90%_55%_at_30%_15%,#3b2a6b_0%,transparent_60%),radial-gradient(80%_60%_at_80%_80%,#0f3a5c_0%,transparent_60%),linear-gradient(180deg,#120c24,#05060c)]" />
      <p className="text-headline text-label/85">{date}</p>
      <p className="text-[5.5rem] font-semibold leading-none tracking-[-0.03em] text-label/95 tabular-nums">{time}</p>

      <div className="mt-auto flex w-full flex-col gap-2 px-3 pb-6">
        <AnimatePresence initial={false}>
          {stack.map((n) => (
            <motion.div
              key={n.index}
              layout
              initial={{ opacity: 0, y: 24, scale: 0.96, filter: "blur(6px)" }}
              animate={{ opacity: 1, y: 0, scale: 1, filter: "blur(0px)" }}
              exit={{ opacity: 0, scale: 0.96 }}
              transition={spring.default}
            >
              <NotificationCard s={s} n={n} />
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
