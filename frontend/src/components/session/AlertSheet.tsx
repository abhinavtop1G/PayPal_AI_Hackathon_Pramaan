"use client";

import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { PhoneCall, PhoneOff, ShieldAlert } from "lucide-react";
import { Button } from "@/components/common/Button";
import { SegmentedControl } from "@/components/common/SegmentedControl";
import { ACTION_LABEL } from "@/config/policy";
import { spring } from "@/config/motion";
import type { Decision } from "@/types/demo";
import { rupees } from "@/utils/format";

const TITLE = {
  en: { hold: "Payment on hold", cool_off: "Payment paused", nudge: "Check before you pay" },
  hi: { hold: "भुगतान रोका गया", cool_off: "भुगतान कुछ देर के लिए रुका", nudge: "भुगतान से पहले जाँच लें" },
} as const;

/** Hindi for the fusion model's reason texts (ml/engine/fusion.py REASON_TEXT) and the campaign overrides. */
const REASON_HI: Record<string, string> = {
  "session follows a known scam pattern": "यह सत्र एक जानी-पहचानी ठगी के पैटर्न जैसा है",
  "receiving account is linked to suspected mule activity": "पाने वाला खाता संदिग्ध म्यूल गतिविधि से जुड़ा है",
  "touch behaviour differs from your usual pattern": "आपके टच करने का तरीका सामान्य से अलग है",
  "amount is much larger than your usual payments": "राशि आपके सामान्य भुगतानों से बहुत ज़्यादा है",
  "first payment to this account": "इस खाते में आपका पहला भुगतान",
  "you are on a call with an unknown number": "आप एक अनजान नंबर से कॉल पर हैं",
  "payee account is under an analyst credit hold": "पाने वाले खाते पर बैंक ने रोक लगाई है",
  "payee belongs to an active scam campaign": "पाने वाला खाता एक सक्रिय ठगी अभियान का हिस्सा है",
  "the number calling you has been reported for fraud": "आपको कॉल कर रहे नंबर की धोखाधड़ी के लिए शिकायत दर्ज है",
};

const COPY = {
  en: { why: "Why we stopped it", call: "Call 1930 · Cyber helpline", end: "End the current call", ended: "Call ended" },
  hi: { why: "हमने इसे क्यों रोका", call: "1930 पर कॉल करें · साइबर हेल्पलाइन", end: "चल रही कॉल काटें", ended: "कॉल कट गई" },
} as const;

/**
 * The customer-facing alert: a bottom sheet over a dimmed scrim (dim-to-focus). It rises on the sheet spring
 * (slight overshoot, the one place bounce belongs) and sits above the app, which recedes behind it.
 * Copy comes from the API in English and Hindi; reasons are the fusion model's top contributors.
 */
export function AlertSheet({
  decision,
  amount,
  payee,
  delay,
  onCall,
  onEndCall,
  callEnded,
  hasCall,
}: {
  decision: Decision;
  amount: number;
  payee: string;
  delay: number;
  onCall: () => void;
  onEndCall: () => void;
  callEnded: boolean;
  /** false when the session has no call (SMS-led scams): the "end the call" button is left out */
  hasCall: boolean;
}) {
  const [lang, setLang] = useState<"en" | "hi">("en");
  const tier = decision.action === "hold" || decision.action === "cool_off" || decision.action === "nudge" ? decision.action : "nudge";
  const message = lang === "en" ? decision.message_en : decision.message_hi;
  return (
    <>
      <motion.div
        aria-hidden
        className="absolute inset-0 z-30 bg-black/55"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1, transition: { duration: 0.3, delay } }}
        exit={{ opacity: 0 }}
      />
      <motion.section
        role="alertdialog"
        aria-modal
        aria-labelledby="alert-title"
        initial={{ y: "100%" }}
        animate={{ y: 0, transition: { ...spring.sheet, delay } }}
        exit={{ y: "100%", transition: spring.default }}
        className="squircle absolute inset-x-1.5 bottom-1.5 z-40 rounded-[2.6rem] bg-[#1c1c1e]/92 px-5 pb-6 pt-2 shadow-[inset_0_0.5px_0_rgb(255_255_255/0.12),0_-20px_60px_rgb(0_0_0/0.5)] backdrop-blur-2xl"
      >
        <div className="mx-auto mb-3 h-[5px] w-9 rounded-full bg-label-tertiary" aria-hidden />

        <div className="flex items-start gap-3">
          <motion.span
            initial={{ scale: 0.5, opacity: 0 }}
            animate={{ scale: 1, opacity: 1, transition: { ...spring.sheet, delay: delay + 0.12 } }}
            className="flex size-12 shrink-0 items-center justify-center rounded-full bg-sys-red/18"
          >
            <ShieldAlert className="size-6 text-sys-red" aria-hidden />
          </motion.span>
          <div className="min-w-0">
            <h2 id="alert-title" className="text-title-3" lang={lang}>
              {TITLE[lang][tier]}
            </h2>
            <p className="text-footnote text-label-secondary">
              {rupees(amount)} to {payee}
            </p>
          </div>
          <span className="ml-auto rounded-full bg-sys-red/15 px-2 py-0.5 text-caption-2 font-semibold uppercase tracking-wider text-sys-red">
            {ACTION_LABEL[decision.action]}
          </span>
        </div>

        <div className="mt-4">
          <SegmentedControl
            label="Alert language"
            size="small"
            value={lang}
            onChange={setLang}
            options={[
              { value: "en", label: "English" },
              { value: "hi", label: "हिन्दी" },
            ]}
          />
        </div>

        <div className="relative mt-3 min-h-[7.5rem]">
          <AnimatePresence mode="popLayout" initial={false}>
            <motion.p
              key={lang}
              lang={lang}
              initial={{ opacity: 0, filter: "blur(6px)" }}
              animate={{ opacity: 1, filter: "blur(0px)" }}
              exit={{ opacity: 0, filter: "blur(6px)" }}
              transition={spring.snappy}
              className={lang === "hi" ? "text-[1rem] leading-[1.6rem]" : "text-subheadline"}
            >
              {message}
            </motion.p>
          </AnimatePresence>
        </div>

        {decision.reasons.length > 0 && (
          <div className="mt-3 rounded-[1rem] bg-fill-quaternary px-3.5 py-2.5">
            <p className={lang === "hi" ? "text-caption-1 font-semibold text-label-tertiary" : "text-eyebrow text-label-tertiary"}>
              {COPY[lang].why}
            </p>
            <ul className="mt-1.5 space-y-1">
              {decision.reasons.map((r) => (
                <li key={r} lang={lang} className="flex items-start gap-2 text-footnote text-label-secondary">
                  <span className="mt-[0.45rem] size-1.5 shrink-0 rounded-full bg-sys-red" aria-hidden />
                  <span className="first-letter:uppercase">{lang === "hi" ? REASON_HI[r] ?? r : r}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-4 grid gap-2">
          <Button tint="red" onClick={onCall}>
            <PhoneCall className="size-5" aria-hidden />
            <span lang={lang}>{COPY[lang].call}</span>
          </Button>
          {hasCall && (
            <Button tint="gray" variant="tinted" onClick={onEndCall} disabled={callEnded}>
              <PhoneOff className="size-5" aria-hidden />
              <span lang={lang}>{callEnded ? COPY[lang].ended : COPY[lang].end}</span>
            </Button>
          )}
        </div>
      </motion.section>
    </>
  );
}
