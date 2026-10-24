# @pramaan/web-sdk

Browser SDK for PRAMAAN risk-based authentication: it observes the page (touch gestures, typing rhythm on a password
field, time to submit, a stable install ID, automation flags) and builds the request `POST /v1/authenticate` scores.
A server entry (`@pramaan/web-sdk/server`) is the typed, signing client for your backend. No runtime dependencies.

```ts
import { Pramaan } from "@pramaan/web-sdk";

const pramaan = Pramaan.init({ consent: true });       // behavioural data only with the customer's consent
pramaan.startFlow();                                     // the payment / login screen opened
pramaan.watchTyping(document.querySelector("#password")!);

const request = await pramaan.collect({
  userId: session.userId,
  transaction: { amount: 2500, payee_id: "kirana-sharma", payee_is_merchant: true },
});
await fetch("/api/pay/authenticate", { method: "POST", body: JSON.stringify(request) });
```

```ts
// your backend
import { PramaanClient } from "@pramaan/web-sdk/server";

const pramaan = new PramaanClient({ baseUrl: process.env.PRAMAAN_URL!, apiKey: process.env.PRAMAAN_KEY,
                                    hmacSecret: process.env.PRAMAAN_SECRET, fallback: "challenge" });
const decision = await pramaan.authenticate({ ...request, user_id: session.userId });
// decision.decision: allow | challenge | block; decision.challenge_type: sms_otp | passkey | bank_callback | cool_off
await pramaan.verifyChallenge(decision.decision_id, passed);
```

A script-tag build is `dist/pramaan.min.js` (`window.Pramaan.Pramaan.init(...)`).

## Drop-in step-up screens

`showChallenge(container, decision, handlers)` renders the step-up the service chose, with its own message in
English or Hindi: a one-time-password field (with attempts), a passkey prompt, the bank call-back wait, or the
cool-off countdown with a scam warning. Your handlers do the checking; it resolves `{ passed, cancelled }`, which your
backend reports with `verifyChallenge`. Bottom sheet by default, or `{ inline: true }` inside a card; Escape,
"Cancel payment" or an `AbortSignal` cancels.

```ts
if (decision.decision === "challenge") {
  const { passed } = await showChallenge(document.body, decision, {
    lang: "hi",
    verifyOtp: (code) => api.checkOtp(code),
    passkey: () => api.approveWithPasskey(),      // WebAuthn against your server
    outOfBand: () => api.waitForCallBack(),       // your call-back team
  });
  await api.reportStepUp(decision.decision_id, passed);
}
```

## What it collects

| signal | how | sent as |
|---|---|---|
| touch gestures | `pointerdown/move/up` from fingers and pens (mouse only with `mouseAsTouch`, for demos); `devicemotion` accelerometer + gyroscope around each touch | `behaviour.gestures`: the last 10-20 gestures, 21 features each (`ml/models/biometrics/data.py`); never coordinates |
| typing rhythm | `keydown` / `keyup` times on a watched field; modifiers and auto-repeat ignored; a correction, paste or blur restarts the attempt | `behaviour.keystrokes`: 31 timings for an 11-key attempt (`ml/models/keystroke/data.py`); never the keys |
| session | `startFlow()` to `collect()`; pointer and key events in between | `time_to_submit_s`, `input_events` |
| device | an install ID in `localStorage`; WebDriver / headless browser | `device.device_id`, `device.is_emulator` |

Positions are normalised to the observed element (or the viewport) and path lengths rescaled to the 1080-px phone the
touch model was trained on. Gestures are encoded 100 ms after the finger lifts, once the hand-motion window is complete.
Soft keyboards on phones report no key codes, so typing rhythm on mobile web needs a physical keyboard; the Android SDK
has a PIN pad for that. Root, SIM, remote-access and call signals need the Android SDK.

## Client behaviour

* `timeoutMs` (3000) per attempt; `retries` (1) after a network error, timeout, 429 (honouring `Retry-After`) or
  502/503/504, at least a second apart (the signature covers the timestamp in seconds, and the gateway rejects a
  repeated signature), with the same `request_id`.
* `fallback`: `"challenge"` (default) answers an SMS OTP when the service is unreachable, `"allow"` fails open,
  `"throw"` raises `PramaanError`. Fallback answers carry `degraded: true`.
* Errors are `PramaanError` with `code` (timeout, network, rate_limited, unauthorized, invalid_request, not_found,
  server), `status` and `retryable`.

## Development

```bash
npm install
npm test          # golden vectors (vs the Python pipeline), keystrokes, client, DOM wiring
npm run test:live # with PRAMAAN_API (and PRAMAAN_SECURED_API + PRAMAAN_TEST_KEY/SECRET for a secured gateway)
npm run build     # dist/ (ESM + .d.ts) and dist/pramaan.min.js
```

The console (`frontend/`) imports this package from source (`@pramaan/web-sdk` → `sdk/web/src`); its Live capture
page is the SDK running unmodified.
