"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { ChevronLeft, ChevronRight, Download, Globe, Search, Smartphone, X } from "lucide-react";
import { loadFeed } from "@/api/auth";
import { useTraffic } from "@/api/console";
import { IconButton } from "@/components/common/Button";
import { SegmentedControl } from "@/components/common/SegmentedControl";
import { DecisionBadge } from "@/components/ui/DecisionBadge";
import { ATTACK_LABEL, CHALLENGE_LABEL, CHALLENGE_SHORT, FAMILY_LABEL, FAMILY_TINT, GENUINE_KIND_LABEL, SIGNAL_FAMILY, SIGNAL_LABEL, inr, pct } from "@/config/authSignals";
import { spring } from "@/config/motion";
import { useConsole } from "@/context/ConsoleContext";
import type { ChallengeType, Decision, Family } from "@/types/auth";

type Src = "day" | "session" | "live";

/** One audit row, whatever its source. */
interface Entry {
  id: string;
  time: string;
  sort: number;
  user: string;
  channel: string;
  amount: number;
  risk: number;
  decision: Decision;
  challenge: ChallengeType | null;
  final: string | null;
  truth: string | null;
  attack: boolean | null;
  signals: [string, number][];
  fam?: [number, number, number];
  latency?: number;
  rule?: string | null;
  note?: string;
}

const PAGE = 25;
const hms = (s: number) => `${String(Math.floor(s / 3600)).padStart(2, "0")}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

/**
 * Every decision with the signals behind it: the recorded test day, this browser session's decisions, or the running
 * service's own audit feed. Filter, search, open a row for its explanation, export what you see as CSV (decisions are
 * kept with their reasons for disputes: RBI's directions make the issuer answer for failed authentication).
 */
export function AuditLog() {
  const { source, session } = useConsole();
  const { data: traffic } = useTraffic();
  const params = useSearchParams();
  const [src, setSrc] = useState<Src>("day");
  const [live, setLive] = useState<Entry[]>([]);
  const [q, setQ] = useState(params?.get("q") ?? "");
  const [dec, setDec] = useState<"all" | Decision>("all");
  const [attacksOnly, setAttacksOnly] = useState(false);
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<Entry | null>(null);

  useEffect(() => {
    if (src !== "live" || source !== "live") return;
    let on = true;
    const load = () => loadFeed().then(({ rows }) => on && setLive(rows.filter((r) => r.kind === "decision").map((r) => ({
      id: r.decision_id, time: new Date(r.ts * 1000).toLocaleTimeString("en-IN", { hour12: false }), sort: r.ts, user: r.user_id,
      channel: "—", amount: r.amount ?? 0, risk: r.risk_score ?? NaN, decision: r.decision as Decision,
      challenge: (r.challenge_type as ChallengeType) ?? null, final: null, truth: null, attack: null,
      signals: (r.reasons ?? []).map((s) => [s, NaN] as [string, number]), latency: r.latency_ms,
    }))));
    load();
    const t = setInterval(load, 5000);
    return () => {
      on = false;
      clearInterval(t);
    };
  }, [src, source]);

  const entries = useMemo<Entry[]>(() => {
    if (src === "day") {
      return (traffic?.rows ?? []).map((r, i) => ({
        id: `d${traffic!.meta.day}-${i}`, time: hms(r.t), sort: r.t, user: r.u, channel: r.ch, amount: r.amt, risk: r.p, decision: r.d,
        challenge: r.c, final: r.d === "challenge" ? r.f : null, truth: r.atk ? ATTACK_LABEL[r.atk] : GENUINE_KIND_LABEL[r.kind] ?? r.kind,
        attack: !!r.atk, signals: r.top, fam: r.fam, latency: r.ms, rule: r.rule,
        note: r.d === "challenge" ? (r.pass ? "challenge passed" : r.atk ? "attacker failed the challenge" : "customer abandoned") : undefined,
      })).reverse();
    }
    if (src === "session") {
      return session.map((e) => ({
        id: e.run.response.decision_id, time: new Date(e.at).toLocaleTimeString("en-IN", { hour12: false }), sort: e.at,
        user: e.run.request.user_id, channel: e.run.request.channel, amount: e.run.response.amount, risk: e.run.response.risk_score,
        decision: e.run.response.decision, challenge: e.run.response.challenge_type, final: e.outcome?.decision ?? null,
        truth: e.run.title.replace(/^(Genuine|Attack): /, ""), attack: e.run.is_attack,
        signals: e.run.response.signals.filter((s) => s.contribution >= 0.1).slice(0, 3).map((s) => [s.name, s.contribution] as [string, number]),
        fam: [e.run.response.family_contribution.behaviour, e.run.response.family_contribution.device, e.run.response.family_contribution.transaction],
        latency: e.run.response.latency_ms, rule: e.run.response.rule, note: e.source === "live" ? "decided live" : "recorded",
      }));
    }
    return live;
  }, [src, traffic, session, live]);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    return entries.filter((e) => (dec === "all" || e.decision === dec) && (!attacksOnly || e.attack) &&
      (!s || e.user.toLowerCase().includes(s) || e.id.toLowerCase().includes(s) || (e.truth ?? "").toLowerCase().includes(s) ||
        e.signals.some(([n]) => (SIGNAL_LABEL[n] ?? n).toLowerCase().includes(s))));
  }, [entries, q, dec, attacksOnly]);
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE));
  const cur = Math.min(page, pages - 1);
  const rows = filtered.slice(cur * PAGE, cur * PAGE + PAGE);
  const counts = useMemo(() => ({
    allow: entries.filter((e) => e.decision === "allow").length, challenge: entries.filter((e) => e.decision === "challenge").length,
    block: entries.filter((e) => e.decision === "block").length,
  }), [entries]);

  const exportCsv = () => {
    const head = ["decision_id", "time", "user_id", "channel", "amount_inr", "risk", "decision", "challenge", "final", "ground_truth", "top_signals", "latency_ms"];
    const esc = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const lines = [head.join(","), ...filtered.map((e) => [e.id, e.time, e.user, e.channel, e.amount, e.risk, e.decision, e.challenge, e.final, e.truth,
      e.signals.map(([n]) => n).join(" "), e.latency].map(esc).join(","))];
    const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `pramaan-audit-${src}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="mx-auto max-w-[96rem] space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-eyebrow text-label-tertiary">Audit log</p>
          <h1 className="mt-1 text-large-title">Every decision, and why</h1>
          <p className="mt-1 max-w-[50rem] text-subheadline text-label-secondary">
            Each decision is logged with its risk, the step-up, the outcome, the signals behind it and the model version:
            what an analyst needs to answer a dispute.
          </p>
        </div>
        <SegmentedControl<Src> label="Source" value={src} onChange={(v) => { setSrc(v); setPage(0); setOpen(null); }} options={[
          { value: "day", label: `Recorded day${traffic ? ` · ${traffic.rows.length.toLocaleString("en-IN")}` : ""}` },
          { value: "session", label: `This session · ${session.length}` },
          ...(source === "live" ? [{ value: "live" as Src, label: "Live service" }] : []),
        ]} />
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <label className="flex h-9 min-w-[16rem] flex-1 items-center gap-2 rounded-full bg-fill-tertiary px-3.5 sm:max-w-[24rem]">
          <Search className="size-4 text-label-tertiary" aria-hidden />
          <input value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} placeholder="Search user, decision id, attack type, signal"
            className="min-w-0 flex-1 bg-transparent text-footnote text-label outline-none placeholder:text-label-tertiary" aria-label="Search the audit log" />
        </label>
        <SegmentedControl<"all" | Decision> size="small" label="Decision" value={dec} onChange={(v) => { setDec(v); setPage(0); }} options={[
          { value: "all", label: `All` }, { value: "allow", label: `Allow ${counts.allow}` },
          { value: "challenge", label: `Challenge ${counts.challenge}` }, { value: "block", label: `Block ${counts.block}` },
        ]} />
        {src !== "live" && (
          <button onClick={() => { setAttacksOnly((a) => !a); setPage(0); }} aria-pressed={attacksOnly}
            className={`h-8 rounded-full px-3 text-caption-1 ${attacksOnly ? "bg-sys-red/20 text-sys-red" : "bg-fill-tertiary text-label-secondary hover:text-label"}`}>
            Attacks only (ground truth)
          </button>
        )}
        <button onClick={exportCsv} className="ml-auto flex h-8 items-center gap-1.5 rounded-full bg-fill-tertiary px-3 text-caption-1 text-label-secondary hover:text-label">
          <Download className="size-3.5" aria-hidden /> Export {filtered.length.toLocaleString("en-IN")} rows
        </button>
      </div>

      <div className="material-regular squircle overflow-hidden rounded-[var(--radius-panel)]">
        <div className="relative overflow-x-auto">
          <table className="w-full min-w-[60rem] text-footnote">
            <thead>
              <tr className="border-b border-separator/60 text-left text-caption-1 text-label-tertiary">
                {["Time", "User", "", "Amount", "Risk", "Decision", "Outcome", src === "day" ? "Ground truth" : "Scenario", "Top signals"].map((h, i) => (
                  <th key={i} scope="col" className="px-3 py-2.5 font-medium first:pl-5">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.id} onClick={() => setOpen(e)} tabIndex={0} onKeyDown={(k) => k.key === "Enter" && setOpen(e)}
                  className={`cursor-pointer border-b border-separator/30 transition-colors hover:bg-fill-quaternary ${open?.id === e.id ? "bg-fill-tertiary" : ""}`}>
                  <td className="px-3 py-2 pl-5 font-mono text-caption-1 tabular-nums text-label-secondary">{e.time}</td>
                  <td className="px-3 py-2 font-mono text-caption-1">{e.user}</td>
                  <td className="px-1 py-2 text-label-tertiary">{e.channel === "web" ? <Globe className="size-3.5" aria-label="web" /> : e.channel === "mobile" ? <Smartphone className="size-3.5" aria-label="mobile" /> : null}</td>
                  <td className="px-3 py-2 tabular-nums">{e.amount > 0 ? inr(e.amount) : "login"}</td>
                  <td className="px-3 py-2 font-mono text-caption-1 tabular-nums">{pct(e.risk)}</td>
                  <td className="px-3 py-2"><DecisionBadge decision={e.decision} size="xs" /></td>
                  <td className="px-3 py-2 text-caption-1 text-label-secondary">
                    {e.challenge ? `${CHALLENGE_SHORT[e.challenge]} → ${e.final ?? "pending"}` : "—"}
                  </td>
                  <td className={`px-3 py-2 text-caption-1 ${e.attack ? "text-sys-red" : "text-label-secondary"}`}>{e.truth ?? "—"}</td>
                  <td className="max-w-[16rem] px-3 py-2">
                    <span className="flex flex-wrap gap-1">
                      {e.signals.slice(0, 3).map(([n]) => (
                        <span key={n} className="flex items-center gap-1 rounded-full bg-fill-quaternary px-1.5 py-px text-caption-2">
                          <span className="size-1.5 rounded-full" style={{ background: FAMILY_TINT[SIGNAL_FAMILY[n] ?? "device"] }} aria-hidden />
                          {SIGNAL_LABEL[n] ?? n}
                        </span>
                      ))}
                    </span>
                  </td>
                </tr>
              ))}
              {!rows.length && (
                <tr><td colSpan={9} className="px-5 py-10 text-center text-footnote text-label-tertiary">
                  {src === "day" && !traffic ? "Loading the recorded day…" : src === "session" ? "No decisions in this session yet: run a scenario in the decision lab." :
                    src === "live" && !live.length ? "Waiting for the service's audit feed…" : "Nothing matches."}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between gap-3 px-5 py-3 text-caption-1 text-label-secondary">
          <span>{filtered.length.toLocaleString("en-IN")} decisions · page {cur + 1} of {pages}</span>
          <span className="flex gap-1.5">
            <IconButton label="Previous page" onClick={() => setPage(Math.max(0, cur - 1))} disabled={cur === 0} className="size-8 disabled:opacity-30"><ChevronLeft className="size-4" /></IconButton>
            <IconButton label="Next page" onClick={() => setPage(Math.min(pages - 1, cur + 1))} disabled={cur >= pages - 1} className="size-8 disabled:opacity-30"><ChevronRight className="size-4" /></IconButton>
          </span>
        </div>
      </div>

      <AnimatePresence>
        {open && <Drawer e={open} onClose={() => setOpen(null)} />}
      </AnimatePresence>
    </div>
  );
}

function Drawer({ e, onClose }: { e: Entry; onClose: () => void }) {
  useEffect(() => {
    const k = (ev: KeyboardEvent) => ev.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  const fams: Family[] = ["behaviour", "device", "transaction"];
  const scale = Math.max(1, ...(e.fam ?? [0]).map(Math.abs));
  return (
    <motion.aside initial={{ x: 40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 40, opacity: 0 }} transition={spring.sheet}
      className="material-thick fixed inset-y-3 right-3 z-40 w-[min(26rem,calc(100vw-1.5rem))] overflow-y-auto rounded-[var(--radius-panel)] p-5"
      role="dialog" aria-label={`Decision ${e.id}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-eyebrow text-label-tertiary">Decision {e.id}</p>
          <p className="mt-1 text-title-3">{e.amount > 0 ? inr(e.amount) : "Login"} · {e.user}</p>
          <p className="text-caption-1 text-label-tertiary">{e.time} · {e.channel}{e.latency ? ` · ${e.latency.toFixed(0)} ms` : ""}</p>
        </div>
        <IconButton label="Close" onClick={onClose}><X className="size-4" /></IconButton>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <DecisionBadge decision={e.decision} size="md" />
        {e.challenge && <span className="text-subheadline">{CHALLENGE_LABEL[e.challenge].title}</span>}
        {e.final && <span className="text-subheadline text-label-secondary">→ {e.final}</span>}
      </div>
      <dl className="mt-4 space-y-1.5 text-footnote">
        {[["Risk", pct(e.risk)], ["Ground truth / scenario", e.truth ?? "—"], ["Outcome", e.note ?? "—"], ["Rule", e.rule ?? "none"]].map(([k, v]) => (
          <div key={k} className="flex justify-between gap-3 border-b border-separator/40 pb-1.5">
            <dt className="text-label-secondary">{k}</dt><dd className={k === "Ground truth / scenario" && e.attack ? "text-sys-red" : ""}>{v}</dd>
          </div>
        ))}
      </dl>
      {e.fam && (
        <div className="mt-5 space-y-2.5">
          <p className="text-eyebrow text-label-tertiary">Risk by signal family (log-odds)</p>
          {fams.map((f, i) => {
            const v = e.fam![i];
            return (
              <div key={f} className="grid grid-cols-[6rem_1fr_3rem] items-center gap-2">
                <span className="text-footnote">{FAMILY_LABEL[f]}</span>
                <div className="relative h-2 rounded-full bg-fill-quaternary">
                  <span className="absolute inset-y-[-3px] left-1/2 w-px bg-separator" aria-hidden />
                  <span className="absolute inset-y-0 rounded-[4px]" style={{ width: `${Math.min(50, (50 * Math.abs(v)) / scale)}%`,
                    background: v >= 0 ? FAMILY_TINT[f] : "var(--color-gray-2)", [v >= 0 ? "left" : "right"]: "50%" }} />
                </div>
                <span className="text-right font-mono text-caption-1 tabular-nums">{v > 0 ? "+" : ""}{v.toFixed(2)}</span>
              </div>
            );
          })}
        </div>
      )}
      <div className="mt-5">
        <p className="mb-2 text-eyebrow text-label-tertiary">Strongest signals</p>
        {e.signals.length ? (
          <ul className="space-y-1.5">
            {e.signals.map(([n, c]) => (
              <li key={n} className="flex items-center justify-between gap-3 text-footnote">
                <span className="flex items-center gap-2"><span className="size-2 rounded-full" style={{ background: FAMILY_TINT[SIGNAL_FAMILY[n] ?? "device"] }} aria-hidden />{SIGNAL_LABEL[n] ?? n}</span>
                {Number.isFinite(c) && <span className="font-mono text-caption-1 text-label-secondary">+{c.toFixed(2)}</span>}
              </li>
            ))}
          </ul>
        ) : <p className="text-footnote text-label-tertiary">No signal raised the risk noticeably.</p>}
      </div>
    </motion.aside>
  );
}
