import type { AuthResponse, ChallengeType } from "../core/types";

/**
 * A drop-in step-up screen for the challenge the service chose. It shows the service's own message (English or
 * Hindi) and the matching interaction; the bank's handlers do the actual verification. Resolves with the outcome,
 * which the bank's backend then reports with PramaanClient.verifyChallenge.
 *
 *   const { passed } = await showChallenge(document.body, decision, {
 *     verifyOtp: (code) => api.verifyOtp(code),
 *     passkey: () => api.approveWithPasskey(),             // WebAuthn against the bank's server
 *     outOfBand: () => api.waitForCallBackResult(),         // the bank's call-back team
 *   });
 */
export interface ChallengeHandlers {
  lang?: "en" | "hi";
  /** SMS OTP: check the code the customer typed; resolve true when it is right */
  verifyOtp?: (code: string) => Promise<boolean>;
  /** passkey: run WebAuthn (navigator.credentials.get) with your server's challenge; resolve true on success */
  passkey?: () => Promise<boolean>;
  /** bank call-back: resolves when the bank's team has confirmed (true) or refused (false) the payment */
  outOfBand?: () => Promise<boolean>;
  /** cool-off length in seconds (the policy's is 30 minutes) */
  coolOffSeconds?: number;
  /** OTP attempts before the step-up fails */
  otpAttempts?: number;
}

export interface ChallengeResult {
  passed: boolean;
  challenge: ChallengeType;
  /** the customer cancelled (as opposed to failing the check) */
  cancelled: boolean;
}

const COPY = {
  en: {
    sms_otp: "Enter the one-time password", passkey: "Approve on your registered phone", bank_callback: "Your bank will call you",
    cool_off: "Payment paused", verify: "Verify", approve: "Approve", cancel: "Cancel payment", resume: "Continue payment",
    wrong: "That code is not right. Attempts left:", waiting: "Waiting for your bank…", noPasskey: "Passkeys are not available in this browser.",
    warn: "Is someone on a call or screen share telling you to pay? Banks, police and courts never ask for payments like this. Hang up and report it at 1930.",
    left: "You can continue in",
  },
  hi: {
    sms_otp: "वन-टाइम पासवर्ड दर्ज करें", passkey: "अपने पंजीकृत फ़ोन पर स्वीकृत करें", bank_callback: "आपका बैंक आपको कॉल करेगा",
    cool_off: "भुगतान रोका गया", verify: "सत्यापित करें", approve: "स्वीकृत करें", cancel: "भुगतान रद्द करें", resume: "भुगतान जारी रखें",
    wrong: "कोड सही नहीं है। बचे प्रयास:", waiting: "आपके बैंक की प्रतीक्षा…", noPasskey: "इस ब्राउज़र में पासकी उपलब्ध नहीं है।",
    warn: "क्या कॉल या स्क्रीन शेयर पर कोई आपसे भुगतान करवा रहा है? बैंक, पुलिस और अदालतें कभी ऐसे भुगतान नहीं माँगतीं। कॉल काटें और 1930 पर शिकायत करें।",
    left: "आप जारी रख सकते हैं",
  },
};

const CSS = `
.pramaan-ch{position:fixed;inset:0;z-index:2147483000;display:flex;align-items:flex-end;justify-content:center;background:rgb(0 0 0/.45);font:15px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif}
.pramaan-ch[data-inline]{position:relative;inset:auto;z-index:auto;background:none;align-items:stretch}
.pramaan-ch-card{width:min(26rem,100%);margin:0;padding:22px 20px 18px;border-radius:22px 22px 0 0;background:#fff;color:#111;box-shadow:0 -10px 40px rgb(0 0 0/.25)}
.pramaan-ch[data-inline] .pramaan-ch-card{border-radius:20px;box-shadow:none;width:100%}
.pramaan-ch h2{margin:0 0 6px;font-size:19px;font-weight:650}
.pramaan-ch p{margin:0 0 14px;color:#555}
.pramaan-ch-otp{display:flex;gap:8px;margin:4px 0 14px}
.pramaan-ch-otp input{width:100%;height:48px;font-size:22px;letter-spacing:.4em;text-align:center;border-radius:12px;border:1px solid #ccc;background:#f6f6f7;color:inherit}
.pramaan-ch button{width:100%;height:46px;margin-top:8px;border:0;border-radius:12px;font:inherit;font-weight:600;cursor:pointer}
.pramaan-ch .pramaan-ch-primary{background:#0a84ff;color:#fff}
.pramaan-ch .pramaan-ch-primary:disabled{opacity:.45;cursor:default}
.pramaan-ch .pramaan-ch-secondary{background:transparent;color:#d70015}
.pramaan-ch-warn{padding:12px;border-radius:12px;background:#fff1f0;color:#a40e0e;margin:0 0 12px}
.pramaan-ch-timer{font:600 30px/1 ui-monospace,Menlo,monospace;margin:6px 0 12px}
.pramaan-ch-error{color:#d70015;min-height:1.2em;margin:0 0 4px;font-size:13px}
@media (prefers-color-scheme:dark){.pramaan-ch-card{background:#1c1c1e;color:#f2f2f7}.pramaan-ch p{color:#aeaeb2}
.pramaan-ch-otp input{background:#2c2c2e;border-color:#3a3a3c}.pramaan-ch-warn{background:#3a1512;color:#ffb4ab}.pramaan-ch .pramaan-ch-secondary{color:#ff6961}}
`;

let styled = false;
function ensureStyles(doc: Document) {
  if (styled && doc.getElementById("pramaan-ch-css")) return;
  const s = doc.createElement("style");
  s.id = "pramaan-ch-css";
  s.textContent = CSS;
  doc.head.appendChild(s);
  styled = true;
}

/** createElement with properties (className, type, disabled, inputMode...) and text. */
function el<K extends keyof HTMLElementTagNameMap>(tag: K, props: Record<string, string | number | boolean> = {}, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  Object.assign(e, props);
  if (text !== undefined) e.textContent = text;
  return e;
}

/**
 * Show the step-up for a challenge decision. `inline: true` renders inside `container` (e.g. a payment card); the
 * default is a bottom sheet over the page. Escape, "Cancel payment" or aborting `signal` fails it as cancelled.
 */
export function showChallenge(container: HTMLElement, decision: AuthResponse, handlers: ChallengeHandlers = {},
  opts: { inline?: boolean; signal?: AbortSignal } = {}): Promise<ChallengeResult> {
  const type: ChallengeType = decision.challenge_type ?? "sms_otp";
  const lang = handlers.lang ?? "en";
  const t = COPY[lang];
  ensureStyles(container.ownerDocument);

  return new Promise<ChallengeResult>((resolve) => {
    const root = el("div", { className: "pramaan-ch" });
    if (opts.inline) root.dataset.inline = "";
    const card = el("div", { className: "pramaan-ch-card" });
    card.setAttribute("role", "dialog");
    card.setAttribute("aria-modal", opts.inline ? "false" : "true");
    card.setAttribute("aria-label", t[type]);
    card.lang = lang;
    card.append(el("h2", {}, t[type]), el("p", {}, lang === "hi" ? decision.message_hi : decision.message_en));
    const error = el("p", { className: "pramaan-ch-error" });
    error.setAttribute("aria-live", "polite");
    let timer: ReturnType<typeof setInterval> | null = null;

    let settled = false;
    const done = (passed: boolean, cancelled = false) => {
      if (settled) return;
      settled = true;
      if (timer) clearInterval(timer);
      root.remove();
      container.ownerDocument.removeEventListener("keydown", onKey);
      resolve({ passed, challenge: type, cancelled });
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && done(false, true);
    if (opts.signal?.aborted) return done(false, true);
    opts.signal?.addEventListener("abort", () => done(false, true), { once: true });
    const cancel = el("button", { className: "pramaan-ch-secondary", type: "button" }, t.cancel);
    cancel.addEventListener("click", () => done(false, true));

    if (type === "sms_otp") {
      let left = handlers.otpAttempts ?? 3;
      const box = el("div", { className: "pramaan-ch-otp" });
      const input = el("input", { inputMode: "numeric", autocomplete: "one-time-code", maxLength: 6, name: "otp" });
      input.setAttribute("aria-label", t.sms_otp);
      box.append(input);
      const go = el("button", { className: "pramaan-ch-primary", type: "button", disabled: true }, t.verify);
      input.addEventListener("input", () => {
        input.value = input.value.replace(/\D/g, "").slice(0, 6);
        go.disabled = input.value.length < 4;
      });
      const submit = async () => {
        if (go.disabled) return;
        go.disabled = true;
        const ok = handlers.verifyOtp ? await handlers.verifyOtp(input.value).catch(() => false) : false;
        if (ok) return done(true);
        left--;
        if (left <= 0) return done(false);
        error.textContent = `${t.wrong} ${left}`;
        input.value = "";
        input.focus();
      };
      go.addEventListener("click", submit);
      input.addEventListener("keydown", (e) => e.key === "Enter" && submit());
      card.append(box, error, go, cancel);
      queueMicrotask(() => input.focus());
    } else if (type === "passkey") {
      const go = el("button", { className: "pramaan-ch-primary", type: "button" }, t.approve);
      go.addEventListener("click", async () => {
        if (!handlers.passkey) {
          error.textContent = t.noPasskey;
          return;
        }
        go.disabled = true;
        const ok = await handlers.passkey().catch(() => false);
        done(ok);
      });
      card.append(error, go, cancel);
      queueMicrotask(() => go.focus());
    } else if (type === "bank_callback") {
      card.append(el("p", {}, t.waiting), cancel);
      handlers.outOfBand?.().then((ok) => root.isConnected && done(ok), () => root.isConnected && done(false));
    } else {
      let secs = Math.max(0, Math.round(handlers.coolOffSeconds ?? 1800));
      const clock = el("div", { className: "pramaan-ch-timer" });
      clock.setAttribute("aria-live", "off");
      const go = el("button", { className: "pramaan-ch-primary", type: "button", disabled: secs > 0 }, t.resume);
      const show = () => {
        clock.textContent = `${t.left} ${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`;
      };
      show();
      timer = setInterval(() => {
        secs = Math.max(0, secs - 1);
        show();
        if (!secs && timer) {
          clearInterval(timer);
          timer = null;
          go.disabled = false;
        }
      }, 1000);
      go.addEventListener("click", () => done(true));
      card.append(el("div", { className: "pramaan-ch-warn" }, t.warn), clock, go, cancel);
    }

    root.append(card);
    container.append(root);
    container.ownerDocument.addEventListener("keydown", onKey);
  });
}
