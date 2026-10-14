"use client";

import { createContext, use, useCallback, useEffect, useMemo, useState } from "react";
import { loadReplay, RECORDED, type Source } from "@/api/demo";
import { PERSONA_BY_ID, type Persona, type PersonaId } from "@/config/personas";
import { SCENARIO_BY_ID, SCENARIOS, type Scenario, type ScenarioId } from "@/config/scenarios";
import type { DemoReplay, EventType, TimelineEntry } from "@/types/demo";
import { deriveView, stopIndex, type SessionView } from "@/utils/derive";

/**
 * How long each event stays on screen before the next one (ms at 1×). Long enough to read the phone and the
 * console, plus a little of the real gap between events so a 30-minute wait still feels longer than a tap.
 */
const DWELL: Partial<Record<EventType, number>> = {
  CALL_START: 3400,
  CALL_END: 1500,
  SMS_RECEIVED: 2600,
  LINK_CLICK: 2600,
  APP_INSTALL: 2400,
  ACCESSIBILITY_GRANT: 2600,
  OTP_RECEIVED: 2000,
  UPI_APP_OPEN: 1400,
  BALANCE_CHECK: 2000,
  PAYEE_ADD: 2400,
  PAYMENT_ATTEMPT: 3000,
  PAYMENT_SUCCESS: 2200,
  CREDIT_RECEIVED: 2000,
  BIO_WINDOW: 800,
};
function dwell(cur: TimelineEntry, next: TimelineEntry | undefined) {
  const gap = next ? Math.min(1200, (next.ts_min - cur.ts_min) * 45) : 0;
  return (DWELL[cur.event] ?? 1200) + gap;
}

export type Speed = 1 | 2 | 4;
export type AppView = "session" | "wall" | "network" | "builder";

/** An analyst action taken in the console during the replay. */
export interface AnalystAction {
  id: number;
  index: number;
  kind: "confirm" | "call" | "release" | "report" | "note";
  label: string;
}

/** A session without a scripted story: opened from the fleet wall, or built live in the builder. */
export interface CustomSession {
  replay: DemoReplay;
  scenario: Scenario;
  persona: Persona;
  /** builder sessions show every event (no stop at the first hold) */
  noStop?: boolean;
  /** where "back" goes */
  from: AppView;
}

interface DemoState {
  appView: AppView;
  setAppView: (v: AppView) => void;
  scenario: Scenario;
  setScenario: (id: ScenarioId) => void;
  persona: Persona;
  setPersona: (id: PersonaId) => void;
  custom: CustomSession | null;
  /** open a custom session in the session view and play it */
  openSession: (s: CustomSession, autoplay?: boolean) => void;
  /** replace the builder's session in place, showing its latest event */
  updateBuilder: (s: CustomSession | null) => void;
  replay: DemoReplay;
  source: Source;
  index: number;
  /** Bumps on every restart or scenario change, so stateful views can remount fresh. */
  run: number;
  last: number;
  playing: boolean;
  done: boolean;
  speed: Speed;
  setSpeed: (s: Speed) => void;
  toggle: () => void;
  restart: () => void;
  /** Jump to an event (pauses playback). */
  seek: (i: number) => void;
  step: (d: 1 | -1) => void;
  /** Event shown in the inspector: an explicit pick, else the current event. */
  inspected: number;
  inspect: (i: number | null) => void;
  actions: AnalystAction[];
  act: (kind: AnalystAction["kind"], label: string) => void;
  view: SessionView;
}

const Ctx = createContext<DemoState | null>(null);

export function useDemo() {
  const v = use(Ctx);
  if (!v) throw new Error("useDemo outside DemoProvider");
  return v;
}

export function DemoProvider({ children }: { children: React.ReactNode }) {
  const [appView, setAppView] = useState<AppView>("session");
  const [scenarioId, setScenarioId] = useState<ScenarioId>("digital_arrest");
  const [personaId, setPersonaId] = useState<PersonaId>("senior");
  const [custom, setCustom] = useState<CustomSession | null>(null);
  const key = `${personaId}:${scenarioId}`;
  const [loaded, setLoaded] = useState<{ key: string; data: DemoReplay; source: Source }>({
    key: "senior:digital_arrest",
    data: RECORDED.senior.digital_arrest,
    source: "recorded",
  });
  const [index, setIndex] = useState(-1);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<Speed>(1);
  const [run, setRun] = useState(0);
  const [picked, setPicked] = useState<{ run: number; index: number | null }>({ run: 0, index: null });
  const [log, setLog] = useState<{ run: number; items: AnalystAction[] }>({ run: 0, items: [] });

  // Ask the live API when one is configured; the recording is already on screen meanwhile.
  useEffect(() => {
    const ac = new AbortController();
    const k = `${personaId}:${scenarioId}`;
    loadReplay(scenarioId, personaId, ac.signal)
      .then((r) => setLoaded({ key: k, ...r }))
      .catch(() => {});
    return () => ac.abort();
  }, [scenarioId, personaId]);

  const replay = custom ? custom.replay : loaded.key === key ? loaded.data : RECORDED[personaId][scenarioId];
  const source: Source = custom ? (custom.from === "builder" ? "live" : "recorded") : loaded.key === key ? loaded.source : "recorded";
  const last = custom?.noStop ? replay.timeline.length - 1 : stopIndex(replay);
  const done = index >= last;
  const running = playing && !done;

  useEffect(() => {
    if (!running) return;
    const delay = index < 0 ? 500 : dwell(replay.timeline[index], replay.timeline[index + 1]) / speed;
    const id = setTimeout(() => setIndex((i) => i + 1), delay);
    return () => clearTimeout(id);
  }, [running, index, replay, speed]);

  const fresh = useCallback((play: boolean) => {
    setIndex(-1);
    setPlaying(play);
    setRun((r) => r + 1);
  }, []);
  const restart = useCallback(() => fresh(true), [fresh]);

  const toggle = useCallback(() => {
    if (done) restart();
    else setPlaying((p) => !p);
  }, [done, restart]);

  const setScenario = useCallback(
    (id: ScenarioId) => {
      setCustom(null);
      setScenarioId(id);
      setAppView("session");
      fresh(false);
    },
    [fresh],
  );
  const setPersona = useCallback(
    (id: PersonaId) => {
      setCustom(null);
      setPersonaId(id);
      fresh(false);
    },
    [fresh],
  );
  const openSession = useCallback(
    (s: CustomSession, autoplay = true) => {
      setCustom(s);
      setAppView("session");
      fresh(autoplay);
    },
    [fresh],
  );
  const updateBuilder = useCallback((s: CustomSession | null) => {
    setCustom(s);
    setPlaying(false);
    setIndex(s ? s.replay.timeline.length - 1 : -1);
    if (!s) setRun((r) => r + 1);
  }, []);

  const seek = useCallback(
    (i: number) => {
      setPlaying(false);
      setIndex(Math.max(-1, Math.min(last, i)));
    },
    [last],
  );
  const step = useCallback((d: 1 | -1) => seek(index + d), [seek, index]);

  const inspect = useCallback((i: number | null) => setPicked({ run, index: i }), [run]);
  const act = useCallback(
    (kind: AnalystAction["kind"], label: string) =>
      setLog((l) => {
        const items = l.run === run ? l.items : [];
        return { run, items: [...items, { id: items.length + 1, index, kind, label }] };
      }),
    [run, index],
  );

  // Session view: Space play/pause · ←/→ step · R restart · 1–8 scenario
  useEffect(() => {
    if (appView !== "session") return;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t?.closest("input, textarea, select, [contenteditable]")) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.code === "Space" && !(t instanceof HTMLButtonElement)) {
        e.preventDefault();
        toggle();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        step(1);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        step(-1);
      } else if (e.key === "r" || e.key === "R") restart();
      else if (/^[1-8]$/.test(e.key)) setScenario(SCENARIOS[Number(e.key) - 1].id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [appView, toggle, restart, setScenario, step]);

  const view = useMemo(() => deriveView(replay, Math.min(index, last)), [replay, index, last]);
  const pickedIndex = picked.run === run && picked.index != null && picked.index <= index ? picked.index : null;

  const value: DemoState = {
    appView,
    setAppView,
    scenario: custom ? custom.scenario : SCENARIO_BY_ID[scenarioId],
    setScenario,
    persona: custom ? custom.persona : PERSONA_BY_ID[personaId],
    setPersona,
    custom,
    openSession,
    updateBuilder,
    replay,
    source,
    index,
    run,
    last,
    playing: running,
    done,
    speed,
    setSpeed,
    toggle,
    restart,
    seek,
    step,
    inspected: pickedIndex ?? Math.min(index, last),
    inspect,
    actions: log.run === run ? log.items : [],
    act,
    view,
  };
  return <Ctx value={value}>{children}</Ctx>;
}
