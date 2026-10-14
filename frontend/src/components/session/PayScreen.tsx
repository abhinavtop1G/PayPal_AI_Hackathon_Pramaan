"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { Check, ChevronLeft, Loader2, ShieldAlert } from "lucide-react";
import { spring } from "@/config/motion";
import type { DemoInput, TimelineEntry } from "@/types/demo";
import { rupees } from "@/utils/format";

export const PROCESSING_MS = 1100;

/**
 * Pay screen: payee, amount, and the payment's state. After a payment attempt it shows "Processing" for a beat
 * (the engine's real latency is ~35 ms; the pause is for the audience), then the outcome.
 */
export function PayScreen({
  payee,
  display,
  payment,
  paid,
}: {
  payee: DemoInput;
  display: { name: string; vpa: string; initials: string };
  payment: TimelineEntry | null;
  paid: boolean;
}) {
  const amount = payment?.input.amount;
  const ageDays = payee.payee_vpa_age_days;
  return (
    <div className="flex h-full flex-col px-5 pb-3 pt-1">
      <header className="flex items-center gap-1 text-sys-blue">
        <ChevronLeft className="size-6" aria-hidden />
        <span className="text-body">Back</span>
        <span className="ml-auto mr-auto -translate-x-6 text-headline text-label">Pay</span>
      </header>

      <div className="mt-6 flex flex-col items-center text-center">
        <span className="flex size-16 items-center justify-center rounded-full bg-sys-orange/20 text-title-3 text-sys-orange">
          {display.initials}
        </span>
        <h2 className="mt-3 text-title-3">{display.name}</h2>
        <p className="text-footnote text-label-secondary">{display.vpa}</p>
        <div className="mt-2 flex flex-wrap justify-center gap-1.5">
          {payee.payee_is_new && <Chip>New payee</Chip>}
          {ageDays != null && <Chip>{ageDays >= 365 ? `Account ${Math.floor(ageDays / 365)} yrs old` : `Account ${Math.round(ageDays)} days old`}</Chip>}
        </div>
      </div>

      <div className="mt-8 flex flex-col items-center">
        <p className={`text-[3.25rem] font-semibold leading-none tracking-[-0.03em] tabular-nums ${amount ? "" : "text-label-tertiary"}`}>
          {amount ? rupees(amount) : "₹0"}
        </p>
        <p className="mt-3 rounded-full bg-fill-tertiary px-3 py-1 text-footnote text-label-secondary">Add a note</p>
      </div>

      <div className="mt-auto">
        {payment ? <PaymentStatus key={payment.event_index} payment={payment} paid={paid} /> : <PayButton label="Pay" />}
      </div>
    </div>
  );
}

function PaymentStatus({ payment, paid }: { payment: TimelineEntry; paid: boolean }) {
  const [resolved, setResolved] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setResolved(true), PROCESSING_MS);
    return () => clearTimeout(t);
  }, []);
  const d = payment.decision;
  const held = resolved && d?.action === "hold";
  const state = !resolved ? "processing" : held ? "held" : paid ? "paid" : "processing";
  return (
    <AnimatePresence mode="popLayout" initial={false}>
      {state === "processing" && (
        <motion.div key="p" exit={{ opacity: 0, scale: 0.96 }}>
          <PayButton label="Processing" busy />
        </motion.div>
      )}
      {state === "held" && (
        <motion.div
          key="h"
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={spring.default}
          className="squircle flex h-[3.25rem] items-center justify-center gap-2 rounded-[0.875rem] bg-sys-red/15 text-headline text-sys-red"
        >
          <ShieldAlert className="size-5" aria-hidden />
          Payment on hold
        </motion.div>
      )}
      {state === "paid" && (
        <motion.div
          key="ok"
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={spring.default}
          className="flex flex-col items-center gap-2"
        >
          <motion.span
            initial={{ scale: 0.4 }}
            animate={{ scale: 1 }}
            transition={spring.sheet}
            className="flex size-14 items-center justify-center rounded-full bg-sys-green"
          >
            <Check className="size-8 text-black" strokeWidth={3} aria-hidden />
          </motion.span>
          <span className="text-headline">Paid {rupees(payment.input.amount ?? 0)}</span>
          <span className="text-caption-1 text-label-secondary">UPI ref 6074 1129 3381</span>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function PayButton({ label, busy }: { label: string; busy?: boolean }) {
  return (
    <span className="squircle flex h-[3.25rem] items-center justify-center gap-2 rounded-[0.875rem] bg-sys-blue text-headline text-white">
      {busy && <Loader2 className="size-5 animate-spin" aria-hidden />}
      {label}
    </span>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return <span className="rounded-full bg-fill-tertiary px-2.5 py-0.5 text-caption-1 text-label-secondary">{children}</span>;
}
