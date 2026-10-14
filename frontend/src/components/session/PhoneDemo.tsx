"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { payeeDisplay } from "@/config/scenarios";
import { spring } from "@/config/motion";
import { useDemo } from "@/context/DemoContext";
import { clock, dateLabel, duration } from "@/utils/format";
import { AlertSheet } from "./AlertSheet";
import { BrowserScreen } from "./BrowserScreen";
import { DynamicIsland } from "./DynamicIsland";
import { IncomingCall } from "./IncomingCall";
import { LockScreen } from "./LockScreen";
import { NotificationBanner } from "./Notifications";
import { PayScreen, PROCESSING_MS } from "./PayScreen";
import { PermissionScreen } from "./PermissionScreen";
import { PhoneFrame, SAFE_AREA } from "./PhoneFrame";
import { UpiHomeScreen } from "./UpiHomeScreen";

const RING_MS = 2000;

/** Screen transitions: apps launch with a zoom; the pay screen pushes in from the right; dialogs fade. */
const SCREEN = {
  lock: { initial: { opacity: 0 }, animate: { opacity: 1, scale: 1, x: 0, filter: "blur(0px)" }, exit: { opacity: 0, scale: 1.06, filter: "blur(8px)" } },
  browser: {
    initial: { opacity: 0, scale: 0.9, filter: "blur(8px)" },
    animate: { opacity: 1, scale: 1, x: 0, filter: "blur(0px)" },
    exit: { opacity: 0, scale: 0.94, filter: "blur(6px)" },
  },
  permission: { initial: { opacity: 0 }, animate: { opacity: 1, scale: 1, x: 0, filter: "blur(0px)" }, exit: { opacity: 0 } },
  home: {
    initial: { opacity: 0, scale: 0.9, filter: "blur(8px)" },
    animate: { opacity: 1, scale: 1, x: 0, filter: "blur(0px)" },
    exit: { opacity: 0.4, x: "-30%" },
  },
  pay: { initial: { x: "100%" }, animate: { x: 0, opacity: 1, scale: 1, filter: "blur(0px)" }, exit: { opacity: 0, x: "100%" } },
} as const;

/**
 * The customer's phone, driven by the replay. Remounted on every restart (keyed by run), so local state such as
 * "the user ended the call" never leaks between runs.
 */
export function PhoneDemo() {
  const { view, scenario, persona, replay, index } = useDemo();
  const [answered, setAnswered] = useState<number | null>(null);
  const [callEnded, setCallEnded] = useState(false);
  const [dialing, setDialing] = useState(false);

  const call = view.call;
  const ringingIdx = call && index === call.startIndex ? call.startIndex : null;
  useEffect(() => {
    if (ringingIdx == null) return;
    const t = setTimeout(() => setAnswered(ringingIdx), RING_MS);
    return () => clearTimeout(t);
  }, [ringingIdx]);
  const ringing = ringingIdx != null && answered !== ringingIdx;
  const caller = call ? scenario.callers[call.kind] ?? { id: "Unknown", detail: "Unknown caller" } : null;

  const decision = view.payment?.decision ?? null;
  const showSheet = !!decision?.notify && decision.action !== "allow" && decision.action !== "monitor";

  const island = dialing
    ? { label: "1930", elapsed: "Calling" }
    : call && caller && !ringing && !callEnded
      ? { label: call.number ?? caller.id, elapsed: duration(view.nowMin - call.startMin) }
      : null;

  // a notification event shows as a banner unless the lock screen is already listing it
  const latestNote = view.notes.at(-1);
  const banner = latestNote && latestNote.index === index && view.screen !== "lock" ? latestNote : null;
  const screen = view.screen;
  const time = clock(replay.start_time, view.nowMin);

  return (
    <PhoneFrame
      time={time}
      tone={screen === "browser" && !showSheet ? "dark" : "light"}
      island={<DynamicIsland call={island} />}
      overlay={
        <>
          <NotificationBanner s={scenario} note={banner} />
          <AnimatePresence>
            {ringing && caller && call && (
              <IncomingCall key={call.startIndex} id={call.number ?? caller.id} detail={caller.detail} video={call.video} reported={call.reported} />
            )}
          </AnimatePresence>
          <AnimatePresence>
            {showSheet && decision && view.payment && (
              <AlertSheet
                key={view.payment.event_index}
                decision={decision}
                amount={view.payment.input.amount ?? 0}
                payee={payeeDisplay(scenario, view.payment.input.payee_id).name}
                delay={PROCESSING_MS / 1000}
                callEnded={callEnded}
                hasCall={!!call || callEnded}
                onEndCall={() => setCallEnded(true)}
                onCall={() => {
                  setCallEnded(true);
                  setDialing(true);
                }}
              />
            )}
          </AnimatePresence>
        </>
      }
    >
      {/* the app recedes slightly behind a modal sheet, like a UIKit page sheet */}
      <motion.div
        className="absolute inset-0 origin-top overflow-hidden"
        animate={showSheet ? { scale: 0.93, borderRadius: 28, opacity: 0.7 } : { scale: 1, borderRadius: 0, opacity: 1 }}
        transition={{ ...spring.default, delay: showSheet ? PROCESSING_MS / 1000 : 0 }}
      >
        <AnimatePresence initial={false} mode="popLayout">
          <motion.div
            key={screen === "pay" ? `pay-${view.payee?.payee_id}` : screen}
            className="absolute inset-0"
            initial={SCREEN[screen].initial}
            animate={SCREEN[screen].animate}
            exit={SCREEN[screen].exit}
            transition={spring.default}
          >
            {screen === "lock" && <LockScreen time={time} date={dateLabel(replay.start_time, view.nowMin)} notes={view.notes} s={scenario} />}
            {screen === "browser" && <BrowserScreen s={scenario} />}
            {screen === "permission" && <PermissionScreen s={scenario} />}
            {screen === "home" && (
              <div className={`h-full bg-bg ${SAFE_AREA}`}>
                <UpiHomeScreen name={persona.name} initials={persona.initials} balanceChecks={view.balanceChecks} />
              </div>
            )}
            {screen === "pay" && view.payee && (
              <div className={`h-full bg-bg ${SAFE_AREA}`}>
                <PayScreen
                  payee={view.payee}
                  display={payeeDisplay(scenario, view.payee.payee_id)}
                  payment={view.payment}
                  paid={view.paid}
                />
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </motion.div>
    </PhoneFrame>
  );
}
