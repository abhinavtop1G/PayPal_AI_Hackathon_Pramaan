"use client";

import { motion } from "motion/react";
import { Phone, PhoneOff, ShieldAlert, Video } from "lucide-react";
import { spring } from "@/config/motion";

/**
 * Full-screen incoming call. It materialises (blur + scale + opacity together) and, when answered, collapses
 * up toward the Dynamic Island it came from, so entry and exit share one path.
 */
export function IncomingCall({ id, detail, video, reported }: { id: string; detail: string; video: boolean; reported?: boolean | null }) {
  return (
    <motion.div
      role="alertdialog"
      aria-label={`Incoming call from ${id}`}
      initial={{ opacity: 0, scale: 1.04, filter: "blur(12px)" }}
      animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
      exit={{ opacity: 0, scale: 0.35, y: "-46%", filter: "blur(8px)" }}
      transition={spring.default}
      style={{ transformOrigin: "50% 2%" }}
      className="absolute inset-0 z-40 flex flex-col items-center px-8 pb-14 pt-24"
    >
      {/* dimmed, blurred wallpaper behind the call UI */}
      <div className="absolute inset-0 -z-10 bg-[radial-gradient(120%_70%_at_50%_0%,#2a2f45_0%,#121320_45%,#050507_100%)]" />
      <div className="absolute inset-0 -z-10 backdrop-blur-2xl" />

      <p className="text-subheadline text-label-secondary">{detail}</p>
      <h2 className="mt-1 text-center text-[2.125rem] font-normal leading-[2.5rem] tracking-[-0.02em] tabular-nums">{id}</h2>
      <p className="mt-1 flex items-center gap-1.5 text-subheadline text-label-secondary">
        {video ? <Video className="size-4" aria-hidden /> : <Phone className="size-4" aria-hidden />}
        {video ? "Video call" : "Voice call"}
      </p>
      {reported && (
        <motion.p
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ ...spring.sheet, delay: 0.4 }}
          className="mt-3 flex items-center gap-1.5 rounded-full bg-sys-red/20 px-3 py-1 text-footnote font-semibold text-sys-red"
        >
          <ShieldAlert className="size-4" aria-hidden /> Reported for fraud · telecom check
        </motion.p>
      )}

      <div className="mt-auto flex w-full justify-between px-4">
        <CallButton label="Decline" className="bg-sys-red">
          <PhoneOff className="size-7" aria-hidden />
        </CallButton>
        <CallButton label="Accept" className="bg-sys-green" pulse>
          <Phone className="size-7 fill-white" aria-hidden />
        </CallButton>
      </div>
    </motion.div>
  );
}

function CallButton({
  label,
  className,
  pulse,
  children,
}: {
  label: string;
  className: string;
  pulse?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2">
      <span className={`relative flex size-[4.6rem] items-center justify-center rounded-full text-white ${className}`}>
        {pulse && (
          <motion.span
            aria-hidden
            className="absolute inset-0 rounded-full bg-sys-green"
            initial={{ opacity: 0.5, scale: 1 }}
            animate={{ opacity: 0, scale: 1.5 }}
            transition={{ duration: 1.2, repeat: Infinity, ease: "easeOut" }}
          />
        )}
        <span className="relative">{children}</span>
      </span>
      <span className="text-footnote">{label}</span>
    </div>
  );
}
