"use client";

import { AnimatePresence, motion } from "motion/react";
import { SessionBuilder } from "@/components/builder/SessionBuilder";
import { SessionTimeline } from "@/components/charts/SessionTimeline";
import { MuleNetwork } from "@/components/network/MuleNetwork";
import { DevicePane } from "@/components/session/DevicePane";
import { BankWall } from "@/components/wall/BankWall";
import { spring } from "@/config/motion";
import { useDemo } from "@/context/DemoContext";
import { ConsoleShell } from "./ConsoleShell";
import { TopBar } from "./TopBar";
import { Toaster } from "@/components/common/Toaster";

/**
 * Four views under one app bar:
 *   Session      – one customer's phone, the analyst console and the full session timeline
 *   Bank wall    – every session in a 12-hour slice of held-out data, live
 *   Mule network – payee-side campaign cases and their money flow
 *   Try it       – build a session event by event against the live API
 * On large screens the page fits the viewport and panes scroll on their own.
 */
export function AppShell() {
  const { appView } = useDemo();
  return (
    <div className="space-backdrop grid min-h-dvh grid-rows-[auto_1fr] lg:h-dvh">
      <TopBar />
      <Toaster />
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.div
          key={appView}
          initial={{ opacity: 0, filter: "blur(6px)" }}
          animate={{ opacity: 1, filter: "blur(0px)" }}
          exit={{ opacity: 0, filter: "blur(6px)" }}
          transition={spring.default}
          className="min-h-0"
        >
          {appView === "session" && <SessionView />}
          {appView === "wall" && (
            <div className="h-full overflow-y-auto">
              <BankWall />
            </div>
          )}
          {appView === "network" && (
            <div className="h-full overflow-y-auto">
              <MuleNetwork />
            </div>
          )}
          {appView === "builder" && (
            <main className="grid h-full min-h-0 grid-cols-1 lg:grid-cols-[minmax(24rem,2fr)_3fr]">
              <section aria-label="Session builder" className="min-h-0 p-4 sm:p-6 lg:overflow-y-auto lg:border-r lg:border-separator/50">
                <SessionBuilder />
              </section>
              <section aria-label="Analyst console" className="min-h-0 p-4 sm:p-6 lg:overflow-y-auto">
                <ConsoleShell />
              </section>
            </main>
          )}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

function SessionView() {
  return (
    <div className="grid h-full min-h-0 grid-rows-[1fr_auto]">
      <main className="grid min-h-0 grid-cols-1 lg:grid-cols-[minmax(24rem,2fr)_3fr]">
        <section aria-label="Customer device" className="relative min-h-0 overflow-hidden px-4 py-4 sm:px-6 lg:border-r lg:border-separator/50">
          <DevicePane />
        </section>
        <section aria-label="Analyst console" className="min-h-0 p-4 sm:p-6 lg:overflow-y-auto">
          <ConsoleShell />
        </section>
      </main>
      <div className="material-regular border-t border-separator/50">
        <SessionTimeline />
      </div>
    </div>
  );
}
