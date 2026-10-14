import { Fingerprint, Globe, Receipt, Smartphone } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { inr } from "@/config/authSignals";
import type { DemoRun } from "@/types/auth";

type Row = [label: string, value: string, flagged?: boolean];

/** What the client SDK sent, grouped as the problem statement frames it: behaviour, device, transaction (+ network).
 *  A value is highlighted when the model's matching feature fired. */
export function RequestCard({ run }: { run: DemoRun | null }) {
  if (!run) return null;
  const { device: d, network: n, behaviour: b, transaction: t } = run.request;
  const f = run.response.features;
  const on = (k: string, min = 0.5) => (f[k] ?? 0) >= min;
  const groups: { title: string; icon: LucideIcon; tint: string; rows: Row[] }[] = [
    {
      title: "Behaviour", icon: Fingerprint, tint: "var(--color-sys-purple)", rows: [
        ["Touch", b.gestures ? String(b.gestures) : "no touch data", on("bio_dev", 0.5)],
        ["Touch deviation", f.bio_dev == null ? "—" : f.bio_dev.toFixed(2), on("bio_dev", 0.5)],
        ["Time to submit", b.time_to_submit_s != null ? `${b.time_to_submit_s} s` : "—", on("fast_submit")],
        ["Input events", b.input_events != null ? String(b.input_events) : "—", on("low_input")],
        ["Unknown call active", b.unknown_call_active ? "yes" : "no", on("unknown_call_active")],
      ],
    },
    {
      title: "Device", icon: Smartphone, tint: "var(--color-sys-cyan)", rows: [
        ["Device", d.device_id + (on("device_new") ? " (new)" : on("device_untrusted") ? " (untrusted)" : " (trusted)"), on("device_new") || on("device_untrusted")],
        ["Emulator / rooted", `${d.is_emulator ? "emulator" : "no"} / ${d.is_rooted ? "rooted" : "no"}`, on("emulator") || on("rooted")],
        ["Remote-access app", d.remote_access_app ? "running" : "no", on("remote_access_app")],
        ["Screen share", d.screen_share_active ? "on" : "off", on("screen_share_active")],
        ["SIM changed", d.sim_change_hours != null ? `${d.sim_change_hours} h ago` : "no / unknown", on("sim_fresh", 0.01)],
        ["Other accounts on device", String(f.accounts_on_device ?? 0), on("accounts_on_device", 2)],
      ],
    },
    {
      title: "Network", icon: Globe, tint: "var(--color-sys-blue)", rows: [
        ["IP", n.ip ?? "—", on("ip_datacenter") || on("ip_anonymiser")],
        ["Location", n.city ?? "—", on("new_city") || on("geo_speed", Math.log1p(900))],
        ["Travel speed", f.geo_speed == null ? "—" : `${Math.round(Math.expm1(f.geo_speed)).toLocaleString("en-IN")} km/h`, on("geo_speed", Math.log1p(900))],
      ],
    },
    {
      title: "Transaction", icon: Receipt, tint: "var(--color-sys-orange)", rows: [
        ["Type", `${run.request.event_type} · ${run.request.channel}`],
        ["Amount", t.amount > 0 ? inr(t.amount) : "—", on("amt_z", 2.5)],
        ["Payee", t.payee_id ? t.payee_id + (on("payee_new") ? " (new)" : "") : "—", on("payee_new")],
        ["Payee risk", t.payee_risk != null ? t.payee_risk.toFixed(2) : "unknown", on("payee_risk", 0.5)],
      ],
    },
  ];
  return (
    <section className="grid gap-3 sm:grid-cols-2">
      {groups.map((g) => (
        <div key={g.title} className="material-regular squircle rounded-[var(--radius-card)] p-4">
          <p className="mb-2 flex items-center gap-2 text-eyebrow text-label-tertiary">
            <g.icon className="size-3.5" style={{ color: g.tint }} aria-hidden /> {g.title}
          </p>
          <dl className="space-y-1">
            {g.rows.map(([k, v, flag]) => (
              <div key={k} className="flex items-baseline justify-between gap-3 text-footnote">
                <dt className="text-label-secondary">{k}</dt>
                <dd className={`truncate text-right font-mono ${flag ? "rounded bg-sys-red/15 px-1.5 text-sys-red" : ""}`} title={v}>{v}</dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </section>
  );
}
