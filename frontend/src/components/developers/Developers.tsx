"use client";

import { useState } from "react";
import { ArrowRight, Check, CircleCheck, Lock, Minus, Server, ShieldCheck, Smartphone, Workflow } from "lucide-react";
import { SegmentedControl } from "@/components/common/SegmentedControl";
import { Panel } from "@/components/layout/Panel";
import { CodeBlock } from "@/components/ui/CodeBlock";
import { FAMILY_TINT } from "@/config/authSignals";
import type { Family } from "@/types/auth";
import { ApiPlayground } from "./ApiPlayground";
import { ChallengePreview } from "./ChallengePreview";

type Tab = "web" | "server" | "android" | "python" | "curl";

const SNIPPETS: Record<Tab, { lang: "ts" | "kotlin" | "bash" | "python"; title: string; code: string }> = {
  web: { lang: "ts", title: "npm i @pramaan/web-sdk · browser", code: `import { Pramaan } from "@pramaan/web-sdk";

// 1. once per page, after the customer's consent (DPDP purpose: behavioural_biometrics)
const pramaan = Pramaan.init({ consent: true });

// 2. the payment / login screen opened
pramaan.startFlow();
pramaan.watchTyping(document.querySelector<HTMLInputElement>("#password")!);

// 3. on submit: what the page observed + this payment → your backend
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const request = await pramaan.collect({
    userId: session.userId,
    transaction: { amount: 2500, payee_id: "kirana-sharma", payee_is_merchant: true },
  });
  const decision = await fetch("/api/pay/authenticate", { method: "POST", body: JSON.stringify(request) }).then((r) => r.json());
  if (decision.decision === "challenge") showStepUp(decision.challenge_type);   // sms_otp | passkey | bank_callback | cool_off
});

// <script src="pramaan.min.js"> also works: window.Pramaan.Pramaan.init(...)` },
  server: { lang: "ts", title: "@pramaan/web-sdk/server · Node 18+, Bun, Deno, edge", code: `import { PramaanClient } from "@pramaan/web-sdk/server";

const pramaan = new PramaanClient({
  baseUrl: process.env.PRAMAAN_URL!,
  apiKey: process.env.PRAMAAN_KEY,          // X-API-Key
  hmacSecret: process.env.PRAMAAN_SECRET,   // X-Timestamp + X-Signature (HMAC-SHA256 of "<ts>.<body>")
  timeoutMs: 3000,
  retries: 1,                               // 429 / 502-504 / network, ≥ 1 s apart, same request_id
  fallback: "challenge",                    // service unreachable → SMS OTP (fail safe), marked degraded
});

app.post("/api/pay/authenticate", async (req, res) => {
  const decision = await pramaan.authenticate({ ...req.body, user_id: req.session.userId });  // never trust the client's id
  res.json({ decision: decision.decision, challenge_type: decision.challenge_type, message: decision.message_en });
});

app.post("/api/pay/verify", async (req, res) => {
  res.json(await pramaan.verifyChallenge(req.body.decision_id, req.body.passed));  // pass → allow, fail → block + 30 min lock
});` },
  android: { lang: "kotlin", title: "com.pramaan.sdk · Android 7+ (API 24), no dependencies", code: `class App : Application() {
    override fun onCreate() {
        super.onCreate()
        Pramaan.init(this, PramaanConfig(consent = userConsented, simChangeHours = { telecomSimSwapApi.hours(msisdn) }))
    }
}

class PayActivity : Activity() {
    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        Pramaan.get().startFlow()   // touches on every activity are observed automatically
        val pad = Pramaan.get().pinPad(this, maxLength = 6) { pin -> submit(pin) }   // records key timing, never digits
        setContentView(pad)
    }

    private fun submit(pin: String) = thread {
        val request = Pramaan.get().collect(userId, transaction = AuthTransaction(amount = 2500.0, payeeId = "kirana-sharma"))
        val decision = backend.authenticate(request)            // your server adds the key + signature
        runOnUiThread {
            when (decision.decision) {
                Decision.ALLOW -> paid()
                Decision.CHALLENGE -> stepUp(decision.challengeType!!)
                Decision.BLOCK -> blocked(decision.messageEn)
            }
        }
    }
}` },
  python: { lang: "python", title: "Python · any backend", code: `import hashlib, hmac, json, time, requests

def authenticate(req: dict) -> dict:
    body = json.dumps(req, separators=(",", ":"))
    ts = str(int(time.time()))
    sig = hmac.new(SECRET.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
    r = requests.post(f"{PRAMAAN_URL}/v1/authenticate", data=body, timeout=3, headers={
        "Content-Type": "application/json", "X-API-Key": API_KEY, "X-Timestamp": ts, "X-Signature": f"sha256={sig}"})
    r.raise_for_status()
    return r.json()   # decision, risk_score, challenge_type, reasons (EN/HI), signals (SHAP), latency_ms` },
  curl: { lang: "bash", title: "bash · signed request", code: `BODY='{"user_id":"demo-asha","device":{"device_id":"asha-pixel-7","platform":"android"},"transaction":{"amount":640,"payee_id":"kirana-sharma"}}'
TS=$(date +%s)
SIG=$(printf '%s' "$TS.$BODY" | openssl dgst -sha256 -hmac "$PRAMAAN_SECRET" -hex | cut -d' ' -f2)
curl -s "$PRAMAAN_URL/v1/authenticate" -H "Content-Type: application/json" \\
  -H "X-API-Key: $PRAMAAN_KEY" -H "X-Timestamp: $TS" -H "X-Signature: sha256=$SIG" -d "$BODY"` },
};

type Cov = "yes" | "no" | "server" | "partial";
const COVERAGE: { signal: string; family: Family; features: string; web: Cov; android: Cov; note: string }[] = [
  { signal: "Touch dynamics", family: "behaviour", features: "bio_dev", web: "partial", android: "yes", note: "21 features per gesture; web on touchscreens, motion sensors where the browser allows" },
  { signal: "Typing rhythm", family: "behaviour", features: "typing_dev", web: "partial", android: "yes", note: "31 timings per attempt; web with physical keyboards, Android with the SDK's PIN pad" },
  { signal: "Time to submit, input count", family: "behaviour", features: "fast_submit, low_input", web: "yes", android: "yes", note: "from startFlow() to collect()" },
  { signal: "Unknown caller on the line", family: "behaviour", features: "unknown_call_active", web: "no", android: "yes", note: "audio mode (cellular / VoIP); caller vs contacts with optional permissions" },
  { signal: "Screen being shared", family: "behaviour", features: "screen_share_active", web: "no", android: "yes", note: "Android 15 screen-recording callback, cast displays" },
  { signal: "Device identity & trust", family: "device", features: "device_new, device_untrusted, n_devices_30d", web: "yes", android: "yes", note: "install ID; trust is learned server-side (7 days + 3 payments, or a strong challenge)" },
  { signal: "Emulator / automation", family: "device", features: "emulator", web: "yes", android: "yes", note: "WebDriver / headless browser; emulator build properties" },
  { signal: "Rooted / jailbroken", family: "device", features: "rooted", web: "no", android: "yes", note: "su binaries, test-keys, root managers; pair with Play Integrity in production" },
  { signal: "Remote-control app", family: "device", features: "remote_access_app", web: "no", android: "yes", note: "AnyDesk, TeamViewer QS, RustDesk… with accessibility control or screen capture" },
  { signal: "SIM changed", family: "device", features: "sim_fresh", web: "no", android: "yes", note: "subscription change on the phone, or a telecom SIM-swap API via simChangeHours" },
  { signal: "IP reputation, fan-out, travel", family: "device", features: "ip_datacenter, ip_anonymiser, ip_accounts_1h, geo_speed, new_city", web: "server", android: "server", note: "from the connection and the load balancer's geo header" },
  { signal: "Amount, payee, history", family: "transaction", features: "amt_z, payee_new, spend_24h_z, txn_count_1h, hour_rarity…", web: "server", android: "server", note: "the app sends amount + payee; history lives in the service's state" },
  { signal: "Payee risk", family: "transaction", features: "payee_risk", web: "server", android: "server", note: "payee intelligence (mule-network model) when the receiving account is known" },
];

const API: [string, string, string][] = [
  ["POST", "/v1/authenticate", "Decide a login or payment: decision, risk, challenge type, EN/HI reasons, SHAP signals, per-stage timings"],
  ["POST", "/v1/challenge/verify", "Report the step-up result: pass → allow (+ trust the device for passkey / call-back), fail → block + 30-min lock"],
  ["POST", "/v1/keystroke/enroll", "Enrol a typing profile (≥ 5 attempts × 31 timings)"],
  ["POST", "/v1/keystroke/verify", "Score one attempt against the profile: score, threshold, typing_deviation"],
  ["POST", "/v1/biometrics/enroll", "Enrol a touch profile (≥ 20 gestures)"],
  ["POST", "/v1/biometrics/verify", "Score 10–20 gestures against the profile (BiLSTM + LDA fusion)"],
  ["GET", "/v1/auth/decisions", "Audit feed: latest decisions and challenge results"],
  ["GET", "/v1/auth/stats", "Counters: decisions by type, challenge mix, p50/p95 latency, backends"],
  ["GET", "/health", "Loaded services, security mode, model version, state and audit backends"],
];

/** Integration guide: the flow, quickstarts per platform, what each SDK can see, the API, security and privacy. */
export function Developers() {
  const [tab, setTab] = useState<Tab>("web");
  const s = SNIPPETS[tab];
  return (
    <div className="mx-auto max-w-[96rem] space-y-5">
      <header>
        <p className="text-eyebrow text-label-tertiary">Developers</p>
        <h1 className="mt-1 text-large-title">Integrate in an afternoon</h1>
        <p className="mt-1 max-w-[52rem] text-subheadline text-label-secondary">
          Two SDKs collect the signals on the customer&apos;s device; your backend forwards them with its API key and
          signature; the service answers allow, challenge (and which one) or block in tens of milliseconds, with the
          signals behind it.
        </p>
      </header>

      <Panel eyebrow="Flow" title="Where each piece runs" icon={Workflow} tint="var(--color-sys-indigo)">
        <Flow />
      </Panel>

      <Panel eyebrow="Quickstart" title="Pick your platform">
        <SegmentedControl<Tab> label="Platform" value={tab} onChange={setTab} options={[
          { value: "web", label: "Web" }, { value: "server", label: "Node server" }, { value: "android", label: "Android" },
          { value: "python", label: "Python" }, { value: "curl", label: "cURL" },
        ]} />
        <CodeBlock className="mt-4" lang={s.lang} title={s.title} code={s.code} />
      </Panel>

      <ChallengePreview />

      <ApiPlayground />

      <Panel eyebrow="Coverage" title="What each SDK can see">
        <div className="relative overflow-x-auto">
          <table className="w-full min-w-[52rem] text-footnote">
            <thead>
              <tr className="text-left text-caption-1 text-label-tertiary">
                <th className="pb-2 font-medium">signal</th><th className="pb-2 font-medium">model features</th>
                <th className="whitespace-nowrap px-2 pb-2 text-center font-medium">Web SDK</th><th className="whitespace-nowrap px-2 pb-2 text-center font-medium">Android SDK</th><th className="pb-2 font-medium">how</th>
              </tr>
            </thead>
            <tbody>
              {COVERAGE.map((c) => (
                <tr key={c.signal} className="border-t border-separator/40 align-top">
                  <td className="py-2 pr-3"><span className="flex items-center gap-2"><span className="size-2 rounded-full" style={{ background: FAMILY_TINT[c.family] }} aria-hidden />{c.signal}</span></td>
                  <td className="py-2 pr-3 font-mono text-caption-1 text-label-secondary">{c.features}</td>
                  <td className="py-2 text-center"><CovCell v={c.web} /></td>
                  <td className="py-2 text-center"><CovCell v={c.android} /></td>
                  <td className="py-2 text-caption-1 text-label-tertiary">{c.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-caption-1 text-label-tertiary">Missing signals are not errors: the model learned web requests without touch data, unknown payees and first sightings (XGBoost default branches).</p>
      </Panel>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Panel eyebrow="API" title="Endpoints" icon={Server} tint="var(--color-sys-blue)">
          <ul className="divide-y divide-separator/40">
            {API.map(([m, p, d]) => (
              <li key={p} className="grid grid-cols-[3.5rem_minmax(0,14rem)_1fr] items-baseline gap-3 py-2.5 text-footnote">
                <span className={`rounded-full px-2 py-0.5 text-center font-mono text-caption-2 ${m === "POST" ? "bg-sys-blue/15 text-sys-blue" : "bg-sys-green/15 text-sys-green"}`}>{m}</span>
                <span className="truncate font-mono">{p}</span>
                <span className="text-label-secondary">{d}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-caption-1 text-label-tertiary">OpenAPI docs at <span className="font-mono">/docs</span> on any running instance.</p>
        </Panel>
        <div className="space-y-5">
          <Panel eyebrow="Security" title="Built for the payment path" icon={Lock} tint="var(--color-sys-red)">
            <ul className="space-y-2 text-footnote text-label-secondary">
              {["API key per client, HMAC-SHA256 over timestamp + body, 5-minute window, each signature accepted once",
                "Per-key token-bucket rate limit; TLS at the load balancer (Cloud Run, asia-south1)",
                "SDK clients retry ≥ 1 s apart with the same request_id, and fall back to an SMS OTP if the service is down",
                "Secrets stay on your server: the browser and app SDKs never hold the key or the signing secret"].map((t) => (
                <li key={t} className="flex gap-2"><Check className="mt-0.5 size-4 shrink-0 text-sys-green" aria-hidden />{t}</li>
              ))}
            </ul>
          </Panel>
          <Panel eyebrow="Privacy" title="What leaves the device" icon={ShieldCheck} tint="var(--color-sys-green)">
            <ul className="space-y-2 text-footnote text-label-secondary">
              {["Gesture features, never coordinates or sensor streams; key timings, never keys or digits",
                "Behavioural data only with consent (DPDP purpose behavioural_biometrics); device and session signals without",
                "Profiles are embeddings; identifiers are opaque and hashed before any cross-institution use",
                "Every decision is logged with its reasons and model version for disputes"].map((t) => (
                <li key={t} className="flex gap-2"><Check className="mt-0.5 size-4 shrink-0 text-sys-green" aria-hidden />{t}</li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>

      <Panel eyebrow="Verification" title="The SDKs compute what the models were trained on" icon={CircleCheck} tint="var(--color-sys-green)">
        <div className="grid gap-4 md:grid-cols-3">
          {[
            ["Golden vectors", "sdk/spec/make_golden.py runs the training pipeline's own feature code (HMOG gestures, CMU timings) and the gateway's signer; both SDKs must reproduce the outputs to 1e-9."],
            ["Web SDK · 31 + 7 tests", "Feature math, DOM wiring and the step-up screens (happy-dom), client retries, timeouts and fallbacks; plus 7 end-to-end tests against a running API, including a secured gateway (signed requests pass, unsigned and wrong signatures get 401)."],
            ["Android SDK · 13 tests", "Same golden vectors on the JVM, client behaviour against a local HTTP server, and a live test against the API. The library and the sample app compile against the Android 35 framework."],
          ].map(([t, d]) => (
            <div key={t} className="squircle rounded-[var(--radius-card)] bg-fill-quaternary p-4">
              <p className="text-headline">{t}</p>
              <p className="mt-1 text-footnote text-label-secondary">{d}</p>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function CovCell({ v }: { v: Cov }) {
  if (v === "yes") return <span className="inline-flex items-center gap-1 text-sys-green"><Check className="size-4" aria-hidden /><span className="sr-only">yes</span></span>;
  if (v === "partial") return <span className="whitespace-nowrap rounded-full bg-sys-yellow/15 px-2 py-0.5 text-caption-2 text-sys-yellow">where available</span>;
  if (v === "server") return <span className="whitespace-nowrap rounded-full bg-fill-tertiary px-2 py-0.5 text-caption-2 text-label-secondary">server-side</span>;
  return <span className="inline-flex text-label-quaternary"><Minus className="size-4" aria-hidden /><span className="sr-only">no</span></span>;
}

function Flow() {
  const steps: { icon: typeof Smartphone; title: string; where: string; body: string; tint: string }[] = [
    { icon: Smartphone, title: "Collect", where: "customer's phone / browser", body: "SDK: gestures, typing timings, device flags, session timing. No secrets.", tint: "var(--color-fam-behaviour)" },
    { icon: Server, title: "Forward", where: "your backend", body: "Adds user id from the session, API key and HMAC signature; calls /v1/authenticate.", tint: "var(--color-sys-blue)" },
    { icon: ShieldCheck, title: "Decide", where: "PRAMAAN", body: "Touch + typing models, 27 features, monotone XGBoost, SHAP, cost-based policy.", tint: "var(--color-sys-indigo)" },
    { icon: CircleCheck, title: "Act", where: "app + backend", body: "Allow, run the chosen step-up, or block; report the step-up with /v1/challenge/verify.", tint: "var(--color-sys-green)" },
  ];
  return (
    <ol className="grid gap-3 md:grid-cols-4">
      {steps.map((s, i) => (
        <li key={s.title} className="relative">
          <div className="squircle h-full rounded-[var(--radius-card)] bg-fill-quaternary p-4">
            <div className="flex items-center gap-2">
              <span className="flex size-8 items-center justify-center rounded-[0.6rem]" style={{ background: `color-mix(in srgb, ${s.tint} 16%, transparent)`, color: s.tint }}>
                <s.icon className="size-4" aria-hidden />
              </span>
              <span className="font-mono text-caption-1 text-label-tertiary">{i + 1}</span>
            </div>
            <p className="mt-3 text-headline">{s.title}</p>
            <p className="text-caption-1 text-label-tertiary">{s.where}</p>
            <p className="mt-2 text-footnote text-label-secondary">{s.body}</p>
          </div>
          {i < steps.length - 1 && <ArrowRight className="absolute -right-[0.95rem] top-1/2 z-10 hidden size-4 -translate-y-1/2 text-label-tertiary md:block" aria-hidden />}
        </li>
      ))}
    </ol>
  );
}
