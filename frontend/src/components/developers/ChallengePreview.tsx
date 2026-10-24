"use client";

import { useEffect, useRef, useState } from "react";
import { MonitorSmartphone, RotateCcw } from "lucide-react";
import { showChallenge, type AuthResponse, type ChallengeResult, type ChallengeType } from "@pramaan/web-sdk";
import { Button } from "@/components/common/Button";
import { SegmentedControl } from "@/components/common/SegmentedControl";
import { Panel } from "@/components/layout/Panel";
import { CodeBlock } from "@/components/ui/CodeBlock";

const MESSAGE: Record<ChallengeType, [string, string]> = {
  sms_otp: ["Enter the one-time password sent to your registered mobile number.", "अपने रजिस्टर्ड मोबाइल नंबर पर भेजा गया OTP दर्ज करें।"],
  passkey: ["Approve this payment on your registered device with your fingerprint or face.", "अपने रजिस्टर्ड डिवाइस पर फ़िंगरप्रिंट या चेहरे से इस भुगतान को स्वीकृत करें।"],
  bank_callback: ["Your bank will call you on your registered number to confirm this payment.", "आपका बैंक इस भुगतान की पुष्टि के लिए आपके रजिस्टर्ड नंबर पर कॉल करेगा।"],
  cool_off: ["This payment is paused for 30 minutes for your safety.", "आपकी सुरक्षा के लिए यह भुगतान 30 मिनट के लिए रोका गया है।"],
};

/** The web SDK's drop-in step-up screens (showChallenge), rendered live with demo handlers. */
export function ChallengePreview() {
  const [type, setType] = useState<ChallengeType>("sms_otp");
  const [lang, setLang] = useState<"en" | "hi">("en");
  const [run, setRun] = useState(0);
  const [result, setResult] = useState<ChallengeResult | null>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ac = new AbortController();
    const decision = {
      decision_id: "preview", user_id: "demo", decision: "challenge", risk_score: 0.02, challenge_type: type, rule: null,
      message_en: MESSAGE[type][0], message_hi: MESSAGE[type][1], reasons: [], family_contribution: { behaviour: 0, device: 0, transaction: 0 },
      signals: [], features: {}, expected_cost: {}, amount: 2500, model_version: "preview", latency_ms: 0,
    } satisfies AuthResponse;
    const wait = (ms: number) => new Promise<boolean>((r) => setTimeout(() => r(true), ms));
    showChallenge(el, decision, {
      lang, coolOffSeconds: 8,
      verifyOtp: async (code) => code === "123456",
      passkey: () => wait(700),
      outOfBand: () => wait(3500),
    }, { inline: true, signal: ac.signal }).then((r) => !ac.signal.aborted && setResult(r));
    return () => ac.abort();
  }, [type, lang, run]);

  const code = `import { showChallenge } from "@pramaan/web-sdk";

if (decision.decision === "challenge") {
  const { passed } = await showChallenge(document.body, decision, {
    lang: "${lang}",
    verifyOtp: (code) => api.checkOtp(code),        // your OTP service
    passkey: () => api.approveWithPasskey(),          // WebAuthn against your server
    outOfBand: () => api.waitForCallBack(),           // your call-back team
  });
  await api.reportStepUp(decision.decision_id, passed); // → PramaanClient.verifyChallenge
}`;

  return (
    <Panel eyebrow="Web SDK · showChallenge()" title="Drop-in step-up screens" icon={MonitorSmartphone} tint="var(--color-sys-orange)">
      <div className="flex flex-wrap items-center gap-2">
        <SegmentedControl<ChallengeType> size="small" label="Step-up" value={type} onChange={(v) => { setType(v); setResult(null); }} options={[
          { value: "sms_otp", label: "SMS OTP" }, { value: "passkey", label: "Passkey" },
          { value: "bank_callback", label: "Bank call-back" }, { value: "cool_off", label: "Cool-off" },
        ]} />
        <SegmentedControl<"en" | "hi"> size="small" label="Language" value={lang} onChange={(v) => { setLang(v); setResult(null); }}
          options={[{ value: "en", label: "English" }, { value: "hi", label: "हिन्दी" }]} />
        <Button size="small" tint="gray" variant="tinted" onClick={() => { setRun((n) => n + 1); setResult(null); }}>
          <RotateCcw className="size-3.5" aria-hidden /> Restart
        </Button>
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
        <div className="min-w-0">
          <div ref={box} className="min-h-[16rem] rounded-[1.4rem] bg-[#0b0b0d] p-3 ring-1 ring-white/[0.07]" />
          <p className="mt-2 text-caption-1 text-label-tertiary">
            {result ? `Resolved: ${result.passed ? "passed" : result.cancelled ? "cancelled by the customer" : "failed"}.` :
              type === "sms_otp" ? "Demo handler: 123456 is the right code." : type === "cool_off" ? "Demo: an 8-second cool-off instead of 30 minutes." :
                type === "passkey" ? "Demo handler: the passkey approves." : "Demo handler: the bank confirms after a few seconds."}
          </p>
        </div>
        <CodeBlock lang="ts" title="your page" code={code} />
      </div>
    </Panel>
  );
}
