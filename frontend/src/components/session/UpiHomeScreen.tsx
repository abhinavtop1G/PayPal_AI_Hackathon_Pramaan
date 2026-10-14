"use client";

import { AnimatePresence, motion } from "motion/react";
import { ArrowUpRight, Building2, Check, ChevronRight, QrCode, ScanLine, Users, Wallet } from "lucide-react";
import { spring } from "@/config/motion";

/** A generic UPI payments home screen (no real bank or app branding). The balance stays masked until checked. */
export function UpiHomeScreen({
  name,
  initials,
  balanceChecks,
}: {
  name: string;
  initials: string;
  balanceChecks: number;
}) {
  const revealed = balanceChecks > 0;
  return (
    <div className="relative flex h-full flex-col gap-5 overflow-hidden px-5 pb-2 pt-2">
      <header className="flex items-center justify-between">
        <div>
          <p className="text-footnote text-label-secondary">Namaste,</p>
          <h1 className="text-title-2">{name}</h1>
        </div>
        <span className="flex size-10 items-center justify-center rounded-full bg-sys-indigo/25 text-headline text-sys-indigo">
          {initials}
        </span>
      </header>

      <section className="squircle relative overflow-hidden rounded-[var(--radius-card)] bg-gradient-to-br from-[#16233b] to-[#0d1424] p-4 shadow-[inset_0_0.5px_0_rgb(255_255_255/0.12)]">
        <div className="flex items-center justify-between">
          <span className="text-eyebrow text-label-secondary">Savings ··· 4821</span>
          <span className="text-caption-1 text-sys-cyan">UPI ID linked</span>
        </div>
        <p className="mt-3 text-caption-1 text-label-secondary">Available balance</p>
        <div className="relative h-[2.125rem]">
          <AnimatePresence initial={false} mode="popLayout">
            {revealed ? (
              <motion.p
                key="shown"
                initial={{ opacity: 0, filter: "blur(8px)", y: 6 }}
                animate={{ opacity: 1, filter: "blur(0px)", y: 0 }}
                transition={spring.default}
                className="text-title-1 tabular-nums"
              >
                ₹ 2,48,310
              </motion.p>
            ) : (
              <motion.p key="hidden" exit={{ opacity: 0, filter: "blur(8px)" }} className="text-title-1 text-label-tertiary">
                ₹ ••••••
              </motion.p>
            )}
          </AnimatePresence>
        </div>
      </section>

      <section className="grid grid-cols-4 gap-2">
        {[
          { icon: ScanLine, label: "Scan & pay", tint: "text-sys-blue" },
          { icon: Users, label: "Pay contacts", tint: "text-sys-green" },
          { icon: Building2, label: "To bank", tint: "text-sys-orange" },
          { icon: Wallet, label: "Balance", tint: "text-sys-purple" },
        ].map(({ icon: Icon, label, tint }) => (
          <div key={label} className="flex flex-col items-center gap-1.5">
            <span className="squircle flex size-14 items-center justify-center rounded-[1.1rem] bg-bg-secondary">
              <Icon className={`size-6 ${tint}`} strokeWidth={2} aria-hidden />
            </span>
            <span className="text-center text-caption-2 text-label-secondary">{label}</span>
          </div>
        ))}
      </section>

      <section className="min-h-0 flex-1">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="text-headline">Recent</h2>
          <span className="text-subheadline text-sys-blue">See all</span>
        </div>
        <ul className="squircle divide-y divide-separator overflow-hidden rounded-[var(--radius-card)] bg-bg-secondary">
          {[
            { name: "Gurpreet (son)", note: "Yesterday", amt: "₹ 5,000", initials: "GS", hue: "bg-sys-teal/25 text-sys-teal" },
            { name: "Punjab Agro Inputs", note: "2 Mar", amt: "₹ 3,240", initials: "PA", hue: "bg-sys-green/25 text-sys-green" },
            { name: "PSPCL Electricity", note: "28 Feb", amt: "₹ 1,180", initials: "PE", hue: "bg-sys-yellow/25 text-sys-yellow" },
          ].map((p) => (
            <li key={p.name} className="flex items-center gap-3 px-3.5 py-3">
              <span className={`flex size-9 shrink-0 items-center justify-center rounded-full text-footnote font-semibold ${p.hue}`}>
                {p.initials}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-subheadline">{p.name}</span>
                <span className="block text-caption-1 text-label-secondary">{p.note}</span>
              </span>
              <span className="flex items-center gap-1 text-subheadline tabular-nums text-label-secondary">
                <ArrowUpRight className="size-3.5" aria-hidden />
                {p.amt}
              </span>
              <ChevronRight className="size-4 text-label-tertiary" aria-hidden />
            </li>
          ))}
        </ul>
      </section>

      <div className="flex justify-center">
        <span className="flex items-center gap-2 rounded-full bg-sys-blue px-5 py-2.5 text-headline text-white">
          <QrCode className="size-5" aria-hidden />
          Pay
        </span>
      </div>

      {/* HUD toast each time the balance is checked (keyed by count so a repeat check shows again) */}
      <AnimatePresence>
        {balanceChecks > 0 && (
          <motion.div
            key={balanceChecks}
            initial={{ opacity: 0, scale: 0.9, filter: "blur(6px)" }}
            animate={{ opacity: [0, 1, 1, 0], scale: [0.9, 1, 1, 0.96], filter: ["blur(6px)", "blur(0px)", "blur(0px)", "blur(4px)"] }}
            transition={{ duration: 1.8, times: [0, 0.15, 0.8, 1] }}
            className="material-thick squircle pointer-events-none absolute left-1/2 top-[34%] flex -translate-x-1/2 flex-col items-center gap-2 rounded-[1.25rem] px-6 py-4"
          >
            <Check className="size-7 text-sys-green" strokeWidth={2.5} aria-hidden />
            <span className="text-footnote font-semibold">Balance checked</span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
