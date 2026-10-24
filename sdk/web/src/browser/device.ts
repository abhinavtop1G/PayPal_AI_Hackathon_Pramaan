import type { AuthDevice } from "../core/types";

const KEY = "pramaan.device_id";
let memoryId: string | null = null;

function randomId(): string {
  const c = globalThis.crypto;
  if (c?.randomUUID) return c.randomUUID();
  return Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join("");
}

/**
 * A stable per-browser install ID, kept in localStorage (in memory when storage is blocked). The service learns
 * which devices each customer uses and trusts; it is not a fingerprint and carries nothing about the person.
 */
export function deviceId(storageKey = KEY): string {
  try {
    const v = localStorage.getItem(storageKey);
    if (v) return v;
    const id = `web-${randomId()}`;
    localStorage.setItem(storageKey, id);
    return id;
  } catch {
    memoryId ??= `web-${randomId()}`;
    return memoryId;
  }
}

/**
 * Signs of an automated browser (WebDriver, headless Chrome, PhantomJS). Reported as `is_emulator`: like an emulated
 * phone, it is a client that is not a person's own device.
 */
export function automationSignals(): string[] {
  if (typeof navigator === "undefined") return [];
  const out: string[] = [];
  const nav = navigator as Navigator & { webdriver?: boolean };
  if (nav.webdriver) out.push("navigator.webdriver");
  const ua = nav.userAgent || "";
  if (/HeadlessChrome/i.test(ua)) out.push("headless-chrome");
  if (/PhantomJS|SlimerJS/i.test(ua)) out.push("phantom");
  const w = globalThis as unknown as Record<string, unknown>;
  if (w.callPhantom || w._phantom || w.__nightmare) out.push("automation-globals");
  if (typeof w.outerWidth === "number" && w.outerWidth === 0 && typeof w.outerHeight === "number" && w.outerHeight === 0) {
    out.push("zero-size-window");
  }
  return out;
}

/** What a browser can honestly say about its device. Root, SIM, remote-access and call signals need the mobile SDK. */
export function webDevice(storageKey?: string): AuthDevice {
  return {
    device_id: deviceId(storageKey),
    platform: "web",
    is_emulator: automationSignals().length > 0,
    is_rooted: false,
    remote_access_app: false,
    screen_share_active: false,
    sim_change_hours: null,
  };
}

export interface Environment {
  userAgent: string;
  language: string;
  timezone: string;
  viewport: { width: number; height: number; dpr: number };
  touchPoints: number;
  motionSensors: boolean;
  secureContext: boolean;
  automation: string[];
}

/** Diagnostics for the integrating developer (stays on the page; not part of the request). */
export function environment(): Environment {
  const w = globalThis as unknown as Window;
  return {
    userAgent: navigator.userAgent,
    language: navigator.language,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    viewport: { width: w.innerWidth, height: w.innerHeight, dpr: w.devicePixelRatio || 1 },
    touchPoints: navigator.maxTouchPoints || 0,
    motionSensors: typeof (w as unknown as { DeviceMotionEvent?: unknown }).DeviceMotionEvent !== "undefined",
    secureContext: w.isSecureContext,
    automation: automationSignals(),
  };
}
