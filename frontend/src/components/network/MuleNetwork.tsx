"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useMemo, useState } from "react";
import { Briefcase, FolderSearch, Lock, Network, ShieldAlert, Sparkles } from "lucide-react";
import { holdCase, loadCampaign, type Source } from "@/api/demo";
import { Button } from "@/components/common/Button";
import { toast } from "@/components/common/Toaster";
import { SegmentedControl } from "@/components/common/SegmentedControl";
import { Panel } from "@/components/layout/Panel";
import { riskColor } from "@/config/policy";
import { spring } from "@/config/motion";
import { useElementSize } from "@/hooks/useElementSize";
import type { CampaignData, Case, CaseGraph, GraphNode } from "@/types/demo";
import { pct, rupees } from "@/utils/format";

/** ₹49.0 L / ₹2.3 Cr */
export function lakh(v: number) {
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(1)} Cr`;
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(1)} L`;
  return rupees(v);
}

const H = 560;

/**
 * Payee side: campaigns of mule accounts found by the receiving-side engine. Left, cases ranked by what an analyst
 * can still recover; centre, the money flow of the selected case (victims → collector accounts → onward hops →
 * exits); right, the case summary in English and Hindi with the actions it recommends. A credit hold is always a
 * human decision.
 */
export function MuleNetwork() {
  const [data, setData] = useState<CampaignData | null>(null);
  const [source, setSource] = useState<Source>("recorded");
  const [sel, setSel] = useState<string | null>(null);
  const [held, setHeld] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const ac = new AbortController();
    loadCampaign(ac.signal)
      .then((r) => {
        setData(r.data);
        setSource(r.source);
      })
      .catch(() => {});
    return () => ac.abort();
  }, []);

  if (!data)
    return (
      <div className="flex flex-col gap-4 p-4 sm:p-6" aria-busy="true" aria-label="Replaying the payee-side ledger">
        <div className="skeleton h-12 w-96 rounded-[1rem]" />
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[18rem_1fr_22rem]">
          <div className="skeleton h-[36rem] rounded-[var(--radius-panel)]" />
          <div className="skeleton h-[36rem] rounded-[var(--radius-panel)]" />
          <div className="skeleton h-[36rem] rounded-[var(--radius-panel)]" />
        </div>
        <p className="text-footnote text-label-tertiary">Replaying the payee-side ledger (about 10 s on first load)…</p>
      </div>
    );
  const c = data.cases.find((x) => x.case_id === sel) ?? data.cases[0];
  const g = data.graphs[c.case_id];

  return (
    <div className="flex min-h-full flex-col gap-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <h1 className="text-title-2">Mule network · campaign cases</h1>
          <p className="text-footnote text-label-secondary">
            Receiving-side view after {Math.round(data.summary.now_day)} days of the synthetic ledger ·{" "}
            {data.summary.accounts_tracked.toLocaleString("en-IN")} accounts tracked · {data.summary.flagged} flagged ·{" "}
            {data.cases.length} cases shown {source === "live" ? "(live API)" : "(recorded)"}
          </p>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-[18rem_1fr_22rem]">
        <Panel eyebrow="Ranked by recoverable money" title="Cases" icon={FolderSearch} tint="var(--color-sys-green)">
          <ol className="flex max-h-[40rem] flex-col gap-1.5 overflow-y-auto pr-1">
            {data.cases.map((k, i) => {
              const on = k.case_id === c.case_id;
              return (
                <li key={k.case_id}>
                  <button
                    onClick={() => setSel(k.case_id)}
                    className={`squircle flex w-full flex-col gap-1 rounded-[0.9rem] px-3 py-2 text-left transition-[scale,background-color] active:scale-[0.98] ${on ? "bg-fill-secondary" : "bg-fill-quaternary hover:bg-fill-tertiary"}`}
                  >
                    <span className="flex items-center gap-2">
                      <span className="text-caption-2 tabular-nums text-label-tertiary">#{i + 1}</span>
                      <span className="font-mono text-footnote font-semibold">{k.case_id}</span>
                      {k.novel && <Sparkles className="size-3.5 text-sys-purple" aria-label="novel pattern" />}
                      {held[k.case_id] && <Lock className="size-3.5 text-sys-blue" aria-label="on hold" />}
                      <span className="ml-auto text-caption-1 font-semibold tabular-nums text-sys-green">{lakh(k.recoverable)}</span>
                    </span>
                    <span className="text-caption-1 text-label-secondary">
                      {k.n_victims} victims · {k.n_accounts} accounts · {lakh(k.loss_in)} in
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        </Panel>

        <Panel
          eyebrow={`${c.case_id} · money flow`}
          icon={Network}
          tint="var(--color-sys-red)"
          title={`${g.totals.victims} victims → ${c.n_accounts} accounts → ${g.totals.exits} exits`}
          accessory={<FlowLegend />}
        >
          <FlowGraph key={c.case_id} g={g} held={!!held[c.case_id]} />
        </Panel>

        <CasePanel c={c} g={g} held={!!held[c.case_id]} onHold={async () => {
          setHeld((h) => ({ ...h, [c.case_id]: true }));
          toast(`Credit hold placed on ${c.n_accounts} accounts of ${c.case_id}`, "alert");
          if (source === "live") await holdCase(c.case_id);
        }} />
      </div>
    </div>
  );
}

function FlowLegend() {
  return (
    <div className="hidden items-center gap-3 text-caption-1 text-label-secondary lg:flex">
      <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-full bg-sys-cyan/70" />victim</span>
      <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-full bg-sys-red" />mule account (fill = risk)</span>
      <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-full ring-2 ring-white/70" />flagged</span>
      <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-full bg-sys-orange" />exit</span>
    </div>
  );
}

function FlowGraph({ g, held }: { g: CaseGraph; held: boolean }) {
  const [ref, { width }] = useElementSize<HTMLDivElement>();
  const reduce = useReducedMotion();
  const [hover, setHover] = useState<string | null>(null);

  const layout = useMemo(() => {
    const hops = [...new Set(g.nodes.map((n) => n.hop))].sort((a, b) => a - b);
    const W = Math.max(width, 320);
    const colX = (h: number) => 40 + (hops.indexOf(h) / Math.max(1, hops.length - 1)) * (W - 80);
    const pos = new Map<string, { x: number; y: number; r: number; n: GraphNode }>();
    const maxAmt = Math.max(...g.nodes.map((n) => n.amount ?? n.balance ?? 1), 1);
    hops.forEach((h) => {
      const col = g.nodes
        .filter((n) => n.hop === h)
        .sort((a, b) => (b.amount ?? b.risk ?? 0) - (a.amount ?? a.risk ?? 0));
      const gap = (H - 40) / Math.max(1, col.length);
      col.forEach((n, i) => {
        const size = n.kind === "account" ? 4 + 8 * Math.sqrt((n.balance ?? 0) / maxAmt + (n.victims ?? 0) / 60) : 3 + 7 * Math.sqrt((n.amount ?? 0) / maxAmt);
        pos.set(n.id, { x: colX(h), y: 20 + gap * (i + 0.5), r: Math.min(14, Math.max(3, size)), n });
      });
    });
    const maxE = Math.max(...g.edges.map((e) => e.amount), 1);
    const edges = g.edges
      .filter((e) => pos.has(e.src) && pos.has(e.dst))
      .map((e) => ({ ...e, a: pos.get(e.src)!, b: pos.get(e.dst)!, w: 0.4 + 3.2 * (Math.log1p(e.amount) / Math.log1p(maxE)) }));
    const labels = hops.map((h) => ({
      x: colX(h),
      t: h === 0 ? "Victims" : h === hops.at(-1) && g.nodes.some((n) => n.kind === "exit" && n.hop === h) ? "Exits" : `Hop ${h}`,
    }));
    return { pos, edges, labels };
  }, [g, width]);

  const lit = (id: string) => !hover || id === hover || layout.edges.some((e) => (e.src === hover && e.dst === id) || (e.dst === hover && e.src === id));
  const hv = hover ? layout.pos.get(hover)?.n : null;

  return (
    <div ref={ref} className="relative w-full" style={{ height: H + 24 }}>
      {width > 0 && (
        <svg width={width} height={H + 24} className="absolute inset-0">
          {layout.labels.map((l) => (
            <text key={l.t + l.x} x={l.x} y={H + 18} textAnchor="middle" className="fill-label-tertiary text-[0.6875rem] font-semibold uppercase tracking-wider">
              {l.t}
            </text>
          ))}
          <g>
            {layout.edges.map((e, i) => {
              const on = !hover || e.src === hover || e.dst === hover;
              const inner = e.a.n.kind === "account" && e.b.n.kind === "account";
              const color = e.a.n.kind === "victim" ? "var(--color-sys-cyan)" : e.b.n.kind === "exit" ? "var(--color-sys-orange)" : "var(--color-sys-red)";
              const mx = (e.a.x + e.b.x) / 2;
              const d = e.a.x === e.b.x
                ? `M${e.a.x},${e.a.y} C${e.a.x + 40},${e.a.y} ${e.b.x + 40},${e.b.y} ${e.b.x},${e.b.y}`
                : `M${e.a.x},${e.a.y} C${mx},${e.a.y} ${mx},${e.b.y} ${e.b.x},${e.b.y}`;
              return (
                <path
                  key={i}
                  d={d}
                  fill="none"
                  stroke={color}
                  strokeWidth={e.w}
                  strokeOpacity={on ? (inner ? 0.55 : 0.35) : 0.04}
                  strokeDasharray={!reduce && !held && on ? "3 7" : undefined}
                  className={!reduce && !held && on ? "animate-[flow_1.2s_linear_infinite]" : ""}
                >
                  <title>{`${e.src} → ${e.dst}: ${rupees(e.amount)} in ${e.count} transfer${e.count > 1 ? "s" : ""}`}</title>
                </path>
              );
            })}
          </g>
          {[...layout.pos.values()].map(({ x, y, r, n }) => {
            const fill = n.kind === "victim" ? "var(--color-sys-cyan)" : n.kind === "exit" ? "var(--color-sys-orange)" : riskColor(n.risk ?? 0);
            return (
              <g
                key={n.id}
                onPointerEnter={() => setHover(n.id)}
                onPointerLeave={() => setHover(null)}
                style={{ opacity: lit(n.id) ? 1 : 0.15, transition: "opacity 200ms" }}
                className="cursor-pointer"
              >
                <motion.circle
                  cx={x}
                  cy={y}
                  r={r}
                  fill={fill}
                  fillOpacity={n.kind === "victim" ? 0.6 : 0.9}
                  stroke={n.flagged ? "rgb(255 255 255 / 0.85)" : "var(--color-bg)"}
                  strokeWidth={n.flagged ? 1.75 : 1}
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ ...spring.default, delay: reduce ? 0 : Math.min(0.6, n.hop * 0.12) }}
                />
                {(held || n.held) && n.kind === "account" && (
                  <text x={x} y={y} dy="0.35em" textAnchor="middle" className="pointer-events-none fill-white text-[0.5rem] font-bold">
                    ⏸
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      )}
      <AnimatePresence>
        {hv && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="material-thick squircle pointer-events-none absolute left-3 top-3 rounded-[0.9rem] px-3 py-2 text-footnote"
          >
            <p className="font-mono font-semibold">{hv.id}</p>
            {hv.kind === "account" ? (
              <p className="text-label-secondary">
                risk {pct(hv.risk ?? 0)} · {hv.victims} victims · balance {rupees(hv.balance ?? 0)}
                {hv.flagged ? " · flagged" : ""}
              </p>
            ) : (
              <p className="text-label-secondary">
                {hv.kind === "victim" ? "paid in" : "left the case"} {rupees(hv.amount ?? 0)}
              </p>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function CasePanel({ c, g, held, onHold }: { c: Case; g: CaseGraph; held: boolean; onHold: () => void }) {
  const [lang, setLang] = useState<"en" | "hi">("en");
  const [done, setDone] = useState<Record<string, boolean>>({});
  return (
    <Panel eyebrow={c.novel ? "Novel pattern" : "Known pattern"} title={c.case_id} icon={Briefcase} tint="var(--color-sys-orange)">
      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-2">
          <Stat label="Paid in by victims" v={lakh(c.loss_in)} />
          <Stat label="Still recoverable" v={lakh(c.recoverable)} color="var(--color-sys-green)" />
          <Stat label="Victims" v={`${c.n_victims}`} sub={`${c.victims_24h} in last 24 h`} />
          <Stat label="Accounts" v={`${c.n_accounts}`} sub={`${c.n_flagged} flagged by the model`} />
          <Stat label="Inflow, last 24 h" v={lakh(c.inflow_24h)} />
          <Stat label="Moved onward" v={lakh(g.totals.exit_amount)} sub={`to ${g.totals.exits} exit accounts`} color="var(--color-sys-orange)" />
        </div>
        <SegmentedControl
          label="Summary language"
          size="small"
          value={lang}
          onChange={setLang}
          options={[
            { value: "en", label: "English" },
            { value: "hi", label: "हिन्दी" },
          ]}
        />
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.p
            key={lang + c.case_id}
            lang={lang}
            initial={{ opacity: 0, filter: "blur(4px)" }}
            animate={{ opacity: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0 }}
            transition={spring.snappy}
            className="text-subheadline text-label-secondary"
          >
            {c.summary[lang]}
          </motion.p>
        </AnimatePresence>
        <div className="flex flex-col gap-2">
          {c.summary.actions.map((a) => {
            const isHold = a.action === "credit_hold";
            const did = isHold ? held : done[a.action];
            return (
              <Button
                key={a.action}
                size="small"
                variant={isHold && !did ? "filled" : "tinted"}
                tint={isHold ? "red" : "blue"}
                disabled={did}
                onClick={() => {
                  if (isHold) return onHold();
                  setDone((d) => ({ ...d, [a.action]: true }));
                  toast(a.label, "ok");
                }}
                className="h-auto min-h-8 justify-start whitespace-normal py-1.5 text-left"
              >
                {isHold ? <ShieldAlert className="size-3.5 shrink-0" aria-hidden /> : null}
                <span>{did ? `Done · ${a.label}` : a.label}</span>
              </Button>
            );
          })}
          <p className="text-caption-2 text-label-tertiary">
            Holds are never automatic: an analyst confirms. Demo actions are local unless the live API is connected.
          </p>
        </div>
      </div>
    </Panel>
  );
}

function Stat({ label, v, sub, color }: { label: string; v: string; sub?: string; color?: string }) {
  return (
    <div className="squircle rounded-[0.9rem] bg-fill-quaternary px-3 py-2">
      <p className="text-caption-2 text-label-tertiary">{label}</p>
      <p className="text-headline tabular-nums" style={{ color }}>{v}</p>
      {sub && <p className="text-caption-2 text-label-tertiary">{sub}</p>}
    </div>
  );
}
