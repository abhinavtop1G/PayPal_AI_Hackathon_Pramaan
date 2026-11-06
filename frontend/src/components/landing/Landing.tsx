"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion } from "motion/react";
import {
  ArrowRight, Binary, BrainCircuit, Fingerprint, Gauge, Hourglass, KeyRound, Landmark, Lock, Phone, Receipt, Scale, Smartphone,
  type LucideIcon,
} from "lucide-react";
import { useReport } from "@/api/console";
import { BarList } from "@/components/charts/BarList";
import { Wordmark } from "@/components/console/Brand";
import { CodeBlock } from "@/components/ui/CodeBlock";
import { FAMILY_TINT } from "@/config/authSignals";
import { HeroDecisions } from "./HeroDecisions";

const ALL_SIGNALS = "risk engine (all signals)";
const OTP_ALWAYS = "SMS OTP on every payment";

/** A report percentage for a headline: 82.78 -> "82.8%", 100 -> "100%". */
const pc = (v: number) => `${Number(v.toFixed(1))}%`;

/** p95 of POST /v1/authenticate over HTTP without touch data, as measured by backend/bench_auth.py. */
function useHttpP95(): number | null {
  const { data } = useReport();
  const p95 = data?.http_latency[0]?.p95;
  return p95 === undefined ? null : Math.round(p95);
}

const fade = { initial: { opacity: 0, y: 16 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true, margin: "-60px" }, transition: { duration: 0.5 } };

/** The public front page: what PRAMAAN is, the evidence, how it decides, and the way into the console. */
export function Landing() {
  const router = useRouter();
  // old deep links (/?scenario=sim_swap&verify=pass) open the decision lab
  useEffect(() => {
    const q = window.location.search;
    if (new URLSearchParams(q).has("scenario")) router.replace(`/console/lab${q}`);
  }, [router]);

  return (
    <div className="min-h-dvh overflow-x-clip bg-black">
      <div aria-hidden className="grid-backdrop pointer-events-none absolute inset-x-0 top-0 h-[64rem]" />
      <Nav />
      <main className="relative">
        <Hero />
        <Proof />
        <Families />
        <StepUps />
        <Pipeline />
        <Compare />
        <Sdks />
        <Cta />
      </main>
      <Footer />
    </div>
  );
}

function Nav() {
  return (
    <header className="sticky top-0 z-30 border-b border-white/[0.06] bg-black/60 backdrop-blur-xl">
      <div className="mx-auto flex max-w-[78rem] items-center justify-between gap-4 px-5 py-3">
        <Wordmark href="/" />
        <nav className="hidden items-center gap-6 text-footnote text-label-secondary md:flex" aria-label="Sections">
          <a href="#how" className="hover:text-label">How it decides</a>
          <a href="#results" className="hover:text-label">Results</a>
          <a href="#sdk" className="hover:text-label">SDKs</a>
          <Link href="/scam" className="hover:text-label">Scam sessions</Link>
        </nav>
        <Link href="/console" className="flex items-center gap-1.5 rounded-full bg-white px-4 py-2 text-footnote font-semibold text-black transition-transform hover:scale-[1.02] active:scale-[0.98]">
          Open console <ArrowRight className="size-3.5" aria-hidden />
        </Link>
      </div>
    </header>
  );
}

function Hero() {
  const p95 = useHttpP95();
  return (
    <section className="mx-auto grid max-w-[78rem] items-center gap-12 px-5 pb-20 pt-16 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] lg:pt-24">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
        <p className="inline-flex items-center gap-2 rounded-full bg-white/[0.06] px-3 py-1 text-caption-1 text-label-secondary ring-1 ring-white/10">
          प्रमाण · “proof” · risk-based transaction authentication
        </p>
        <h1 className="mt-5 text-[3.25rem] font-bold leading-[1.02] tracking-[-0.035em] sm:text-[4.25rem]">
          Proof it&apos;s really you, <span className="text-brand">{p95 === null ? "in milliseconds." : `in ${p95} ms.`}</span>
        </h1>
        <p className="mt-5 max-w-[34rem] text-[1.15rem] leading-relaxed text-label-secondary">
          For every login and payment, PRAMAAN reads behaviour, device and transaction signals together, then allows it,
          blocks it, or picks the one step-up that actually stops the likely attack. Every decision comes with the signals
          behind it, in English and Hindi.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link href="/console/lab?autoplay" className="flex items-center gap-2 rounded-full bg-gradient-to-r from-[#5e5ce6] to-[#3f8cf0] px-5 py-3 text-subheadline font-semibold text-white shadow-[0_10px_30px_rgb(94_92_230/0.45)] transition-transform hover:scale-[1.02] active:scale-[0.98]">
            Watch it decide <ArrowRight className="size-4" aria-hidden />
          </Link>
          <Link href="/console/capture" className="flex items-center gap-2 rounded-full bg-white/[0.08] px-5 py-3 text-subheadline font-semibold ring-1 ring-white/10 transition-colors hover:bg-white/[0.12]">
            <Fingerprint className="size-4" aria-hidden /> Try the SDK on yourself
          </Link>
        </div>
        <p className="mt-6 text-caption-1 text-label-tertiary">
          p95 over HTTP with API-key and signature checks, laptop CPU. Attacks are simulated; touch and typing data are real (HMOG, CMU).
        </p>
      </motion.div>
      <motion.div initial={{ opacity: 0, y: 24, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.7, delay: 0.1 }}>
        <HeroDecisions />
      </motion.div>
    </section>
  );
}

function Proof() {
  const { data } = useReport();
  let items: [string, string, string][] = [];
  if (data) {
    const { designs, ranking } = data.auth;
    const all = designs[ALL_SIGNALS];
    const otp = designs[OTP_ALWAYS];
    const bestSingle = Math.max(...Object.entries(ranking).filter(([k]) => k !== ALL_SIGNALS).map(([, r]) => r.roc_auc));
    items = [
      [pc(all.attacks_stopped_pct), "of attack requests stopped", `SMS OTP on every payment: ${pc(otp.attacks_stopped_pct)}`],
      [pc(all.genuine_challenged_pct), "of genuine requests challenged", `SMS OTP on every payment: ${pc(otp.genuine_challenged_pct)}`],
      [ranking[ALL_SIGNALS].roc_auc.toFixed(3), "ROC-AUC on held-out days", `best single family: ${bestSingle.toFixed(2)}`],
      [pc(all.per_scenario.sim_swap), "of SIM swaps stopped", `SMS OTP on every payment: ${pc(otp.per_scenario.sim_swap)}, the code goes to the attacker`],
    ];
  }
  return (
    <section id="results" className="border-y border-white/[0.06] bg-white/[0.015]">
      <div className="mx-auto grid max-w-[78rem] grid-cols-2 gap-px px-5 lg:grid-cols-4">
        {!data && [0, 1, 2, 3].map((i) => <div key={i} className="px-2 py-9 sm:px-6"><div className="skeleton h-28 rounded-2xl" /></div>)}
        {items.map(([v, l, c], i) => (
          <motion.div key={l} {...fade} transition={{ duration: 0.5, delay: 0.06 * i }} className="px-2 py-9 sm:px-6">
            <p className="text-[2.6rem] font-bold tracking-[-0.03em]">{v}</p>
            <p className="mt-1 text-subheadline">{l}</p>
            <p className="mt-1 text-caption-1 text-label-tertiary">{c}</p>
          </motion.div>
        ))}
      </div>
    </section>
  );
}

function SectionHead({ eyebrow, title, body }: { eyebrow: string; title: string; body: string }) {
  return (
    <motion.div {...fade} className="max-w-[46rem]">
      <p className="text-eyebrow text-sys-blue">{eyebrow}</p>
      <h2 className="mt-2 text-[2.25rem] font-bold leading-tight tracking-[-0.025em]">{title}</h2>
      <p className="mt-3 text-callout text-label-secondary">{body}</p>
    </motion.div>
  );
}

function Families() {
  const fams: { key: "behaviour" | "device" | "transaction"; icon: LucideIcon; title: string; q: string; items: string[] }[] = [
    { key: "behaviour", icon: Fingerprint, title: "Behaviour", q: "Is it the owner's hands?", items: ["touch dynamics (BiLSTM on real HMOG gestures)", "typing rhythm (1D-CNN on CMU keystrokes)", "time to submit, input count", "an unknown caller on the line"] },
    { key: "device", icon: Smartphone, title: "Device", q: "Is it the owner's phone?", items: ["new or untrusted device", "SIM changed hours ago", "emulator, root, remote-control app", "hosting / Tor IP, impossible travel"] },
    { key: "transaction", icon: Receipt, title: "Transaction", q: "Is it the owner's kind of payment?", items: ["amount vs their history", "new payee, payee risk (mule network)", "spend in the last 24 h", "unusual hour, failed challenges"] },
  ];
  return (
    <section id="how" className="mx-auto max-w-[78rem] px-5 py-24">
      <SectionHead eyebrow="27 signals · one model" title="Three questions about every payment"
        body="Signals interact: a new phone is normal after a SIM change only if the touch pattern still matches; a large amount is normal on a trusted device. So one monotone model reads all three families together, and no single family comes close." />
      <div className="mt-10 grid gap-4 md:grid-cols-3">
        {fams.map((f, i) => (
          <motion.div key={f.key} {...fade} transition={{ duration: 0.5, delay: 0.08 * i }}
            className="material-regular panel-sheen squircle rounded-[var(--radius-panel)] p-6">
            <span className="flex size-11 items-center justify-center rounded-[0.8rem]" style={{ background: `color-mix(in srgb, ${FAMILY_TINT[f.key]} 18%, transparent)`, color: FAMILY_TINT[f.key] }}>
              <f.icon className="size-5" aria-hidden />
            </span>
            <p className="mt-4 text-title-3">{f.title}</p>
            <p className="text-subheadline text-label-secondary">{f.q}</p>
            <ul className="mt-4 space-y-2">
              {f.items.map((x) => (
                <li key={x} className="flex gap-2 text-footnote text-label-secondary">
                  <span className="mt-1.5 size-1.5 shrink-0 rounded-full" style={{ background: FAMILY_TINT[f.key] }} aria-hidden />{x}
                </li>
              ))}
            </ul>
          </motion.div>
        ))}
      </div>
    </section>
  );
}

function StepUps() {
  const items: { icon: LucideIcon; title: string; when: string; why: string; tint: string }[] = [
    { icon: KeyRound, title: "Passkey on the registered phone", when: "new device or a fresh SIM", why: "An SMS OTP would go to the attacker's SIM.", tint: "var(--color-sys-blue)" },
    { icon: Phone, title: "Bank call-back", when: "remote-control app, someone else's hands, a large amount", why: "A person confirms on the registered number.", tint: "var(--color-sys-green)" },
    { icon: Hourglass, title: "Cool-off + scam warning", when: "the owner, on their own phone, on a call", why: "The real owner would type any OTP; time and a warning break the spell.", tint: "var(--color-sys-orange)" },
    { icon: Lock, title: "SMS OTP", when: "nothing points at a hijacked phone or SIM", why: "Enough, and familiar.", tint: "var(--color-gray-1)" },
  ];
  return (
    <section className="mx-auto max-w-[78rem] px-5 pb-24">
      <SectionHead eyebrow="Policy" title="The right step-up, not just more friction"
        body="The policy compares the expected cost of allowing, challenging and blocking, and blocks only when an attack is more likely than not. When it challenges, it picks the step-up that fits the signals." />
      <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {items.map((s, i) => (
          <motion.div key={s.title} {...fade} transition={{ duration: 0.5, delay: 0.06 * i }} className="squircle rounded-[var(--radius-card)] bg-white/[0.04] p-5 ring-1 ring-white/[0.07]">
            <s.icon className="size-5" style={{ color: s.tint }} aria-hidden />
            <p className="mt-3 text-headline">{s.title}</p>
            <p className="mt-1 text-caption-1 text-label-tertiary">when: {s.when}</p>
            <p className="mt-2 text-footnote text-label-secondary">{s.why}</p>
          </motion.div>
        ))}
      </div>
    </section>
  );
}

function Pipeline() {
  const p95 = useHttpP95();
  const steps: [LucideIcon, string, string][] = [
    [Smartphone, "SDK", "signals on the device"], [Lock, "Gateway", "key · HMAC · replay · rate"], [Fingerprint, "Touch + typing", "BiLSTM · 1D-CNN"],
    [Landmark, "Payee intel", "mule-network risk"], [Binary, "27 features", "live state, causal"], [BrainCircuit, "Monotone XGBoost", "exact tree-SHAP"],
    [Scale, "Policy", "expected cost + rules"], [Gauge, "Decision", "allow · challenge · block"],
  ];
  return (
    <section className="border-y border-white/[0.06] bg-white/[0.015] py-20">
      <div className="mx-auto max-w-[78rem] px-5">
        <SectionHead eyebrow="Request path" title={p95 === null ? "One request, in milliseconds" : `One request, about ${p95} ms`}
          body="Each stage reports its own time; the decision lab shows the trace for every request, with the SHAP waterfall behind the score." />
        <ol className="mt-10 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">
          {steps.map(([Icon, t, d], i) => (
            <motion.li key={t} {...fade} transition={{ duration: 0.4, delay: 0.05 * i }} className="relative">
              <div className={`squircle h-full rounded-[1rem] p-3.5 ${i === steps.length - 1 ? "bg-gradient-to-br from-[#5e5ce6]/30 to-[#64d2ff]/10 ring-1 ring-[#5e5ce6]/40" : "bg-white/[0.04] ring-1 ring-white/[0.07]"}`}>
                <div className="flex items-center justify-between"><Icon className="size-4 text-label-secondary" aria-hidden /><span className="font-mono text-caption-2 text-label-tertiary">{i + 1}</span></div>
                <p className="mt-2 text-footnote font-semibold">{t}</p>
                <p className="text-caption-2 text-label-tertiary">{d}</p>
              </div>
            </motion.li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function Compare() {
  const { data } = useReport();
  const auth = data?.auth;
  const all = auth?.designs[ALL_SIGNALS];
  const otp = auth?.designs[OTP_ALWAYS];
  const order: [string, string][] = [
    ["SMS OTP on every payment", "SMS OTP on every payment"], ["rules engine + SMS OTP", "Rules engine + SMS OTP"],
    ["device signals only", "Device signals only"], ["behaviour signals only", "Behaviour signals only"],
    ["transaction signals only", "Transaction signals only"], ["risk engine (all signals)", "PRAMAAN: all signals"],
  ];
  return (
    <section className="mx-auto grid max-w-[78rem] gap-10 px-5 py-24 lg:grid-cols-2">
      <SectionHead eyebrow="Evaluation"
        title={all && otp
          ? `Stops ${(all.attacks_stopped_pct / otp.attacks_stopped_pct).toFixed(1)}× more attacks than OTP-always, with ${Math.round(otp.genuine_challenged_pct / all.genuine_challenged_pct)}× less friction`
          : "Against an SMS OTP on every payment"}
        body={auth
          ? `${auth.data.users.toLocaleString("en-US")} simulated customers, ${Math.round(auth.data.requests / 1000)}k requests over ${auth.split.days} days; trained on days 0–${auth.split.train_end}, tested on days ${auth.split.valid_end}–${auth.split.days} through the real service, challenge outcomes simulated. Every design runs on the same replay.`
          : "Every design runs on the same replay."} />
      <motion.div {...fade} className="material-regular squircle rounded-[var(--radius-panel)] p-6">
        <p className="mb-4 text-footnote text-label-secondary">Attack requests finally stopped · genuine requests challenged</p>
        {data ? (
          <BarList ariaLabel="Attack requests stopped by design" max={100} rows={order.map(([k, label]) => {
            const d = data.auth.designs[k];
            return { key: k, label, value: d.attacks_stopped_pct, display: `${d.attacks_stopped_pct}%`, sub: `${d.genuine_challenged_pct}% of genuine requests challenged`,
              color: k === "risk engine (all signals)" ? "var(--color-brand-2)" : "var(--color-gray-2)" };
          })} />
        ) : <div className="skeleton h-72 rounded-2xl" />}
        <Link href="/console/model" className="mt-5 inline-flex items-center gap-1.5 text-footnote text-sys-blue hover:underline">Full evaluation <ArrowRight className="size-3.5" aria-hidden /></Link>
      </motion.div>
    </section>
  );
}

function Sdks() {
  return (
    <section id="sdk" className="border-t border-white/[0.06] py-24">
      <div className="mx-auto max-w-[78rem] px-5">
        <SectionHead eyebrow="SDKs" title="Collect on the device. Decide in the cloud."
          body="A zero-dependency web SDK (TypeScript) and Android SDK (Kotlin) compute touch and typing features exactly as the models were trained, checked against the Python pipeline with shared golden vectors. Raw coordinates and keys never leave the device." />
        <div className="mt-10 grid gap-4 lg:grid-cols-2">
          <motion.div {...fade} className="min-w-0">
            <CodeBlock lang="ts" title="@pramaan/web-sdk" code={`const pramaan = Pramaan.init({ consent: true });
pramaan.startFlow();
pramaan.watchTyping(passwordInput);

const request = await pramaan.collect({
  userId, transaction: { amount: 2500, payee_id: "kirana-sharma" },
});
// → your backend → PramaanClient.authenticate(request)`} />
          </motion.div>
          <motion.div {...fade} transition={{ duration: 0.5, delay: 0.08 }} className="min-w-0">
            <CodeBlock lang="kotlin" title="com.pramaan.sdk (Android)" code={`Pramaan.init(application)          // watches every activity

Pramaan.get().startFlow()
val pad = Pramaan.get().pinPad(this) { pin -> submit(pin) }

val request = Pramaan.get().collect(userId,
    transaction = AuthTransaction(amount = 2500.0, payeeId = "kirana-sharma"))
// root, emulator, remote-control apps, SIM change, caller on the line`} />
          </motion.div>
        </div>
        <Link href="/console/developers" className="mt-6 inline-flex items-center gap-1.5 text-footnote text-sys-blue hover:underline">Integration guide <ArrowRight className="size-3.5" aria-hidden /></Link>
      </div>
    </section>
  );
}

function Cta() {
  const links: [string, string, string][] = [
    ["/console", "Operations overview", "A held-out day of traffic, decided on a compressed clock"],
    ["/console/lab", "Decision lab", "Nine attacks and look-alikes, end to end, with SHAP and the customer's screen"],
    ["/console/capture", "Live capture", "Your own typing and swipes through the web SDK"],
    ["/console/policy", "Policy tuner", "Trade friction against fraud and watch a whole day re-decided"],
  ];
  return (
    <section className="mx-auto max-w-[78rem] px-5 pb-24">
      <div className="squircle relative overflow-hidden rounded-[2rem] bg-gradient-to-br from-[#1c1a4a] via-[#0d1830] to-[#062033] p-8 ring-1 ring-white/10 sm:p-12">
        <div aria-hidden className="absolute -right-20 -top-20 size-80 rounded-full bg-[#64d2ff]/20 blur-3xl" />
        <h2 className="relative text-[2rem] font-bold tracking-[-0.02em]">See it decide.</h2>
        <div className="relative mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {links.map(([href, t, d]) => (
            <Link key={href} href={href} className="group rounded-[1.2rem] bg-white/[0.06] p-5 ring-1 ring-white/10 transition-colors hover:bg-white/[0.1]">
              <p className="flex items-center justify-between text-headline">{t}<ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" aria-hidden /></p>
              <p className="mt-1 text-footnote text-label-secondary">{d}</p>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-white/[0.06]">
      <div className="mx-auto flex max-w-[78rem] flex-wrap items-start justify-between gap-6 px-5 py-10 text-caption-1 text-label-tertiary">
        <div className="max-w-[34rem]">
          <Wordmark href="/" sub="Parallel Risk-Adaptive Multi-modal Authentication & Anomaly Network" />
          <p className="mt-3">Team CaffeineEaters: Abhinav Saini, Aditi Pundir, Mannat Kaur, Aryamann Sharma. Built on the RAKSHAM scam-detection work.</p>
          <p className="mt-2">Attack and genuine behaviours are simulated; touch windows (HMOG) and typing attempts (CMU) are real data; challenge efficacies are assumptions. The numbers validate the service and compare designs, not real-world accuracy.</p>
        </div>
        <nav className="flex gap-8" aria-label="Footer">
          <div className="space-y-1.5">
            <p className="text-label-secondary">Console</p>
            <Link href="/console" className="block hover:text-label">Overview</Link>
            <Link href="/console/lab" className="block hover:text-label">Decision lab</Link>
            <Link href="/console/capture" className="block hover:text-label">Live capture</Link>
          </div>
          <div className="space-y-1.5">
            <p className="text-label-secondary">More</p>
            <Link href="/console/model" className="block hover:text-label">Model</Link>
            <Link href="/console/developers" className="block hover:text-label">Developers</Link>
            <Link href="/scam" className="block hover:text-label">Scam sessions</Link>
          </div>
        </nav>
      </div>
    </footer>
  );
}
