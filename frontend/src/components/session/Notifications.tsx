"use client";

import { AnimatePresence, motion } from "motion/react";
import { Download, IndianRupee, KeyRound, MessageSquare } from "lucide-react";
import type { Scenario } from "@/config/scenarios";
import { spring } from "@/config/motion";
import type { Note } from "@/utils/derive";
import { rupees } from "@/utils/format";

const STYLE = {
  sms: { icon: MessageSquare, tint: "bg-sys-green" },
  otp: { icon: KeyRound, tint: "bg-sys-green" },
  install: { icon: Download, tint: "bg-sys-orange" },
  credit: { icon: IndianRupee, tint: "bg-sys-blue" },
} as const;

/** What a notification says, from the scenario's story layer and the event's own fields. */
export function noteContent(s: Scenario, n: Note) {
  const x = n.input;
  switch (n.kind) {
    case "sms":
      return { app: "Messages", title: s.sms?.sender ?? (x.sms_sender_kind === "bank_shortcode" ? "AX-BANK" : "Unknown"), body: s.sms?.body ?? "New message" };
    case "otp":
      return { app: "Messages", title: s.otp?.sender ?? "OTP", body: s.otp?.body ?? "Your one-time password has arrived." };
    case "install":
      return {
        app: s.app?.name ?? "New app",
        title: x.app_source === "sideload" ? "Installed from a downloaded file" : "Installed from Play Store",
        body: x.app_source === "sideload" ? "Open the app and allow screen access to continue verification." : "Your app is up to date.",
      };
    case "credit":
      return { app: "UPI", title: "Money received", body: s.credit?.(x.amount ?? 0) ?? `${rupees(x.amount ?? 0)} credited` };
  }
}

export function NotificationCard({ s, n, compact }: { s: Scenario; n: Note; compact?: boolean }) {
  const { icon: Icon, tint } = STYLE[n.kind];
  const c = noteContent(s, n);
  return (
    <div className="material-thin squircle flex items-start gap-3 rounded-[1.4rem] p-3.5">
      <span className={`flex size-9 shrink-0 items-center justify-center rounded-[0.6rem] ${tint}`}>
        <Icon className="size-5 text-white" aria-hidden />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline justify-between gap-2">
          <span className="truncate text-footnote font-semibold">{c.title}</span>
          <span className="shrink-0 text-caption-1 text-label-secondary">{c.app}</span>
        </span>
        <span className={`block text-footnote text-label/90 ${compact ? "line-clamp-2" : "line-clamp-3"}`}>{c.body}</span>
      </span>
    </div>
  );
}

/** A banner that drops in from the top while the current event is a notification, then retracts. */
export function NotificationBanner({ s, note }: { s: Scenario; note: Note | null }) {
  return (
    <div className="pointer-events-none absolute inset-x-2 top-[3.2rem] z-[44]">
      <AnimatePresence>
        {note && (
          <motion.div
            key={note.index}
            initial={{ y: -90, opacity: 0, scale: 0.96 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: -90, opacity: 0, scale: 0.96 }}
            transition={spring.default}
          >
            <NotificationCard s={s} n={note} compact />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
