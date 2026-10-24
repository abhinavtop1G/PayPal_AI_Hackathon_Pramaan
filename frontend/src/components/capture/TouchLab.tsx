"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Hand, UserPlus } from "lucide-react";
import { GESTURE_FEATURES, type GestureFeatures, type TouchVerifyResult } from "@pramaan/web-sdk";
import { Button } from "@/components/common/Button";
import { toast } from "@/components/common/Toaster";
import { Panel } from "@/components/layout/Panel";
import { useConsole } from "@/context/ConsoleContext";
import { DEMO_USER, LAB_USER, type SdkBus } from "./sdkBus";

type Trail = { id: number; pts: [number, number][] };

const SHOWN: [string, (f: GestureFeatures) => string][] = [
  ["duration", (f) => `${Math.round(Math.expm1(f.log_duration_ms ?? 0))} ms`],
  ["pause before", (f) => `${(Math.expm1(f.log_gap_ms ?? 0) / 1000).toFixed(1)} s`],
  ["travel (1080-px ref.)", (f) => `${Math.round(Math.expm1(f.log_path_len ?? 0))} px`],
  ["speed", (f) => `${Math.round(Math.expm1(f.log_speed ?? 0)).toLocaleString("en-IN")} px/s`],
  ["start (x, y)", (f) => `${(f.x0 ?? 0).toFixed(2)}, ${(f.y0 ?? 0).toFixed(2)}`],
  ["move (dx, dy)", (f) => `${(f.dx ?? 0).toFixed(2)}, ${(f.dy ?? 0).toFixed(2)}`],
  ["points", (f) => String(Math.round(Math.expm1(f.log_n_points ?? 0)))],
  ["tap", (f) => (f.is_tap ? "yes" : "no")],
  ["hand motion |a|", (f) => (f.acc_mean == null ? "no sensor" : `${f.acc_mean.toFixed(2)} m/s² ± ${(f.acc_std ?? 0).toFixed(2)}`)],
  ["rotation |ω|", (f) => (f.gyr_mean == null ? "no sensor" : `${f.gyr_mean.toFixed(2)} rad/s`)],
];

/**
 * Touch biometrics, live: the web SDK turns each finger (or, on a laptop, mouse) gesture on the pad into the 21
 * features the touch model was trained on; the trails are drawn only on this page. With the API, a window of 10-20
 * gestures is verified against a profile (BiLSTM + LDA fusion).
 */
export function TouchLab({ bus, padRef }: { bus: SdkBus; padRef: (el: HTMLDivElement | null) => (() => void) | void }) {
  const { client } = useConsole();
  const [trails, setTrails] = useState<Trail[]>([]);
  const [features, setFeatures] = useState<GestureFeatures[]>([]);
  const [result, setResult] = useState<{ who: string; r: TouchVerifyResult } | null>(null);
  const [enrolled, setEnrolled] = useState(false);
  const [busy, setBusy] = useState(false);
  const live = useRef<Trail | null>(null);
  const box = useRef<HTMLDivElement | null>(null);
  const seq = useRef(0);
  const setPad = useCallback((el: HTMLDivElement | null) => {
    box.current = el;
    return padRef(el);
  }, [padRef]);

  useEffect(() => {
    const on = (f: GestureFeatures) => setFeatures((xs) => [...xs, f].slice(-40));
    bus.onGesture.add(on);
    return () => {
      bus.onGesture.delete(on);
    };
  }, [bus]);

  const local = (e: React.PointerEvent): [number, number] => {
    const r = box.current!.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  };
  const down = (e: React.PointerEvent) => {
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
    live.current = { id: ++seq.current, pts: [local(e)] };
    setTrails((t) => [...t.slice(-11), live.current!]);
  };
  const move = (e: React.PointerEvent) => {
    if (!live.current) return;
    live.current.pts.push(local(e));
    setTrails((t) => t.map((x) => (x.id === live.current?.id ? { ...live.current } : x)));
  };
  const up = () => {
    live.current = null;
  };

  const verify = async (who: "asha" | "me") => {
    if (!client) return;
    const n = features.length >= 20 ? 20 : 10;
    setBusy(true);
    try {
      const r = await client.verifyTouch(who === "asha" ? DEMO_USER : LAB_USER, features.slice(-n));
      setResult({ who: who === "asha" ? "Asha's" : "your", r });
    } catch (e) {
      toast(`Touch verification failed: ${(e as Error).message}`, "alert");
    } finally {
      setBusy(false);
    }
  };
  const enrol = async () => {
    if (!client) return;
    setBusy(true);
    try {
      await client.enrollTouch(LAB_USER, features.slice(-20));
      setEnrolled(true);
      setFeatures([]);
      toast("Touch profile enrolled from 20 gestures. Make 10 more to verify against it.");
    } catch (e) {
      toast(`Enrolment failed: ${(e as Error).message}`, "alert");
    } finally {
      setBusy(false);
    }
  };

  const last = features[features.length - 1];
  return (
    <Panel eyebrow="Behaviour · touch dynamics" title="Swipe and tap" icon={Hand} tint="var(--color-fam-behaviour)">
      <div className="grid gap-5 md:grid-cols-[17rem_minmax(0,1fr)]">
        <div ref={setPad} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}
          className="squircle relative h-[26rem] touch-none select-none overflow-hidden rounded-[2rem] bg-[#0b0b0d] ring-1 ring-white/10"
          style={{ backgroundImage: "radial-gradient(circle at 1px 1px, rgb(255 255 255 / 0.08) 1px, transparent 0)", backgroundSize: "22px 22px" }}
          aria-label="Touch pad watched by the SDK">
          <svg className="pointer-events-none absolute inset-0 size-full" aria-hidden>
            {trails.map((t, i) => (
              <g key={t.id} opacity={0.25 + (0.75 * (i + 1)) / trails.length}>
                <polyline points={t.pts.map((p) => p.join(",")).join(" ")} fill="none" stroke="var(--color-fam-behaviour)" strokeWidth={3}
                  strokeLinecap="round" strokeLinejoin="round" />
                <circle cx={t.pts[0][0]} cy={t.pts[0][1]} r={5} fill="var(--color-fam-behaviour)" />
              </g>
            ))}
          </svg>
          {!trails.length && (
            <p className="pointer-events-none absolute inset-x-6 top-1/2 -translate-y-1/2 text-center text-footnote text-label-tertiary">
              Scroll-swipe and tap here like on a phone. On a laptop, drag with the mouse.
            </p>
          )}
          <span className="pointer-events-none absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-fill-tertiary px-2.5 py-1 text-caption-1 tabular-nums">
            {features.length} gesture{features.length === 1 ? "" : "s"} encoded
          </span>
        </div>

        <div className="min-w-0 space-y-3">
          {last ? (
            <dl className="grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2">
              {SHOWN.map(([k, fmt]) => (
                <div key={k} className="flex items-baseline justify-between gap-3 border-b border-separator/40 py-1 text-footnote">
                  <dt className="text-label-secondary">{k}</dt>
                  <dd className="font-mono tabular-nums">{fmt(last)}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="rounded-[0.8rem] bg-fill-quaternary p-3 text-caption-1 text-label-tertiary">
              Each gesture becomes {GESTURE_FEATURES.length} numbers (ml/models/biometrics/data.py), computed 100 ms after the finger lifts so the
              hand-motion window is complete. Raw coordinates never leave the device.
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button size="small" variant="tinted" disabled={!client || busy || features.length < 10} onClick={() => verify("asha")}>
              Verify against Asha ({Math.min(features.length, 10)}/10)
            </Button>
            {!enrolled ? (
              <Button size="small" variant="tinted" tint="gray" disabled={!client || busy || features.length < 20} onClick={enrol}>
                <UserPlus className="size-3.5" aria-hidden /> Enrol me ({Math.min(features.length, 20)}/20)
              </Button>
            ) : (
              <Button size="small" variant="tinted" tint="green" disabled={!client || busy || features.length < 10} onClick={() => verify("me")}>
                Verify against me ({Math.min(features.length, 10)}/10)
              </Button>
            )}
          </div>
          {result && (
            <div className="squircle rounded-[var(--radius-card)] bg-fill-quaternary p-3.5">
              <p className={`text-headline ${result.r.matches_profile ? "text-sys-green" : "text-sys-red"}`}>
                {result.r.matches_profile ? `Looks like ${result.who} hands` : `Not ${result.who} hands`}
              </p>
              <p className="mt-1 text-caption-1 text-label-secondary">
                BiLSTM + LDA fusion over {result.r.window_gestures} gestures: score {result.r.fused_score.toFixed(2)} vs threshold {result.r.threshold_at_eer.toFixed(2)} ·
                bio_dev {result.r.behavioural_deviation > 0 ? "+" : ""}{result.r.behavioural_deviation.toFixed(2)} · model EER {(100 * result.r.valid_eer).toFixed(1)}%
              </p>
            </div>
          )}
          <p className="text-caption-1 text-label-tertiary">
            {client ? "Mouse drags are not finger gestures, so expect “not Asha”. Enrol your own and compare." :
              "Connect the API to verify windows against a profile; the features above are computed by the SDK in this page either way."}
          </p>
        </div>
      </div>
    </Panel>
  );
}
