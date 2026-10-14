"use client";

import { AnimatePresence, motion } from "motion/react";
import { useSyncExternalStore } from "react";
import { CheckCircle2, Info, ShieldAlert } from "lucide-react";
import { spring } from "@/config/motion";

type Tone = "ok" | "info" | "alert";
interface Toast {
  id: number;
  text: string;
  tone: Tone;
}

// tiny external store: any component can call toast(); <Toaster/> renders the stack
let toasts: Toast[] = [];
let seq = 0;
const subs = new Set<() => void>();
const emit = () => subs.forEach((f) => f());

/** Show a short confirmation at the bottom centre; it leaves by itself after a few seconds. */
export function toast(text: string, tone: Tone = "ok") {
  const id = ++seq;
  toasts = [...toasts.slice(-2), { id, text, tone }];
  emit();
  setTimeout(() => {
    toasts = toasts.filter((t) => t.id !== id);
    emit();
  }, 3200);
}

const ICON = { ok: CheckCircle2, info: Info, alert: ShieldAlert };
const COLOR = { ok: "var(--color-sys-green)", info: "var(--color-sys-blue)", alert: "var(--color-sys-red)" };

export function Toaster() {
  const list = useSyncExternalStore(
    (f) => {
      subs.add(f);
      return () => subs.delete(f);
    },
    () => toasts,
    () => toasts,
  );
  return (
    <div className="pointer-events-none fixed inset-x-0 top-[4.75rem] z-[100] flex flex-col items-center gap-2" aria-live="polite">
      <AnimatePresence initial={false}>
        {list.map((t) => {
          const Icon = ICON[t.tone];
          return (
            <motion.div
              key={t.id}
              layout
              initial={{ opacity: 0, y: -16, scale: 0.96, filter: "blur(6px)" }}
              animate={{ opacity: 1, y: 0, scale: 1, filter: "blur(0px)" }}
              exit={{ opacity: 0, y: -8, scale: 0.98, filter: "blur(4px)" }}
              transition={spring.default}
              className="squircle flex max-w-[34rem] items-center gap-2.5 rounded-full bg-[#2c2c2e]/95 py-2.5 pl-3.5 pr-5 text-subheadline shadow-[inset_0_0.5px_0_rgb(255_255_255/0.14),0_16px_40px_rgb(0_0_0/0.5)] backdrop-blur-xl"
            >
              <Icon className="size-5 shrink-0" style={{ color: COLOR[t.tone] }} aria-hidden />
              {t.text}
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
