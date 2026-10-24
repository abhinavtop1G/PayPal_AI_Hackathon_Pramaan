"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { CircleCheck, Fingerprint, Hourglass, Landmark, Loader2, Phone, PhoneOff, ShieldX, Siren } from "lucide-react";
import { PhoneFrame, SAFE_AREA } from "@/components/session/PhoneFrame";
import { inr } from "@/config/authSignals";
import { spring } from "@/config/motion";
import type { Lang } from "@/context/ConsoleContext";
import type { ChallengeOutcome, DemoRun } from "@/types/auth";

const SCALE = 0.66;

type Screen = "deciding" | "allowed" | "otp" | "passkey" | "callback" | "cooloff" | "blocked" | "locked";

/**
 * What the customer sees on their phone for this decision, in the bank app: approved, the step-up the policy chose
 * (OTP entry, passkey prompt, the bank's call, the cool-off with a scam warning), or blocked; then the final outcome
 * once the challenge is passed or failed. Messages come from the API (English / Hindi).
 */
export function CustomerPhone({ run, outcome, busy, lang }: { run: DemoRun | null; outcome: ChallengeOutcome | null; busy: boolean; lang: Lang }) {
  const r = run?.response;
  let screen: Screen = "deciding";
  if (r && !busy) {
    if (outcome) screen = outcome.decision === "allow" ? "allowed" : "locked";
    else if (r.decision === "allow") screen = "allowed";
    else if (r.decision === "block") screen = "blocked";
    else screen = ({ sms_otp: "otp", passkey: "passkey", bank_callback: "callback", cool_off: "cooloff" } as const)[r.challenge_type ?? "sms_otp"];
  }
  const msg = outcome ? (lang === "hi" ? outcome.message_hi : outcome.message_en) : r ? (lang === "hi" ? r.message_hi : r.message_en) : "";
  const payee = run?.request.transaction.payee_id ?? "";
  const amount = r?.amount ?? 0;
  return (
    <div className="mx-auto" style={{ width: 414 * SCALE, height: 868 * SCALE }}>
      <div style={{ transform: `scale(${SCALE})`, transformOrigin: "top left", width: 414, height: 868 }} className="p-3">
        <PhoneFrame time="9:41">
          <div className={`flex h-full flex-col bg-gradient-to-b from-[#0d1424] to-black px-6 ${SAFE_AREA}`} lang={lang === "hi" ? "hi" : undefined}>
            <div className="mt-3 flex items-center gap-2.5">
              <span className="flex size-9 items-center justify-center rounded-full bg-sys-blue/20 text-sys-blue"><Landmark className="size-5" aria-hidden /></span>
              <div>
                <p className="text-[1.05rem] font-semibold">Your bank</p>
                <p className="text-[0.8rem] text-label-tertiary">{r?.amount ? "UPI payment" : "Sign in"}</p>
              </div>
            </div>
            <div className="mt-6 text-center">
              <p className="text-[0.9rem] text-label-secondary">{amount > 0 ? `Paying ${payee}` : "Signing in"}</p>
              {amount > 0 && <p className="mt-1 text-[2.6rem] font-bold tracking-[-0.03em]">{inr(amount)}</p>}
            </div>
            <div className="relative mt-6 flex-1">
              <AnimatePresence mode="wait" initial={false}>
                <motion.div key={screen + (r?.decision_id ?? "")} initial={{ opacity: 0, y: 14, filter: "blur(6px)" }}
                  animate={{ opacity: 1, y: 0, filter: "blur(0px)" }} exit={{ opacity: 0, y: -10, filter: "blur(6px)" }} transition={spring.default}
                  className="absolute inset-0">
                  <ScreenBody screen={screen} msg={msg} latency={r?.latency_ms} trusted={!!outcome?.device_trusted} />
                </motion.div>
              </AnimatePresence>
            </div>
          </div>
        </PhoneFrame>
      </div>
    </div>
  );
}

function ScreenBody({ screen, msg, latency, trusted }: { screen: Screen; msg: string; latency?: number; trusted: boolean }) {
  switch (screen) {
    case "deciding":
      return <Centered icon={<Loader2 className="size-14 animate-spin text-label-tertiary" />} title="Verifying…" body="Checking behaviour, device and payment pattern." />;
    case "allowed":
      return <Centered icon={<CircleCheck className="size-16 text-sys-green" />} title="Payment successful"
        body={`${msg}${trusted ? " This phone is now trusted." : ""}`} foot={latency ? `decided in ${latency.toFixed(0)} ms` : undefined} />;
    case "blocked":
      return <Centered icon={<ShieldX className="size-16 text-sys-red" />} title="Payment stopped" body={msg} foot="Helpline 1930 · cyber fraud" />;
    case "locked":
      return <Centered icon={<ShieldX className="size-16 text-sys-red" />} title="Blocked" body={`${msg} Payments from this account are paused for 30 minutes.`} />;
    case "otp":
      return <Otp msg={msg} />;
    case "passkey":
      return (
        <Centered icon={<span className="flex size-20 items-center justify-center rounded-full bg-sys-blue/15"><Fingerprint className="size-11 text-sys-blue" /></span>}
          title="Approve on your registered phone" body={msg} foot="Passkey · FIDO2 · works without SMS" />
      );
    case "callback":
      return (
        <div className="flex h-full flex-col items-center text-center">
          <span className="relative mt-2 flex size-20 items-center justify-center rounded-full bg-sys-green/15">
            <span className="pulse-ring absolute inset-0 rounded-full text-sys-green" />
            <Phone className="size-9 text-sys-green" />
          </span>
          <p className="mt-4 text-[1.2rem] font-semibold">Your bank is calling</p>
          <p className="text-[0.85rem] text-label-tertiary">Fraud desk · registered number</p>
          <p className="mt-4 text-[0.95rem] leading-snug text-label-secondary">{msg}</p>
          <div className="mt-auto mb-6 flex gap-10">
            <span className="flex size-14 items-center justify-center rounded-full bg-sys-red"><PhoneOff className="size-6" /></span>
            <span className="flex size-14 items-center justify-center rounded-full bg-sys-green"><Phone className="size-6" /></span>
          </div>
        </div>
      );
    case "cooloff":
      return <CoolOff msg={msg} />;
  }
}

function Centered({ icon, title, body, foot }: { icon: React.ReactNode; title: string; body: string; foot?: string }) {
  return (
    <div className="flex h-full flex-col items-center text-center">
      <div className="mt-2">{icon}</div>
      <p className="mt-4 text-[1.3rem] font-semibold tracking-[-0.01em]">{title}</p>
      <p className="mt-2 text-[0.95rem] leading-snug text-label-secondary">{body}</p>
      {foot && <p className="mt-auto mb-6 text-[0.8rem] text-label-tertiary">{foot}</p>}
    </div>
  );
}

function Otp({ msg }: { msg: string }) {
  const [n, setN] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setN((x) => (x >= 6 ? 6 : x + 1)), 420);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="flex h-full flex-col items-center text-center">
      <p className="text-[1.2rem] font-semibold">Enter the one-time password</p>
      <p className="mt-2 text-[0.9rem] leading-snug text-label-secondary">{msg}</p>
      <div className="mt-6 flex gap-2">
        {Array.from({ length: 6 }, (_, i) => (
          <span key={i} className={`flex h-12 w-10 items-center justify-center rounded-xl text-[1.4rem] font-semibold ${i < n ? "bg-fill-secondary" : "bg-fill-quaternary ring-1 ring-white/10"}`}>
            {i < n ? "•" : ""}
          </span>
        ))}
      </div>
      <p className="mt-auto mb-6 text-[0.8rem] text-label-tertiary">SMS from AX-YRBANK · resend in 0:29</p>
    </div>
  );
}

function CoolOff({ msg }: { msg: string }) {
  const [left, setLeft] = useState(30 * 60);
  useEffect(() => {
    const t = setInterval(() => setLeft((x) => Math.max(0, x - 1)), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="flex h-full flex-col items-center text-center">
      <span className="flex size-16 items-center justify-center rounded-full bg-sys-orange/15"><Hourglass className="size-8 text-sys-orange" /></span>
      <p className="mt-3 font-mono text-[2.2rem] font-semibold tabular-nums">{`${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`}</p>
      <p className="text-[0.85rem] text-label-tertiary">payment paused</p>
      <div className="mt-4 rounded-2xl bg-sys-red/12 p-3 text-left">
        <p className="flex items-center gap-1.5 text-[0.9rem] font-semibold text-sys-red"><Siren className="size-4" /> Is someone on a call telling you to pay?</p>
        <p className="mt-1 text-[0.85rem] leading-snug text-label-secondary">{msg}</p>
      </div>
    </div>
  );
}
