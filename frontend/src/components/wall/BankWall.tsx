"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { BarChart3, BellRing, Check, LayoutGrid, Pause, Play, RotateCcw, X } from "lucide-react";
import { loadFleet } from "@/api/demo";
import { AnimatedNumber } from "@/components/common/AnimatedNumber";
import { IconButton } from "@/components/common/Button";
import { SegmentedControl } from "@/components/common/SegmentedControl";
import { Panel } from "@/components/layout/Panel";
import { customPersona } from "@/config/personas";
import { ACTION_COLOR, ACTION_LABEL, riskColor, SESSION_LABEL, TYPOLOGY_LABEL } from "@/config/policy";
import { genericScenario } from "@/config/scenarios";
import { spring } from "@/config/motion";
import { useDemo } from "@/context/DemoContext";
import type { Decision, DemoReplay, Fleet, FleetSession } from "@/types/demo";
import { counterfactual } from "@/utils/derive";
import { pct, rupees } from "@/utils/format";

/** One fleet session with its event times on the wall clock (minutes since the window opened). */
interface Row {
  s: FleetSession;
  start: number;
  times: number[];
  end: number;
  alert: { at: number; index: number; d: Decision; amount: number } | null;
  firstPay: number | null;
  protectedAmt: number;
}

type Status = "waiting" | "live" | "clear" | "nudge" | "cool_off" | "hold";

function prep(f: Fleet): Row[] {
  const t0 = new Date(f.window.start).getTime();
  return f.sessions.map((s) => {
    const start = (new Date(s.start_time).getTime() - t0) / 60000;
    const times = s.timeline.map((e) => start + e.ts_min);
    const ai = s.timeline.findIndex((e) => e.decision?.notify && e.decision.action !== "allow" && e.decision.action !== "monitor");
    const pi = s.timeline.findIndex((e) => e.event === "PAYMENT_ATTEMPT");
    const cf = counterfactual(s as unknown as DemoReplay);
    return {
      s,
      start,
      times,
      end: times.at(-1) ?? start,
      alert: ai >= 0 ? { at: times[ai], index: ai, d: s.timeline[ai].decision!, amount: s.timeline[ai].input.amount ?? 0 } : null,
      firstPay: pi >= 0 ? times[pi] : null,
      protectedAmt: cf.held ? cf.amount : 0,
    };
  });
}

/** Index of the last event at or before t (−1 if none). */
function seen(times: number[], t: number) {
  let lo = 0;
  let hi = times.length - 1;
  let ans = -1;
  while (lo <= hi) {
    const m = (lo + hi) >> 1;
    if (times[m] <= t) {
      ans = m;
      lo = m + 1;
    } else hi = m - 1;
  }
  return ans;
}

function statusAt(r: Row, t: number): { status: Status; p: number } {
  if (t < r.start) return { status: "waiting", p: 0 };
  const i = seen(r.times, t);
  const p = i >= 0 ? r.s.timeline[i].workflow.p_scam_in_progress : 0;
  if (r.alert && r.alert.at <= t) return { status: r.alert.d.action as Status, p };
  if (t <= r.end) return { status: "live", p };
  return { status: "clear", p };
}

const RATES = [
  { value: "10", label: "10 min/s" },
  { value: "30", label: "30 min/s" },
  { value: "90", label: "90 min/s" },
];

/**
 * Bank-wide view: every customer session in a 12-hour slice of the simulator's held-out test data, replayed on a
 * compressed clock through the same pipeline (one shared alert policy). Tiles light up as sessions run; interruptions
 * land in the alert queue, checked against the simulator's ground truth.
 */
export function BankWall() {
  const { openSession } = useDemo();
  const [fleet, setFleet] = useState<Fleet | null>(null);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [rate, setRate] = useState("30");
  const [filter, setFilter] = useState<"all" | "scam" | "genuine" | "alerts">("all");

  useEffect(() => {
    const ac = new AbortController();
    loadFleet(ac.signal).then(setFleet).catch(() => {});
    return () => ac.abort();
  }, []);
  const rows = useMemo(() => (fleet ? prep(fleet) : []), [fleet]);
  const span = fleet ? fleet.window.hours * 60 : 720;
  // the window is `span`; sessions that started in it can run on for days (investment scams), but the wall's clock
  // stops at the window's end and such sessions simply stay live
  const tEnd = span;

  // wall clock: advance `rate` simulated minutes per real second while playing (10 updates a second is plenty
  // for 270 tiles; tiles and numbers ease between updates on their own)
  useEffect(() => {
    if (!playing) return;
    let prev = performance.now();
    const id = setInterval(() => {
      const now = performance.now();
      const dt = (now - prev) / 1000;
      prev = now;
      setT((x) => Math.min(tEnd, x + dt * Number(rate)));
    }, 100);
    return () => clearInterval(id);
  }, [playing, rate, tEnd]);
  const finished = t >= tEnd;

  const states = rows.map((r) => statusAt(r, t));
  const k = useMemo(() => {
    let started = 0, live = 0, payments = 0, scamsAlerted = 0, scamsPaying = 0, genuine = 0, genuineAlerted = 0, saved = 0;
    rows.forEach((r, i) => {
      const st = states[i].status;
      if (st === "waiting") return;
      started++;
      if (st === "live") live++;
      payments += r.s.timeline.filter((_, j) => r.times[j] <= t && r.s.timeline[j].event === "PAYMENT_ATTEMPT").length;
      const alerted = !!r.alert && r.alert.at <= t;
      if (r.s.is_scam) {
        if (r.firstPay != null && r.firstPay <= t) scamsPaying++;
        if (alerted) scamsAlerted++;
        if (alerted && r.alert!.d.action === "hold") saved += r.protectedAmt;
      } else {
        genuine++;
        if (alerted) genuineAlerted++;
      }
    });
    return { started, live, payments, scamsAlerted, scamsPaying, genuine, genuineAlerted, saved };
  }, [rows, states, t]);

  const alerts = rows
    .map((r, i) => ({ r, i }))
    .filter(({ r }) => r.alert && r.alert.at <= t)
    .sort((a, b) => b.r.alert!.at - a.r.alert!.at);

  const open = (r: Row) =>
    openSession({
      replay: r.s as unknown as DemoReplay,
      scenario: genericScenario(
        `${SESSION_LABEL[r.s.typology] ?? r.s.typology}`,
        r.s.is_scam,
        `Held-out simulator session ${r.s.session_id} (ground truth: ${r.s.is_scam ? "scam" : "genuine"}).`,
      ),
      persona: customPersona(`Customer ${r.s.user.id.slice(-4)}`, `${r.s.user.age_group} · usual ${rupees(r.s.user.avg_txn_amount)}`),
      from: "wall",
    });

  const clockLabel = (m: number) => {
    if (!fleet) return "";
    const d = new Date(new Date(fleet.window.start).getTime() + m * 60000);
    return `${d.getHours()}:${String(d.getMinutes()).padStart(2, "0")}`;
  };

  const visible = rows
    .map((r, i) => ({ r, i, st: states[i] }))
    .filter(({ r, st }) =>
      filter === "all" ? true : filter === "scam" ? r.s.is_scam : filter === "genuine" ? !r.s.is_scam : st.status !== "waiting" && st.status !== "live" && st.status !== "clear",
    );

  if (!fleet)
    return (
      <div className="flex flex-col gap-4 p-4 sm:p-6" aria-busy="true" aria-label="Loading the fleet">
        <div className="skeleton h-12 w-80 rounded-[1rem]" />
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 2xl:grid-cols-6">
          {Array.from({ length: 6 }, (_, i) => <div key={i} className="skeleton h-[5.25rem] rounded-[var(--radius-card)]" />)}
        </div>
        <div className="skeleton h-[28rem] rounded-[var(--radius-panel)]" />
      </div>
    );

  return (
    <div className="flex min-h-full flex-col gap-4 p-4 sm:p-6">
      {/* clock + transport */}
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h1 className="text-title-2">Bank-wide live wall</h1>
          <p className="text-footnote text-label-secondary">
            {rows.length} customer sessions · {fleet.window.hours} h of held-out simulator data, replayed through the pipeline
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className="material-thin rounded-full px-3 py-1.5 text-title-3 tabular-nums">{clockLabel(t)}</span>
          <IconButton label="Restart" onClick={() => { setT(0); setPlaying(true); }}>
            <RotateCcw className="size-4" />
          </IconButton>
          <IconButton
            label={playing && !finished ? "Pause" : "Play"}
            onClick={() => (finished ? (setT(0), setPlaying(true)) : setPlaying((p) => !p))}
            className="size-10 bg-sys-blue text-white hover:bg-sys-blue/85"
          >
            {playing && !finished ? <Pause className="size-4 fill-current" /> : <Play className="size-4 translate-x-px fill-current" />}
          </IconButton>
          <SegmentedControl label="Clock speed" size="small" value={rate} onChange={setRate} options={RATES} />
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 2xl:grid-cols-6">
        <Kpi label="Sessions so far" value={k.started} sub={`${k.live} live now`} />
        <Kpi label="Payment attempts" value={k.payments} />
        <Kpi label="Scams interrupted" value={k.scamsAlerted} sub={`of ${k.scamsPaying} that reached a payment`} color="var(--color-sys-red)" />
        <Kpi label="Genuine interrupted" value={k.genuineAlerted} sub={`of ${k.genuine} genuine sessions`} color={k.genuineAlerted ? "var(--color-sys-yellow)" : "var(--color-sys-green)"} />
        <Kpi label="Alerts per 1k genuine" value={k.genuine ? (1000 * k.genuineAlerted) / k.genuine : 0} fmt={(v) => v.toFixed(1)} />
        <Kpi label="Money protected" value={k.saved} fmt={rupees} color="var(--color-sys-green)" sub="payments after each hold" />
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-[1fr_24rem]">
        <Panel
          eyebrow="Every customer session"
          title="Session grid"
          icon={LayoutGrid}
          accessory={
            <SegmentedControl
              label="Filter"
              size="small"
              value={filter}
              onChange={setFilter}
              options={[
                { value: "all", label: "All" },
                { value: "scam", label: "Scams" },
                { value: "genuine", label: "Genuine" },
                { value: "alerts", label: "Alerted" },
              ]}
            />
          }
        >
          <div className="mb-3 flex flex-wrap gap-3 text-caption-1 text-label-secondary">
            <Legend c="var(--color-fill-tertiary)" l="not started" />
            <Legend c="var(--color-sys-blue)" l="live (fill = risk)" ring />
            <Legend c="color-mix(in srgb, var(--color-sys-green) 35%, transparent)" l="finished, no alert" />
            <Legend c="var(--color-sys-yellow)" l="nudge" />
            <Legend c="var(--color-sys-red)" l="hold" />
            <span className="ml-auto text-label-tertiary">click a tile to open the session</span>
          </div>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(1.75rem,1fr))] gap-1.5">
            {visible.map(({ r, st }) => (
              <Tile key={r.s.session_id} r={r} st={st.status} p={st.p} onOpen={() => open(r)} />
            ))}
          </div>
        </Panel>

        <Panel eyebrow={`${alerts.length} interruptions`} title="Alert queue" icon={BellRing} tint="var(--color-sys-red)">
          <ol className="flex max-h-[34rem] flex-col gap-1.5 overflow-y-auto pr-1">
            <AnimatePresence initial={false}>
              {alerts.map(({ r }) => {
                const a = r.alert!;
                const top = Object.entries(r.s.timeline[a.index].workflow.typology_top3).sort((x, y) => y[1] - x[1])[0];
                const correct = r.s.is_scam;
                return (
                  <motion.li
                    key={r.s.session_id}
                    layout="position"
                    initial={{ opacity: 0, y: -12, filter: "blur(4px)" }}
                    animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                    transition={spring.default}
                  >
                    <button
                      onClick={() => open(r)}
                      className="squircle flex w-full items-center gap-3 rounded-[0.9rem] bg-fill-quaternary px-3 py-2 text-left transition-[scale,background-color] hover:bg-fill-tertiary active:scale-[0.98]"
                    >
                      <span className="w-11 text-caption-1 tabular-nums text-label-tertiary">{clockLabel(a.at)}</span>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-1.5 text-footnote font-semibold">
                          <span style={{ color: ACTION_COLOR[a.d.action] }}>{ACTION_LABEL[a.d.action]}</span>
                          <span className="tabular-nums">{rupees(a.amount)}</span>
                          <span className="truncate text-label-secondary">· {r.s.user.age_group}</span>
                        </span>
                        <span className="block truncate text-caption-1 text-label-secondary">
                          looks like {TYPOLOGY_LABEL[top[0]] ?? top[0]} · risk {pct(a.d.fused_risk)}
                        </span>
                      </span>
                      <span
                        title={correct ? "Ground truth: scam" : "Ground truth: genuine (false alarm)"}
                        className={`flex size-6 items-center justify-center rounded-full ${correct ? "bg-sys-green/15 text-sys-green" : "bg-sys-yellow/15 text-sys-yellow"}`}
                      >
                        {correct ? <Check className="size-3.5" /> : <X className="size-3.5" />}
                      </span>
                    </button>
                  </motion.li>
                );
              })}
            </AnimatePresence>
            {!alerts.length && <li className="py-6 text-center text-footnote text-label-tertiary">No interruptions yet</li>}
          </ol>
        </Panel>
      </div>

      <Panel eyebrow="Activity" title="Events and alerts over the window" icon={BarChart3} tint="var(--color-sys-teal)">
        <Activity rows={rows} t={t} tEnd={tEnd} onSeek={(m) => setT(m)} clockLabel={clockLabel} />
      </Panel>
      <p className="text-caption-1 text-label-tertiary">{fleet.note}</p>
    </div>
  );
}

function Kpi({ label, value, sub, color, fmt = (v: number) => Math.round(v).toLocaleString("en-IN") }: { label: string; value: number; sub?: string; color?: string; fmt?: (v: number) => string }) {
  return (
    <div className="material-thin squircle relative overflow-hidden rounded-[var(--radius-card)] px-4 py-3">
      {color && (
        <span aria-hidden className="absolute inset-x-0 top-0 h-[2px]" style={{ background: `linear-gradient(90deg, transparent, ${color}, transparent)` }} />
      )}
      <p className="truncate text-caption-1 text-label-secondary">{label}</p>
      <span className="mt-0.5 block text-title-2" style={{ color }}>
        <AnimatedNumber value={value} format={fmt} />
      </span>
      {sub && <p className="truncate text-caption-2 text-label-tertiary">{sub}</p>}
    </div>
  );
}

function Legend({ c, l, ring }: { c: string; l: string; ring?: boolean }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="size-3 rounded-[0.25rem]" style={ring ? { boxShadow: `inset 0 0 0 1.5px ${c}` } : { background: c }} aria-hidden />
      {l}
    </span>
  );
}

function Tile({ r, st, p, onOpen }: { r: Row; st: Status; p: number; onOpen: () => void }) {
  const bg =
    st === "waiting" ? "var(--color-fill-quaternary)"
    : st === "live" ? `color-mix(in srgb, ${riskColor(p)} ${Math.round(18 + p * 50)}%, transparent)`
    : st === "clear" ? "color-mix(in srgb, var(--color-sys-green) 22%, transparent)"
    : ACTION_COLOR[st];
  return (
    <button
      onClick={onOpen}
      disabled={st === "waiting"}
      title={`${r.s.session_id} · ${SESSION_LABEL[r.s.typology] ?? r.s.typology} (ground truth) · ${r.s.user.age_group} · ${st}${st !== "waiting" ? ` · risk ${pct(p)}` : ""}`}
      className="relative aspect-square rounded-[0.4rem] transition-[background-color,scale] duration-300 hover:scale-110 active:scale-95 disabled:cursor-default disabled:hover:scale-100"
      style={{ background: bg }}
    >
      {st === "live" && (
        <motion.span
          aria-hidden
          className="absolute inset-0 rounded-[0.4rem]"
          style={{ boxShadow: `inset 0 0 0 1.5px ${riskColor(p)}` }}
          animate={{ opacity: [1, 0.35, 1] }}
          transition={{ duration: 1.6, repeat: Infinity }}
        />
      )}
      {r.s.is_scam && st !== "waiting" && <span className="absolute right-0.5 top-0.5 size-1 rounded-full bg-white/70" aria-hidden />}
    </button>
  );
}

function Activity({ rows, t, tEnd, onSeek, clockLabel }: { rows: Row[]; t: number; tEnd: number; onSeek: (m: number) => void; clockLabel: (m: number) => string }) {
  const B = 48;
  const bin = tEnd / B;
  const counts = Array(B).fill(0);
  const alerts: { at: number; hold: boolean; scam: boolean }[] = [];
  rows.forEach((r) => {
    r.times.forEach((m) => (counts[Math.min(B - 1, Math.floor(m / bin))] += 1));
    if (r.alert) alerts.push({ at: r.alert.at, hold: r.alert.d.action === "hold", scam: r.s.is_scam });
  });
  const max = Math.max(...counts, 1);
  const ref = useRef<HTMLDivElement>(null);
  return (
    <div>
      <div
        ref={ref}
        className="relative h-28 cursor-pointer"
        onPointerDown={(e) => {
          const b = ref.current!.getBoundingClientRect();
          onSeek(Math.max(0, Math.min(tEnd, ((e.clientX - b.left) / b.width) * tEnd)));
        }}
      >
        <div className="absolute inset-x-0 bottom-5 top-0 flex items-end gap-[2px]">
          {counts.map((c, i) => (
            <span
              key={i}
              className="flex-1 rounded-t-[2px] transition-colors"
              style={{ height: `${(c / max) * 100}%`, background: (i + 1) * bin <= t ? "var(--color-sys-blue)" : "var(--color-fill-tertiary)" }}
            />
          ))}
        </div>
        {alerts.map((a, i) => (
          <span
            key={i}
            title={`${a.hold ? "Hold" : "Nudge"} at ${clockLabel(a.at)} · ${a.scam ? "scam" : "genuine"}`}
            className="absolute bottom-[1.05rem] size-2 -translate-x-1/2 rounded-full"
            style={{ left: `${(a.at / tEnd) * 100}%`, background: a.hold ? "var(--color-sys-red)" : "var(--color-sys-yellow)", opacity: a.at <= t ? 1 : 0.25 }}
          />
        ))}
        <span className="pointer-events-none absolute bottom-4 top-0 w-[2px] rounded-full bg-label" style={{ left: `${(t / tEnd) * 100}%` }} />
        <div className="absolute inset-x-0 bottom-0 flex justify-between text-caption-2 text-label-tertiary tabular-nums">
          {[0, 0.25, 0.5, 0.75, 1].map((f) => (
            <span key={f}>{clockLabel(f * tEnd)}</span>
          ))}
        </div>
      </div>
      <p className="mt-2 text-caption-1 text-label-tertiary">Bars: events per {Math.round(bin)} min. Dots: interruptions (red hold, yellow nudge). Click to jump.</p>
    </div>
  );
}
