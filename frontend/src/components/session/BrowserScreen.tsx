import { AlertTriangle, Lock, RotateCw, ShieldCheck } from "lucide-react";
import type { Scenario } from "@/config/scenarios";

/** A mobile browser on the page the SMS linked to. Scam pages look urgent and official; real ones look ordinary. */
export function BrowserScreen({ s }: { s: Scenario }) {
  const page = s.page ?? { url: "example.in", title: "Page", body: "", cta: "Continue", tone: "legit" as const };
  const scam = page.tone === "scam";
  return (
    <div className="flex h-full flex-col bg-[#f2f2f7] pb-8 pt-[3.4rem] text-black">
      <div className="mx-3 mb-3 flex items-center gap-2 rounded-[0.75rem] bg-white px-3 py-2 shadow-[0_1px_2px_rgb(0_0_0/0.08)]">
        <Lock className="size-3.5 text-black/50" aria-hidden />
        <span className="flex-1 truncate text-center text-subheadline">{page.url}</span>
        <RotateCw className="size-3.5 text-black/50" aria-hidden />
      </div>
      <div className="mx-3 flex-1 overflow-hidden rounded-[1rem] bg-white p-5 shadow-[0_1px_2px_rgb(0_0_0/0.08)]">
        <div className={`mb-4 flex h-10 items-center gap-2 rounded-[0.6rem] px-3 text-footnote font-semibold text-white ${scam ? "bg-[#c0392b]" : "bg-[#1f7a4d]"}`}>
          {scam ? <AlertTriangle className="size-4" aria-hidden /> : <ShieldCheck className="size-4" aria-hidden />}
          {scam ? "Action required within 2 hours" : "Official site"}
        </div>
        <h2 className="text-title-2 text-black">{page.title}</h2>
        <p className="mt-2 text-subheadline text-black/70">{page.body}</p>
        <div className="mt-5 space-y-2">
          {[0.9, 0.75, 0.82].map((w, i) => (
            <div key={i} className="h-2.5 rounded-full bg-black/8" style={{ width: `${w * 100}%` }} />
          ))}
        </div>
        <span className={`mt-6 flex h-12 items-center justify-center rounded-[0.8rem] text-headline text-white ${scam ? "bg-[#d35400]" : "bg-[#0a84ff]"}`}>
          {page.cta}
        </span>
      </div>
    </div>
  );
}
