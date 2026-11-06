"use client";

import { AnimatePresence, motion } from "motion/react";
import { Activity, Braces, ClipboardList, Gavel, IndianRupee, Layers, LineChart, type LucideIcon, Scale, ScanSearch, Sparkles, Workflow } from "lucide-react";
import { AnimatedNumber } from "@/components/common/AnimatedNumber";
import { RiskTimeline } from "@/components/charts/RiskTimeline";
import { CaseLog } from "@/components/session/CaseLog";
import { EventFeed } from "@/components/session/EventFeed";
import { ExplainPanel } from "@/components/session/ExplainPanel";
import { InspectorPanel } from "@/components/session/InspectorPanel";
import { PipelinePanel } from "@/components/session/PipelinePanel";
import { PolicyPanel } from "@/components/session/PolicyPanel";
import { TypologyPanel } from "@/components/session/TypologyPanel";
import { ACTION_COLOR, ACTION_LABEL, riskColor, STAGE_COLOR, STAGE_LABEL, TYPOLOGY_LABEL } from "@/config/policy";
import { spring } from "@/config/motion";
import { useDemo } from "@/context/DemoContext";
import { counterfactual } from "@/utils/derive";
import { pct, rupees } from "@/utils/format";
import { Panel } from "./Panel";

/** Right pane: the bank's fraud-operations console for the session being replayed. */
export function ConsoleShell() {
  const { replay } = useDemo();
  return (
    <div className="flex min-h-full flex-col gap-4">
      <StatusStrip />

      <Panel eyebrow="Step by step" title="Inside the decision" icon={Workflow} tint="var(--color-sys-indigo)">
        <PipelinePanel />
      </Panel>

      <Panel
        eyebrow="Live session"
        title="Risk timeline"
        icon={LineChart}
        tint="var(--color-sys-red)"
        className="min-h-[22rem]"
        accessory={
          <div className="hidden items-center gap-3 text-caption-1 text-label-secondary sm:flex">
            <span className="flex items-center gap-1.5">
              <span className="h-0.5 w-4 rounded-full bg-gradient-to-r from-sys-green via-sys-orange to-sys-red" aria-hidden />
              Workflow risk (GRU)
            </span>
            <span className="flex items-center gap-1.5">
              <span className="size-2 rotate-45 rounded-[1px] border-2 border-label-secondary" aria-hidden />
              Payment risk (fusion)
            </span>
          </div>
        }
      >
        <div className="grid h-full grid-cols-1 gap-4 2xl:grid-cols-[1fr_16rem]">
          <RiskTimeline key={replay.typology} />
          <div className="hidden min-h-0 overflow-hidden 2xl:block">
            <EventFeed />
          </div>
        </div>
      </Panel>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Panel eyebrow="Explainability" title="Why this session" icon={Sparkles} tint="var(--color-sys-purple)">
          <ExplainPanel />
        </Panel>
        <Panel eyebrow="Alert policy" title="Fraud cost vs. friction" icon={Scale} tint="var(--color-sys-orange)">
          <PolicyPanel />
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Panel eyebrow="Pattern" title="Which scam is this?" icon={ScanSearch} tint="var(--color-sys-pink)">
          <TypologyPanel />
        </Panel>
        <Panel eyebrow="Case management" title="Analyst case log" icon={ClipboardList} tint="var(--color-sys-teal)">
          <CaseLog />
        </Panel>
      </div>

      <Panel eyebrow="Raw API" title="Event inspector" icon={Braces} tint="var(--color-sys-cyan)">
        <InspectorPanel />
      </Panel>
    </div>
  );
}

function StatusStrip() {
  const { view, index, last, replay, done } = useDemo();
  const cur = view.current;
  const p = cur?.workflow.p_scam_in_progress ?? 0;
  const stage = cur?.workflow.stage ?? "none";
  const typ = cur ? Object.entries(cur.workflow.typology_top3).sort((a, b) => b[1] - a[1])[0] : null;
  const d = view.lastDecision?.decision ?? null;
  const cf = counterfactual(replay);
  const atRisk = view.decisions.reduce((s, e) => s + (e.input.amount ?? 0), 0);
  const built = replay.typology === "builder"; // a session built by hand has no ground truth: don't call it genuine
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 2xl:grid-cols-5">
      <Tile label="Workflow risk" icon={Activity} accent={cur ? riskColor(p) : undefined}>
        <span style={{ color: cur ? riskColor(p) : undefined }}>
          <AnimatedNumber value={cur ? p : 0} format={(v) => (cur ? pct(v) : "—")} />
        </span>
      </Tile>
      <Tile label="Scam stage (model)" icon={Layers} accent={cur ? STAGE_COLOR[stage] : undefined}>
        <span className="flex items-center gap-2">
          <span className="size-2.5 rounded-full" style={{ background: STAGE_COLOR[stage] }} aria-hidden />
          <Swap k={stage}>{cur ? STAGE_LABEL[stage] : "—"}</Swap>
        </span>
      </Tile>
      <Tile label="Likely pattern" icon={ScanSearch} accent={typ && p >= 0.5 ? "var(--color-sys-pink)" : undefined}>
        <Swap k={typ && p >= 0.5 ? typ[0] : "none"}>{typ && p >= 0.5 ? TYPOLOGY_LABEL[typ[0]] ?? typ[0] : "—"}</Swap>
      </Tile>
      <Tile label={`Decision · event ${Math.max(0, Math.min(index, last) + 1)}/${last + 1}`} icon={Gavel} accent={d ? ACTION_COLOR[d.action] : undefined}>
        <Swap k={d ? `${d.action}-${view.lastDecision!.event_index}` : "none"}>
          {d ? <span style={{ color: ACTION_COLOR[d.action] }}>{ACTION_LABEL[d.action]}</span> : <span className="text-label-tertiary">No payment yet</span>}
        </Swap>
      </Tile>
      <Tile
        icon={IndianRupee}
        accent={done ? (cf.held ? (replay.is_scam ? "var(--color-sys-green)" : "var(--color-sys-yellow)") : "var(--color-sys-green)") : undefined}
        label={
          cf.held && done
            ? replay.is_scam ? "Money protected" : built ? "Payment held" : "Genuine payment held"
            : done && !cf.held ? "Paid without friction" : "Payments so far"
        }
      >
        <Swap k={`${done}-${view.decisions.length}`}>
          {cf.held && done && replay.is_scam ? (
            <span className="text-sys-green" title={`${cf.payments} payments the simulated victim makes after this point if not stopped`}>
              {rupees(cf.amount)}
            </span>
          ) : cf.held && done ? (
            <span className="text-sys-yellow" title={built ? "The engine held this payment (see the policy panel for why)" : "A false alarm: the engine held a genuine payment (see the policy panel for why)"}>
              {rupees(view.lastDecision?.input.amount ?? 0)}
            </span>
          ) : (
            <span className={done ? "text-sys-green" : ""}>{rupees(done && !cf.held ? cf.amount : atRisk)}</span>
          )}
        </Swap>
      </Tile>
    </div>
  );
}

/** Status tile: label + live value; a hairline of light along the top edge takes the state's colour. */
function Tile({ label, icon: Icon, accent, children }: { label: string; icon: LucideIcon; accent?: string; children: React.ReactNode }) {
  return (
    <div className="material-thin squircle relative overflow-hidden rounded-[var(--radius-card)] px-4 py-3">
      <motion.span
        aria-hidden
        className="absolute inset-x-0 top-0 h-[2px]"
        initial={false}
        animate={{ opacity: accent ? 1 : 0 }}
        style={{ background: `linear-gradient(90deg, transparent, ${accent ?? "transparent"}, transparent)` }}
      />
      <motion.span
        aria-hidden
        className="pointer-events-none absolute -top-10 left-1/2 h-16 w-3/4 -translate-x-1/2 rounded-full blur-2xl"
        initial={false}
        animate={{ opacity: accent ? 0.22 : 0 }}
        style={{ background: accent }}
      />
      <p className="relative flex items-center justify-between gap-2 truncate text-caption-1 text-label-secondary">
        {label}
        <Icon className="size-3.5 shrink-0 text-label-tertiary" aria-hidden />
      </p>
      <div className="relative mt-0.5 truncate text-title-3 tabular-nums">{children}</div>
    </div>
  );
}

/** Cross-fades its children when `k` changes (blur + opacity, no travel). */
function Swap({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <AnimatePresence mode="popLayout" initial={false}>
      <motion.span
        key={k}
        className="inline-block"
        initial={{ opacity: 0, filter: "blur(6px)" }}
        animate={{ opacity: 1, filter: "blur(0px)" }}
        exit={{ opacity: 0, filter: "blur(6px)" }}
        transition={spring.snappy}
      >
        {children}
      </motion.span>
    </AnimatePresence>
  );
}
