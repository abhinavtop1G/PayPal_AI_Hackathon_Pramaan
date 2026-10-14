"use client";

import { motion } from "motion/react";
import { Eye, MousePointerClick } from "lucide-react";
import type { Scenario } from "@/config/scenarios";
import { spring } from "@/config/motion";

/** The system permission dialog a remote-control app needs: screen access (Android accessibility service). */
export function PermissionScreen({ s }: { s: Scenario }) {
  const name = s.app?.name ?? "This app";
  return (
    <div className="absolute inset-0 flex items-center justify-center bg-black/60 px-7">
      <div className="absolute inset-0 -z-10 bg-[radial-gradient(90%_55%_at_30%_15%,#3b2a6b_0%,transparent_60%),linear-gradient(180deg,#120c24,#05060c)]" />
      <motion.div
        initial={{ scale: 1.08, opacity: 0, filter: "blur(8px)" }}
        animate={{ scale: 1, opacity: 1, filter: "blur(0px)" }}
        transition={spring.default}
        className="squircle w-full overflow-hidden rounded-[1.4rem] bg-[#2c2c2e]/95 text-center backdrop-blur-xl"
      >
        <div className="px-5 pb-4 pt-5">
          <p className="text-headline">{s.app?.permission ?? `Allow ${name} to control your device?`}</p>
          <div className="mt-3 space-y-2 text-left">
            <p className="flex items-start gap-2 text-footnote text-label-secondary">
              <Eye className="mt-0.5 size-4 shrink-0" aria-hidden /> View and read everything on your screen, including OTPs
            </p>
            <p className="flex items-start gap-2 text-footnote text-label-secondary">
              <MousePointerClick className="mt-0.5 size-4 shrink-0" aria-hidden /> Tap, type and perform actions for you
            </p>
          </div>
        </div>
        <div className="grid grid-cols-2 border-t border-separator">
          <span className="border-r border-separator py-3 text-body text-sys-blue">Deny</span>
          <motion.span
            initial={{ backgroundColor: "rgb(255 255 255 / 0)" }}
            animate={{ backgroundColor: ["rgb(255 255 255 / 0)", "rgb(255 255 255 / 0.12)", "rgb(255 255 255 / 0)"] }}
            transition={{ delay: 1.2, duration: 0.5 }}
            className="py-3 text-body font-semibold text-sys-blue"
          >
            Allow
          </motion.span>
        </div>
      </motion.div>
    </div>
  );
}
