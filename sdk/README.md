# PRAMAAN client SDKs

Two SDKs collect the signals the risk model reads, on the customer's own device, and a client calls the API:

| | [`web/`](web/README.md) `@pramaan/web-sdk` | [`android/`](android/README.md) `com.pramaan.sdk` |
|---|---|---|
| language | TypeScript, zero runtime dependencies | Kotlin, zero dependencies beyond the Android framework |
| touch dynamics | pointer events (touchscreens), motion sensors where the browser allows | every activity's touches, accelerometer + gyroscope at 100 Hz |
| typing rhythm | key-down / key-up on a password field (physical keyboards) | the SDK's PIN pad, or hardware keys |
| device | install ID, automation (WebDriver / headless) | install ID, root, emulator, remote-control apps, screen recording, SIM change, unknown caller |
| client | `PramaanClient` for Node / Bun / Deno / edge (`@pramaan/web-sdk/server`) | `PramaanClient` for Android and JVM backends |
| step-up UI | `showChallenge()`: OTP, passkey, call-back and cool-off screens, EN / HI | `PinPadView` for typing-rhythm PIN entry |

Both clients sign requests (`X-Signature: sha256=HMAC(secret, "<ts>.<body>")`), retry 429 / 502-504 / network errors
at least a second apart with the same `request_id`, and fall back to an SMS OTP when the service cannot be reached.
In production the app sends what the SDK collected to the bank's backend, which holds the API key and secret.

## Golden vectors

`spec/make_golden.py` runs the training pipeline's own code (`ml/models/biometrics/data.py` gesture features,
`ml/models/keystroke/data.py` timing layout, `backend/security.py` signing) on fixed raw inputs and writes
`spec/golden.json`. Both SDKs' tests replay the same raw touch frames, sensor samples and key events and must match to
1e-9, so a phone or browser sends exactly what the models were trained on.

```bash
python sdk/spec/make_golden.py                      # regenerate after changing the pipeline
cd sdk/web && npm install && npm test               # 31 tests
PRAMAAN_API=http://127.0.0.1:8000 npm run test:live # 7 end-to-end tests against a running API
cd sdk/android && gradle :pramaan:testDebugUnitTest # 13 tests (JVM), PRAMAAN_API enables the live test
```
