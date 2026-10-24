"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Keyboard, RotateCcw, UserPlus } from "lucide-react";
import { manhattanDistance, manhattanProfile, type KeystrokeAttempt, type ManhattanProfile, type TypingVerifyResult } from "@pramaan/web-sdk";
import { useReport } from "@/api/console";
import { Button } from "@/components/common/Button";
import { SegmentedControl } from "@/components/common/SegmentedControl";
import { toast } from "@/components/common/Toaster";
import { Panel } from "@/components/layout/Panel";
import { useConsole } from "@/context/ConsoleContext";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { DistanceStrip } from "./DistanceStrip";
import { KeyRoll } from "./KeyRoll";
import { DEMO_USER, LAB_USER, type SdkBus } from "./sdkBus";

const LABELS = [".", "t", "i", "e", "5", "R", "o", "a", "n", "l", "⏎"];
const ENROL_N = 5;
type Mode = "asha" | "me";

interface Tried {
  timings: number[];
  vsAsha: number;
  vsMe: number | null;
  apiAsha?: TypingVerifyResult;
  apiMe?: TypingVerifyResult;
}

/** Leave-one-out distances of each enrolment attempt from a profile built on the others. */
function looDistances(attempts: number[][]): number[] {
  return attempts.map((a, i) => manhattanDistance(manhattanProfile(attempts.filter((_, j) => j !== i)), a).distance);
}

/**
 * Typing biometrics, live: the web SDK records key-down / key-up times on the field below (never the keys), and the
 * attempt is compared with the demo customer's typing profile, or with yours after five enrolment attempts. On the
 * page: the scaled-Manhattan distance (the SDK's on-device preview). With the API: the service's 1D-CNN + Manhattan
 * fusion decides.
 */
export function TypingLab({ bus }: { bus: SdkBus }) {
  const { client } = useConsole();
  const { data: report } = useReport();
  const coarse = useMediaQuery("(pointer: coarse) and (hover: none)");
  const input = useRef<HTMLInputElement>(null);
  const [value, setValue] = useState("");
  const [mode, setMode] = useState<Mode>("asha");
  const [enrol, setEnrol] = useState<number[][] | null>(null);
  const [mine, setMine] = useState<{ profile: ManhattanProfile; loo: number[]; enrolledApi: boolean } | null>(null);
  const [tries, setTries] = useState<Tried[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const password = report?.typing_demo.password ?? ".tie5Roanl";
  const asha = report?.typing_demo.profile;
  const state = useRef({ enrol, mine, asha });
  useEffect(() => {
    state.current = { enrol, mine, asha };
  }, [enrol, mine, asha]);

  useEffect(() => {
    const el = input.current;
    if (!el || !bus.sdk) return;
    return bus.sdk.watchTyping(el);
  }, [bus.sdk]);

  useEffect(() => {
    const onReset = (why: string) => why === "edit" && setNote("Correction: the attempt restarts (corrected attempts are not comparable).");
    const onAttempt = async (a: KeystrokeAttempt) => {
      const typed = input.current?.value ?? "";
      setValue("");
      if (input.current) input.current.value = "";
      const { enrol: en, mine: me, asha: prof } = state.current;
      if (typed !== password || a.keys !== 11) {
        setNote(`Type exactly ${password} then Enter (got "${typed}"). Only timings are used, but the same text keeps attempts comparable.`);
        return;
      }
      setNote(null);
      if (en) {
        const next = [...en, a.timings];
        if (next.length < ENROL_N) {
          setEnrol(next);
          return;
        }
        setEnrol(null);
        let enrolledApi = false;
        if (client) {
          try {
            enrolledApi = !!(await client.enrollTyping(LAB_USER, next)).enrolled;
          } catch (e) {
            toast(`Enrolment on the API failed: ${(e as Error).message}`, "alert");
          }
        }
        setMine({ profile: manhattanProfile(next), loo: looDistances(next), enrolledApi });
        setMode("me");
        toast(`Typing profile enrolled from ${ENROL_N} attempts${enrolledApi ? " (on the device and the API)" : " (on this page)"}`);
        return;
      }
      if (!prof) return;
      const t: Tried = {
        timings: a.timings,
        vsAsha: manhattanDistance({ mean: prof.mean, mad: prof.mad, n: prof.n }, a.timings).distance,
        vsMe: me ? manhattanDistance(me.profile, a.timings).distance : null,
      };
      setTries((xs) => [t, ...xs].slice(0, 12));
      if (client) {
        const [ra, rm] = await Promise.all([
          client.verifyTyping(DEMO_USER, a.timings).catch(() => undefined),
          me?.enrolledApi ? client.verifyTyping(LAB_USER, a.timings).catch(() => undefined) : Promise.resolve(undefined),
        ]);
        setTries((xs) => xs.map((x) => (x === t ? { ...x, apiAsha: ra, apiMe: rm } : x)));
      }
    };
    bus.onAttempt.add(onAttempt);
    bus.onReset.add(onReset);
    return () => {
      bus.onAttempt.delete(onAttempt);
      bus.onReset.delete(onReset);
    };
  }, [bus, client, password]);

  const last = tries[0];
  const groups = useMemo(() => {
    if (mode === "me" && mine) return [{ key: "you", label: "your enrolment", values: mine.loo, color: "var(--color-series-1)" }];
    const d = report?.typing_demo.distances;
    if (!d) return [];
    return [
      { key: "normal", label: "Asha, later days", values: d.normal, color: "var(--color-sys-green)" },
      { key: "coerced", label: "Asha, stressed", values: d.coerced, color: "var(--color-sys-yellow)" },
      { key: "remote", label: "other people", values: d.remote, color: "var(--color-series-2)" },
      { key: "bot", label: "scripted", values: d.bot, color: "var(--color-sys-red)" },
    ];
  }, [mode, mine, report]);
  const myDist = last ? (mode === "me" ? last.vsMe : last.vsAsha) : null;
  const api = last ? (mode === "me" ? last.apiMe : last.apiAsha) : undefined;
  const reference = mode === "me" && mine ? mine.profile.mean : asha?.mean;
  const closest = myDist == null ? null : nearest(groups, myDist);

  return (
    <Panel eyebrow="Behaviour · typing rhythm" title="Type the password" icon={Keyboard} tint="var(--color-fam-behaviour)"
      accessory={mine ? (
        <SegmentedControl<Mode> size="small" label="Compare with" value={mode} onChange={setMode}
          options={[{ value: "asha", label: "Asha's profile" }, { value: "me", label: "My profile" }]} />
      ) : undefined}>
      <div className="grid gap-5 lg:grid-cols-2">
        <div className="min-w-0 space-y-3">
          <p className="text-footnote text-label-secondary">
            Type <span className="rounded bg-fill-tertiary px-1.5 py-0.5 font-mono text-label">{password}</span> and press Enter: the
            CMU benchmark password the keystroke model was trained on. The demo customer&apos;s profile is a real CMU subject.
          </p>
          <div className="flex gap-1" aria-hidden>
            {password.split("").map((c, i) => (
              <span key={i} className={`flex h-9 flex-1 items-center justify-center rounded-[0.5rem] font-mono text-callout ${
                i < value.length ? (value[i] === c ? "bg-sys-blue/20 text-label" : "bg-sys-red/20 text-sys-red") : "bg-fill-quaternary text-label-tertiary"}`}>{c}</span>
            ))}
          </div>
          <input ref={input} value={value} onChange={(e) => setValue(e.target.value)} spellCheck={false} autoComplete="off" autoCapitalize="off"
            placeholder={enrol ? `Enrolment attempt ${enrol.length + 1} of ${ENROL_N}` : "type here, then Enter"} aria-label="Password field watched by the SDK"
            className="h-12 w-full rounded-[0.8rem] bg-fill-tertiary px-4 font-mono text-headline tracking-[0.15em] text-label outline-none ring-sys-blue placeholder:tracking-normal placeholder:text-label-tertiary focus:ring-2" />
          {note && <p className="text-caption-1 text-sys-orange">{note}</p>}
          {coarse && (
            <p className="text-caption-1 text-label-tertiary">
              On a phone, the on-screen keyboard does not tell web pages when keys go down and up, so no attempt is recorded
              here: use a laptop keyboard. (The Android SDK has its own PIN pad for this.)
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            {!enrol ? (
              <Button size="small" variant="tinted" onClick={() => { setEnrol([]); input.current?.focus(); }}>
                <UserPlus className="size-3.5" aria-hidden /> {mine ? "Re-enrol my typing" : `Enrol my typing (${ENROL_N} attempts)`}
              </Button>
            ) : (
              <span className="flex items-center gap-1.5 text-caption-1 text-label-secondary">
                Enrolling
                {Array.from({ length: ENROL_N }, (_, i) => <span key={i} className={`size-2 rounded-full ${i < enrol.length ? "bg-sys-blue" : "bg-fill-secondary"}`} />)}
                <button className="ml-1 text-sys-blue" onClick={() => setEnrol(null)}>cancel</button>
              </span>
            )}
            {tries.length > 0 && (
              <Button size="small" tint="gray" variant="tinted" onClick={() => setTries([])}><RotateCcw className="size-3.5" aria-hidden /> Clear</Button>
            )}
          </div>
          {last ? (
            <div>
              <p className="mb-1 text-caption-1 text-label-tertiary">Your last attempt (bars) against {mode === "me" ? "your" : "Asha's"} average rhythm (outlines)</p>
              <KeyRoll attempt={last.timings} reference={reference} labels={LABELS} />
            </div>
          ) : (
            <p className="rounded-[0.8rem] bg-fill-quaternary p-3 text-caption-1 text-label-tertiary">
              Nothing about the keys is recorded: an attempt is 31 numbers (hold, down-down and up-down times), the layout
              in ml/models/keystroke/data.py.
            </p>
          )}
        </div>

        <div className="min-w-0 space-y-3">
          <p className="text-footnote text-label-secondary">Distance from {mode === "me" ? "your" : "Asha's"} profile (scaled Manhattan, lower = closer). Dots: reference attempts.</p>
          {groups.length > 0 && <DistanceStrip groups={groups} mine={myDist} />}
          {last && (
            <div className="squircle space-y-1.5 rounded-[var(--radius-card)] bg-fill-quaternary p-3.5">
              {api ? (
                <>
                  <p className={`text-headline ${api.matches_profile ? "text-sys-green" : "text-sys-red"}`}>
                    {api.matches_profile ? `Matches ${mode === "me" ? "your" : "Asha's"} typing` : `Not ${mode === "me" ? "your" : "Asha's"} typing`}
                  </p>
                  <p className="text-caption-1 text-label-secondary">
                    Service verdict (1D-CNN + scaled Manhattan fusion): score {api.score.toFixed(2)} vs threshold {api.threshold.toFixed(2)} ·
                    typing_dev {api.typing_deviation > 0 ? "+" : ""}{api.typing_deviation.toFixed(2)} (the model&apos;s typing signal)
                  </p>
                </>
              ) : (
                <>
                  <p className="text-headline">{closest ? `Closest to: ${closest}` : "—"}</p>
                  <p className="text-caption-1 text-label-tertiary">
                    On-device preview only. {client ? "Waiting for the service…" : "Connect the API (NEXT_PUBLIC_PRAMAAN_API) for the model's verdict."}
                  </p>
                </>
              )}
            </div>
          )}
          {tries.length > 1 && (
            <p className="text-caption-1 text-label-tertiary">
              Your attempts vs {mode === "me" ? "you" : "Asha"}: {tries.slice(0, 8).map((t) => ((mode === "me" ? t.vsMe : t.vsAsha) ?? 0).toFixed(0)).join(" · ")}
            </p>
          )}
        </div>
      </div>
    </Panel>
  );
}

function nearest(groups: { label: string; values: number[] }[], v: number): string | null {
  let best: string | null = null, bd = Infinity;
  for (const g of groups) {
    if (!g.values.length) continue;
    const s = [...g.values].sort((a, b) => a - b);
    const med = s[Math.floor(s.length / 2)];
    const d = Math.abs(Math.log(v) - Math.log(med));
    if (d < bd) {
      bd = d;
      best = g.label;
    }
  }
  return best;
}
