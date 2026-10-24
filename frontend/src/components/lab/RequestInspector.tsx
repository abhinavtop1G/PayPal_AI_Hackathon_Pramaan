"use client";

import { useState } from "react";
import { Fingerprint, Globe, Receipt, Smartphone, type LucideIcon } from "lucide-react";
import { SegmentedControl } from "@/components/common/SegmentedControl";
import { CodeBlock } from "@/components/ui/CodeBlock";
import { FAMILY_TINT, inr } from "@/config/authSignals";
import type { DemoRun } from "@/types/auth";

type Tab = "signals" | "request" | "response" | "integrate";
type Row = [label: string, value: string, flagged?: boolean];

/** What the SDK sent and what came back: the signals grouped by family (fired ones flagged), raw JSON both ways,
 *  and the integration code that would produce this request. */
export function RequestInspector({ run }: { run: DemoRun }) {
  const [tab, setTab] = useState<Tab>("signals");
  return (
    <div>
      <SegmentedControl<Tab> label="Inspector view" value={tab} onChange={setTab} size="small" options={[
        { value: "signals", label: "Signals" }, { value: "request", label: "Request" },
        { value: "response", label: "Response" }, { value: "integrate", label: "Integrate" },
      ]} />
      <div className="mt-4">
        {tab === "signals" && <SignalTable run={run} />}
        {tab === "request" && <CodeBlock lang="json" title="POST /v1/authenticate · request" code={JSON.stringify(run.request, null, 2)} maxHeight="26rem" />}
        {tab === "response" && <CodeBlock lang="json" title="200 OK · response" code={JSON.stringify(run.response, null, 2)} maxHeight="26rem" />}
        {tab === "integrate" && <Integrate run={run} />}
      </div>
    </div>
  );
}

function SignalTable({ run }: { run: DemoRun }) {
  const { device: d, network: n, behaviour: b, transaction: t } = run.request;
  const f = run.response.features;
  const on = (k: string, min = 0.5) => (f[k] ?? 0) >= min;
  const groups: { title: string; icon: LucideIcon; tint: string; rows: Row[] }[] = [
    { title: "Behaviour", icon: Fingerprint, tint: FAMILY_TINT.behaviour, rows: [
      ["Touch", b.gestures ? String(b.gestures) : "no touch data", on("bio_dev", 0.5)],
      ["Touch deviation", f.bio_dev == null ? "—" : f.bio_dev.toFixed(2), on("bio_dev", 0.5)],
      ["Typing", b.keystrokes ? String(b.keystrokes) : "no typing data", on("typing_dev", 0)],
      ["Typing deviation", f.typing_dev == null ? "—" : f.typing_dev.toFixed(2), on("typing_dev", 0)],
      ["Time to submit", b.time_to_submit_s != null ? `${b.time_to_submit_s} s` : "—", on("fast_submit")],
      ["Input events", b.input_events != null ? String(b.input_events) : "—", on("low_input")],
      ["Unknown call active", b.unknown_call_active ? "yes" : "no", on("unknown_call_active")],
    ] },
    { title: "Device", icon: Smartphone, tint: FAMILY_TINT.device, rows: [
      ["Device", d.device_id + (on("device_new") ? " (new)" : on("device_untrusted") ? " (untrusted)" : " (trusted)"), on("device_new") || on("device_untrusted")],
      ["Emulator / rooted", `${d.is_emulator ? "emulator" : "no"} / ${d.is_rooted ? "rooted" : "no"}`, on("emulator") || on("rooted")],
      ["Remote-access app", d.remote_access_app ? "running" : "no", on("remote_access_app")],
      ["Screen share", d.screen_share_active ? "on" : "off", on("screen_share_active")],
      ["SIM changed", d.sim_change_hours != null ? `${d.sim_change_hours} h ago` : "no / unknown", on("sim_fresh", 0.01)],
      ["Other accounts on device", String(f.accounts_on_device ?? 0), on("accounts_on_device", 2)],
    ] },
    { title: "Network", icon: Globe, tint: FAMILY_TINT.device, rows: [
      ["IP", n.ip ?? "—", on("ip_datacenter") || on("ip_anonymiser")],
      ["Location", n.city ?? "—", on("new_city") || on("geo_speed", Math.log1p(900))],
      ["Travel speed", f.geo_speed == null ? "—" : `${Math.round(Math.expm1(f.geo_speed)).toLocaleString("en-IN")} km/h`, on("geo_speed", Math.log1p(900))],
      ["Accounts on this IP (1 h)", String(f.ip_accounts_1h ?? 0), on("ip_accounts_1h", 3)],
    ] },
    { title: "Transaction", icon: Receipt, tint: FAMILY_TINT.transaction, rows: [
      ["Type", `${run.request.event_type} · ${run.request.channel}`],
      ["Amount", t.amount > 0 ? inr(t.amount) : "—", on("amt_z", 2.5)],
      ["Payee", t.payee_id ? t.payee_id + (on("payee_new") ? " (new)" : "") : "—", on("payee_new")],
      ["Payee risk", f.payee_risk != null ? f.payee_risk.toFixed(2) : "unknown", on("payee_risk", 0.5)],
      ["Unusual hour", f.hour_rarity != null ? f.hour_rarity.toFixed(2) : "—", on("hour_rarity", 0.8)],
    ] },
  ];
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {groups.map((g) => (
        <div key={g.title} className="squircle min-w-0 rounded-[var(--radius-card)] bg-fill-quaternary p-3.5">
          <p className="mb-2 flex items-center gap-2 text-eyebrow text-label-tertiary">
            <g.icon className="size-3.5" style={{ color: g.tint }} aria-hidden /> {g.title}
          </p>
          <dl className="space-y-1">
            {g.rows.map(([k, v, flag]) => (
              <div key={k} className="flex items-baseline justify-between gap-3 text-footnote">
                <dt className="shrink-0 text-label-secondary">{k}</dt>
                <dd className={`min-w-0 truncate text-right font-mono ${flag ? "rounded bg-sys-red/15 px-1.5 text-sys-red" : ""}`} title={v}>{v}</dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
      <p className="text-caption-1 text-label-tertiary md:col-span-2">Highlighted: the model&apos;s matching feature fired for this request.</p>
    </div>
  );
}

function Integrate({ run }: { run: DemoRun }) {
  const [lang, setLang] = useState<"web" | "android" | "curl">("web");
  const t = run.request.transaction, uid = run.request.user_id;
  const tx = [`amount: ${t.amount}`, t.payee_id ? `payee_id: "${t.payee_id}"` : null, t.payee_is_merchant != null ? `payee_is_merchant: ${t.payee_is_merchant}` : null]
    .filter(Boolean).join(", ");
  const web = `import { Pramaan } from "@pramaan/web-sdk";

// once, when the payment screen opens
const pramaan = Pramaan.init({ consent: true });
pramaan.startFlow();
pramaan.watchTyping(document.querySelector("#password")!);

// on submit: what the browser observed, plus this payment
const request = await pramaan.collect({
  userId: "${uid}",
  eventType: "${run.request.event_type}",
  transaction: { ${tx} },
});
await fetch("/api/pay/authenticate", { method: "POST", body: JSON.stringify(request) });

// your backend (holds the API key + signing secret)
import { PramaanClient } from "@pramaan/web-sdk/server";
const pramaan = new PramaanClient({ baseUrl: process.env.PRAMAAN_URL!, apiKey: process.env.PRAMAAN_KEY,
                                    hmacSecret: process.env.PRAMAAN_SECRET });
const decision = await pramaan.authenticate(request);   // → ${run.response.decision}${run.response.challenge_type ? ` · ${run.response.challenge_type}` : ""}`;
  const android = `// Application.onCreate
Pramaan.init(this)

// payment screen
Pramaan.get().startFlow()
val pad = Pramaan.get().pinPad(this, maxLength = 10) { pin -> submit(pin) }

// on submit (off the main thread)
val request = Pramaan.get().collect(
    userId = "${uid}",
    transaction = AuthTransaction(amount = ${t.amount}${t.payee_id ? `, payeeId = "${t.payee_id}"` : ""}),
)
val decision = backend.authenticate(request)   // → ${run.response.decision.toUpperCase()}
when (decision.decision) {
    Decision.ALLOW -> pay()
    Decision.CHALLENGE -> stepUp(decision.challengeType!!)   // ${run.response.challenge_type ?? "sms_otp | passkey | bank_callback | cool_off"}
    Decision.BLOCK -> showBlocked(decision.messageEn)
}`;
  const body = { ...run.request, behaviour: { ...run.request.behaviour, gestures: undefined, keystrokes: undefined } };
  const curl = `# touch gestures and typing timings omitted here; the SDKs collect them
BODY='${JSON.stringify(body)}'
TS=$(date +%s)
SIG=$(printf '%s' "$TS.$BODY" | openssl dgst -sha256 -hmac "$PRAMAAN_SECRET" -hex | cut -d' ' -f2)
curl -s https://pramaan.example.in/v1/authenticate \\
  -H "Content-Type: application/json" -H "X-API-Key: $PRAMAAN_KEY" \\
  -H "X-Timestamp: $TS" -H "X-Signature: sha256=$SIG" \\
  -d "$BODY"`;
  return (
    <div className="space-y-3">
      <SegmentedControl<"web" | "android" | "curl"> label="Platform" size="small" value={lang} onChange={setLang}
        options={[{ value: "web", label: "Web SDK" }, { value: "android", label: "Android SDK" }, { value: "curl", label: "cURL" }]} />
      {lang === "web" && <CodeBlock lang="ts" title="TypeScript · browser + server" code={web} />}
      {lang === "android" && <CodeBlock lang="kotlin" title="Kotlin · com.pramaan.sdk" code={android} />}
      {lang === "curl" && <CodeBlock lang="bash" title="bash · signed request" code={curl} />}
    </div>
  );
}
