"use client";

import type { GestureFeatures, KeystrokeAttempt, Pramaan } from "@pramaan/web-sdk";

/** Fan-out for the page's one SDK instance: its callbacks reach every lab on the page. */
export interface SdkHub {
  onGesture: Set<(f: GestureFeatures) => void>;
  onAttempt: Set<(a: KeystrokeAttempt) => void>;
  onReset: Set<(why: string) => void>;
}

export interface SdkBus extends SdkHub {
  sdk: Pramaan | null;
}

export function newHub(): SdkHub {
  return { onGesture: new Set(), onAttempt: new Set(), onReset: new Set() };
}

/** Session-scoped ids for the "enrol me" flows, so a visitor's profiles never touch the demo customer's. */
export const LAB_USER = `lab-${Math.random().toString(36).slice(2, 8)}`;
export const DEMO_USER = "demo-asha";
