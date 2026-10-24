"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "motion/react";
import {
  Activity, BookOpen, Fingerprint, FlaskConical, Gauge, Home, Scale, ScrollText, ShieldHalf, type LucideIcon,
} from "lucide-react";
import { Toaster } from "@/components/common/Toaster";
import { spring } from "@/config/motion";
import { AUTH_API } from "@/api/auth";
import { ConsoleProvider, useConsole } from "@/context/ConsoleContext";
import { Wordmark } from "./Brand";

const NAV: { href: string; label: string; icon: LucideIcon; hint: string }[] = [
  { href: "/console", label: "Overview", icon: Gauge, hint: "A day of traffic, decided" },
  { href: "/console/lab", label: "Decision lab", icon: FlaskConical, hint: "One request, end to end" },
  { href: "/console/policy", label: "Policy tuner", icon: Scale, hint: "Friction against fraud" },
  { href: "/console/capture", label: "Live capture", icon: Fingerprint, hint: "The web SDK on this page" },
  { href: "/console/audit", label: "Audit log", icon: ScrollText, hint: "Every decision and why" },
  { href: "/console/model", label: "Model", icon: Activity, hint: "Evaluation and baselines" },
  { href: "/console/developers", label: "Developers", icon: BookOpen, hint: "SDKs and API" },
];

/** The console: sidebar navigation on wide screens, a scrolling tab bar on narrow ones, and the API status. */
export function ConsoleFrame({ children }: { children: React.ReactNode }) {
  return (
    <ConsoleProvider>
      <div className="space-backdrop min-h-dvh lg:grid lg:grid-cols-[15.5rem_minmax(0,1fr)]">
        <Sidebar />
        <MobileBar />
        <Toaster />
        <main className="min-w-0 px-4 pb-16 pt-4 sm:px-6 lg:px-8 lg:pt-7">{children}</main>
      </div>
    </ConsoleProvider>
  );
}

function useActive() {
  const path = usePathname() ?? "";
  return (href: string) => (href === "/console" ? path === href : path.startsWith(href));
}

function Sidebar() {
  const active = useActive();
  return (
    <aside className="material-thick sticky top-0 hidden h-dvh flex-col border-r border-separator/50 px-3 py-5 lg:flex" aria-label="Console">
      <div className="px-2"><Wordmark href="/" sub="Risk-based authentication" /></div>
      <nav className="mt-7 space-y-0.5">
        <p className="mb-1.5 px-3 text-eyebrow text-label-tertiary">Console</p>
        {NAV.map((n) => {
          const on = active(n.href);
          return (
            <Link key={n.href} href={n.href} aria-current={on ? "page" : undefined}
              className={`group relative flex items-center gap-3 rounded-[0.8rem] px-3 py-2 transition-colors ${on ? "text-label" : "text-label-secondary hover:bg-fill-quaternary hover:text-label"}`}>
              {on && <motion.span layoutId="nav-active" transition={spring.snappy}
                className="absolute inset-0 rounded-[0.8rem] bg-fill-secondary shadow-[inset_0_0.5px_0_rgb(255_255_255/0.1)]" />}
              <n.icon className={`relative size-[1.05rem] ${on ? "text-sys-blue" : ""}`} aria-hidden />
              <span className="relative min-w-0">
                <span className="block text-subheadline font-medium">{n.label}</span>
                <span className="block truncate text-caption-2 text-label-tertiary">{n.hint}</span>
              </span>
            </Link>
          );
        })}
      </nav>
      <div className="mt-6 space-y-0.5">
        <p className="mb-1.5 px-3 text-eyebrow text-label-tertiary">More</p>
        <Link href="/scam" className="flex items-center gap-3 rounded-[0.8rem] px-3 py-2 text-subheadline text-label-secondary hover:bg-fill-quaternary hover:text-label">
          <ShieldHalf className="size-[1.05rem]" aria-hidden /> Scam-session layer
        </Link>
        <Link href="/" className="flex items-center gap-3 rounded-[0.8rem] px-3 py-2 text-subheadline text-label-secondary hover:bg-fill-quaternary hover:text-label">
          <Home className="size-[1.05rem]" aria-hidden /> Home
        </Link>
      </div>
      <div className="mt-auto"><ApiStatus /></div>
    </aside>
  );
}

function MobileBar() {
  const active = useActive();
  return (
    <header className="material-thick sticky top-0 z-30 border-b border-separator/50 lg:hidden">
      <div className="flex items-center justify-between gap-3 px-4 py-2.5">
        <Wordmark href="/" />
        <ApiStatus compact />
      </div>
      <nav className="flex gap-1 overflow-x-auto px-3 pb-2" aria-label="Console">
        {NAV.map((n) => (
          <Link key={n.href} href={n.href} className={`flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-footnote ${active(n.href) ? "bg-fill-secondary text-label" : "text-label-secondary"}`}>
            <n.icon className="size-3.5" aria-hidden /> {n.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}

function ApiStatus({ compact }: { compact?: boolean }) {
  const { source, health, checking } = useConsole();
  const live = source === "live";
  const auth = health?.auth as { model_version?: string; state_backend?: string } | undefined;
  if (compact) {
    return (
      <span className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-caption-1 ${live ? "bg-sys-green/12 text-sys-green" : "bg-fill-tertiary text-label-secondary"}`}>
        <span className={`size-1.5 rounded-full ${live ? "bg-sys-green" : "bg-label-tertiary"}`} aria-hidden />
        {checking ? "Connecting" : live ? "Live API" : "Recorded"}
      </span>
    );
  }
  return (
    <div className="squircle rounded-[var(--radius-card)] bg-fill-quaternary p-3">
      <p className="flex items-center gap-2 text-footnote font-semibold">
        <span className={`size-2 rounded-full ${live ? "pulse-ring bg-sys-green text-sys-green" : "bg-label-tertiary"}`} aria-hidden />
        {checking ? "Connecting to API…" : live ? "Live API" : "Recorded replay"}
      </p>
      <p className="mt-1 text-caption-1 text-label-tertiary">
        {live
          ? `${health?.loaded.join(" · ")} · ${health?.security.mode}${auth?.model_version ? ` · ${auth.model_version}` : ""}`
          : checking ? `Looking for the service at ${AUTH_API}`
            : AUTH_API ? `No answer from ${AUTH_API}: playing recordings of the API's own output.`
              : "Plays recordings of the API's own output. Set NEXT_PUBLIC_PRAMAAN_API to decide live."}
      </p>
    </div>
  );
}
